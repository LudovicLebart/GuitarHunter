"""
Scraper LeBonCoin — approche Playwright "douce" (mêmes mesures stealth que
FacebookScraper : rotation UA/viewport, flags anti-détection — mais SANS
contournement actif de DataDome type SSL Pinning/TLS spoofing). Calibré et
validé le 2026-07-21 (voir docs/management/JOURNAL.md).

Extraction via le JSON structuré __NEXT_DATA__ embarqué par LeBonCoin
(Next.js) plutôt que des sélecteurs CSS fragiles. Liste blanche stricte de
champs — le bloc "owner" (pseudo/user_id/store_id du vendeur) n'est jamais
extrait ni stocké, conformément à la règle "pas de données personnelles"
fixée pour ce chantier.

Comportement anti-prévisibilité (délibéré) : une session qui ouvre une page,
attend un temps fixe puis ferme, répétée à l'identique à chaque cycle, est
elle-même un signal comportemental détectable dans la durée — DataDome ne se
limite pas à un challenge JS ponctuel, il réévalue en continu. Ce module
introduit donc : délais aléatoires (jamais fixes), scroll/mouvement de souris
simulés (sans besoin fonctionnel — les résultats sont déjà dans le JSON dès
le chargement), et une session réutilisable sur plusieurs recherches (pas de
fermeture systématique du navigateur après chaque appel).
"""
import logging
import random
import re
import json
import time
import urllib.parse

from playwright.sync_api import sync_playwright

# Mêmes familles que FacebookScraper (backend/scraping/core.py) — cohérence
# de posture de furtivité entre les deux scrapers.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
]

DATADOME_CHALLENGE_MARKERS = ["captcha-delivery.com"]
SUSPICIOUS_TITLE_KEYWORDS = ["just a moment", "vérification", "attention requise", "access denied", "pardon our interruption"]


