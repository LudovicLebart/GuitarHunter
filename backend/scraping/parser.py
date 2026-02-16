import unicodedata
import re
import time
import logging
from typing import Optional, Dict, Any
from playwright.sync_api import Page, Locator

logger = logging.getLogger(__name__)

class ListingParser:
    """
    Responsable de l'extraction des données brutes depuis les éléments du DOM.
    Contient la logique fragile des sélecteurs CSS/XPath.
    """

    @staticmethod
    def extract_facebook_id(url: str) -> Optional[str]:
        try:
            if "/item/" in url:
                segment = url.split("/item/")[1]
                fb_id = segment.split("/")[0].split("?")[0]
                if fb_id.isdigit():
                    return fb_id
            return None
        except Exception as e:
            logger.warning(f"Erreur extraction ID depuis {url}: {e}")
            return None

    @staticmethod
    def normalize_city_name(name: str) -> str:
        if not name: return ""
        # 1. Garder la partie avant la virgule et mettre en minuscule
        name = name.split(',')[0].strip().lower()
        
        # 2. Remplacer les tirets et points par des espaces pour uniformiser
        name = name.replace('-', ' ').replace('.', ' ')
        
        # 3. Gérer les abréviations courantes (St -> Saint, Ste -> Sainte)
        words = name.split()
        fixed_words = []
        for w in words:
            if w == 'st': fixed_words.append('saint')
            elif w == 'ste': fixed_words.append('sainte')
            else: fixed_words.append(w)
        name = " ".join(fixed_words)

        # 4. Normalisation Unicode (accents)
        return unicodedata.normalize('NFD', name).encode('ascii', 'ignore').decode("utf-8")

    @staticmethod
    def parse_listing_card(link_element: Locator, location_filter: str) -> Dict[str, Any]:
        """Extrait les infos de base depuis la carte de l'annonce dans la liste."""
        title = "Titre Inconnu"
        price = 0
        spec_loc = None
        
        try:
            text = link_element.inner_text()
            # DEBUG LOG
            # logger.info(f"DEBUG PARSER - Raw text: {repr(text)}")
            
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            img = link_element.locator("img").first
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
            
            price_found = False
            for l in lines:
                if any(c in l for c in ['$', '€', '£', 'Free', 'Gratuit']):
                    # DEBUG LOG
                    # logger.info(f"DEBUG PARSER - Processing price line: {repr(l)}")
                    
                    if "Free" in l or "Gratuit" in l:
                        price = 0
                        price_found = True
                        break
                    
                    # Stratégie 1 : Chercher un nombre AVANT le symbole (ex: 240 C$280 C$)
                    match = re.search(r'(\d+(?:[\s.,]\d+)*)\s*(?:C?\$|€|£)', l)
                    if match:
                        digits_str = ''.join(filter(str.isdigit, match.group(1)))
                        if digits_str:
                            price = int(digits_str)
                            # logger.info(f"DEBUG PARSER - Strategy 1 found: {price}")
                            price_found = True
                            break
                    
                    # Stratégie 2 : Chercher un nombre APRES le symbole (ex: $240)
                    match = re.search(r'(?:C?\$|€|£)\s*(\d+(?:[\s.,]\d+)*)', l)
                    if match:
                        digits_str = ''.join(filter(str.isdigit, match.group(1)))
                        if digits_str:
                            price = int(digits_str)
                            # logger.info(f"DEBUG PARSER - Strategy 2 found: {price}")
                            price_found = True
                            break
                            
                    # Stratégie 3 (Fallback) : Le premier nombre trouvé sur la ligne
                    match = re.search(r'(\d+(?:[\s.,]\d+)*)', l)
                    if match:
                        digits_str = ''.join(filter(str.isdigit, match.group(1)))
                        if digits_str:
                            price = int(digits_str)
                            # logger.info(f"DEBUG PARSER - Strategy 3 found: {price}")
                            price_found = True
                            break
            
            if len(lines) >= 3:
                pot_loc = lines[-1]
                if len(pot_loc) < 40 and not any(c in pot_loc for c in ['$', '€']):
                    spec_loc = pot_loc
            
            return {"title": title, "price": price, "location": spec_loc, "imageUrl": img_url}
        except Exception as e:
            logger.debug(f"Erreur parsing carte annonce: {e}")
            return {"title": title, "price": price, "location": spec_loc, "imageUrl": "https://via.placeholder.com/400"}

    @staticmethod
    def parse_details_page(page: Page, initial_title: str, initial_location: str) -> Dict[str, Any]:
        """Extrait les détails complets depuis la page de l'annonce."""
        description = f"Annonce Marketplace. {initial_title}. Localisation: {initial_location}"
        image_urls = []
        coordinates = None
        
        try:
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
        except Exception as e:
            logger.debug(f"Erreur extraction images: {e}")

        try:
            map_src = None
            map_img = page.locator('img[src*="staticmap"]').first
            if map_img.count() > 0: map_src = map_img.get_attribute('src')
            
            if not map_src:
                map_div = page.locator('div[style*="static_map.php"], div[style*="staticmap"]').first
                if map_div.count() > 0:
                    style = map_div.get_attribute('style')
                    if style:
                        match = re.search(r'url\((?:&quot;|"|\')?(.*?)(?:&quot;|"|\')?\)', style)
                        if match: map_src = match.group(1).replace('&amp;', '&')

            if map_src:
                match = re.search(r'center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', map_src)
                if match: coordinates = {"lat": float(match.group(1)), "lng": float(match.group(2))}
        except Exception as e:
            logger.debug(f"Erreur extraction coordonnées: {e}")

        try:
            desc = page.locator('meta[property="og:description"]').get_attribute('content')
            if desc and len(desc.strip()) > 10: description = desc.strip()
            else:
                all_texts = page.locator('div[role="main"] span[dir="auto"]').all_inner_texts()
                long_texts = [t.strip() for t in all_texts if len(t.strip()) > 50]
                if long_texts: description = max(long_texts, key=len)
        except Exception as e:
            logger.debug(f"Erreur extraction description: {e}")

        return {"description": description[:3000], "imageUrls": image_urls, "coordinates": coordinates}
