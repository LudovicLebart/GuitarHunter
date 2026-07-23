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
introduit donc : délais non-uniformes (jamais fixes, avec de rares hésitations
plus longues), trajectoires de souris interpolées et scroll par paliers (pas
de téléportation ni de saut brutal), et une session réutilisable sur plusieurs
recherches (pas de fermeture systématique du navigateur après chaque appel).

Toutes ces actions (scroll, survol, ouverture d'annonce, ajout favori) sont
purement décoratives — aucun besoin fonctionnel, les résultats de recherche
sont déjà entièrement disponibles dans le JSON __NEXT_DATA__ dès le chargement
de la page. Leur seul critère est de ressembler à un humain qui parcourt une
liste d'annonces ; elles sont tirées au hasard, pas exécutées systématiquement
dans le même ordre/nombre à chaque page.
"""
import logging
import math
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

# Sélecteurs confirmés sur un vrai résultat de recherche LeBonCoin (voir JOURNAL.md).
AD_CARD_SELECTOR = '[data-qa-id="aditem_container"]'
AD_LINK_SELECTOR = f'{AD_CARD_SELECTOR} a'
SAVE_AD_BUTTON_SELECTOR = '[data-qa-id="listitem_save_ad"]'


class LeboncoinScraper:
    def __init__(self, storage_state_path, logger=None):
        self.storage_state_path = storage_state_path
        self.logger = logger or logging.getLogger(__name__)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None  # onglet réutilisé sur toute la session (pas de nouvel onglet par recherche)
        self._responses = []
        self._mouse_pos = (640, 400)  # position de départ arbitraire, mise à jour à chaque déplacement

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
        """Pause à distribution non-uniforme (asymétrique vers le bas, avec de
        rares hésitations plus longues) plutôt qu'un `random.uniform` plat — une
        signature statistique trop régulière est elle-même détectable dans la
        durée sur de nombreux cycles."""
        if random.random() < 0.12:
            time.sleep(random.uniform(high, high * 2.0))
        else:
            time.sleep(random.triangular(low, high, low))

    def _human_mouse_move(self, page, target_x, target_y):
        """Déplace la souris vers (target_x, target_y) en plusieurs étapes
        intermédiaires (courbe lissée + micro-jitter), au lieu de la
        téléportation instantanée d'un simple `page.mouse.move()`."""
        start_x, start_y = self._mouse_pos
        steps = random.randint(8, 20)
        for i in range(1, steps + 1):
            t = i / steps
            eased = t * t * (3 - 2 * t)  # smoothstep : accélération puis décélération
            jitter_x = random.uniform(-3, 3) if 0 < i < steps else 0
            jitter_y = random.uniform(-3, 3) if 0 < i < steps else 0
            x = start_x + (target_x - start_x) * eased + jitter_x
            y = start_y + (target_y - start_y) * eased + jitter_y
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.008, 0.03))
        self._mouse_pos = (target_x, target_y)

    def _human_scroll(self, page, total_delta):
        """Défile de `total_delta` px (signe = direction) en plusieurs paliers
        suivant une courbe en cloche (accélération puis décélération), au lieu
        d'un seul saut brutal de `page.mouse.wheel()`."""
        steps = random.randint(5, 12)
        weights = [math.sin(math.pi * (i + 0.5) / steps) for i in range(steps)]
        weight_sum = sum(weights)
        remaining = total_delta
        for i, w in enumerate(weights):
            chunk = remaining if i == steps - 1 else round(total_delta * w / weight_sum)
            page.mouse.wheel(0, chunk)
            remaining -= chunk
            self._human_pause(0.05, 0.25)

    def _simulate_browsing(self, page):
        """Actions décoratives (scroll, survol d'une annonce) tirées au hasard,
        pas exécutées systématiquement dans le même ordre/nombre à chaque page."""
        try:
            cards = page.query_selector_all(AD_CARD_SELECTOR)
            possible_actions = ["scroll_down", "scroll_down", "hover_card", "scroll_up", "idle"]
            random.shuffle(possible_actions)
            for action in possible_actions[:random.randint(2, 4)]:
                if action == "scroll_down":
                    self._human_scroll(page, random.randint(300, 900))
                elif action == "scroll_up":
                    self._human_scroll(page, -random.randint(150, 500))
                elif action == "hover_card" and cards:
                    card = random.choice(cards)
                    card.scroll_into_view_if_needed()
                    box = card.bounding_box()
                    if box:
                        self._human_mouse_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        self._human_pause(0.8, 2.5)  # "s'arrête" sur l'annonce
                elif action == "idle":
                    self._human_pause(0.5, 1.5)
        except Exception as e:
            # warning (pas debug) : un échec silencieux ici serait invisible en usage
            # normal (niveau INFO) alors que c'est un signal utile à diagnostiquer.
            self.logger.warning(f"Simulation de navigation échouée (non bloquant) : {e}")

    def _maybe_open_random_ad(self, page, probability=0.25):
        """Ouvre parfois une annonce au hasard (clic réel sur la liste), puis
        revient en arrière — aucune donnée n'est extraite de cette page (tout
        est déjà dans le JSON de la liste), uniquement pour la vraisemblance
        comportementale."""
        if random.random() > probability:
            return
        try:
            links = page.query_selector_all(AD_LINK_SELECTOR)
            if not links:
                return
            link = random.choice(links)
            link.scroll_into_view_if_needed()
            box = link.bounding_box()
            if box:
                self._human_mouse_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            self._human_pause(0.3, 1.0)
            link.click()
            self.logger.info("   👀 Ouverture d'une annonce au hasard (comportement décoratif).")
            self._human_pause(1.5, 4.0)  # dwell sur l'annonce
            self._human_scroll(page, random.randint(200, 600))
            self._human_pause(1.0, 3.0)
            page.go_back(wait_until="domcontentloaded")
            self._human_pause(1.0, 2.5)
        except Exception as e:
            self.logger.warning(f"Ouverture d'annonce aléatoire échouée (non bloquant) : {e}")

    def _maybe_save_random_ad(self, page, probability=0.1):
        """Ajoute parfois une annonce en favori (clic réel sur le bouton cœur de
        la liste — effet de bord réel et persistant sur le compte, accepté pour
        l'instant, pas de retrait automatique)."""
        if random.random() > probability:
            return
        try:
            buttons = page.query_selector_all(SAVE_AD_BUTTON_SELECTOR)
            if not buttons:
                return
            button = random.choice(buttons)
            button.scroll_into_view_if_needed()
            box = button.bounding_box()
            if box:
                self._human_mouse_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            self._human_pause(0.3, 1.0)
            button.click()
            self.logger.info("   ❤️  Annonce ajoutée aux favoris (comportement décoratif).")
        except Exception as e:
            self.logger.warning(f"Ajout aux favoris échoué (non bloquant) : {e}")

    def _maybe_revisit_previous_page(self, page, page_num, probability=0.15):
        """Revient parfois sur la page précédente (navigateur, pas de
        re-extraction) avant de continuer — un humain ne progresse pas toujours
        strictement en avant dans une pagination."""
        if page_num <= 1 or random.random() > probability:
            return
        try:
            self.logger.info("   ↩️  Retour furtif à la page précédente (comportement décoratif).")
            page.go_back(wait_until="domcontentloaded")
            self._human_pause(1.5, 3.5)
            self._simulate_browsing(page)
            page.go_forward(wait_until="domcontentloaded")
            self._human_pause(1.0, 2.0)
        except Exception as e:
            self.logger.warning(f"Retour à la page précédente échoué (non bloquant) : {e}")

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

            # Actions décoratives (après extraction, pour ne jamais risquer de
            # perturber la récupération des données réelles) — aucune ne sert à
            # l'extraction, uniquement à la vraisemblance comportementale.
            self._simulate_browsing(page)
            self._maybe_open_random_ad(page)
            self._maybe_save_random_ad(page)
            self._maybe_revisit_previous_page(page, page_num)

            if page_num >= effective_max_pages:
                break
            page_num += 1
            self._human_pause(1.5, 4.0)  # pause entre deux pages, pas d'enchaînement mécanique

        self._human_pause(1.0, 3.0)  # temps de présence variable sur la page avant de repartir
        return all_ads, None  # onglet laissé ouvert — réutilisé au prochain appel, fermé seulement via close_session()
