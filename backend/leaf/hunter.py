"""Orchestrateur Leaf Hunter côté bot : un passage = lecture des sources -> pipeline pur -> Postgres -> ntfy.

Appelé depuis la boucle de `main.py` (job planifié + commandes `LEAF_*`). Toutes les erreurs sont capturées : un passage
Leaf ne doit JAMAIS perturber le bot guitare. Le logger est celui du bot (`bot.{uid8}.leaf`), seul visible dans l'app."""
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.leaf import config as leaf_config
from backend.leaf import notify as leaf_notify
from backend.leaf import pipeline, scoring
from backend.leaf.sources import BlockedError, autohebdo, fetch_html, kijiji_autos
from backend.leaf.sources.detail import DetailFetcher

LOOP_TICK_S = 60                # la boucle de fond relit la config chaque minute (fréquence modifiable à chaud)
CLEANUP_EVERY_S = 6 * 3600
STALE_DAYS = 14                 # une annonce non revue depuis 14 jours (sources saines) est marquée vendue
ALERT_AFTER_FAILURES = 3        # alerte santé : au 3e échec consécutif d'une source (une fois par série)
MAX_INDIVIDUAL_NOTIFICATIONS = 5


def collect_sources(scan: Dict[str, Any], fetch: Callable[[str], str] = fetch_html
                    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(annonces brutes, passages par source). Résultat d'une source : ok | no_cards | blocked | error."""
    raws: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    if "kijiji" in scan["sources"]:
        t0, found, outcome, detail = time.time(), [], "ok", None
        for page in range(1, scan["pages"] + 1):
            try:
                got = kijiji_autos.parse_search_page(fetch(kijiji_autos.build_search_url(page, scan["min_price"], scan["max_price"])))
            except BlockedError as e:
                outcome, detail = "blocked", str(e)
                break
            except Exception as e:
                outcome, detail = "error", f"page {page} : {e}"
                break
            found += got
            if not got:
                break
        if outcome == "ok" and not found:
            outcome = "no_cards"
        raws += found
        runs.append({"source": "kijiji", "outcome": outcome, "detail": detail, "cards_seen": len(found),
                     "duration_ms": int((time.time() - t0) * 1000)})
    if "autohebdo" in scan["sources"]:
        t0, found, outcome, detail = time.time(), [], "ok", None
        for year in scan["years"]:
            try:
                found += autohebdo.parse_results_page(fetch(autohebdo.build_search_url(year)), year)
            except BlockedError as e:
                outcome, detail = "blocked", str(e)
                break
            except Exception as e:
                outcome, detail = "error", f"{year} : {e}"
                break
        if outcome == "ok" and not found:
            outcome = "no_cards"
        raws += found
        runs.append({"source": "autohebdo", "outcome": outcome, "detail": detail, "cards_seen": len(found),
                     "duration_ms": int((time.time() - t0) * 1000)})
    return raws, runs


_LOCKS: Dict[str, threading.Lock] = {}          # un verrou PAR UTILISATEUR, partagé entre boucle de fond et commandes
_LOCKS_GUARD = threading.Lock()
_BACKGROUND: Dict[str, threading.Thread] = {}   # une seule boucle de fond par utilisateur (le watchdog relance main_loop)


def _lock_for(user_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(user_id, threading.Lock())


class LeafHunter:
    def __init__(self, repo, user_id: str, logger: Optional[logging.Logger] = None,
                 collector: Optional[Callable[[Dict[str, Any]], Tuple[list, list]]] = None,
                 detail_fetcher_factory: Optional[Callable[[], Any]] = None,
                 notifier: Callable[..., bool] = leaf_notify.send):
        self.repo, self.user_id = repo, user_id
        self.log = logger or logging.getLogger(__name__)
        self._collector = collector or collect_sources
        self._detail_factory = detail_fetcher_factory or DetailFetcher
        self._notify = notifier
        self._lock = _lock_for(user_id)    # anti-chevauchement (boucle de fond + commande manuelle, même verrou)

    # ------------------------------------------------------------------ configuration

    def config(self) -> Dict[str, Any]:
        return leaf_config.normalize_config(self.repo.get_leaf_config(self.user_id))

    def is_enabled(self) -> bool:
        return leaf_config.server_enabled() and self.config()["enabled"]

    # ------------------------------------------------------------------ passage

    def run_scan(self, force: bool = False, strict: bool = False) -> Optional[Dict[str, Any]]:
        """Un passage complet. None si désactivé / déjà en cours ; sinon un bilan. `force` (commande manuelle)
        ignore seulement l'interrupteur par utilisateur, jamais celui du serveur. `strict` (commande) : une erreur
        ou un passage déjà en cours LÈVE au lieu de renvoyer None, pour que la commande soit marquée échouée."""
        try:
            if not leaf_config.server_enabled():
                return None
            cfg = self.config()
            if not cfg["enabled"] and not force:
                return None
            if not self._lock.acquire(blocking=False):
                self.log.info("[Leaf] Passage déjà en cours, ignoré.")
                if strict:
                    raise RuntimeError("Un passage Leaf est déjà en cours.")
                return None
            try:
                return self._scan(cfg)
            finally:
                self._lock.release()
        except Exception as e:
            self.log.error(f"[Leaf] Passage interrompu : {e}", exc_info=True)
            if strict:
                raise
            return None

    def _scan(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        scan, notify_cfg = cfg["scan"], cfg["notify"]
        self.log.info(f"[Leaf] Passage : sources {', '.join(scan['sources'])}, budget {scan['min_price']}-{scan['max_price']} $.")
        raws, runs = self._collector(scan)
        for r in runs:
            self.repo.record_run(self.user_id, r["source"], r["outcome"], r.get("detail"), r.get("cards_seen"),
                                 None, r.get("duration_ms"))
            if r["outcome"] in ("blocked", "error"):
                self.log.warning(f"[Leaf] {r['source']} : {r['outcome']} ({r.get('detail')})")
            self._health_alert(r["source"], r["outcome"])

        criteria = {k: scan[k] for k in ("years", "min_price", "max_price", "max_km")}
        fetcher = self._detail_factory() if scan["read_details"] else None
        result = pipeline.evaluate_listings(raws, criteria, detail_fetcher=fetcher, home=scan["home"])

        # `price_fit` seulement quand assez d'annonces connues (sinon None : « marché insuffisant »).
        comparables = self.repo.comparables()
        events: List[Tuple[str, Dict[str, Any], Optional[float]]] = []
        for listing in result["kept"]:
            fit = scoring.price_fit(listing, comparables)
            if fit:
                listing["price_fit"] = fit
            outcome = self.repo.upsert_listing(listing)
            self.repo.record_match(self.user_id, listing["id"])
            if outcome["action"] in ("new", "price_drop"):
                events.append((outcome["action"], listing, outcome["previous_price"]))
        # Annonce déjà stockée mais qui ne passe plus les filtres/règles : retirée de la vue active (données périmées).
        withdrawn = self.repo.mark_rejected([l["id"] for l in result["rejected"] + result["ignored"] if l.get("id")])
        if withdrawn:
            self.log.info(f"[Leaf] {withdrawn} annonce(s) déjà stockée(s) ne passent plus les filtres : retirée(s) de la vue.")
        stats = {"read": len(raws), "kept": len(result["kept"]), "rejected": len(result["rejected"]),
                 "ignored": len(result["ignored"]), "new": sum(1 for e in events if e[0] == "new"),
                 "price_drops": sum(1 for e in events if e[0] == "price_drop")}
        self.log.info(f"[Leaf] {stats['read']} annonces lues : {stats['kept']} retenues ({stats['new']} nouvelles, "
                      f"{stats['price_drops']} baisses de prix), {stats['rejected']} rejetées par les règles, "
                      f"{stats['ignored']} hors périmètre.")
        if notify_cfg["enabled"]:
            self._notify_events(events, notify_cfg)
        return stats

    # ------------------------------------------------------------------ notifications

    @staticmethod
    def _describe(listing: Dict[str, Any]) -> str:
        km = f"{listing['km']:,} km".replace(",", " ") if listing.get("km") is not None else "km ?"
        soh = f"SOH {listing['soh_announced']:.0f} %" if listing.get("soh_announced") is not None else "SOH ?"
        return f"{listing.get('year') or '?'} Leaf {listing.get('trim') or '?'} — {listing['price']:.0f} $ — {km} — {soh}"

    def _notify_events(self, events, notify_cfg) -> None:
        wanted = [e for e in events if (e[0] == "new" and notify_cfg["new"]) or (e[0] == "price_drop" and notify_cfg["price_drop"])]
        if not wanted:
            return
        if len(wanted) > MAX_INDIVIDUAL_NOTIFICATIONS:    # premier passage : un seul résumé plutôt qu'une rafale
            lines = [self._describe(l) for _, l, _ in wanted[:10]]
            self._notify(f"Leaf : {len(wanted)} annonces", "\n".join(lines), logger=self.log)
            return
        for action, listing, previous in wanted:
            if action == "new":
                self._notify("Leaf : nouvelle annonce", self._describe(listing), click_url=listing.get("url"),
                             tags=["car"], logger=self.log)
            else:
                self._notify(f"Leaf : baisse de prix ({previous:.0f} → {listing['price']:.0f} $)",
                             self._describe(listing), priority="high", click_url=listing.get("url"),
                             tags=["chart_with_downwards_trend"], logger=self.log)

    def _health_alert(self, source: str, outcome: str) -> None:
        """Alerte unique au 3e échec consécutif d'une source (bloquée, en erreur ou sans carte)."""
        if outcome == "ok":
            return
        recent = self.repo.recent_outcomes(self.user_id, source, ALERT_AFTER_FAILURES + 1)
        failing = 0
        for o in recent:
            if o == "ok":
                break
            failing += 1
        if failing == ALERT_AFTER_FAILURES:
            self._notify(f"Leaf : source {source} en panne", f"{ALERT_AFTER_FAILURES} passages de suite sans résultat "
                         f"({outcome}). Vérifier le site ou le parseur.", priority="high", tags=["warning"], logger=self.log)

    # ------------------------------------------------------------------ commandes

    def cleanup(self) -> int:
        """Marque « vendues » les annonces non revues depuis STALE_DAYS — SEULEMENT si le dernier passage de chaque
        source activée a répondu `ok` (une source bloquée ou en panne ne prouve rien sur les annonces)."""
        if not leaf_config.server_enabled():
            return 0
        for source in self.config()["scan"]["sources"]:
            last = self.repo.recent_outcomes(self.user_id, source, 1)
            if not last or last[0] != "ok":
                self.log.info(f"[Leaf] Nettoyage reporté : la source {source} n'a pas répondu normalement au dernier passage.")
                return 0
        n = self.repo.mark_stale_sold(STALE_DAYS)
        self.log.info(f"[Leaf] Nettoyage : {n} annonce(s) non revues depuis {STALE_DAYS} jours marquée(s) vendues.")
        return n

    # ------------------------------------------------------------------ boucle de fond

    def run_background(self, stop_event: Optional[threading.Event] = None) -> None:
        """Boucle d'un fil dédié : chaque minute, relit la config (fréquence modifiable à chaud) et lance un passage
        quand l'échéance est atteinte ; nettoyage toutes les 6 h. Un passage long ne bloque donc ni le watchdog ni
        les tâches planifiées du bot."""
        stop = stop_event or threading.Event()
        last_scan = last_cleanup = 0.0
        stop.wait(30)                     # laisse le bot finir de démarrer
        while not stop.is_set():
            try:
                if self.is_enabled():
                    now = time.time()
                    if now - last_scan >= self.config()["scan"]["frequency"] * 60:
                        last_scan = now
                        self.run_scan()
                    if now - last_cleanup >= CLEANUP_EVERY_S:
                        last_cleanup = now
                        self.cleanup()
            except Exception as e:
                self.log.error(f"[Leaf] Erreur de la boucle de fond : {e}", exc_info=True)
            stop.wait(LOOP_TICK_S)

    def ensure_background(self, stop_event: Optional[threading.Event] = None) -> bool:
        """Démarre la boucle de fond de cet utilisateur si elle ne tourne pas déjà (idempotent : `main_loop` est relancé
        par le watchdog). True si un nouveau fil a été créé."""
        with _LOCKS_GUARD:
            t = _BACKGROUND.get(self.user_id)
            if t and t.is_alive():
                return False
            t = threading.Thread(target=self.run_background, args=(stop_event,), daemon=True, name=f"leaf-{self.user_id[:8]}")
            _BACKGROUND[self.user_id] = t
        t.start()
        return True

    def command_handlers(self) -> Dict[str, Callable[[Any], Any]]:
        """Handlers des commandes `LEAF_*`. Échec CLAIR si Leaf est désactivé sur le serveur (la commande est marquée
        échouée au lieu de réussir sans rien faire)."""
        def need_server():
            if not leaf_config.server_enabled():
                raise RuntimeError("Leaf Hunter est désactivé sur ce serveur (LEAF_ENABLED).")

        def refresh(_):
            need_server()
            self.run_scan(force=True, strict=True)

        def clean(_):
            need_server()
            self.cleanup()
        return {"LEAF_REFRESH": refresh, "LEAF_CLEANUP": clean}
