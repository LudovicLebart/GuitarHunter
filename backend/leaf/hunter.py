"""Orchestrateur Leaf Hunter côté bot : un passage = lecture des sources -> pipeline pur -> Postgres -> ntfy.

Appelé depuis la boucle de `main.py` (job planifié + commandes `LEAF_*`). Toutes les erreurs sont capturées : un passage
Leaf ne doit JAMAIS perturber le bot guitare. Le logger est celui du bot (`bot.{uid8}.leaf`), seul visible dans l'app."""
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.leaf import config as leaf_config
from backend.leaf import notify as leaf_notify
from backend.leaf import ai_extract, expert as leaf_expert, photo_extract, pipeline, scoring, verdict
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
_EXPERT_LOCKS: Dict[str, threading.Lock] = {}     # un verrou PAR UTILISATEUR autour de « vérifier le plafond + appeler l'Expert »
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


def _expert_lock_for(user_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _EXPERT_LOCKS.setdefault(user_id, threading.Lock())


def _lock_for(user_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(user_id, threading.Lock())


class LeafHunter:
    def __init__(self, repo, user_id: str, logger: Optional[logging.Logger] = None,
                 collector: Optional[Callable[[Dict[str, Any]], Tuple[list, list]]] = None,
                 detail_fetcher_factory: Optional[Callable[[], Any]] = None,
                 notifier: Callable[..., bool] = leaf_notify.send, browser_guard: Optional[Any] = None,
                 stop_events: Tuple[Any, ...] = (), analyzer: Optional[Any] = None, ai: Optional[Any] = None,
                 photo_uploader: Optional[Callable[[List[str], str], Any]] = None):
        self.repo, self.user_id = repo, user_id
        self.log = logger or logging.getLogger(__name__)
        if ai is None and analyzer is not None:
            from backend.leaf.ai import LeafAI
            ai = LeafAI(analyzer, self.log)
        self._ai = ai                      # niveau 2 (IA) : absent = jamais d'appel de modèle
        self._cap_notified_day = None
        self._photo_uploader = photo_uploader      # (urls, deal_id) -> (urls stables, gs_uris) : photos Facebook (elles expirent)
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

    def run_scan(self, force: bool = False, strict: bool = False, force_ai: bool = False) -> Optional[Dict[str, Any]]:
        """Un passage complet. None si désactivé / déjà en cours ; sinon un bilan. `force` (commande manuelle)
        ignore seulement l'interrupteur par utilisateur, jamais celui du serveur. `strict` (commande) : une erreur
        ou un passage déjà en cours LÈVE au lieu de renvoyer None, pour que la commande soit marquée échouée. `force_ai` : refait
        l'analyse IA de chaque annonce retenue même si son texte et son prix n'ont pas changé (toujours dans le plafond quotidien)."""
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
                return self._scan(cfg, force_ai)
            finally:
                self._lock.release()
        except Exception as e:
            self.log.error(f"[Leaf] Passage interrompu : {e}", exc_info=True)
            if strict:
                raise
            return None

    def _scan(self, cfg: Dict[str, Any], force_ai: bool = False) -> Dict[str, Any]:
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
            listing = result["kept"][i] = self._enrich(listing, cfg["analysis"], budget, force_ai)
            self._stabilize_photos(listing)
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
            return {"left": 0, "photo_left": 0}
        try:
            return {"left": max(0, acfg["max_calls_per_day"] - self.repo.count_ai_calls()),
                    "photo_left": max(0, acfg["max_photo_calls_per_day"] - self.repo.count_ai_calls("leaf_photo")) if acfg["photos"] else 0}
        except Exception as e:           # compteur illisible : par prudence, aucun appel
            self.log.error(f"[Leaf] IA : plafond illisible ({e}), analyses suspendues.")
            return {"left": 0, "photo_left": 0}

    def _enrich(self, listing: Dict[str, Any], acfg: Dict[str, Any], budget: Dict[str, int], force_ai: bool = False) -> Dict[str, Any]:
        """Applique l'analyse IA (en cache si le texte et le prix n'ont pas changé, sinon un appel dans la limite du plafond),
        recalcule les scores avec les faits PROUVÉS, puis calcule le verdict EN CODE. Ne lève jamais : sans IA, le verdict
        reste calculé sur les règles seules."""
        try:
            stored = self.repo.get_ai(listing["id"])
            fp = ai_extract.fingerprint(listing)
            ai = None
            if stored and stored.get("fingerprint") == fp and not (force_ai and acfg["enabled"] and self._ai is not None
                                                                   and not listing.get("detail_unavailable")):
                ai = stored                                              # gratuit : texte et prix inchangés (sauf ré-analyse demandée)
            elif listing.get("detail_unavailable"):
                # Fiche illisible à ce passage : le texte est celui, plus court, de la carte. Ni appel payant, ni écrasement d'une analyse
                # faite sur le texte complet : l'analyse stockée (si elle existe) est réutilisée telle quelle.
                ai = stored
            elif acfg["enabled"] and self._ai is not None:
                if budget["left"] > 0:
                    budget["left"] -= 1
                    ai, err = self._ai.extract(listing, acfg["providers"])
                    if err:
                        self.log.warning(f"[Leaf] IA : analyse impossible ({err}).")
                else:
                    self._notify_cap(acfg)
            if ai is None and stored:
                listing = {**listing, "ai_stale": True}                  # l'ancienne analyse (conservée en base, intacte) est affichée comme périmée
            if ai is not None:
                listing = ai_extract.apply_to_listing(listing, ai)
                if ai is not stored:
                    listing["ai"] = ai                                   # nouvelle analyse seulement ; sinon la copie stockée est conservée telle quelle
                listing["battery_score"] = scoring.battery_score(listing.get("soh_announced"))
                listing["winter_fit"] = scoring.winter_fit(listing)
                listing["equipment"] = scoring.equipment_score(listing)
                listing["risk_flags"] = scoring.risk_flags(listing)
        except Exception as e:
            self.log.error(f"[Leaf] IA : enrichissement ignoré ({e}).", exc_info=True)
        listing = self._enrich_photos(listing, acfg, budget, force_ai)
        v = verdict.compute_verdict(listing)
        listing["verdict"], listing["verdict_reasons"] = v["verdict"], v["reasons"]
        return listing

    def _stabilize_photos(self, listing: Dict[str, Any]) -> None:
        """Les photos Facebook EXPIRENT : copiées vers le stockage (comme pour les guitares) à la première lecture seulement ; les
        passages suivants gardent les adresses déjà stables. Sans stockage ou en cas d'échec, les adresses d'origine sont gardées."""
        if listing.get("source") != "facebook" or self._photo_uploader is None or not listing.get("image_urls"):
            return
        try:
            existing = self.repo.get_vehicle(listing["id"])
            if existing and existing.get("image_urls"):
                listing["image_urls"] = list(existing["image_urls"])
                return
            stable, _ = self._photo_uploader(listing["image_urls"], listing["id"])
            if stable:
                listing["image_urls"] = list(stable)
        except Exception as e:
            self.log.warning(f"[Leaf] Photos Facebook non copiées vers le stockage ({e}) : adresses d'origine conservées (elles expirent).")

    def _enrich_photos(self, listing: Dict[str, Any], acfg: Dict[str, Any], budget: Dict[str, int], force: bool = False) -> Dict[str, Any]:
        """Lecture des captures d'écran (SOH LeafSpy...) : seulement si l'option est active, que le SOH est ENCORE inconnu après le texte
        (règles et IA), que la fiche a été lue et qu'il reste du budget. En cache tant que les photos ne changent pas (`analysis.photos`,
        conservée par les passages) ; une lecture déjà faite est appliquée gratuitement même si l'option est ensuite éteinte. Ne lève jamais."""
        try:
            urls = photo_extract.photo_urls(listing)
            if not urls:
                return listing
            fp = photo_extract.fingerprint(urls)
            stored = self.repo.get_photos(listing["id"])
            can_read = (acfg["enabled"] and acfg["photos"] and self._ai is not None and listing.get("soh_announced") is None
                        and not listing.get("detail_unavailable"))
            photos = None
            if stored and stored.get("fingerprint") == fp and not (force and can_read):
                photos = stored                                           # photos inchangées : rien à relire
            elif can_read:
                if budget.get("photo_left", 0) >= 2:                      # un tri et une lecture : jusqu'à 2 appels
                    budget["photo_left"] -= 2
                    photos, err = self._ai.read_photos(listing, acfg["providers"])
                    if err:
                        self.log.warning(f"[Leaf] Photos : lecture impossible ({err}).")
                else:
                    self.log.info("[Leaf] Photos : plafond quotidien de lectures atteint, les suivantes attendent.")
            if photos:
                if photos is not stored:
                    listing = {**listing, "photos": photos}
                else:
                    listing = {**listing, "photos": stored}
                flags = list(listing.get("flags") or [])
                flags += [f for f in photos.get("flags") or [] if f not in flags]
                listing["flags"] = flags
        except Exception as e:
            self.log.error(f"[Leaf] Photos : lecture ignorée ({e}).", exc_info=True)
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

    def reanalyze_deal(self, deal_id: str) -> Dict[str, Any]:
        """Ré-analyse UNE annonce déjà stockée : relit sa fiche (Kijiji / AutoHebdo ; Facebook garde son texte stocké), refait normalisation,
        règles, scores et verdict avec le code ACTUEL, et refait l'analyse IA (nouvel appel, dans le plafond). Utile quand les règles ont
        été améliorées ou que le vendeur a modifié son annonce. Échec CLAIR si la fiche est illisible ou si l'annonce ne passe plus les
        règles (elle est alors retirée de la vue de l'utilisateur, avec la raison)."""
        cfg = self.config()
        scan = cfg["scan"]
        row = self.repo.get_visible_vehicle(self.user_id, deal_id)
        if row is None:
            raise RuntimeError("Annonce introuvable.")
        raw = {"id": row["id"], "source": row["source"], "source_id": row["source_id"], "url": row["link"], "title": row["title"],
               "description": row["description"], "price": float(row["price"]) if row["price"] is not None else None, "year": row["year"],
               "km": row["km"], "trim": row["trim"], "vin": row["vin"], "seller_type": row["seller_type"], "city": row["location"],
               "latitude": row["latitude"], "longitude": row["longitude"], "image_urls": list(row["image_urls"] or []), "model": "leaf"}
        if row["source"] == "facebook":                                  # pas de relecture sans navigateur : on garde le texte stocké
            raw["detail_fetched"], raw["year_optional"] = True, True
        criteria = {k: scan[k] for k in ("years", "min_price", "max_price", "max_km")}
        fetcher = None if raw.get("detail_fetched") else self._detail_factory()
        result = pipeline.evaluate_listings([raw], criteria, detail_fetcher=fetcher, home=scan["home"])
        if not result["kept"]:
            dropped = (result["rejected"] or result["ignored"])[0]
            reason = ", ".join(dropped.get("reject_reasons") or [dropped.get("ignored_reason") or "?"])
            self.repo.mark_withdrawn(self.user_id, [deal_id])
            raise RuntimeError(f"Après relecture, l'annonce ne passe plus les règles ({reason}) : retirée de votre liste.")
        listing = result["kept"][0]
        if listing.get("detail_unavailable"):
            raise RuntimeError("La fiche de l'annonce est illisible pour le moment (site bloqué ?) : réessayez plus tard.")
        fit = scoring.price_fit(listing, self.repo.comparables())
        if fit:
            listing["price_fit"] = fit
        budget = self._ai_budget(cfg["analysis"])
        listing = self._enrich(listing, cfg["analysis"], budget, force_ai=True)
        self.repo.upsert_listing(listing)
        self.repo.record_match(self.user_id, deal_id)                    # lève un retrait antérieur : l'annonce repasse les règles
        self.log.info(f"[Leaf] Ré-analyse terminée ({deal_id[-12:]}) : verdict {listing.get('verdict')}.")
        return listing

    def _expert_photos(self, listing: Dict[str, Any], acfg: Dict[str, Any]) -> Tuple[list, list]:
        """Photos jointes à l'Expert (option « lire aussi les photos » seulement) : les captures retenues par le tri (`analysis.photos.selected`)
        et la première photo, au plus 4, en haute résolution. Ne lève jamais : sans photo, l'Expert travaille sur le texte seul."""
        if not acfg.get("photos") or self._ai is None:
            return [], []
        try:
            urls = photo_extract.photo_urls(listing)
            order = [n for n in ((listing.get("photos") or {}).get("selected") or []) if 1 <= n <= len(urls)]
            if urls and 1 not in order:
                order.append(1)
            order = (order or list(range(1, min(len(urls), 3) + 1)))[:leaf_expert.MAX_EXPERT_PHOTOS]
            images = self._ai.analyzer._download_images([photo_extract.sized_url(urls[n - 1], "large") for n in order])
            return (images, order) if len(images) == len(order) else ([], [])
        except Exception as e:
            self.log.warning(f"[Leaf] Expert : photos non jointes ({e}).")
            return [], []

    def analyze_deal(self, deal_id: str) -> Dict[str, Any]:
        """Analyse approfondie (Expert, niveau 3) d'UNE annonce, à la demande. Échec CLAIR (la commande est marquée échouée) si
        l'IA est éteinte, le plafond atteint, l'annonce introuvable ou le modèle en panne : le bouton affiche la cause."""
        acfg = self.config()["analysis"]
        if not acfg["enabled"]:
            raise RuntimeError("L'analyse IA est éteinte : activez-la dans les réglages de Leaf.")
        if self._ai is None:
            raise RuntimeError("Analyseur indisponible (bot hors ligne).")
        row = self.repo.get_visible_vehicle(self.user_id, deal_id)
        if row is None:
            raise RuntimeError("Annonce introuvable.")
        # Vérification du plafond ET appel sous un même verrou : deux clics rapprochés ne dépassent pas le plafond. Le compte porte sur les
        # réponses OBTENUES (`ok`) : une nouvelle tentative après une erreur passagère ne consomme pas deux places.
        with _expert_lock_for(self.user_id):
            used = self.repo.count_ai_calls("leaf_t3", ok_only=True)
            if used >= acfg["max_expert_per_day"]:
                raise RuntimeError(f"Plafond atteint : {used} analyses approfondies sur 24 h (maximum {acfg['max_expert_per_day']}, réglable).")
            listing = leaf_expert.row_to_listing(row)
            images, numbers = self._expert_photos(listing, acfg)
            opinion, err = self._ai.expert(listing, images, numbers)
            if opinion is None:
                raise RuntimeError(f"L'Expert n'a pas répondu : {err}")
            self.repo.store_expert(deal_id, opinion)
        self.log.info(f"[Leaf] Analyse approfondie terminée ({deal_id[-12:]}) : à visiter = {opinion['worth_visiting']}.")
        return opinion

    def command_handlers(self) -> Dict[str, Callable[[Any], Any]]:
        """Handlers des commandes `LEAF_*`. Échec CLAIR si Leaf est désactivé sur le serveur (la commande est marquée
        échouée au lieu de réussir sans rien faire)."""
        def need_server():
            if not leaf_config.server_enabled():
                raise RuntimeError("Leaf Hunter est désactivé sur ce serveur (LEAF_ENABLED).")

        def refresh(payload):
            need_server()
            self.run_scan(force=True, strict=True, force_ai=isinstance(payload, dict) and payload.get("forceAi") is True)

        def clean(_):
            need_server()
            self.cleanup()
        def analyze(payload):
            need_server()
            deal_id = payload.get("dealId") if isinstance(payload, dict) else None
            if not isinstance(deal_id, str):
                raise RuntimeError("Annonce non précisée.")
            self.analyze_deal(deal_id)
        def reanalyze(payload):
            need_server()
            deal_id = payload.get("dealId") if isinstance(payload, dict) else None
            if not isinstance(deal_id, str):
                raise RuntimeError("Annonce non précisée.")
            with self._lock:                                             # même verrou que les passages : pas de relecture simultanée
                self.reanalyze_deal(deal_id)
        return {"LEAF_REFRESH": refresh, "LEAF_CLEANUP": clean, "LEAF_ANALYZE": analyze, "LEAF_REANALYZE": reanalyze}
