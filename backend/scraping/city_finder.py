"""Recherche de l'ID Facebook Marketplace d'une ville (v2, 2026-10-23).

Pourquoi une v2 (voir docs/management/plans/FB_CITY_IDS_AND_SCRAPER_HEALTH_PLAN.md) : la v1 cliquait la
première suggestion du sélecteur de lieu. Facebook OMET la région des lieux proches de l'IP du client —
« Bromont | Ville » (Québec) et « Bromont-Lamothe, Auvergne, France | Ville » — donc l'indice « Québec » ne
correspondait jamais, la v1 retombait sur la 1re suggestion et le bot a gardé l'ID d'un Bromont français :
tout le scan Facebook tournait en France, sans la moindre alerte.

Principe de la v2 : **ne jamais croire un ID sans l'avoir vérifié**, parce que le clic sur une suggestion
n'est pas fiable (deux suggestions différentes ont donné le même ID, et l'attente d'URL de la v1 rendait la
main sur l'ancienne URL). Pour chaque suggestion plausible (nom exact, région absente ou compatible) :
  1. clic PAR LIBELLÉ, puis attente du CHANGEMENT d'URL, ID numérique exigé ;
  2. sonde de `/marketplace/<id>/` : ville affichée par le bouton de lieu (doit être la ville demandée) et
     part des cartes dont le lieu est dans la province attendue (« , QC »), éventuellement proches de la ville
     (voir `city_verification.py` — fonctions pures, testées sans Facebook).

L'orchestration (`CityFinder.lookup`) est séparée de Playwright (`PlaywrightCityDriver`) : on la teste avec
un faux pilote.
"""
import logging
import random
import re
import time
import urllib.parse
from collections import namedtuple

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from backend.scraping import city_verification as cv
from backend.scraping.parser import ListingParser

_module_logger = logging.getLogger(__name__)

# Rétro-compatibilité : l'ancien nom était importé ailleurs.
_REGION_ALIASES = cv.REGION_ALIASES

LEGACY = "LEGACY"  # indice de province inconnu : impossible de vérifier, ancien comportement (needsReview)

CityLookupResult = namedtuple("CityLookupResult", ["city_id", "coords", "label", "status", "detail", "evidence"])
SelectResult = namedtuple("SelectResult", ["city_id", "segment", "changed", "coords"])
ProbeResult = namedtuple("ProbeResult", ["cards", "landed_label"])


class FacebookBlocked(Exception):
    """Redirection login / captcha / checkpoint : arrêter toute la série de requêtes."""


