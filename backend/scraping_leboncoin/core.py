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
limite pas à un challenge JS ponctuel, il réévalue en continu. Le cycle de
session et le comportement "humain" générique (pauses, souris, scroll, pause
nocturne) vivent dans `backend/scraping_common/` (partagés avec les futurs
modules — Kijiji, Reverb...) ; ce module ne garde que ce qui est propre à
LeBonCoin : construction d'URL, extraction, détection de blocage, et les
actions décoratives spécifiques (ouverture d'annonce, favoris).

Toutes ces actions (scroll, survol, ouverture d'annonce, ajout favori) sont
purement décoratives — aucun besoin fonctionnel, les résultats de recherche
sont déjà entièrement disponibles dans le JSON __NEXT_DATA__ dès le chargement
de la page. Leur seul critère est de ressembler à un humain qui parcourt une
liste d'annonces ; elles sont tirées au hasard, pas exécutées systématiquement
dans le même ordre/nombre à chaque page.
"""
import random
import re
import json
import time
import urllib.parse

from playwright.sync_api import Error as PlaywrightError

from backend.scraping_common import BaseMarketplaceScraper

DATADOME_CHALLENGE_MARKERS = ["captcha-delivery.com"]
SUSPICIOUS_TITLE_KEYWORDS = ["just a moment", "vérification", "attention requise", "access denied", "pardon our interruption"]

# Sélecteurs confirmés sur un vrai résultat de recherche LeBonCoin (voir JOURNAL.md).
AD_CARD_SELECTOR = '[data-qa-id="aditem_container"]'
AD_LINK_SELECTOR = f'{AD_CARD_SELECTOR} a'
SAVE_AD_BUTTON_SELECTOR = '[data-qa-id="listitem_save_ad"]'


class LeboncoinScraper(BaseMarketplaceScraper):
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

    def _read_through_page(self, page, min_dwell_s):
        """Simule la lecture complète d'une page de résultats (une trentaine
        d'annonces) avant de changer de page : reste un temps minimum, puis
        termine par une descente jusqu'en bas de la page — c'est là que se
        trouvent les boutons de pagination, un humain doit physiquement y
        arriver avant de cliquer "page suivante", pas y sauter directement."""
        try:
            started = time.time()
            cards = page.query_selector_all(AD_CARD_SELECTOR)
            while time.time() - started < min_dwell_s:
                action = random.choice(["scroll_down", "hover_card", "idle"])
                if action == "scroll_down":
                    self._human_scroll(page, random.randint(200, 600))
                elif action == "hover_card" and cards:
                    card = random.choice(cards)
                    card.scroll_into_view_if_needed()
                    box = card.bounding_box()
                    if box:
                        self._human_mouse_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        self._human_pause(1.0, 3.0)
                else:
                    self._human_pause(0.5, 2.0)
            # Descente jusqu'aux boutons de pagination, en bas de la liste —
            # largement suffisant pour ~35 annonces, sans excès (un scroll trop
            # massif d'un coup peut forcer le chargement de beaucoup d'images
            # lazy-load en rafale et faire monter la charge mémoire/rendu).
            self._human_scroll(page, random.randint(4000, 8000))
            self._human_pause(0.5, 1.5)
        except Exception as e:
            self.logger.warning(f"Lecture de page échouée (non bloquant) : {e}")

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
               owner_type=None, max_pages_limit=None, known_ids=None):
        """Recherche paginée (jusqu'au max_pages annoncé par LeBonCoin lui-même,
        ou max_pages_limit si fourni et plus restrictif — jamais au-delà, aucune
        page inexistante n'est demandée).

        `known_ids` (optionnel) : ensemble d'identifiants déjà connus (ex: déjà
        en base). Le tri de recherche étant "plus récent d'abord" (sort=time&
        order=desc), dès qu'une page ne contient plus aucune annonce inconnue,
        tout ce qui suit est nécessairement encore plus ancien donc déjà connu
        — la pagination s'arrête alors immédiatement, sans avoir besoin de
        vérifier les pages suivantes.

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
            try:
                page.goto(url, timeout=0, wait_until="domcontentloaded")
            except PlaywrightError as e:
                # Erreur Playwright transitoire (crash du rendu Chromium, navigation
                # interrompue par une autre navigation concurrente — ex: go_back()/
                # go_forward() d'une action décorative pas encore stabilisée, etc.) —
                # une seule nouvelle tentative avant d'abandonner, pour ne pas perdre
                # toute une campagne de test à cause d'un seul incident transitoire.
                # Recréation de l'onglet seulement si c'est un vrai crash du rendu ;
                # sinon une simple pause suffit, le même onglet reste utilisable.
                self.logger.warning(f"⚠️ Navigation échouée, nouvelle tentative : {e}")
                if "crashed" in str(e).lower():
                    self.page = None
                    page = self._get_page()
                else:
                    self._human_pause(1.0, 2.5)
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
            # _read_through_page assure un temps de lecture minimum (une trentaine
            # d'annonces à parcourir) et termine en bas de page, là où se trouvent
            # les boutons de pagination — jamais un saut direct vers la page suivante.
            self._read_through_page(page, min_dwell_s=random.uniform(45, 75))
            self._maybe_open_random_ad(page)
            self._maybe_save_random_ad(page)
            self._maybe_revisit_previous_page(page, page_num)

            if known_ids is not None and ads and all(ad["id"] in known_ids for ad in ads):
                self.logger.info("   ⏹️  Toutes les annonces de cette page sont déjà connues — "
                                  "arrêt de la pagination (tri = plus récent d'abord, la suite est forcément plus ancienne).")
                break

            if page_num >= effective_max_pages:
                break
            page_num += 1
            self._human_pause(1.5, 4.0)  # pause entre deux pages, pas d'enchaînement mécanique

        self._human_pause(1.0, 3.0)  # temps de présence variable sur la page avant de repartir
        return all_ads, None  # onglet laissé ouvert — réutilisé au prochain appel, fermé seulement via close_session()
