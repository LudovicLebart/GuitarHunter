import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import Locator, Page

from ..parser import ListingParser

_module_logger = logging.getLogger(__name__)

# URL d'une annonce Kijiji : /v-<slug>/<ville-slug>/<titre-slug>/<id numérique>
_ID_PATTERN = re.compile(r"/v-[^?]*?/(\d+)(?:[/?]|$)")


class KijijiListingParser:
    """
    Responsable de l'extraction des données brutes depuis les pages Kijiji.
    Contient la logique fragile des sélecteurs CSS — voir la note de validation
    en tête de `kijiji/core.py::KijijiScraper` : ces sélecteurs n'ont pas pu être
    vérifiés contre le DOM réel de kijiji.ca (site inaccessible depuis cet
    environnement de développement) et doivent être confirmés avant mise en
    production.
    """

    @staticmethod
    def extract_kijiji_id(url: str) -> Optional[str]:
        if not url:
            return None
        match = _ID_PATTERN.search(url)
        return match.group(1) if match else None

    @staticmethod
    def parse_listing_card(link_element: Locator, logger: logging.Logger = None) -> Dict[str, Any]:
        """Extrait les infos de base depuis la carte de l'annonce dans la liste de résultats."""
        log = logger or _module_logger
        title = "Titre Inconnu"
        price = 0
        location = None
        img_url = "https://via.placeholder.com/400"

        try:
            title_el = link_element.locator(
                "[data-testid='listing-title'], [data-testid='listing-card-title'], h3, h2"
            ).first
            if title_el.count() > 0:
                text = title_el.inner_text().strip()
                if text:
                    title = text

            price_el = link_element.locator(
                "[data-testid='listing-price'], [data-testid='listing-card-price']"
            ).first
            if price_el.count() > 0:
                price = ListingParser.extract_price_from_text(price_el.inner_text())

            loc_el = link_element.locator(
                "[data-testid='listing-location'], [data-testid='listing-card-location']"
            ).first
            if loc_el.count() > 0:
                loc_text = loc_el.inner_text().strip()
                if loc_text:
                    location = loc_text

            img = link_element.locator("img").first
            if img.count() > 0:
                src = img.get_attribute("src") or img.get_attribute("data-src")
                if src:
                    img_url = src
                if title == "Titre Inconnu":
                    alt = img.get_attribute("alt")
                    if alt and len(alt) > 3:
                        title = alt

            # --- Repli générique si les data-testid ci-dessus ont changé ---
            if title == "Titre Inconnu" or price == 0:
                text = link_element.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if title == "Titre Inconnu":
                    for l in lines:
                        if "$" not in l and len(l) > 3:
                            title = l
                            break
                if price == 0:
                    for l in lines:
                        if "$" in l:
                            price = ListingParser.extract_price_from_text(l)
                            break

            return {"title": title, "price": price, "location": location, "imageUrl": img_url}
        except Exception as e:
            log.debug(f"Erreur parsing carte annonce Kijiji: {e}")
            return {"title": title, "price": price, "location": location, "imageUrl": img_url}

    @staticmethod
    def parse_details_page(page: Page, initial_title: str, kijiji_id: str = None, logger: logging.Logger = None) -> Dict[str, Any]:
        """
        Extrait les détails complets depuis la fiche annonce Kijiji.
        Stratégie en 2 temps : JSON-LD (balise <script type="application/ld+json">,
        présente sur la plupart des sites de petites annonces pour le SEO — plus
        stable qu'un sélecteur CSS car standardisée par schema.org) en priorité,
        repli sur le DOM sinon.
        """
        log = logger or _module_logger
        description = f"Annonce Kijiji. {initial_title}."
        image_urls: List[str] = []
        price = 0
        location = None

        json_ld = KijijiListingParser._extract_json_ld(page, log)
        if json_ld:
            desc = json_ld.get("description")
            if desc and len(desc.strip()) > 10:
                description = desc.strip()

            images = json_ld.get("image")
            if isinstance(images, str):
                image_urls = [images]
            elif isinstance(images, list):
                image_urls = [i for i in images if isinstance(i, str)]

            offers = json_ld.get("offers")
            if isinstance(offers, dict):
                raw_price = offers.get("price")
                if raw_price is not None:
                    try:
                        price = int(float(raw_price))
                    except (TypeError, ValueError):
                        pass

            area = json_ld.get("areaServed")
            if isinstance(area, dict):
                location = area.get("name")
            elif isinstance(area, str):
                location = area

        if not image_urls:
            image_urls = KijijiListingParser._extract_images_from_dom(page, log)

        if description.startswith("Annonce Kijiji."):
            try:
                meta_desc = page.locator('meta[property="og:description"]').get_attribute("content")
                if meta_desc and len(meta_desc.strip()) > 10:
                    description = meta_desc.strip()
            except Exception as e:
                log.debug(f"Erreur extraction meta og:description: {e}")

        if price == 0:
            try:
                price_el = page.locator("[data-testid='vip-price'], [data-testid='price']").first
                if price_el.count() > 0:
                    price = ListingParser.extract_price_from_text(price_el.inner_text())
            except Exception as e:
                log.debug(f"Erreur extraction prix fiche détail: {e}")

        if not location:
            try:
                loc_el = page.locator("[data-testid='vip-location'], [data-testid='location']").first
                if loc_el.count() > 0:
                    location = loc_el.inner_text().strip()
            except Exception as e:
                log.debug(f"Erreur extraction localisation fiche détail: {e}")

        return {
            "description": description[:3000],
            "imageUrls": image_urls[:10],
            "price": price,
            "location": location,
        }

    @staticmethod
    def _extract_json_ld(page: Page, log: logging.Logger) -> Optional[Dict[str, Any]]:
        try:
            scripts = page.locator('script[type="application/ld+json"]').all()
            for script in scripts:
                raw = script.inner_text()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                candidates = data if isinstance(data, list) else [data]
                for candidate in candidates:
                    if isinstance(candidate, dict) and candidate.get("@type") in ("Product", "Offer"):
                        return candidate
        except Exception as e:
            log.debug(f"Erreur extraction JSON-LD: {e}")
        return None

    @staticmethod
    def _extract_images_from_dom(page: Page, log: logging.Logger) -> List[str]:
        collected: List[str] = []
        seen = set()
        try:
            for _ in range(10):
                imgs = page.locator(
                    "[data-testid='image-gallery'] img, [data-testid='vip-gallery'] img, "
                    "div[class*='gallery' i] img"
                ).all()
                found = False
                for img in imgs:
                    try:
                        if not img.is_visible():
                            continue
                        src = img.get_attribute("src") or img.get_attribute("data-src")
                        if not src or src in seen:
                            continue
                        collected.append(src)
                        seen.add(src)
                        found = True
                    except Exception:
                        continue
                if len(collected) >= 10 or not found:
                    break
                try:
                    page.keyboard.press("ArrowRight")
                    time.sleep(0.5)
                except Exception:
                    pass
        except Exception as e:
            log.debug(f"Erreur extraction images DOM: {e}")
        return collected