class PlaywrightCityDriver:
    """Opérations Facebook de `CityFinder.lookup`, chacune sur une page neuve (aucun état partagé)."""

    LOCATION_INPUT = "input[aria-label='Lieu'], input[aria-label='Location'], input[placeholder*='Lieu'], input[placeholder*='Location']"
    APPLY_BUTTON = "div[aria-label='Appliquer'], div[aria-label='Apply']"
    PROBE_MAX_CARDS = 30

    def __init__(self, scraper, pace=True):
        self.scraper = scraper
        self.logger = scraper.logger
        self.pace = pace

    # -- utilitaires ---------------------------------------------------------------------------
    def _pause(self, low=1.0, high=2.5):
        if self.pace:
            time.sleep(random.uniform(low, high))

    def _guard(self, page):
        url = page.url.lower()
        if "/login" in url or "captcha" in url or "checkpoint" in url:
            raise FacebookBlocked(f"redirection {page.url}")

    @staticmethod
    def _location_button(page):
        btn = page.locator("div[role='button']").filter(has_text=re.compile(r"\d+\s*(km|mi)", re.IGNORECASE)).first
        if not btn.is_visible(timeout=5000):
            btn = page.locator("div[aria-label*='Lieu'], div[aria-label*='Location'], div[aria-label*='Lugar']").first
        return btn

    @staticmethod
    def _option_label(element):
        return " | ".join(line.strip() for line in element.inner_text().split("\n") if line.strip())

    def _open_picker(self, page, city_name):
        page.goto("https://www.facebook.com/marketplace/", timeout=30000)
        self._guard(page)
        self.scraper._close_login_popup(page)
        self._location_button(page).click(force=True, timeout=10000)
        page.wait_for_selector("div[role='dialog']", timeout=8000)
        field = page.locator(self.LOCATION_INPUT).first
        field.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        field.fill(city_name)
        time.sleep(3)
        return page.locator("div[role='option']").all()

    # -- interface du pilote -------------------------------------------------------------------
    def list_suggestions(self, city_name):
        self.scraper._ensure_session()
        page = self.scraper.context.new_page()
        try:
            return [self._option_label(o) for o in self._open_picker(page, city_name)]
        finally:
            page.close()

    def select(self, city_name, label, occurrence=0):
        """Clique la suggestion `label` (n-ième occurrence si plusieurs libellés identiques), applique,
        attend que l'URL CHANGE et retourne (ID numérique ou None, segment brut, URL changée ?, coords)."""
        self._pause()
        self.scraper._ensure_session()
        page = self.scraper.context.new_page()
        try:
            options = self._open_picker(page, city_name)
            matching = [o for o in options if self._option_label(o) == label]
            if len(matching) <= occurrence:
                raise LookupError(f"suggestion « {label} » (n°{occurrence + 1}) absente après rechargement")
            before = page.url
            matching[occurrence].click()
            time.sleep(0.5)
            page.locator(self.APPLY_BUTTON).first.click()
            changed = True
            try:
                page.wait_for_function("u => location.href !== u", arg=before, timeout=10000)
            except PlaywrightTimeoutError:
                changed = False
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeoutError:
                pass
            self._guard(page)
            coords = None
            query = urllib.parse.parse_qs(urllib.parse.urlparse(page.url).query)
            if query.get("latitude") and query.get("longitude"):
                try:
                    coords = {"lat": float(query["latitude"][0]), "lon": float(query["longitude"][0])}
                except ValueError:
                    coords = None
            return SelectResult(cv.numeric_city_id(page.url), cv.marketplace_segment(page.url), changed, coords)
        finally:
            page.close()

    def probe(self, city_id):
        """Ouvre `/marketplace/<id>/` (fil général de la ville, toutes catégories) et retourne le lieu
        affiché par le bouton de lieu ainsi que le lieu de chaque carte lue."""
        self._pause()
        self.scraper._ensure_session()
        page = self.scraper.context.new_page()
        try:
            page.goto(f"https://www.facebook.com/marketplace/{city_id}/", timeout=45000)
            self._guard(page)
            self.scraper._close_login_popup(page)
            try:
                page.wait_for_selector("a[href*='/marketplace/item/']", timeout=15000)
            except PlaywrightTimeoutError:
                pass
            landed = ""
            try:
                landed = " ".join(self._location_button(page).inner_text(timeout=5000).split())
            except Exception:
                pass
            for _ in range(2):
                page.mouse.wheel(0, 1000)
                time.sleep(1.5)
            cards = []
            for link in page.locator("a[href*='/marketplace/item/']").all()[: self.PROBE_MAX_CARDS]:
                location = ListingParser.parse_listing_card(link, "", logger=self.logger).get("location")
                if location:
                    cards.append(location)
            return ProbeResult(cards, landed)
        finally:
            page.close()


