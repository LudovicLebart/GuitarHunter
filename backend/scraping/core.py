import time
import random
import urllib.parse
import logging
import re
from typing import Dict, Any
from playwright.sync_api import sync_playwright, Page

# --- AJOUT : Importation de la configuration des proxies ---
import sys
import os
# Ajout du chemin racine au sys.path pour permettre l'import de config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
try:
    from config import PROXIES
except ImportError:
    PROXIES = []
# --- FIN AJOUT ---

from .config import ScraperConfig
from .parser import ListingParser

class FacebookScraper:
    def __init__(self, city_coordinates, city_mapping, allowed_cities=None, config: ScraperConfig = None, logger: logging.Logger = None):
        self.city_coordinates = city_coordinates
        self.city_mapping = city_mapping
        # allowed_cities est supposé contenir des noms de villes déjà normalisés
        self.allowed_cities = set(allowed_cities) if allowed_cities else set()
        self.config = config or ScraperConfig()
        # Logger par-utilisateur (Firestore/LogViewer) injecté par bot.py ; repli sur le
        # logger de module pour les scripts autonomes (migrate_images.py, tests, etc.)
        self.logger = logger or logging.getLogger(__name__)

        self.playwright = None
        self.browser = None
        self.context = None

        # --- STEALTH: Randomization Arrays ---
        self._user_agents = [
            # Chrome Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            # Edge Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
            # Firefox Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            # Chrome macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            # Safari macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15"
        ]
        
        self._viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
            {"width": 2560, "height": 1440}
        ]

    def start_session(self):
        """Démarre la session Playwright et le navigateur."""
        if self.browser: return

        self.logger.info("Démarrage de la session Playwright...")
        self.playwright = sync_playwright().start()
        
        # Args for stealth
        launch_args = [
            "--start-minimized",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox"
        ]

        # --- AJOUT : Logique de rotation de proxy ---
        proxy_config = None
        if PROXIES:
            selected_proxy = random.choice(PROXIES)
            self.logger.info(f"🌐 Utilisation du proxy : {selected_proxy}")
            proxy_config = {"server": selected_proxy}
        # --- FIN AJOUT ---
        
        self.browser = self.playwright.chromium.launch(
            headless=self.config.headless,
            args=launch_args,
            proxy=proxy_config  # Ajout de la configuration du proxy ici
        )
        
        # Pick random UA and Viewport
        ua = random.choice(self._user_agents)
        vp = random.choice(self._viewports)
        self.logger.debug(f"Stealth Init -> UA: {ua[:40]}..., VP: {vp['width']}x{vp['height']}")

        self.context = self.browser.new_context(
            viewport=vp,
            user_agent=ua,
            locale=self.config.locale,
            timezone_id=self.config.timezone,
            geolocation=self.config.geolocation,
            permissions=["geolocation"],
            extra_http_headers={"Referer": "https://www.google.com/"}
        )

    def get_city_id_and_coords(self, city_name: str):
        """
        Recherche une ville sur Facebook Marketplace pour obtenir son ID interne.
        Retourne un tuple (city_id, coords) où :
        - city_id (str|None) : l'ID numérique Facebook extrait de l'URL.
        - coords (None) : les coordonnées GPS ne sont pas extraites ici.
          Le fallback Nominatim est géré en amont dans bot.py (_geocode_nominatim).
        """
        city_id = None
        coords = None  # Intentionnellement None : géocodage délégué à Nominatim dans bot.py
        page = None    # Initialisé à None pour sécuriser le bloc finally

        try:
            self._ensure_session()
            page = self.context.new_page()

            # 1. Navigation vers Marketplace
            page.goto("https://www.facebook.com/marketplace/", timeout=30000)
            self._close_login_popup(page)
            
            # 2. Ouvrir le sélecteur de lieu
            # Sélecteur typique : le texte de la ville actuelle à gauche
            location_button = page.locator("div[role='button']").filter(has_text="·").first
            if location_button.count() == 0:
                 # Fallback : chercher par texte "Lieu" ou icône Map
                 location_button = page.locator("div[role='main']").locator("div[role='button']").first
            
            location_button.click()
            time.sleep(2)
            
            # 3. Taper le nom de la ville
            # L'input est souvent un champ de recherche avec un label "Lieu" ou "Location"
            input_selector = "input[aria-label='Lieu'], input[aria-label='Location'], input[placeholder='Rechercher un lieu']"
            search_input = page.locator(input_selector).first
            search_input.fill(city_name)
            time.sleep(2)
            
            # 4. Sélectionner la première suggestion
            # Les suggestions sont dans une liste de résultats
            first_suggestion = page.locator("ul[role='listbox'] li, div[role='option']").first
            if first_suggestion.count() > 0:
                first_suggestion.click()
                time.sleep(1)
                
                # 5. Cliquer sur le bouton "Appliquer" (Apply)
                apply_button = page.locator("div[role='button']").filter(has_text="Appliquer").first
                if apply_button.count() == 0:
                    apply_button = page.locator("div[role='button']").filter(has_text="Apply").first
                
                if apply_button.count() > 0:
                    apply_button.click()
                    # Attendre que l'URL change ou que la page se recharge
                    page.wait_for_load_state("networkidle", timeout=10000)
                    time.sleep(2)
                    
                    # 6. Extraire l'ID de l'URL
                    # L'URL devient https://www.facebook.com/marketplace/CITY_ID/
                    current_url = page.url
                    match = re.search(r'/marketplace/(\d+)/', current_url)
                    if match:
                        city_id = match.group(1)
                        self.logger.info(f"✅ ID Facebook trouvé pour '{city_name}': {city_id}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche de ville FB: {e}")
        finally:
            if page:
                page.close()
            
        return city_id, coords

    def close_session(self):
        """Ferme proprement la session Playwright."""
        if self.context:
            self.context.close()
            self.context = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        self.logger.info("Session Playwright fermée.")

    def _ensure_session(self):
        if not self.context: self.start_session()

    def _close_login_popup(self, page: Page):
        try:
            time.sleep(1)
            close_btn = page.locator("div[aria-label='Fermer'], div[aria-label='Close'], div[role='button'][aria-label*='Fermer']").first
            if close_btn.count() > 0 and close_btn.is_visible(timeout=2000):
                close_btn.click()
                time.sleep(1)
        except Exception as e:
            self.logger.debug(f"Popup de login introuvable ou erreur: {e}")

    def _is_valid_detail_page(self, page: Page, expected_fb_id: str) -> bool:
        """Vérifie que la page chargée est bien la fiche détail de l'annonce attendue
        (et non le feed/accueil Marketplace suite à une redirection anti-bot)."""
        if "/login" in page.url or "captcha" in page.url.lower():
            self.logger.warning(f"🚨 Page détail invalide (redirection login/captcha): {page.url}")
            return False
        if f"/marketplace/item/{expected_fb_id}" not in page.url:
            self.logger.warning(f"⚠️ Page détail invalide (URL inattendue, feed probable): {page.url}")
            return False
        return True

    def _extract_scan_url_fields(self, page: Page):
        """Extrait titre/prix/localisation depuis la fiche détail (chemin scan_specific_url)."""
        title = "Titre Inconnu"
        price = 0
        location = "Inconnue"
        try:
            og_title = page.locator('meta[property="og:title"]').get_attribute('content')
            if og_title: title = og_title.split(' - ')[0]

            # --- LOGIQUE DE PRIX POUR SCAN_URL (CENTRALISÉE) ---
            # On essaie de trouver le prix dans le texte visible
            p_txt = page.locator('div[role="main"] span', has_text="$").first.inner_text()

            # Utilisation de la méthode centralisée et robuste
            price = ListingParser.extract_price_from_text(p_txt)

            l_txt = page.locator('div[role="main"] span', has_text="·").first.inner_text()
            location = l_txt.split('·')[0].strip()
        except Exception as e:
            self.logger.debug(f"Erreur extraction champs scan_url: {e}")
        return title, price, location

    def _reload_page(self, page: Page):
        """Recharge la page courante et attend qu'elle soit stabilisée (même séquence
        que le chargement initial : fermeture popup, attente du conteneur principal, pause)."""
        page.reload(timeout=self.config.timeout_navigation)
        self._close_login_popup(page)
        try: page.wait_for_selector("div[role='main']", timeout=self.config.timeout_selector)
        except Exception as e:
            self.logger.debug(f"Timeout attente div[role='main']: {e}")
        time.sleep(2)

    def _parse_details_with_reload_retry(self, page: Page, title: str, location: str, fb_id: str) -> Dict[str, Any]:
        """Parse la fiche détail ; si aucune image n'est extraite (signal fiable d'échec —
        contrairement à l'absence de carrousel, qui est aussi le cas normal d'une annonce à
        une seule photo), tente un reload puis une ré-extraction unique, et ne garde le
        résultat du reload que s'il apporte strictement plus d'images."""
        details = ListingParser.parse_details_page(page, title, location, fb_id, logger=self.logger)

        if not details['imageUrls']:
            self.logger.warning(f"   ⚠️ [DIAG] 0 image extraite pour '{title}' (fb_id={fb_id}) — tentative de reload. URL: {page.url}")
            try:
                debug_path = f"debug_no_image_{fb_id or int(time.time())}.png"
                page.screenshot(path=debug_path)
                self.logger.warning(f"   ⚠️ [DIAG] Capture enregistrée: {debug_path}")
            except Exception as e:
                self.logger.debug(f"Erreur capture diagnostic: {e}")

            try:
                self._reload_page(page)
                if self._is_valid_detail_page(page, fb_id):
                    retry_details = ListingParser.parse_details_page(page, title, location, fb_id, logger=self.logger)
                    self.logger.info(f"   🔁 [DIAG] Après reload: {len(retry_details['imageUrls'])} image(s) (avant: 0).")
                    if len(retry_details['imageUrls']) > len(details['imageUrls']):
                        details = retry_details
            except Exception as e:
                self.logger.warning(f"   ⚠️ Erreur reload diagnostic: {e}")

        return details

    def _apply_filters(self, page: Page, min_price: int, max_price: int):
        # Prix
        try:
            self.logger.info(f"   💰 Application des prix : {min_price}$ - {max_price}$")
            
            if min_price > 0:
                min_input = page.locator("input[aria-label='Prix minimum'], input[aria-label='Minimum price'], input[placeholder='Min'], input[placeholder='Min.']").first
                if min_input.is_visible(timeout=3000):
                    min_input.click()
                    time.sleep(0.5)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    time.sleep(0.2)
                    for digit in str(min_price):
                        page.keyboard.type(digit)
                        time.sleep(0.1)
                    time.sleep(0.5)

            max_input = page.locator("input[aria-label='Prix maximum'], input[aria-label='Maximum price'], input[placeholder='Max'], input[placeholder='Max.']").first
            
            if max_input.is_visible(timeout=3000):
                max_input.click()
                time.sleep(0.5)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                time.sleep(0.2)
                
                for digit in str(max_price):
                    page.keyboard.type(digit)
                    time.sleep(0.1)
                
                time.sleep(0.5)
                page.keyboard.press("Enter")
                self.logger.info("   ✅ Prix appliqués. Attente du rechargement...")
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(3)
            else:
                self.logger.warning("   ⚠️ Champ 'Prix maximum' introuvable.")
        except Exception as e:
            self.logger.warning(f"Erreur filtre prix: {e}")

    def is_city_allowed(self, city_name):
        """Vérifie si une ville est dans la liste blanche (insensible à la casse/accents)."""
        if not city_name: return False
        
        norm_name = ListingParser.normalize_city_name(city_name)
        
        # Vérification directe dans le set (O(1)) car self.allowed_cities contient déjà des noms normalisés
        if norm_name in self.allowed_cities:
            return True
            
        # Fallback : vérification partielle si nécessaire (ex: "Montreal-Nord" vs "Montreal")
        # Mais attention aux faux positifs. Pour l'instant, on reste strict.
        
        # Log pour debug si la ville est rejetée
        self.logger.debug(f"Ville rejetée: '{city_name}' (normalisé: '{norm_name}')")
        return False

    def _scan_result(self, deals=None, anti_bot_blocked=False, rejected_out_of_list=0, total_cards_seen=0):
        """Forme standard retournée par scan_marketplace() à chaque point de sortie,
        pour permettre à run_scan() de comptabiliser les échecs (pas seulement les deals trouvés)."""
        return {
            "deals": deals or [],
            "anti_bot_blocked": anti_bot_blocked,
            "rejected_out_of_list": rejected_out_of_list,
            "total_cards_seen": total_cards_seen,
        }

    def scan_marketplace(self, scan_config, should_skip_callback=None, stop_event=None):
        self._ensure_session()

        # Mise à jour de allowed_cities si passé dans la config (optionnel, mais utile si dynamique)
        if hasattr(self, 'allowed_cities') and isinstance(self.allowed_cities, list):
             self.allowed_cities = set(self.allowed_cities)

        search_query = scan_config['search_query']
        location = scan_config['location']
        min_price = scan_config['min_price']
        max_price = scan_config['max_price']
        max_ads = scan_config['max_ads']

        self.logger.info(f"\n🌍 Scan Facebook: '{search_query}' @ {location}...")

        if stop_event and stop_event.is_set():
            self.logger.info("🛑 Scan annulé avant de démarrer (STOP_BOT).")
            return self._scan_result()

        norm_loc = ListingParser.normalize_city_name(location)
        city_id = self.city_mapping.get(norm_loc)
        if not city_id:
            if location.isdigit(): city_id = location
            else:
                self.logger.error(f"❌ Ville '{location}' inconnue.")
                return self._scan_result()

        # --- Forcer la géolocalisation pour éviter les annonces "Ship to you" basées sur l'IP ---
        coords = self.city_coordinates.get(norm_loc)
        if coords:
            try:
                self.context.set_geolocation({"latitude": coords['lat'], "longitude": coords['lng']})
                self.logger.info(f"   📍 Géolocalisation forcée sur {norm_loc} ({coords['lat']}, {coords['lng']})")
            except Exception as e:
                self.logger.debug(f"   ⚠️ Impossible de forcer la géolocalisation: {e}")

        page = self.context.new_page()
        found_deals = [] # Liste pour stocker les annonces trouvées
        rejected_out_of_list = 0
        listings_count = 0

        try:
            q = urllib.parse.quote(search_query)
            url = f"https://www.facebook.com/marketplace/{city_id}/search/?minPrice={min_price}&query={q}&exact=false"
            if max_price > 0:
                 url = f"https://www.facebook.com/marketplace/{city_id}/search/?minPrice={min_price}&maxPrice={max_price}&query={q}&exact=false"

            self.logger.info(f"   ➡️ Navigation: {url}")
            page.goto(url, timeout=self.config.timeout_navigation)
            
            # --- ANTIBOT: Check for Captcha / Login redirect ---
            if "/login" in page.url or "captcha" in page.url.lower():
                self.logger.error(f"🚨 BLOCAGE ANTI-BOT DÉTECTÉ sur le scan principal (Redirection {page.url}).")
                return self._scan_result(anti_bot_blocked=True)

            try: page.evaluate("document.body.style.zoom = '0.5'")
            except Exception as e: self.logger.debug(f"Zoom échoué: {e}")
            
            try: page.get_by_role("button", name="Allow all cookies").click(timeout=3000)
            except Exception as e: self.logger.debug(f"Bouton cookies 'Allow all' non cliqué: {e}")
            try: page.get_by_role("button", name="Decline optional cookies").click(timeout=3000)
            except Exception as e: self.logger.debug(f"Bouton cookies 'Decline' non cliqué: {e}")
            self._close_login_popup(page)
            self._apply_filters(page, min_price, max_price)

            self.logger.info("   📜 Défilement dynamique...")
            previous_count = 0
            stagnant_iterations = 0
            target_ads_to_load = max_ads * 3 + 30  # Marge de sécurité pour survivre au filtrage (ville/prix)
            for i in range(self.config.max_scroll_iterations):
                if stop_event and stop_event.is_set():
                    self.logger.info("🛑 Scan annulé pendant le défilement (STOP_BOT).")
                    return self._scan_result()
                page.mouse.wheel(0, 1000)
                time.sleep(2)

                current_count = len(page.locator("a[href*='/marketplace/item/']").all())
                if current_count >= target_ads_to_load:
                    self.logger.info(f"   📜 {current_count} annonces chargées (≥ cible de {target_ads_to_load}), arrêt du défilement.")
                    break
                if current_count <= previous_count:
                    stagnant_iterations += 1
                    if stagnant_iterations >= 2:
                        self.logger.info(f"   📜 Défilement stabilisé à {current_count} annonces après {i + 1} itération(s).")
                        break
                else:
                    stagnant_iterations = 0
                previous_count = current_count

            listings = page.locator("a[href*='/marketplace/item/']").all()
            listings_count = len(listings)
            self.logger.info(f"   👀 {listings_count} éléments trouvés.")

            count = 0
            seen = set()

            for link in listings:
                if count >= max_ads: break

                if stop_event and stop_event.is_set():
                    self.logger.info("🛑 Scan annulé pendant le traitement des annonces (STOP_BOT).")
                    return self._scan_result(found_deals, rejected_out_of_list=rejected_out_of_list, total_cards_seen=listings_count)
                
                href = link.get_attribute("href")
                if not href: continue
                full_link = f"https://www.facebook.com{href}" if href.startswith("/") else href
                clean_link = full_link.split('?')[0]
                
                if clean_link in seen: continue
                seen.add(clean_link)
                
                fb_id = ListingParser.extract_facebook_id(clean_link)
                if not fb_id: continue

                card_info = ListingParser.parse_listing_card(link, location, logger=self.logger)
                
                # --- NEW, STRICT FILTERING LOGIC ---
                spec_loc = card_info['location']
                
                # Si la localisation n'a pas pu être extraite, on ignore l'annonce par sécurité
                if not spec_loc:
                    self.logger.debug(f"   ⏩ Ignoré (localisation introuvable sur la carte)")
                    continue

                if not self.is_city_allowed(spec_loc):
                    self.logger.info(f"   ⏩ Ignoré (ville non autorisée): {spec_loc}")
                    rejected_out_of_list += 1
                    continue
                # --- END OF NEW LOGIC ---

                title = card_info['title']
                price = card_info['price']
                img_url = card_info['imageUrl']

                # --- OPTIMIZATION: Check if we should skip this deal ---
                if should_skip_callback and should_skip_callback(fb_id, price):
                    self.logger.info(f"   ⏩ Ignoré (déjà traité et inchangé): {title}")
                    continue
                # --- END OPTIMIZATION ---

                if price > 0 or "Gratuit" in title or "Free" in title:
                    self.logger.info(f"   ✨ Trouvé: {title} ({price}$) dans {spec_loc}")
                    
                    details_page = self.context.new_page()
                    try:
                        details_page.goto(clean_link, timeout=self.config.timeout_navigation)
                        self._close_login_popup(details_page)
                        try: details_page.wait_for_selector("div[role='main']", timeout=10000)
                        except Exception as e:
                            self.logger.debug(f"Timeout fiche détail div[role='main']: {e}")
                        time.sleep(2)
                        self.logger.debug(f"   🔎 [DIAG] URL fiche détail chargée: {details_page.url}")

                        if self._is_valid_detail_page(details_page, fb_id):
                            details = self._parse_details_with_reload_retry(details_page, title, location, fb_id)
                        else:
                            self.logger.warning(f"   ⚠️ Fiche détail non chargée pour '{title}' — repli sur l'image de la carte uniquement.")
                            details = {"description": f"Annonce Marketplace. {title}. Localisation: {location}", "imageUrls": [], "coordinates": None, "published_at_raw": None}
                    finally:
                        details_page.close()

                    coords = details['coordinates']
                    final_img = details['imageUrls'][0] if details['imageUrls'] else img_url
                    
                    listing_data = {
                        "title": title, "price": price, "description": details['description'],
                        "imageUrl": final_img, "imageUrls": details['imageUrls'],
                        "link": clean_link, "location": spec_loc,
                        "id": fb_id, "published_at_raw": details.get('published_at_raw'),
                        "published_at_ts": details.get('published_at_ts')
                    }
                    if coords:
                        self.logger.info(f"   📍 Coordonnées GPS trouvées: {coords}")
                        listing_data["latitude"] = coords["lat"]
                        listing_data["longitude"] = coords["lng"]
                    else:
                        self.logger.info("   ⚠️ Pas de coordonnées GPS trouvées.")
                    
                    found_deals.append(listing_data) # Ajout à la liste
                    count += 1
        except Exception as e:
            self.logger.error(f"❌ Erreur scan: {e}", exc_info=True)
        finally:
            page.close()
        return self._scan_result(found_deals, rejected_out_of_list=rejected_out_of_list, total_cards_seen=listings_count)

    def scan_specific_url(self, url, on_deal_found):
        self._ensure_session()
        
        self.logger.info(f"\n🔗 Scan URL: {url}")
        fb_id = ListingParser.extract_facebook_id(url)
        
        page = self.context.new_page()
        try:
            page.goto(url, timeout=self.config.timeout_navigation)
            
            if not fb_id:
                fb_id = ListingParser.extract_facebook_id(page.url)
            
            if not fb_id:
                self.logger.error("❌ ID introuvable.")
                return

            # --- ANTIBOT: Check for Captcha / Login redirect ---
            if "/login" in page.url or "captcha" in page.url.lower():
                self.logger.error(f"🚨 BLOCAGE ANTI-BOT DÉTECTÉ (Redirection {page.url}). Session compromise.")
                return

            self._close_login_popup(page)
            try: page.wait_for_selector("div[role='main']", timeout=self.config.timeout_selector)
            except Exception as e:
                self.logger.debug(f"Timeout fiche détail scan_url div[role='main']: {e}")
            time.sleep(2)
            self.logger.debug(f"   🔎 [DIAG] URL fiche détail chargée: {page.url}")

            if not self._is_valid_detail_page(page, fb_id):
                self.logger.error(f"❌ Fiche détail non chargée correctement pour {url} — annonce ignorée.")
                return

            title, price, location = self._extract_scan_url_fields(page)
            details = ListingParser.parse_details_page(page, title, location, fb_id, logger=self.logger)

            if not details['imageUrls']:
                self.logger.warning(f"   ⚠️ [DIAG] 0 image extraite pour fb_id={fb_id} (scan_url) — tentative de reload. URL: {page.url}")
                try:
                    debug_path = f"debug_no_image_{fb_id or int(time.time())}.png"
                    page.screenshot(path=debug_path)
                    self.logger.warning(f"   ⚠️ [DIAG] Capture enregistrée: {debug_path}")
                except Exception as e:
                    self.logger.debug(f"Erreur capture diagnostic: {e}")

                try:
                    self._reload_page(page)
                    if self._is_valid_detail_page(page, fb_id):
                        retry_title, retry_price, retry_location = self._extract_scan_url_fields(page)
                        retry_details = ListingParser.parse_details_page(page, retry_title, retry_location, fb_id, logger=self.logger)
                        self.logger.info(f"   🔁 [DIAG] Après reload: {len(retry_details['imageUrls'])} image(s) (avant: 0).")
                        if len(retry_details['imageUrls']) > len(details['imageUrls']):
                            title, price, location, details = retry_title, retry_price, retry_location, retry_details
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Erreur reload diagnostic: {e}")

            clean_link = page.url.split('?')[0]
            
            listing_data = {
                "title": title, "price": price, "description": details['description'],
                "imageUrl": details['imageUrls'][0] if details['imageUrls'] else "",
                "imageUrls": details['imageUrls'],
                "link": clean_link, "location": location,
                "searchDistance": 0, "id": fb_id,
                "published_at_raw": details.get('published_at_raw'),
                "published_at_ts": details.get('published_at_ts')
            }
            if details['coordinates']:
                listing_data["latitude"] = details['coordinates']["lat"]
                listing_data["longitude"] = details['coordinates']["lng"]

            on_deal_found(listing_data)
            self.logger.info(f"✅ Scan URL terminé: {title}")

        except Exception as e:
            self.logger.error(f"❌ Erreur scan URL: {e}", exc_info=True)
        finally:
            page.close()

    def check_listing_availability(self, url):
        self._ensure_session()
        is_available = True
        page = self.context.new_page()
        try:
            # On retire les paramètres de tracking pour la vérification de l'URL brute
            clean_url = url.split('?')[0]
            self.logger.info(f"   🔍 Vérification disponibilité: {clean_url}")
            
            # Augmentation du timeout pour la navigation
            response = page.goto(clean_url, timeout=30000, wait_until="domcontentloaded")
            
            # 1. Vérification du code HTTP (si Facebook renvoie 404/410)
            if response and response.status in [404, 410]:
                self.logger.info(f"   🚫 Annonce supprimée (HTTP {response.status})")
                return False

            # 2. Vérification des redirections
            # Facebook redirige vers /marketplace/ (accueil) quand l'item est totalement supprimé
            if "/marketplace/item/" not in page.url:
                self.logger.info(f"   🚫 Redirection détectée (URL actuelle: {page.url}) - Annonce supprimée.")
                return False

            import json
            # 4. Recherche des marqueurs d'indisponibilité (Regex + Case-Insensitive)
            # On cherche dans le texte visible et les attributs ARIA (plus stables)
            
            # Utilisation de frontières de mots (\b) pour éviter les faux positifs 
            # ex: "soldering iron" ne doit pas matcher "sold"
            # ex: "revendu" ne doit pas matcher "^vendu$"
            unavailable_patterns = [
                r"annonce n.est plus disponible",
                r"listing is no longer available",
                r"^(?:est )?vendu\s*!?$",       # Strict: "vendu", "est vendu", "vendu!"
                r"^(?:is )?sold\s*!?$",         # Strict: "sold", "is sold", "sold!"
                r"plus disponible",
                r"out of stock",
                r"^expired$",
                r"^expirée$"
            ]
            
            # Sécurisation du passage des patterns Python vers JS
            patterns_json = json.dumps(unavailable_patterns)
            
            # Injection des patterns dans l'évaluation JS avec vérification stricte de visibilité
            found_marker = page.evaluate(f"""() => {{
                const patterns = {patterns_json}.map(p => new RegExp(p, 'i'));
                
                // On limite la recherche aux éléments qui sont typiquement des badges ou statuts (pas la description entière)
                const elements = document.querySelectorAll('span, div[role="button"], h1, h2');
                for (const el of elements) {{
                    const text = el.innerText.trim();
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    
                    if (!text && !ariaLabel) continue;

                    // Vérification de visibilité réelle (display: none, visibility: hidden, opacity: 0)
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {{
                        continue;
                    }}

                    // La taille du rectangle peut être 0 si l'élément est dans un conteneur caché
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;

                    for (const regex of patterns) {{
                        if (regex.test(text) || regex.test(ariaLabel)) {{
                            return text || ariaLabel;
                        }}
                    }}
                }}
                return null;
            }}""")

            if found_marker:
                self.logger.info(f"   🚫 Marqueur d'indisponibilité trouvé: '{found_marker}'")
                return False

        except Exception as e:
            self.logger.warning(f"   ⚠️ Erreur durant le check availability: {e}")
            # En cas d'erreur (timeout), on préfère garder l'annonce (optimiste)
            return True
        finally:
            page.close()
        return is_available
