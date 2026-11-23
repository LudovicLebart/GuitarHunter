"""Orchestrateur Leaf Hunter côté bot : un passage = lecture des sources -> pipeline pur -> Postgres -> ntfy.

Appelé depuis la boucle de `main.py` (job planifié + commandes `LEAF_*`). Toutes les erreurs sont capturées : un passage
Leaf ne doit JAMAIS perturber le bot guitare. Le logger est celui du bot (`bot.{uid8}.leaf`), seul visible dans l'app."""
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.leaf import config as leaf_config
from backend.leaf import notify as leaf_notify
from backend.leaf import ai_extract, pipeline, scoring, verdict
from backend.leaf.sources import BlockedError, autohebdo, fetch_html, kijiji_autos
from backend.leaf.sources.detail import DetailFetcher

LOOP_TICK_S = 60                # la boucle de fond relit la config chaque minute (fréquence modifiable à chaud)
CLEANUP_EVERY_S = 6 * 3600
STALE_DAYS = 14                 # une annonce non revue depuis 14 jours (sources saines) est marquée vendue
ALERT_AFTER_FAILURES = 3        # alerte santé : au 3e échec consécutif d'une source (une fois par série)
MAX_INDIVIDUAL_NOTIFICATIONS = 5


BROWSER_WAIT_S = 120            # attente maximale d'un emplacement de navigateur (les scans de guitares peuvent durer)