class CityFinder:
    @staticmethod
    def lookup(driver, city_name, region_hint=None, expected_coords=None, gazetteer=None,
               max_candidates=4, logger=None):
        """Retourne un `CityLookupResult`. `status` : VERIFIED (ID sûr), LEGACY (indice de province
        inconnu : ID non vérifié, à marquer needsReview), sinon AMBIGUOUS / INDETERMINATE / NOT_FOUND avec
        `city_id = None` (ne jamais enregistrer un ID douteux)."""
        log = logger or _module_logger
        labels = driver.list_suggestions(city_name)
        if not labels:
            return CityLookupResult(None, None, None, cv.NOT_FOUND, "aucune suggestion Facebook", [])

        province = cv.province_code(region_hint)
        candidates = cv.filter_candidates(labels, city_name, region_hint)

        if not province:
            return CityFinder._legacy(driver, city_name, labels, candidates, log)

        if not candidates:
            return CityLookupResult(None, None, None, cv.NOT_FOUND,
                                    f"aucune des {len(labels)} suggestion(s) ne correspond au nom « {city_name} » dans la région « {region_hint} » : {labels}", [])

        evidence, scored, coords_by_id, label_by_id = [], [], {}, {}
        for cand in candidates[:max_candidates]:
            occurrence = sum(1 for l in labels[: cand["index"]] if l == cand["label"])
            try:
                sel = driver.select(city_name, cand["label"], occurrence)
            except FacebookBlocked:
                raise
            except Exception as e:  # une suggestion qui échoue ne doit pas empêcher d'essayer les autres
                evidence.append({"label": cand["label"], "error": f"clic impossible : {str(e)[:100]}"})
                continue
            # ID numérique, sinon alias texte (« montreal ») : jamais accepté sans le sondage ci-dessous.
            fb_id = sel.city_id or cv.slug_from_segment(sel.segment)
            if not fb_id:
                evidence.append({"label": cand["label"], "error": f"pas d'ID numérique (segment « {sel.segment} »)", "url_changed": sel.changed})
                continue
            if any(e.get("id") == fb_id for e in evidence):
                continue  # même ID déjà sondé (clic non fiable : plusieurs libellés -> un seul ID)

            probe = driver.probe(fb_id)
            name_ok = cv.landed_name_matches(probe.landed_label, city_name)
            score = cv.score_probe(probe.cards, province, expected_coords, gazetteer)
            evidence.append({"id": fb_id, "label": cand["label"], "landed": probe.landed_label,
                             "name_ok": name_ok, "url_changed": sel.changed, **score})
            coords_by_id[fb_id], label_by_id[fb_id] = sel.coords, cand["label"]
            # Une page qui n'affiche pas la ville demandée (clic non pris en compte) ne peut pas valider.
            scored.append({"id": fb_id, **(score if name_ok else {"n": 0, "part_province": 0.0, "part_near": None})})

        probed = [e for e in evidence if "id" in e]
        if not probed:
            return CityLookupResult(None, None, None, cv.NOT_FOUND, "aucun ID numérique obtenu pour les suggestions plausibles", evidence)
        if not any(e["name_ok"] for e in probed):
            return CityLookupResult(None, None, None, cv.NOT_FOUND,
                                    "la page chargée n'affiche pas la ville demandée : " + ", ".join(f"{e['id']}→« {e['landed']} »" for e in probed), evidence)

        decision = cv.decide(scored)
        if decision.status == cv.VERIFIED:
            cid = decision.city_id
            log.info(f"✅ ID Facebook vérifié pour « {city_name} » : {cid} ({label_by_id[cid]})")
            return CityLookupResult(cid, coords_by_id.get(cid), label_by_id[cid], cv.VERIFIED, decision.detail, evidence)
        log.warning(f"⚠️ ID Facebook de « {city_name} » non vérifié ({decision.status}) : {decision.detail}")
        return CityLookupResult(None, None, None, decision.status, decision.detail, evidence)

    @staticmethod
    def _legacy(driver, city_name, labels, candidates, log):
        """Pas de province connue (ancien payload en simple chaîne, ou région hors Canada) : vérification
        impossible, on garde le comportement historique (1re suggestion plausible) mais NON vérifié."""
        pick = candidates[0] if candidates else {"index": 0, "label": labels[0]}
        occurrence = sum(1 for l in labels[: pick["index"]] if l == pick["label"])
        sel = driver.select(city_name, pick["label"], occurrence)
        city_id = sel.city_id or sel.segment
        log.warning(f"⚠️ ID Facebook de « {city_name} » NON vérifié (aucune province connue) : {city_id}")
        return CityLookupResult(city_id, sel.coords, pick["label"], LEGACY, "indice de province inconnu : non vérifié", [])

    @staticmethod
    def lookup_with_scraper(scraper, city_name, region_hint=None, expected_coords=None, gazetteer=None):
        scraper._ensure_session()
        return CityFinder.lookup(PlaywrightCityDriver(scraper), city_name, region_hint=region_hint,
                                 expected_coords=expected_coords, gazetteer=gazetteer, logger=scraper.logger)

    @staticmethod
    def find_city_id_and_coords(scraper, city_name, region_hint=None, expected_coords=None, gazetteer=None):
        """Compatibilité avec l'ancien contrat : (city_id, city_coords, matched_label, matched_confidently).
        `city_id` est None si l'ID n'a pas pu être VÉRIFIÉ (jamais un ID douteux) ; `matched_confidently`
        n'est vrai que pour un ID VERIFIED. Les appelants qui veulent la raison de l'échec utilisent
        `lookup_with_scraper`."""
        try:
            result = CityFinder.lookup_with_scraper(scraper, city_name, region_hint, expected_coords, gazetteer)
        except FacebookBlocked as e:
            scraper.logger.error(f"🚨 CityFinder bloqué par Facebook : {e}")
            return None, None, None, False
        except Exception as e:
            scraper.logger.critical(f"Erreur critique dans CityFinder: {e}", exc_info=True)
            return None, None, None, False
        if result.status in (cv.VERIFIED, LEGACY):
            return result.city_id, result.coords, result.label, result.status == cv.VERIFIED
        return None, None, None, False