class LeboncoinScraper:
    def __init__(self, storage_state_path, logger=None):
        self.storage_state_path = storage_state_path
        self.logger = logger or logging.getLogger(__name__)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None  # onglet réutilisé sur toute la session (pas de nouvel onglet par recherche)
        self._responses = []

    def start_session(self):
        """Démarre la session Playwright. Sans effet si déjà démarrée — permet
        d'appeler search() plusieurs fois dans la même session (comportement
        humain : l'onglet reste ouvert, on relance des recherches)."""
        if self.context:
            return
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-sandbox"],
        )
        ua = random.choice(USER_AGENTS)
        vp = random.choice(VIEWPORTS)
        self.context = self.browser.new_context(
            storage_state=self.storage_state_path, user_agent=ua, viewport=vp, locale="fr-FR"
        )
        self.logger.info("Session LeBonCoin démarrée.")

    def close_session(self):
        if self.context:
            self.context.close()  # ferme aussi self.page
            self.context = None
        self.page = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        self.logger.info("Session LeBonCoin fermée.")

    def _ensure_session(self):
        if not self.context:
            self.start_session()

    def _get_page(self):
        """Onglet unique réutilisé pour toutes les recherches de la session — un
        humain relance des recherches dans le même onglet, il n'en ouvre pas un
        nouveau à chaque fois. Recréé seulement si absent ou fermé (ex: fermé
        manuellement par l'utilisateur)."""
        if self.page is None or self.page.is_closed():
            self.page = self.context.new_page()
            self.page.on("response", lambda r: self._responses.append(r))
        return self.page

    def _human_pause(self, low, high):
        time.sleep(random.uniform(low, high))

    def _simulate_browsing(self, page):
        """Scroll + mouvement de souris — signal comportemental, pas un besoin
        fonctionnel (les résultats sont déjà tous dans le JSON __NEXT_DATA__ dès
        le chargement de la page)."""
        try:
            for _ in range(random.randint(1, 3)):
                page.mouse.wheel(0, random.randint(300, 1000))
                self._human_pause(0.5, 1.8)
            page.mouse.move(random.randint(100, 800), random.randint(100, 600))
        except Exception as e:
            # warning (pas debug) : un échec silencieux ici serait invisible en usage
            # normal (niveau INFO) alors que c'est un signal utile à diagnostiquer.
            self.logger.warning(f"Simulation de navigation échouée (non bloquant) : {e}")

    @staticmethod
    def build_url(query, locations=None, category="30", min_price=0, max_price=0, owner_type=None, page_num=1):
        query_encoded = urllib.parse.quote(query)
        url = f"https://www.leboncoin.fr/recherche?category={category}&text={query_encoded}"
        if locations:
            # safe="," pour préserver la séparation multi-villes.
            url += f"&locations={urllib.parse.quote(locations, safe=',')}"
        if min_price > 0 or max_price > 0:
            # Format confirmé : price={min}-{max} (deux nombres, ex: price=50-200).
            # Borne non fournie laissée vide (généralisation du format confirmé,
            # non vérifiée indépendamment pour le cas à une seule borne).
            min_part = str(min_price) if min_price > 0 else ""
            max_part = str(max_price) if max_price > 0 else ""
            url += f"&price={min_part}-{max_part}"
        if owner_type:
            url += f"&owner_type={owner_type}"
        url += "&sort=time&order=desc"  # annonces les plus récentes en premier
        if page_num > 1:
            url += f"&page={page_num}"
        return url

    def _looks_blocked(self, page, responses):
        if any(marker in page.url for marker in DATADOME_CHALLENGE_MARKERS):
            return True, f"Redirection vers un domaine de challenge DataDome : {page.url}"
        for resp in responses:
            if resp.status in (403, 429):
                return True, f"Réponse HTTP {resp.status} sur {resp.url}"
        title = (page.title() or "").lower()
        if any(kw in title for kw in SUSPICIOUS_TITLE_KEYWORDS):
            return True, f"Titre de page suspect : '{page.title()}'"
        return False, None

    @staticmethod
    def extract_ads(html):
        """Parse le JSON __NEXT_DATA__ et retourne (annonces_minimisées, max_pages).
        Retourne (None, None) si le bloc est absent ou d'une forme inattendue."""
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not match:
            return None, None
        try:
            data = json.loads(match.group(1))
            search_data = data["props"]["pageProps"]["searchData"]
            ads = search_data["ads"]
            max_pages = search_data.get("max_pages", 1)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None, None

        if ads is None:  # clé présente mais valeur JSON null (forme dégradée)
            return None, None

        results = []
        for ad in ads:
            location = ad.get("location") or {}
            images = ad.get("images") or {}
            price_list = ad.get("price") or []
            results.append({
                "id": ad.get("list_id"),
                "title": ad.get("subject"),
                "price": price_list[0] if price_list else None,
                "description": ad.get("body") or None,  # vide sur la page de résultats
                "url": ad.get("url"),
                "published_at": ad.get("first_publication_date"),
                "location": {
                    "city": location.get("city"),
                    "zipcode": location.get("zipcode"),
                    "lat": location.get("lat"),
                    "lng": location.get("lng"),
                },
                "image_urls": images.get("urls") or [],
                # NOTE : le bloc "owner" (pseudo, user_id, store_id du vendeur) est
                # intentionnellement exclu — aucune donnée personnelle vendeur stockée.
            })
        return results, max_pages

    def search(self, query, locations=None, category="30", min_price=0, max_price=0,
               owner_type=None, max_pages_limit=None):
        """Recherche paginée (jusqu'au max_pages annoncé par LeBonCoin lui-même,
        ou max_pages_limit si fourni et plus restrictif — jamais au-delà, aucune
        page inexistante n'est demandée).

        Retourne (annonces, blocage) : blocage est None si tout s'est bien passé.
        Sinon une chaîne décrivant le problème — soit un vrai blocage DataDome,
        soit un échec d'extraction (préfixé "extraction_failed: ") signalé de la
        même façon pour que l'appelant ne confonde jamais un vrai résultat vide
        avec une extraction cassée par un changement de structure du site.

        La page/l'onglet n'est JAMAIS fermé automatiquement par cette méthode —
        ni en cas de succès, ni en cas de blocage, ni en cas d'échec d'extraction.
        Le même onglet est réutilisé d'un appel à l'autre (comportement humain :
        on relance des recherches dans le même onglet). Seule `close_session()`
        ferme réellement le navigateur, à la demande explicite de l'appelant."""
        self._ensure_session()
        page = self._get_page()

        all_ads = []
        page_num = 1
        effective_max_pages = None  # connu seulement après la 1ère page chargée

        while True:
            self._responses.clear()  # ne garder que les réponses de CETTE page (évite les faux
                                      # positifs de blocage dus à un vieux 403 d'une page précédente)
            url = self.build_url(query, locations, category, min_price, max_price, owner_type, page_num)
            page_label = f"{page_num}/{effective_max_pages}" if effective_max_pages else str(page_num)
            self.logger.info(f"➡️  Navigation LeBonCoin (page {page_label}) : {url}")
            page.goto(url, timeout=0, wait_until="domcontentloaded")
            self._human_pause(2.0, 4.5)

            blocked, reason = self._looks_blocked(page, self._responses)
            if blocked:
                self.logger.warning(f"🚨 Blocage LeBonCoin détecté : {reason}")
                try:
                    page.screenshot(path="leboncoin_probe_blocked.png")
                    self.logger.info("   Capture d'écran sauvegardée : leboncoin_probe_blocked.png")
                except Exception as e:
                    self.logger.debug(f"Capture d'écran échouée : {e}")
                self.logger.info("   Page laissée ouverte (intervention manuelle possible, ex: slider).")
                return all_ads, reason

            self._simulate_browsing(page)

            ads, max_pages = self.extract_ads(page.content())
            if ads is None:
                reason = "extraction_failed: bloc __NEXT_DATA__ introuvable ou de forme inattendue"
                self.logger.warning(f"⚠️ {reason} — arrêt de la pagination.")
                try:
                    with open("leboncoin_probe_page.html", "w", encoding="utf-8") as f:
                        f.write(page.content())
                    self.logger.info("   HTML sauvegardé : leboncoin_probe_page.html")
                except Exception as e:
                    self.logger.debug(f"Sauvegarde HTML échouée : {e}")
                self.logger.info("   Page laissée ouverte (inspection manuelle possible).")
                return all_ads, reason

            all_ads.extend(ads)
            effective_max_pages = min(max_pages, max_pages_limit) if max_pages_limit is not None else max_pages

            if page_num >= effective_max_pages:
                break
            page_num += 1
            self._human_pause(1.5, 4.0)  # pause entre deux pages, pas d'enchaînement mécanique

        self._human_pause(1.0, 3.0)  # temps de présence variable sur la page avant de repartir
        return all_ads, None  # onglet laissé ouvert — réutilisé au prochain appel, fermé seulement via close_session()
