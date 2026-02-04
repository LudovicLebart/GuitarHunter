import unicodedata
import re
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
        name = name.split(',')[0].strip().lower()
        return unicodedata.normalize('NFD', name).encode('ascii', 'ignore').decode("utf-8")

    @staticmethod
    def parse_listing_card(link_element: Locator, location_filter: str) -> Dict[str, Any]:
        """Extrait les infos de base depuis la carte de l'annonce dans la liste."""
        title = "Titre Inconnu"
        price = 0
        spec_loc = location_filter
        
        try:
            text = link_element.inner_text()
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
            
            for l in lines:
                if any(c in l for c in ['$', '€', '£', 'Free', 'Gratuit']):
                    digits = ''.join(filter(str.isdigit, l))
                    if digits: price = int(digits)
                    elif "Free" in l or "Gratuit" in l: price = 0
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
