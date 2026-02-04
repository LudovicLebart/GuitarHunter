import time
import urllib.parse
import logging
from playwright.sync_api import sync_playwright, Page

from .config import ScraperConfig
from .parser import ListingParser
from .utils import calculate_distance

logger = logging.getLogger(__name__)

class FacebookScraper:
    def __init__(self, city_coordinates, city_mapping, allowed_cities=None, config: ScraperConfig = None):
        self.city_coordinates = city_coordinates
        self.city_mapping = city_mapping
        self.allowed_cities = allowed_cities or []
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

    def _apply_filters(self, page: Page, distance: int, min_price: int, max_price: int):
        # Rayon
        try:
            time.sleep(2)
            loc_btn = page.locator("div[role='button']").filter(has_text="km").first
            if loc_btn.count() > 0 and loc_btn.is_visible():
                loc_btn.click()
                time.sleep(2)
                modal = page.locator("div[role='dialog']").first
                if modal.count() > 0:
                    radius_dropdown = modal.locator("div, span").filter(has_text="kilomètres").last
                    if radius_dropdown.count() == 0: radius_dropdown = modal.locator("div, span").filter(has_text="km").last
                    
                    if radius_dropdown.count() > 0:
                        radius_dropdown.click()
                        try: page.wait_for_selector("div[role='option']", timeout=5000)
                        except: pass
                        
                        options = page.locator("div[role='option']").all()
                        best_opt = None
                        min_diff = float('inf')
                        for opt in [o for o in options if o.is_visible()]:
                            digits = ''.join(filter(str.isdigit, opt.inner_text()))
                            if digits:
                                diff = abs(int(digits) - distance)
                                if diff < min_diff:
                                    min_diff = diff
                                    best_opt = opt
                        
                        if best_opt:
                            best_opt.click()
                            time.sleep(1)
                    
                    apply_btn = modal.locator("div[aria-label*='Appliquer'], div[aria-label*='Apply']").first
                    if apply_btn.count() > 0:
                        apply_btn.click()
                        time.sleep(5)
                    else:
                        page.keyboard.press("Escape")
        except Exception as e:
            logger.warning(f"Erreur filtre rayon: {e}")

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
        for allowed in self.allowed_cities:
            if ListingParser.normalize_city_name(allowed) == norm_name:
                return True
        return False

    def scan_marketplace(self, scan_config, on_deal_found):
        self._ensure_session()
        
        search_query = scan_config['search_query']
        location = scan_config['location']
        distance = scan_config['distance']
        min_price = scan_config['min_price']
        max_price = scan_config['max_price']
        max_ads = scan_config['max_ads']

        logger.info(f"\n🌍 Scan Facebook: '{search_query}' @ {location}...")
        
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
            tmp_max = max_price - 1 if max_price > min_price and max_price > 0 else max_price
            url = f"https://www.facebook.com/marketplace/{city_id}/search/?minPrice={min_price}&maxPrice={tmp_max}&query={q}&exact=false"
            
            logger.info(f"   ➡️ Navigation: {url}")
            page.goto(url, timeout=self.config.timeout_navigation)
            try: page.evaluate("document.body.style.zoom = '0.5'")
            except: pass
            
            try: page.get_by_role("button", name="Allow all cookies").click(timeout=3000)
            except: pass
            try: page.get_by_role("button", name="Decline optional cookies").click(timeout=3000)
            except: pass
            self._close_login_popup(page)
            self._apply_filters(page, distance, min_price, max_price)

            logger.info("   📜 Défilement...")
            for _ in range(self.config.scroll_iterations):
                page.mouse.wheel(0, 1000)
                time.sleep(2)

            listings = page.locator("a[href*='/marketplace/item/']").all()
            logger.info(f"   👀 {len(listings)} éléments trouvés.")
            
            count = 0
            seen = set()
            consecutive_bad = 0
            
            target_key = ListingParser.normalize_city_name(location)
            target_coords = self.city_coordinates.get(target_key)

            for link in listings:
                if count >= max_ads: break
                
                href = link.get_attribute("href")
                if not href: continue
                full_link = f"https://www.facebook.com{href}" if href.startswith("/") else href
                clean_link = full_link.split('?')[0]
                
                if clean_link in seen: continue
                seen.add(clean_link)
                
                fb_id = ListingParser.extract_facebook_id(clean_link)
                if not fb_id: continue

                card_info = ListingParser.parse_listing_card(link, location)
                title = card_info['title']
                price = card_info['price']
                spec_loc = card_info['location']
                img_url = card_info['imageUrl']

                # --- LOGIQUE DE FILTRAGE MISE À JOUR ---
                is_too_far = False
                
                # 1. Si la ville est dans la liste blanche, on accepte d'office
                if self.is_city_allowed(spec_loc):
                    logger.info(f"   ✅ Ville autorisée détectée: {spec_loc}")
                
                # 2. Sinon, on applique le filtre de distance classique
                elif target_coords:
                    spec_coords = self.city_coordinates.get(ListingParser.normalize_city_name(spec_loc))
                    if spec_coords:
                        dist = calculate_distance(target_coords['lat'], target_coords['lng'], spec_coords['lat'], spec_coords['lng'])
                        if dist > distance * 1.1:
                            logger.info(f"   ⏩ [Pré-filtre] Ignoré: {spec_loc} ({dist:.1f}km)")
                            is_too_far = True
                    else:
                        # Si on ne connait pas les coords de la ville de l'annonce, on est prudent
                        # Mais si on n'a pas trouvé la ville dans allowed_cities, c'est peut-être une ville inconnue
                        pass

                if is_too_far:
                    consecutive_bad += 1
                    if consecutive_bad >= 30: break
                    continue
                
                consecutive_bad = 0

                if price > 0 or "Gratuit" in title or "Free" in title:
                    logger.info(f"   ✨ Trouvé: {title} ({price}$)")
                    
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
                    
                    # Vérification GPS finale
                    # Si la ville était autorisée par nom, on ignore la distance GPS aussi ?
                    # Oui, pour être cohérent avec la demande "si une annonce a le nom de la ville on l'accepte d'office sans regarder le radius"
                    
                    if not self.is_city_allowed(spec_loc) and coords and target_coords:
                        dist = calculate_distance(target_coords['lat'], target_coords['lng'], coords['lat'], coords['lng'])
                        if dist > distance * 1.1:
                            logger.info(f"   ⏩ [GPS] Trop loin ({dist:.1f}km)")
                            continue

                    final_img = details['imageUrls'][0] if details['imageUrls'] else img_url
                    
                    listing_data = {
                        "title": title, "price": price, "description": details['description'],
                        "imageUrl": final_img, "imageUrls": details['imageUrls'],
                        "link": clean_link, "location": spec_loc,
                        "searchDistance": distance, "id": fb_id
                    }
                    if coords:
                        listing_data["latitude"] = coords["lat"]
                        listing_data["longitude"] = coords["lng"]
                    
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
                
                p_txt = page.locator('div[role="main"] span', has_text="$").first.inner_text()
                digits = ''.join(filter(str.isdigit, p_txt))
                if digits: price = int(digits)
                
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
            page.goto(url, timeout=15000)
            sold = page.locator('span:has-text("Cette annonce n’est plus disponible"), span:has-text("This listing is no longer available")')
            if sold.count() > 0: is_available = False
        except: pass
        finally:
            page.close()
        return is_available
