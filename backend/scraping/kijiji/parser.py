import json
import logging
import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import Locator, Page

from ..parser import ListingParser

_module_logger = logging.getLogger(__name__)


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
        """
        L'ID d'une annonce Kijiji est toujours le DERNIER segment du chemin
        (`/v-<categorie>/<lieu>/<titre>/<id>`), jamais le premier segment
        numérique rencontré après `/v-` — un slug intermédiaire (lieu, année de
        fabrication dans le titre, etc.) peut lui aussi être purement numérique.
        """
        if not url or "/v-" not in url:
            return None
        path = url.split("?")[0].rstrip("/")
        last_segment = path.rsplit("/", 1)[-1]
        return last_segment if last_segment.isdigit() else None

    @staticmethod
    def extract_location_slug(url: str) -> Optional[str]:
        """
        Dérive un lieu approximatif depuis le 2e segment du chemin de l'URL
        (`/v-<catégorie>/<lieu>/<titre>/<id>`, ex: "longueuil-rive-sud" -> "Longueuil
        Rive Sud"). Utilisé en dernier repli quand ni le JSON-LD ni le DOM n'exposent
        la localisation (constaté en test live : Kijiji encode systématiquement le
        lieu dans l'URL, contrairement à Facebook).
        """
        if not url or "/v-" not in url:
            return None
        path = url.split("?")[0].rstrip("/")
        parts = [p for p in path.split("/") if p]
        for i, part in enumerate(parts):
            if part.startswith("v-") and i + 1 < len(parts):
                candidate = parts[i + 1]
                if candidate.isdigit():
                    return None
                return candidate.replace("-", " ").title()
        return None

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
        Stratégie en cascade, du plus fiable au moins fiable :
          1. `#__NEXT_DATA__` (état Apollo SSR de Next.js — confirmé en test live du
             2026-07-26 : contient title/description/price/location (nom + coordonnées
             GPS)/imageUrls exacts pour l'annonce, structuré et garanti présent puisque
             requis à l'hydratation React. Plus fiable que JSON-LD ou tout sélecteur CSS.
          2. JSON-LD (`<script type="application/ld+json">`, standard schema.org).
          3. Repli DOM (sélecteurs `data-testid`) et, pour le lieu, le slug d'URL.
        """
        log = logger or _module_logger
        description = f"Annonce Kijiji. {initial_title}."
        description_found = False
        image_urls: List[str] = []
        price = 0
        price_found = False
        location = None
        latitude = None
        longitude = None

        next_listing = KijijiListingParser._extract_next_data_listing(page, log)
        if next_listing:
            desc = next_listing.get("description")
            if desc and desc.strip():
                description = desc.strip()
                description_found = True

            image_urls = [u for u in (next_listing.get("imageUrls") or []) if isinstance(u, str)]

            price_obj = next_listing.get("price")
            if isinstance(price_obj, dict) and price_obj.get("amount") is not None:
                try:
                    # `amount` est exprimé en cents (ex: 22000 -> 220.00 $).
                    price = int(round(float(price_obj["amount"]) / 100))
                    price_found = True
                except (TypeError, ValueError):
                    pass

            loc_obj = next_listing.get("location")
            if isinstance(loc_obj, dict):
                if loc_obj.get("name"):
                    location = loc_obj["name"]
                coords = loc_obj.get("coordinates")
                if isinstance(coords, dict) and coords.get("latitude") is not None and coords.get("longitude") is not None:
                    latitude = coords["latitude"]
                    longitude = coords["longitude"]

        json_ld = None
        if not image_urls or not price_found or not description_found:
            json_ld = KijijiListingParser._extract_json_ld(page, log)

        if json_ld:
            if not description_found:
                desc = json_ld.get("description")
                if desc and len(desc.strip()) > 10:
                    description = desc.strip()
                    description_found = True

            if not image_urls:
                image_urls = KijijiListingParser._extract_images_from_json_ld(json_ld)

            if not price_found:
                offers = json_ld.get("offers")
                offer_list = offers if isinstance(offers, list) else ([offers] if isinstance(offers, dict) else [])
                for offer in offer_list:
                    if not isinstance(offer, dict):
                        continue
                    raw_price = offer.get("price")
                    if raw_price is not None:
                        try:
                            price = int(float(raw_price))
                            price_found = True
                            break
                        except (TypeError, ValueError):
                            continue

            if not location:
                area = json_ld.get("areaServed")
                if isinstance(area, dict):
                    location = area.get("name")
                elif isinstance(area, str):
                    location = area

        if not image_urls:
            image_urls = KijijiListingParser._extract_images_from_dom(page, log)

        if not description_found:
            try:
                meta_desc = page.locator('meta[property="og:description"]').get_attribute("content")
                if meta_desc and len(meta_desc.strip()) > 10:
                    description = meta_desc.strip()
            except Exception as e:
                log.debug(f"Erreur extraction meta og:description: {e}")

        if not price_found:
            try:
                price_el = page.locator("[data-testid='vip-price'], [data-testid='price']").first
                if price_el.count() > 0:
                    text = price_el.inner_text()
                    has_digits = any(c.isdigit() for c in text)
                    is_free = "Free" in text or "Gratuit" in text
                    # Distingue "prix trouvé mais gratuit (0$)" d'un "prix introuvable" (repose
                    # sinon sur card_price côté core.py) — même logique que ListingParser (FB).
                    if has_digits or is_free:
                        price = ListingParser.extract_price_from_text(text)
                        price_found = True
            except Exception as e:
                log.debug(f"Erreur extraction prix fiche détail: {e}")

        if not location:
            try:
                loc_el = page.locator("[data-testid='vip-location'], [data-testid='location']").first
                if loc_el.count() > 0:
                    location = loc_el.inner_text().strip()
            except Exception as e:
                log.debug(f"Erreur extraction localisation fiche détail: {e}")

        if not location:
            # Dernier repli : Kijiji encode systématiquement le lieu dans l'URL elle-même
            # (`/v-<catégorie>/<lieu>/<titre>/<id>`) — fiable même quand ni __NEXT_DATA__,
            # ni JSON-LD, ni le DOM n'exposent la localisation.
            location = KijijiListingParser.extract_location_slug(page.url)

        return {
            "description": description[:3000],
            "imageUrls": image_urls[:10],
            "price": price,
            "price_found": price_found,
            "location": location,
            "latitude": latitude,
            "longitude": longitude,
        }

    @staticmethod
    def _extract_next_data_listing(page: Page, log: logging.Logger) -> Optional[Dict[str, Any]]:
        """Lit `#__NEXT_DATA__` (état SSR Next.js/Apollo, injecté dans toute page rendue
        par le framework — pas un détail d'implémentation fragile) et retourne l'objet
        `StandardListing:{id}` correspondant à l'annonce affichée."""
        try:
            script = page.locator('script#__NEXT_DATA__').first
            if script.count() == 0:
                return None
            raw = script.inner_text()
            if not raw:
                return None
            data = json.loads(raw)
        except Exception as e:
            log.debug(f"Erreur lecture __NEXT_DATA__: {e}")
            return None
        return KijijiListingParser._pick_standard_listing(data, log)

    @staticmethod
    def _pick_standard_listing(next_data: Dict[str, Any], log: logging.Logger = None) -> Optional[Dict[str, Any]]:
        """Logique pure (testable sans Page réelle) : extrait l'objet `StandardListing:{id}`
        depuis le JSON déjà parsé de `#__NEXT_DATA__`."""
        log = log or _module_logger
        try:
            page_props = next_data.get("props", {}).get("pageProps", {})
            listing_id = page_props.get("listingId")
            apollo_state = page_props.get("__APOLLO_STATE__")
            if listing_id and isinstance(apollo_state, dict):
                entry = apollo_state.get(f"StandardListing:{listing_id}")
                if isinstance(entry, dict):
                    return entry
        except Exception as e:
            log.debug(f"Erreur lecture chemin direct __NEXT_DATA__: {e}")

        # Repli robuste si la structure exacte évolue : premier StandardListing trouvé
        # dans l'état Apollo, quel que soit le chemin pour y accéder.
        try:
            apollo_state = next_data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__")
            if isinstance(apollo_state, dict):
                for key, value in apollo_state.items():
                    if key.startswith("StandardListing:") and isinstance(value, dict):
                        return value
        except Exception as e:
            log.debug(f"Erreur repli scan __NEXT_DATA__: {e}")
        return None

    @staticmethod
    def extract_all_standard_listings(page: Page, log: logging.Logger = None) -> Dict[str, Dict[str, Any]]:
        """
        Extrait tous les `StandardListing:{id}` présents dans l'état Apollo
        (`__NEXT_DATA__`) d'une page de RÉSULTATS de recherche — même source que
        `parse_details_page()`, mais couvrant toutes les annonces affichées en un seul
        accès, sans sélecteur DOM par carte (confirmé en test live du 2026-07-26 :
        title/description/price/location/url exacts pour chacune).

        ⚠️ Ne contient qu'UNE URL d'image par annonce (aperçu — `imageCount` indique le
        vrai total) : la fiche détail individuelle reste nécessaire pour la galerie
        complète. Retourne un dict vide si `__NEXT_DATA__`/`__APOLLO_STATE__` est absent
        (repli DOM alors nécessaire côté appelant).
        """
        log = log or _module_logger
        try:
            script = page.locator('script#__NEXT_DATA__').first
            if script.count() == 0:
                return {}
            raw = script.inner_text()
            if not raw:
                return {}
            data = json.loads(raw)
        except Exception as e:
            log.debug(f"Erreur lecture __NEXT_DATA__ (résultats): {e}")
            return {}
        return KijijiListingParser._pick_all_standard_listings(data, log)

    @staticmethod
    def _pick_all_standard_listings(next_data: Dict[str, Any], log: logging.Logger = None) -> Dict[str, Dict[str, Any]]:
        """Logique pure (testable sans Page réelle) : extrait tous les `StandardListing:{id}`
        de l'état Apollo déjà parsé, indexés par ID."""
        log = log or _module_logger
        results: Dict[str, Dict[str, Any]] = {}
        try:
            apollo_state = next_data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__")
            if not isinstance(apollo_state, dict):
                return results
            for key, value in apollo_state.items():
                if key.startswith("StandardListing:") and isinstance(value, dict):
                    listing_id = value.get("id")
                    if listing_id:
                        results[str(listing_id)] = value
        except Exception as e:
            log.debug(f"Erreur extraction de tous les StandardListing: {e}")
        return results

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
                    if not isinstance(candidate, dict):
                        continue
                    type_val = candidate.get("@type")
                    # @type est valide en chaîne unique OU en tableau de types (schema.org).
                    types = type_val if isinstance(type_val, list) else [type_val]
                    if any(t in ("Product", "Offer") for t in types):
                        return candidate
        except Exception as e:
            log.debug(f"Erreur extraction JSON-LD: {e}")
        return None

    @staticmethod
    def _extract_images_from_json_ld(json_ld: Dict[str, Any]) -> List[str]:
        """Le champ `image` schema.org accepte une URL, une liste d'URLs, ou une liste
        d'objets `ImageObject` (`{"url": "..."}`) — les 3 formes sont légales."""
        images = json_ld.get("image")
        urls: List[str] = []
        if isinstance(images, str):
            urls.append(images)
        elif isinstance(images, dict):
            url = images.get("url") or images.get("contentUrl")
            if url:
                urls.append(url)
        elif isinstance(images, list):
            for item in images:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict):
                    url = item.get("url") or item.get("contentUrl")
                    if url:
                        urls.append(url)
        return urls

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
