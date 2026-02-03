import time
import urllib.parse
import unicodedata
import re
import math
from playwright.sync_api import sync_playwright

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calcule la distance en km entre deux points géographiques (Haversine)."""
    try:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except Exception as e:
        print(f"⚠️ Erreur calcul distance: {e}")
        return 0

class FacebookScraper:
    def __init__(self, city_coordinates, city_mapping):
        self.city_coordinates = city_coordinates
        self.city_mapping = city_mapping

    def extract_facebook_id(self, url):
        """Extrait l'ID numérique unique de l'annonce Facebook depuis l'URL."""
        try:
            if "/item/" in url:
                segment = url.split("/item/")[1]
                fb_id = segment.split("/")[0].split("?")[0]
                if fb_id.isdigit():
                    return fb_id
            return None
        except Exception as e:
            print(f"⚠️ Erreur extraction ID: {e}")
            return None

    def _normalize_city_name(self, name):
        """Normalise le nom de la ville."""
        if not name: return ""
        name = name.split(',')[0].strip().lower()
        return unicodedata.normalize('NFD', name).encode('ascii', 'ignore').decode("utf-8")

    def _setup_browser(self, p):
        """Initialise le navigateur."""
        browser = p.chromium.launch(headless=False, args=["--start-minimized"])
        montreal_geo = {"latitude": 45.5017, "longitude": -73.5673}
        context = browser.new_context(
            viewport=None,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="fr-CA",
            timezone_id="America/Montreal",
            geolocation=montreal_geo,
            permissions=["geolocation"],
            extra_http_headers={"Referer": "https://www.google.com/"}
        )
        return browser, context

    def _close_login_popup(self, page):
        """Ferme le popup de connexion."""
        try:
            time.sleep(1)
            close_btn = page.locator("div[aria-label='Fermer'], div[aria-label='Close'], div[role='button'][aria-label*='Fermer']").first
            if close_btn.count() > 0 and close_btn.is_visible(timeout=2000):
                close_btn.click()
                time.sleep(1)
        except: pass

    def _apply_filters(self, page, distance, min_price, max_price):
        """Applique les filtres de rayon et de prix."""
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
                        
                        # Logique de sélection du rayon (simplifiée pour la brièveté)
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
            print(f"⚠️ Erreur filtre rayon: {e}")

        # Prix
        try:
            print(f"   💰 Application des prix : {min_price}$ - {max_price}$")
            
            # Prix Minimum
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

            # Prix Maximum
            max_input = page.locator("input[aria-label='Prix maximum'], input[aria-label='Maximum price'], input[placeholder='Max'], input[placeholder='Max.']").first
            
            if max_input.is_visible(timeout=3000):
                max_input.click()
                time.sleep(0.5)
                # On efface le champ proprement (Ctrl+A -> Backspace)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                time.sleep(0.2)
                
                # On tape le prix chiffre par chiffre pour simuler un humain
                for digit in str(max_price):
                    page.keyboard.type(digit)
                    time.sleep(0.1)
                
                time.sleep(0.5)
                page.keyboard.press("Enter")
                print("   ✅ Prix appliqués. Attente du rechargement...")
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(3)
            else:
                print("   ⚠️ Champ 'Prix maximum' introuvable.")
        except Exception as e:
            print(f"⚠️ Erreur filtre prix: {e}")

    def _extract_listing_details(self, context, clean_link, title, price, location):
        """Extrait les détails d'une annonce."""
        description = f"Annonce Marketplace. {title}. Localisation: {location}"
        image_urls = []
        coordinates = None
        
        try:
            page = context.new_page()
            page.goto(clean_link, timeout=45000)
            self._close_login_popup(page)
            try: page.wait_for_selector("div[role='main']", timeout=10000)
            except: pass
            time.sleep(2)

            # Images
            collected = []
            seen = set()
            for _ in range(10):
                try:
                    imgs = page.locator("div[role='main'] img").all()
                    found = False
                    for img in imgs:
                        if not img.is_visible(): continue
                        box = img.bounding_box()
                        if box and box['width'] > 300 and box['height'] > 300:
                            src = img.get_attribute("src")
                            if src and "scontent" in src and src not in seen:
                                collected.append(src)
                                seen.add(src)
                                found = True
                except: pass
                if not found and len(collected) > 0: break
                if len(collected) >= 10: break
                try:
                    page.keyboard.press("ArrowRight")
                    time.sleep(0.8)
                except: pass
            image_urls = collected

            # Coordonnées
            try:
                map_src = None
                map_img = page.locator('img[src*="staticmap"]').first
                if map_img.count() > 0:
                    map_src = map_img.get_attribute('src')
                
                if not map_src:
                    map_div = page.locator('div[style*="static_map.php"], div[style*="staticmap"]').first
                    if map_div.count() > 0:
                        style = map_div.get_attribute('style')
                        if style:
                            match = re.search(r'url\((?:&quot;|"|\')?(.*?)(?:&quot;|"|\')?\)', style)
                            if match: map_src = match.group(1).replace('&amp;', '&')

                if map_src:
                    match = re.search(r'center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', map_src)
                    if match:
                        coordinates = {"lat": float(match.group(1)), "lng": float(match.group(2))}
            except: pass

            # Description
            try:
                desc = page.locator('meta[property="og:description"]').get_attribute('content')
                if desc and len(desc.strip()) > 10: description = desc.strip()
                else:
                    # Fallback description extraction logic...
                    all_texts = page.locator('div[role="main"] span[dir="auto"]').all_inner_texts()
                    long_texts = [t.strip() for t in all_texts if len(t.strip()) > 50]
                    if long_texts: description = max(long_texts, key=len)
            except: pass

            page.close()
        except:
            if 'page' in locals(): page.close()
        
        return description[:3000], image_urls, coordinates

    def scan_marketplace(self, scan_config, on_deal_found):
        """Scanne le Marketplace."""
        search_query = scan_config['search_query']
        location = scan_config['location']
        distance = scan_config['distance']
        min_price = scan_config['min_price']
        max_price = scan_config['max_price']
        max_ads = scan_config['max_ads']

        print(f"\n🌍 Scan Facebook: '{search_query}' @ {location}...")
        
        norm_loc = self._normalize_city_name(location)
        city_id = self.city_mapping.get(norm_loc)
        if not city_id:
            if location.isdigit(): city_id = location
            else:
                print(f"❌ Ville '{location}' inconnue.")
                return

        with sync_playwright() as p:
            browser, context = self._setup_browser(p)
            page = context.new_page()
            
            q = urllib.parse.quote(search_query)
            tmp_max = max_price - 1 if max_price > min_price and max_price > 0 else max_price
            url = f"https://www.facebook.com/marketplace/{city_id}/search/?minPrice={min_price}&maxPrice={tmp_max}&query={q}&exact=false"
            
            try:
                print(f"   ➡️ Navigation: {url}")
                page.goto(url, timeout=60000)
                try: page.evaluate("document.body.style.zoom = '0.5'")
                except: pass
                
                # Cookies & Popup
                try: page.get_by_role("button", name="Allow all cookies").click(timeout=3000)
                except: pass
                try: page.get_by_role("button", name="Decline optional cookies").click(timeout=3000)
                except: pass
                self._close_login_popup(page)
                self._apply_filters(page, distance, min_price, max_price)

                # Scroll
                print("   📜 Défilement...")
                for _ in range(3):
                    page.mouse.wheel(0, 1000)
                    time.sleep(2)

                listings = page.locator("a[href*='/marketplace/item/']").all()
                print(f"   👀 {len(listings)} éléments trouvés.")
                
                count = 0
                seen = set()
                consecutive_bad = 0
                
                target_key = self._normalize_city_name(location)
                target_coords = self.city_coordinates.get(target_key)

                for link in listings:
                    if count >= max_ads: break
                    
                    href = link.get_attribute("href")
                    if not href: continue
                    full_link = f"https://www.facebook.com{href}" if href.startswith("/") else href
                    clean_link = full_link.split('?')[0]
                    
                    if clean_link in seen: continue
                    seen.add(clean_link)
                    
                    fb_id = self.extract_facebook_id(clean_link)
                    if not fb_id: continue

                    # Basic extraction
                    text = link.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    title = "Titre Inconnu"
                    price = 0
                    
                    # Title logic
                    img = link.locator("img").first
                    img_url = "https://via.placeholder.com/400"
                    if img.count() > 0:
                        src = img.get_attribute("src")
                        if src: img_url = src
                        alt = img.get_attribute("alt")
                        if alt and len(alt) > 3: title = alt
                    
                    if not title or title == "Titre Inconnu":
                        for l in lines:
                            if not any(c in l for c in ['$', '€', '£', 'Free']) and len(l) > 3:
                                title = l
                                break
                    
                    # Price logic
                    for l in lines:
                        if any(c in l for c in ['$', '€', '£', 'Free', 'Gratuit']):
                            digits = ''.join(filter(str.isdigit, l))
                            if digits: price = int(digits)
                            elif "Free" in l or "Gratuit" in l: price = 0
                            break
                    
                    # Location logic
                    spec_loc = location
                    if len(lines) >= 3:
                        pot_loc = lines[-1]
                        if len(pot_loc) < 40 and not any(c in pot_loc for c in ['$', '€']):
                            spec_loc = pot_loc

                    # Pre-filter distance
                    is_too_far = False
                    if target_coords:
                        spec_coords = self.city_coordinates.get(self._normalize_city_name(spec_loc))
                        if spec_coords:
                            dist = calculate_distance(target_coords['lat'], target_coords['lng'], spec_coords['lat'], spec_coords['lng'])
                            if dist > distance * 1.1:
                                print(f"   ⏩ [Pré-filtre] Ignoré: {spec_loc} ({dist:.1f}km)")
                                is_too_far = True

                    if is_too_far:
                        consecutive_bad += 1
                        if consecutive_bad >= 30: break
                        continue
                    
                    consecutive_bad = 0

                    if price > 0 or "Gratuit" in text or "Free" in text:
                        print(f"   ✨ Trouvé: {title} ({price}$)")
                        
                        # Callback pour vérifier doublon avant d'ouvrir
                        should_process = True
                        # Note: La vérification de doublon est faite par l'appelant via le callback si nécessaire, 
                        # mais ici on va simplifier et extraire les détails.
                        
                        desc, imgs, coords = self._extract_listing_details(context, clean_link, title, price, location)
                        
                        # GPS Filter
                        if coords and target_coords:
                            dist = calculate_distance(target_coords['lat'], target_coords['lng'], coords['lat'], coords['lng'])
                            if dist > distance * 1.1:
                                print(f"   ⏩ [GPS] Trop loin ({dist:.1f}km)")
                                continue

                        final_img = imgs[0] if imgs else img_url
                        
                        listing_data = {
                            "title": title, "price": price, "description": desc,
                            "imageUrl": final_img, "imageUrls": imgs,
                            "link": clean_link, "location": spec_loc,
                            "searchDistance": distance, "id": fb_id
                        }
                        if coords:
                            listing_data["latitude"] = coords["lat"]
                            listing_data["longitude"] = coords["lng"]
                        
                        on_deal_found(listing_data)
                        count += 1

            except Exception as e:
                print(f"❌ Erreur scan: {e}")
            finally:
                browser.close()

    def scan_specific_url(self, url, on_deal_found):
        """Scanne une URL spécifique."""
        print(f"\n🔗 Scan URL: {url}")
        fb_id = self.extract_facebook_id(url)
        
        with sync_playwright() as p:
            browser, context = self._setup_browser(p)
            try:
                page = context.new_page()
                page.goto(url, timeout=60000)
                
                if not fb_id:
                    fb_id = self.extract_facebook_id(page.url)
                
                if not fb_id:
                    print("❌ ID introuvable.")
                    return

                self._close_login_popup(page)
                try: page.wait_for_selector("div[role='main']", timeout=15000)
                except: pass
                time.sleep(2)

                # Extraction basique depuis la page de détails
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
                page.close()

                desc, imgs, coords = self._extract_listing_details(context, clean_link, title, price, location)
                
                listing_data = {
                    "title": title, "price": price, "description": desc,
                    "imageUrl": imgs[0] if imgs else "", "imageUrls": imgs,
                    "link": clean_link, "location": location,
                    "searchDistance": 0, "id": fb_id
                }
                if coords:
                    listing_data["latitude"] = coords["lat"]
                    listing_data["longitude"] = coords["lng"]

                on_deal_found(listing_data)
                print(f"✅ Scan URL terminé: {title}")

            except Exception as e:
                print(f"❌ Erreur scan URL: {e}")
            finally:
                browser.close()

    def check_listing_availability(self, url):
        """Vérifie si une annonce est toujours disponible."""
        is_available = True
        with sync_playwright() as p:
            browser, context = self._setup_browser(p)
            page = context.new_page()
            try:
                page.goto(url, timeout=15000)
                sold = page.locator('span:has-text("Cette annonce n’est plus disponible"), span:has-text("This listing is no longer available")')
                if sold.count() > 0: is_available = False
            except: pass
            finally: browser.close()
        return is_available