def collect_sources(scan: Dict[str, Any], fetch: Callable[[str], str] = fetch_html, logger: Optional[logging.Logger] = None,
                    browser_guard: Optional[Any] = None, should_skip: Optional[Callable[[str, Any], bool]] = None,
                    stop_event: Optional[Any] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(annonces brutes, passages par source). Résultat d'une source : ok | no_cards | blocked | error | skipped.
    `browser_guard` (sémaphore du bot, facultatif) limite les navigateurs ouverts en même temps (Facebook seulement)."""
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
    if "facebook" in scan["sources"]:
        from backend.leaf.sources import facebook
        acquired = True
        if browser_guard:
            acquired = browser_guard.acquire(timeout=BROWSER_WAIT_S)     # jamais d'attente illimitée : Kijiji/AutoHebdo sont déjà lus
        if not acquired:
            runs.append({"source": "facebook", "outcome": "skipped", "cards_seen": 0, "duration_ms": 0,
                         "detail": "navigateurs occupés par les scans de guitares"})
        else:
            try:
                found, run = facebook.collect_facebook(scan, logger, should_skip=should_skip, stop_event=stop_event)
            finally:
                if browser_guard:
                    browser_guard.release()
            raws += found
            runs.append(run)
    return raws, runs


class _AnyStop:
    """`is_set()` vrai dès qu'un des événements d'arrêt du bot (STOP_BOT, STOP_SCAN) l'est : interrompt un scan Facebook en cours."""
    def __init__(self, events):
        self._events = tuple(e for e in events if e is not None)

    def is_set(self) -> bool:
        return any(e.is_set() for e in self._events)


_LOCKS: Dict[str, threading.Lock] = {}          # un verrou PAR UTILISATEUR, partagé entre boucle de fond et commandes
_LOCKS_GUARD = threading.Lock()
_BACKGROUND: Dict[str, Tuple[threading.Thread, threading.Event]] = {}   # une seule boucle de fond par utilisateur
_CURRENT: Dict[str, "LeafHunter"] = {}          # hunter COURANT de chaque utilisateur (remplacé quand le watchdog reconstruit le bot)
RETRY_AFTER_NONE_S = 600                        # passage manqué (verrou pris, erreur) : nouvel essai dans 10 min, pas à la période suivante


def stop_background(user_id: str) -> None:
    """Arrête la boucle de fond d'un utilisateur (bot retiré ou main_loop terminée)."""
    with _LOCKS_GUARD:
        entry = _BACKGROUND.pop(user_id, None)
        _CURRENT.pop(user_id, None)
    if entry:
        entry[1].set()


def _background_loop(user_id: str, stop: threading.Event) -> None:
    """Chaque minute : relit la config (fréquence modifiable à chaud) et lance un passage à l'échéance ; nettoyage toutes les
    6 h. Un passage long ne bloque ni le watchdog ni les tâches planifiées du bot. `last_scan` ne bouge qu'après un VRAI
    passage : un passage manqué (verrou pris par une commande manuelle, erreur) est retenté après RETRY_AFTER_NONE_S."""
    last_scan = last_cleanup = retry_at = 0.0
    stop.wait(30)                         # laisse le bot finir de démarrer
    while not stop.is_set():
        hunter = _CURRENT.get(user_id)
        try:
            if hunter and hunter.is_enabled():
                now = time.time()
                if now >= retry_at and now - last_scan >= hunter.config()["scan"]["frequency"] * 60:
                    if hunter.run_scan() is not None:
                        last_scan = time.time()
                    else:
                        retry_at = time.time() + RETRY_AFTER_NONE_S
                if now - last_cleanup >= CLEANUP_EVERY_S:
                    last_cleanup = now
                    hunter.cleanup()
        except Exception as e:
            (hunter.log if hunter else logging.getLogger(__name__)).error(f"[Leaf] Erreur de la boucle de fond : {e}", exc_info=True)
        stop.wait(LOOP_TICK_S)


def _lock_for(user_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(user_id, threading.Lock())


class LeafHunter:
    def __init__(self, repo, user_id: str, logger: Optional[logging.Logger] = None,
                 collector: Optional[Callable[[Dict[str, Any]], Tuple[list, list]]] = None,
                 detail_fetcher_factory: Optional[Callable[[], Any]] = None,
                 notifier: Callable[..., bool] = leaf_notify.send, browser_guard: Optional[Any] = None,
                 stop_events: Tuple[Any, ...] = (), analyzer: Optional[Any] = None, ai: Optional[Any] = None):
        self.repo, self.user_id = repo, user_id
        self.log = logger or logging.getLogger(__name__)
        if ai is None and analyzer is not None:
            from backend.leaf.ai import LeafAI
            ai = LeafAI(analyzer, self.log)
        self._ai = ai                      # niveau 2 (IA) : absent = jamais d'appel de modèle
        self._cap_notified_day = None
        self._stop = _AnyStop(stop_events)
        self._collector = collector or (lambda scan: collect_sources(
            scan, logger=self.log, browser_guard=browser_guard, stop_event=self._stop,
            should_skip=lambda fb_id, price: self.repo.known_unchanged(self.user_id, f"leaf_facebook_{fb_id}", price)))
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
        scan = self._with_facebook_city(scan)
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
        budget = self._ai_budget(cfg["analysis"])
        for i, listing in enumerate(result["kept"]):
            fit = scoring.price_fit(listing, comparables)
            if fit:
                listing["price_fit"] = fit
            listing = result["kept"][i] = self._enrich(listing, cfg["analysis"], budget)
            outcome = self.repo.upsert_listing(listing)
            self.repo.record_match(self.user_id, listing["id"])
            if outcome["action"] in ("new", "price_drop"):
                events.append((outcome["action"], listing, outcome["previous_price"]))
        # Annonces écartées par CET utilisateur : elles existent toujours (fraîcheur globale), mais sortent de SA vue.
        seen_but_excluded = [l["id"] for l in result["rejected"] + result["ignored"] if l.get("id")]
        self.repo.touch_seen(seen_but_excluded)
        withdrawn = self.repo.mark_withdrawn(self.user_id, seen_but_excluded)
        if withdrawn:
            self.log.info(f"[Leaf] {withdrawn} annonce(s) déjà stockée(s) ne passent plus vos filtres : retirée(s) de votre vue.")
        stats = {"read": len(raws), "kept": len(result["kept"]), "rejected": len(result["rejected"]),
                 "ignored": len(result["ignored"]), "new": sum(1 for e in events if e[0] == "new"),
                 "price_drops": sum(1 for e in events if e[0] == "price_drop")}
        self.log.info(f"[Leaf] {stats['read']} annonces lues : {stats['kept']} retenues ({stats['new']} nouvelles, "
                      f"{stats['price_drops']} baisses de prix), {stats['rejected']} rejetées par les règles, "
                      f"{stats['ignored']} hors périmètre.")
        if notify_cfg["enabled"]:
            self._notify_events(events, notify_cfg)
        return stats

    # ------------------------------------------------------------------ IA (niveau 2) et verdict

    def _ai_budget(self, acfg: Dict[str, Any]) -> Dict[str, int]:
        """Appels restants aujourd'hui (fenêtre de 24 h, tous les appels `leaf_t2` comptent, réussis ou non)."""
        if not acfg["enabled"] or self._ai is None:
            return {"left": 0}
        try:
            return {"left": max(0, acfg["max_calls_per_day"] - self.repo.count_ai_calls())}
        except Exception as e:           # compteur illisible : par prudence, aucun appel
            self.log.error(f"[Leaf] IA : plafond illisible ({e}), analyses suspendues.")
            return {"left": 0}

    def _enrich(self, listing: Dict[str, Any], acfg: Dict[str, Any], budget: Dict[str, int]) -> Dict[str, Any]:
        """Applique l'analyse IA (en cache si le texte et le prix n'ont pas changé, sinon un appel dans la limite du plafond),
        recalcule les scores avec les faits PROUVÉS, puis calcule le verdict EN CODE. Ne lève jamais : sans IA, le verdict
        reste calculé sur les règles seules."""
        try:
            stored = self.repo.get_ai(listing["id"])
            fp = ai_extract.fingerprint(listing)
            ai = None
            if stored and stored.get("fingerprint") == fp:
                ai = stored                                              # gratuit : texte et prix inchangés
            elif acfg["enabled"] and self._ai is not None:
                if budget["left"] > 0:
                    budget["left"] -= 1
                    ai, err = self._ai.extract(listing, acfg["providers"])
                    if err:
                        self.log.warning(f"[Leaf] IA : analyse impossible ({err}).")
                else:
                    self._notify_cap(acfg)
            if ai is None and stored:
                listing = {**listing, "ai": {**stored, "stale": True}}   # ancienne analyse, affichée comme périmée, jamais appliquée
            if ai is not None:
                listing = ai_extract.apply_to_listing(listing, ai)
                listing["ai"] = ai
                listing["battery_score"] = scoring.battery_score(listing.get("soh_announced"))
                listing["winter_fit"] = scoring.winter_fit(listing)
                listing["equipment"] = scoring.equipment_score(listing)
                listing["risk_flags"] = scoring.risk_flags(listing)
        except Exception as e:
            self.log.error(f"[Leaf] IA : enrichissement ignoré ({e}).", exc_info=True)
        v = verdict.compute_verdict(listing)
        listing["verdict"], listing["verdict_reasons"] = v["verdict"], v["reasons"]
        return listing

    def _notify_cap(self, acfg: Dict[str, Any]) -> None:
        today = time.strftime("%Y-%m-%d")
        if self._cap_notified_day == today:
            return
        self._cap_notified_day = today
        self.log.warning(f"[Leaf] IA : plafond de {acfg['max_calls_per_day']} analyses atteint, les suivantes attendent.")
        self._notify("Leaf : plafond d'analyses IA atteint", f"{acfg['max_calls_per_day']} analyses sur 24 h. Les prochaines annonces "
                     "sont affichées sans résumé IA ; le plafond se règle dans les réglages.", logger=self.log)

    def _with_facebook_city(self, scan: Dict[str, Any]) -> Dict[str, Any]:
        """Facebook cherche par ville : on prend la ville du catalogue la plus proche du point de référence (dans son rayon).
        Aucune ville -> pas de recherche Facebook (le passage est tracé « skipped », jamais une recherche au hasard)."""
        if "facebook" not in scan["sources"]:
            return scan
        home = scan.get("home") or {}
        city = None
        try:
            if home.get("latitude") is not None and home.get("longitude") is not None:
                city = self.repo.nearest_facebook_city(home["latitude"], home["longitude"], home.get("max_km") or 150)
        except Exception as e:           # une panne de lecture des villes ne doit pas arrêter Kijiji/AutoHebdo
            self.log.error(f"[Leaf] Facebook : ville introuvable ({e}) ; la source est ignorée à ce passage.")
        if city:
            self.log.info(f"[Leaf] Facebook : ville de recherche « {city['name']} » ({city['distance_km']:.0f} km du point de référence).")
        return {**scan, "facebook_city": city}

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
                strong = listing.get("verdict") == "CANDIDAT_FORT"
                self._notify("Leaf : candidat fort" if strong else "Leaf : nouvelle annonce", self._describe(listing),
                             priority="high" if strong else "default", click_url=listing.get("url"),
                             tags=["star" if strong else "car"], logger=self.log)
            else:
                self._notify(f"Leaf : baisse de prix ({previous:.0f} → {listing['price']:.0f} $)",
                             self._describe(listing), priority="high", click_url=listing.get("url"),
                             tags=["chart_with_downwards_trend"], logger=self.log)

    def _health_alert(self, source: str, outcome: str) -> None:
        """Alerte unique au 3e échec consécutif d'une source (bloquée, en erreur ou sans carte)."""
        if outcome in ("ok", "skipped"):          # « skipped » = réglage (aucune ville dans le rayon...), pas une panne
            return
        recent = self.repo.recent_outcomes(self.user_id, source, ALERT_AFTER_FAILURES + 3)
        failing = 0
        for o in recent:
            if o == "skipped":
                continue
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
            if source == "facebook":     # n'entre ni dans le balayage (20 annonces lues) ni dans sa condition
                continue
            last = self.repo.recent_outcomes(self.user_id, source, 1)
            if not last or last[0] != "ok":
                self.log.info(f"[Leaf] Nettoyage reporté : la source {source} n'a pas répondu normalement au dernier passage.")
                return 0
        n = self.repo.mark_stale_sold(STALE_DAYS)
        self.log.info(f"[Leaf] Nettoyage : {n} annonce(s) non revues depuis {STALE_DAYS} jours marquée(s) vendues.")
        return n

    # ------------------------------------------------------------------ boucle de fond

    def ensure_background(self) -> bool:
        """Démarre la boucle de fond de cet utilisateur si elle ne tourne pas, et la fait pointer vers CE hunter (le watchdog
        reconstruit le bot, donc son logger : la boucle relit toujours le hunter courant, jamais un ancien logger muet).
        Idempotent. True si un nouveau fil a été créé."""
        with _LOCKS_GUARD:
            _CURRENT[self.user_id] = self
            entry = _BACKGROUND.get(self.user_id)
            if entry and entry[0].is_alive() and not entry[1].is_set():
                return False
            stop = threading.Event()
            t = threading.Thread(target=_background_loop, args=(self.user_id, stop), daemon=True, name=f"leaf-{self.user_id[:8]}")
            _BACKGROUND[self.user_id] = (t, stop)
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
