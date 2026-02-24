import time
import urllib.parse
import logging
from playwright.sync_api import sync_playwright, Page

from .config import ScraperConfig
from .parser import ListingParser

logger = logging.getLogger(__name__)

class FacebookScraper:
    def __init__(self, city_coordinates, city_mapping, allowed_cities=None, config: ScraperConfig = None):
        self.city_coordinates = city_coordinates
        self.city_mapping = city_mapping
        # allowed_cities est supposé contenir des noms de villes déjà normalisés
        self.allowed_cities = set(allowed_cities) if allowed_cities else set()
        self.config = config or ScraperConfig()
        
        self.playwright = None
        self.browser = None
        self.context = None

    def start_session(self):
        """Démarre la session Playwright et le navigateur."""
        if self.browser: return

        logger.info("Démarrage de la session Playwright...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.config.headless,
            args=["--start-minimized"]
        )
        self.context = self.browser.new_context(
            viewport=None,
            user_agent=self.config.user_agent,
            locale=self.config.locale,
            timezone_id=self.config.timezone,
            geolocation=self.config.geolocation,
            permissions=["geolocation"],
            extra_http_headers={"Referer": "https://www.google.com/"}
        )

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
        logger.info("Session Playwright fermée.")

    def _ensure_session(self):
        if not self.context: self.start_session()

    def _close_login_popup(self, page: Page):
        try:
            time.sleep(1)
            close_btn = page.locator("div[aria-label='Fermer'], div[aria-label='Close'], div[role='button'][aria-label*='Fermer']").first
            if close_btn.count() > 0 and close_btn.is_visible(timeout=2000):
                close_btn.click()
                time.sleep(1)
        except: pass

    def _apply_filters(self, page: Page, min_price: int, max_price: int):
        # Prix
        try:
            logger.info(f"   💰 Application des prix : {min_price}$ - {max_price}$")
            
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
                logger.info("   ✅ Prix appliqués. Attente du rechargement...")
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(3)
            else:
                logger.warning("   ⚠️ Champ 'Prix maximum' introuvable.")
        except Exception as e:
            logger.warning(f"Erreur filtre prix: {e}")

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
        logger.debug(f"Ville rejetée: '{city_name}' (normalisé: '{norm_name}')")
        return False

    def scan_marketplace(self, scan_config, on_deal_found, should_skip_callback=None, stop_event=None):
        self._ensure_session()
        
        # Mise à jour de allowed_cities si passé dans la config (optionnel, mais utile si dynamique)
        if hasattr(self, 'allowed_cities') and isinstance(self.allowed_cities, list):
             self.allowed_cities = set(self.allowed_cities)

        search_query = scan_config['search_query']
        location = scan_config['location']
        min_price = scan_config['min_price']
        max_price = scan_config['max_price']
        max_ads = scan_config['max_ads']

        logger.info(f"\n🌍 Scan Facebook: '{search_query}' @ {location}...")
        
        if stop_event and stop_event.is_set():
            logger.info("🛑 Scan annulé avant de démarrer (STOP_BOT).")
            return
            
        norm_loc = ListingParser.normalize_city_name(location)
        city_id = self.city_mapping.get(norm_loc)
        if not city_id:
            if location.isdigit(): city_id = location
            else:
                logger.error(f"❌ Ville '{location}' inconnue.")
                return

        page = self.context.new_page()
        
        try:
            q = urllib.parse.quote(search_query)
            url = f"https://www.facebook.com/marketplace/{city_id}/search/?minPrice={min_price}&query={q}&exact=false"
            if max_price > 0:
                 url = f"https://www.facebook.com/marketplace/{city_id}/search/?minPrice={min_price}&maxPrice={max_price}&query={q}&exact=false"

            logger.info(f"   ➡️ Navigation: {url}")
            page.goto(url, timeout=self.config.timeout_navigation)
            try: page.evaluate("document.body.style.zoom = '0.5'")
            except: pass
            
            try: page.get_by_role("button", name="Allow all cookies").click(timeout=3000)
            except: pass
            try: page.get_by_role("button", name="Decline optional cookies").click(timeout=3000)
            except: pass
            self._close_login_popup(page)
            self._apply_filters(page, min_price, max_price)

            logger.info("   📜 Défilement...")
            for _ in range(self.config.scroll_iterations):
                if stop_event and stop_event.is_set():
                    logger.info("🛑 Scan annulé pendant le défilement (STOP_BOT).")
                    return
                page.mouse.wheel(0, 1000)
                time.sleep(2)

            listings = page.locator("a[href*='/marketplace/item/']").all()
            logger.info(f"   👀 {len(listings)} éléments trouvés.")
            
            count = 0
            seen = set()
            
            for link in listings:
                if count >= max_ads: break
                
                if stop_event and stop_event.is_set():
                    logger.info("🛑 Scan annulé pendant le traitement des annonces (STOP_BOT).")
                    return
                
                href = link.get_attribute("href")
                if not href: continue
                full_link = f"https://www.facebook.com{href}" if href.startswith("/") else href
                clean_link = full_link.split('?')[0]
                
                if clean_link in seen: continue
                seen.add(clean_link)
                
                fb_id = ListingParser.extract_facebook_id(clean_link)
                if not fb_id: continue

                card_info = ListingParser.parse_listing_card(link, location)
                
                # --- NEW, STRICT FILTERING LOGIC ---
                spec_loc = card_info['location']
                
                # Si la localisation n'a pas pu être extraite, on ignore l'annonce par sécurité
                if not spec_loc:
                    logger.debug(f"   ⏩ Ignoré (localisation introuvable sur la carte)")
                    continue

                if not self.is_city_allowed(spec_loc):
                    logger.info(f"   ⏩ Ignoré (ville non autorisée): {spec_loc}")
                    continue
                # --- END OF NEW LOGIC ---

                title = card_info['title']
                price = card_info['price']
                img_url = card_info['imageUrl']

                # --- OPTIMIZATION: Check if we should skip this deal ---
                if should_skip_callback and should_skip_callback(fb_id, price):
                    logger.info(f"   ⏩ Ignoré (déjà traité et inchangé): {title}")
                    continue
                # --- END OPTIMIZATION ---

                if price > 0 or "Gratuit" in title or "Free" in title:
                    logger.info(f"   ✨ Trouvé: {title} ({price}$) dans {spec_loc}")
                    
                    details_page = self.context.new_page()
                    try:
                        details_page.goto(clean_link, timeout=self.config.timeout_navigation)
                        self._close_login_popup(details_page)
                        try: details_page.wait_for_selector("div[role='main']", timeout=10000)
                        except: pass
                        time.sleep(2)
                        
                        details = ListingParser.parse_details_page(details_page, title, location)
                    finally:
                        details_page.close()
                    
                    coords = details['coordinates']
                    final_img = details['imageUrls'][0] if details['imageUrls'] else img_url
                    
                    listing_data = {
                        "title": title, "price": price, "description": details['description'],
                        "imageUrl": final_img, "imageUrls": details['imageUrls'],
                        "link": clean_link, "location": spec_loc,
                        "id": fb_id
                    }
                    if coords:
                        logger.info(f"   📍 Coordonnées GPS trouvées: {coords}")
                        listing_data["latitude"] = coords["lat"]
                        listing_data["longitude"] = coords["lng"]
                    else:
                        logger.info("   ⚠️ Pas de coordonnées GPS trouvées.")
                    
                    on_deal_found(listing_data)
                    count += 1

        except Exception as e:
            logger.error(f"❌ Erreur scan: {e}", exc_info=True)
        finally:
            page.close()

    def scan_specific_url(self, url, on_deal_found):
        self._ensure_session()
        
        logger.info(f"\n🔗 Scan URL: {url}")
        fb_id = ListingParser.extract_facebook_id(url)
        
        page = self.context.new_page()
        try:
            page.goto(url, timeout=self.config.timeout_navigation)
            
            if not fb_id:
                fb_id = ListingParser.extract_facebook_id(page.url)
            
            if not fb_id:
                logger.error("❌ ID introuvable.")
                return

            self._close_login_popup(page)
            try: page.wait_for_selector("div[role='main']", timeout=self.config.timeout_selector)
            except: pass
            time.sleep(2)

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
            except: pass

            clean_link = page.url.split('?')[0]
            details = ListingParser.parse_details_page(page, title, location)
            
            listing_data = {
                "title": title, "price": price, "description": details['description'],
                "imageUrl": details['imageUrls'][0] if details['imageUrls'] else "",
                "imageUrls": details['imageUrls'],
                "link": clean_link, "location": location,
                "searchDistance": 0, "id": fb_id
            }
            if details['coordinates']:
                listing_data["latitude"] = details['coordinates']["lat"]
                listing_data["longitude"] = details['coordinates']["lng"]

            on_deal_found(listing_data)
            logger.info(f"✅ Scan URL terminé: {title}")

        except Exception as e:
            logger.error(f"❌ Erreur scan URL: {e}", exc_info=True)
        finally:
            page.close()

    def check_listing_availability(self, url):
        self._ensure_session()
        is_available = True
        page = self.context.new_page()
        try:
            # On retire les paramètres de tracking pour la vérification de l'URL brute
            clean_url = url.split('?')[0]
            logger.info(f"   🔍 Vérification disponibilité: {clean_url}")
            
            # Augmentation du timeout pour la navigation
            response = page.goto(clean_url, timeout=30000, wait_until="domcontentloaded")
            
            # 1. Vérification du code HTTP (si Facebook renvoie 404/410)
            if response and response.status in [404, 410]:
                logger.info(f"   🚫 Annonce supprimée (HTTP {response.status})")
                return False

            # 2. Vérification des redirections
            # Facebook redirige vers /marketplace/ (accueil) quand l'item est totalement supprimé
            if "/marketplace/item/" not in page.url:
                logger.info(f"   🚫 Redirection détectée (URL actuelle: {page.url}) - Annonce supprimée.")
                return False

            # 3. Attente courte pour laisser l'interface se stabiliser
            time.sleep(2)

            # 4. Recherche des marqueurs textuels "Sold" / "Vendu"
            # On cherche dans le conteneur principal et spécifiquement les spans
            
            unavailable_markers = [
                'Cette annonce n’est plus disponible',
                'This listing is no longer available',
                'Vendu',
                'Sold'
            ]
            
            # On utilise une évaluation JS pour chercher le texte exact dans les éléments visibles
            # C'est plus robuste que les sélecteurs CSS qui peuvent changer
            found_marker = page.evaluate(f"""() => {{
                const markers = {unavailable_markers};
                const elements = document.querySelectorAll('span, div[role="button"], div[role="main"] div');
                for (const el of elements) {{
                    const text = el.innerText.trim();
                    if (markers.includes(text)) {{
                        // Vérifie si l'élément est vraiment visible
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return text;
                    }}
                }}
                return null;
            }}""")

            if found_marker:
                logger.info(f"   🚫 Marqueur d'indisponibilité trouvé: '{found_marker}'")
                return False

        except Exception as e:
            logger.warning(f"   ⚠️ Erreur durant le check availability: {e}")
            # En cas d'erreur (timeout), on préfère garder l'annonce (optimiste)
            return True
        finally:
            page.close()
        return is_available
