import json
import logging
import random
import re
import time
from typing import Any, Dict, List

from playwright.sync_api import sync_playwright, Page

from .config import KijijiScraperConfig
from .parser import KijijiListingParser


class KijijiScraper:
    """
    Scraper Playwright pour Kijiji.ca, calqué sur `FacebookScraper`
    (`backend/scraping/core.py`) pour faciliter une intégration future dans
    `bot.py::run_scan()` (même forme de `listing_data` en sortie).

    ⚠️ VALIDATION REQUISE AVANT PRODUCTION : ce module a été développé dans un
    environnement dont la politique réseau bloque `kijiji.ca` — aucun accès
    direct au site n'a été possible pour inspecter le DOM réel. Les sélecteurs
    `data-testid` et le parcours du champ de recherche ci-dessous sont basés
    sur la structure connue de Kijiji, avec des replis génériques, mais
    doivent être vérifiés/ajustés lors d'un premier run réel (voir
    `scan_specific_url()` pour tester une annonce isolément sans dépendre du
    scroll de recherche).

    Écarts assumés par rapport à `FacebookScraper` (non des oublis) : pas de
    rotation de proxy, pas de géolocalisation forcée, pas de filtre par liste
    blanche de villes — ces trois éléments dépendent d'un mapping ville→ID
    Kijiji qui n'existe pas encore côté produit (contrairement à
    `city_mapping` sur Facebook). `check_listing_availability()` est en
    revanche fourni, pour la tâche de nettoyage périodique.

    Note d'API : `config` et `logger` sont volontairement **keyword-only**
    (contrairement à `FacebookScraper.__init__(city_coordinates, city_mapping,
    ...)`) car cette classe n'a pas d'équivalent positionnel à
    `city_coordinates`/`city_mapping` — ça évite qu'un futur appel copié-collé
    depuis `bot.py` (ex: `KijijiScraper({}, {}, logger=...)`) lie silencieusement
    les mauvais arguments ; il échouera bruyamment à l'appel à la place.
    """

    def __init__(self, *, config: KijijiScraperConfig = None, logger: logging.Logger = None):
        self.config = config or KijijiScraperConfig()
        # Logger par-utilisateur (Firestore/LogViewer) injecté par bot.py ; repli sur le
        # logger de module pour les scripts autonomes/tests.
        self.logger = logger or logging.getLogger(__name__)

        self.playwright = None
        self.browser = None
        self.context = None

        self._user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        ]
        self._viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
        ]

    def start_session(self):
        """Démarre la session Playwright et le navigateur."""
        if self.browser:
            return

        self.logger.info("Démarrage de la session Playwright (Kijiji)...")
        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=self.config.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        ua = random.choice(self._user_agents)
        vp = random.choice(self._viewports)
        self.logger.debug(f"Stealth Init -> UA: {ua[:40]}..., VP: {vp['width']}x{vp['height']}")

        self.context = self.browser.new_context(
            viewport=vp,
            user_agent=ua,
            locale=self.config.locale,
            timezone_id=self.config.timezone,
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
        self.logger.info("Session Playwright fermée (Kijiji).")

    def _ensure_session(self):
        if not self.context:
            self.start_session()

    def _accept_cookies(self, page: Page):
        """OneTrust est le bandeau de consentement le plus répandu ; repli texte si absent."""
        try:
            btn = page.locator("#onetrust-accept-btn-handler").first
            if btn.count() > 0 and btn.is_visible(timeout=2000):
                btn.click()
                time.sleep(0.5)
                return
        except Exception as e:
            self.logger.debug(f"Bandeau cookies OneTrust introuvable: {e}")
        try:
            btn = page.get_by_role("button", name=re.compile("accept|accepter", re.IGNORECASE)).first
            if btn.count() > 0 and btn.is_visible(timeout=2000):
                btn.click()
                time.sleep(0.5)
        except Exception as e:
            self.logger.debug(f"Repli bouton cookies (texte) introuvable: {e}")

    def _is_valid_detail_page(self, page: Page, expected_id: str) -> bool:
        """Vérifie que la page chargée est bien la fiche détail de l'annonce attendue
        (et non le feed/accueil suite à une redirection anti-bot). Compare l'ID exact
        du dernier segment de chemin plutôt qu'une simple sous-chaîne (un ID court comme
        "123" serait sinon "trouvé" par accident dans une URL contenant "45123")."""
        if "/login" in page.url or "captcha" in page.url.lower():
            self.logger.warning(f"🚨 Page détail invalide (redirection login/captcha): {page.url}")
            return False
        actual_id = KijijiListingParser.extract_kijiji_id(page.url)
        if expected_id and actual_id != expected_id:
            self.logger.warning(f"⚠️ Page détail invalide (ID inattendu: {actual_id}, attendu: {expected_id}): {page.url}")
            return False
        return True

    def scan_marketplace(self, scan_config: Dict[str, Any], should_skip_callback=None, stop_event=None) -> List[Dict[str, Any]]:
        """
        Recherche des annonces sur Kijiji via le champ de recherche du site (plutôt
        qu'une URL construite à la main : contrairement à Facebook, Kijiji exige un ID
        numérique de localisation par ville dans son URL de recherche, non disponible
        ici — pas de `city_mapping` équivalent pour cette première itération).

        scan_config attendu (sous-ensemble du contrat `FacebookScraper.scan_marketplace`) :
          - search_query (str)
          - location (str, optionnel — texte libre tapé dans le champ lieu du site)
          - max_ads (int)
        """
        self._ensure_session()

        search_query = scan_config["search_query"]
        location = scan_config.get("location")
        max_ads = scan_config.get("max_ads", 20)

        self.logger.info(f"\n🌍 Scan Kijiji: '{search_query}' @ {location or 'Canada'}...")

        if stop_event and stop_event.is_set():
            self.logger.info("🛑 Scan Kijiji annulé avant de démarrer (STOP_BOT).")
            return []

        page = self.context.new_page()
        found_deals: List[Dict[str, Any]] = []

        try:
            page.goto("https://www.kijiji.ca/", timeout=self.config.timeout_navigation)
            self._accept_cookies(page)

            keyword_input = page.locator(
                "input#keywordSearch, input[name='keywords'], input[placeholder*='Search' i], input[placeholder*='Rechercher' i]"
            ).first
            if keyword_input.count() == 0:
                self.logger.error("❌ Champ de recherche Kijiji introuvable — sélecteurs à vérifier (voir docstring de classe).")
                return []
            keyword_input.fill(search_query)

            if location:
                location_input = page.locator(
                    "input#locationAutoComplete, input[name='location'], input[placeholder*='Location' i], input[placeholder*='Lieu' i]"
                ).first
                if location_input.count() > 0:
                    location_input.fill(location)
                    time.sleep(1)
                    # Le filtre de lieu de Kijiji se lie généralement à une suggestion
                    # d'autocomplétion (pas au texte brut saisi) : on tente de la
                    # sélectionner ; à défaut, on ferme juste le menu et on continue
                    # (le filtre de lieu risque alors de ne pas s'appliquer).
                    suggestion = page.locator("[role='option'], li[role='option'], ul[role='listbox'] li").first
                    if suggestion.count() > 0:
                        suggestion.click()
                        time.sleep(0.5)
                    else:
                        self.logger.debug("Aucune suggestion de localisation Kijiji trouvée — le filtre de lieu pourrait ne pas s'appliquer.")
                        page.keyboard.press("Escape")

            keyword_input.click()
            page.keyboard.press("Enter")
            try:
                page.wait_for_load_state("networkidle", timeout=self.config.timeout_navigation)
            except Exception as e:
                self.logger.debug(f"Timeout networkidle après soumission recherche Kijiji: {e}")
            time.sleep(2)

            if "/login" in page.url or "captcha" in page.url.lower():
                self.logger.error(f"🚨 BLOCAGE ANTI-BOT DÉTECTÉ sur le scan Kijiji (Redirection {page.url}).")
                return []

            self.logger.info("   📜 Défilement dynamique...")
            previous_count = 0
            stagnant_iterations = 0
            target_ads_to_load = max_ads + 10
            for i in range(self.config.max_scroll_iterations):
                if stop_event and stop_event.is_set():
                    self.logger.info("🛑 Scan Kijiji annulé pendant le défilement (STOP_BOT).")
                    return found_deals
                page.mouse.wheel(0, 1000)
                time.sleep(1.5)

                current_count = page.locator("a[href^='/v-']").count()
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

            listings = page.locator("a[href^='/v-']").all()
            self.logger.info(f"   👀 {len(listings)} éléments trouvés.")

            count = 0
            seen = set()

            for link in listings:
                if count >= max_ads:
                    break
                if stop_event and stop_event.is_set():
                    self.logger.info("🛑 Scan Kijiji annulé pendant le traitement des annonces (STOP_BOT).")
                    return found_deals

                href = link.get_attribute("href")
                if not href:
                    continue
                full_link = f"https://www.kijiji.ca{href}" if href.startswith("/") else href
                clean_link = full_link.split("?")[0]

                if clean_link in seen:
                    continue
                seen.add(clean_link)

                kijiji_id = KijijiListingParser.extract_kijiji_id(clean_link)
                if not kijiji_id:
                    continue

                card_info = KijijiListingParser.parse_listing_card(link, logger=self.logger)
                title = card_info["title"]
                card_price = card_info["price"]
                card_location = card_info["location"]
                img_url = card_info["imageUrl"]

                if should_skip_callback and should_skip_callback(kijiji_id, card_price):
                    self.logger.info(f"   ⏩ Ignoré (déjà traité et inchangé): {title}")
                    continue

                self.logger.info(f"   ✨ Trouvé: {title} ({card_price}$) dans {card_location or '?'}")

                details_page = self.context.new_page()
                try:
                    details_page.goto(clean_link, timeout=self.config.timeout_navigation)
                    self._accept_cookies(details_page)
                    try:
                        details_page.wait_for_load_state("networkidle", timeout=self.config.timeout_selector)
                    except Exception as e:
                        self.logger.debug(f"Timeout networkidle fiche détail Kijiji: {e}")
                    time.sleep(1.5)

                    if self._is_valid_detail_page(details_page, kijiji_id):
                        details = KijijiListingParser.parse_details_page(details_page, title, kijiji_id, logger=self.logger)
                    else:
                        self.logger.warning(f"   ⚠️ Fiche détail non chargée pour '{title}' — repli sur les infos de la carte uniquement.")
                        details = {"description": f"Annonce Kijiji. {title}.", "imageUrls": [], "price": 0, "price_found": False, "location": None}
                finally:
                    details_page.close()

                # Un prix de 0$ trouvé sur la fiche détail (annonce gratuite) est légitime et
                # ne doit pas être écrasé par le prix de la carte — d'où le flag `price_found`
                # plutôt qu'un simple `details["price"] or card_price` (qui traiterait 0 comme
                # un échec d'extraction).
                final_price = details["price"] if details.get("price_found") else card_price
                final_location = details["location"] or card_location
                final_img = details["imageUrls"][0] if details["imageUrls"] else img_url

                listing_data = {
                    "title": title,
                    "price": final_price,
                    "description": details["description"],
                    "imageUrl": final_img,
                    "imageUrls": details["imageUrls"],
                    "link": clean_link,
                    "location": final_location,
                    "id": kijiji_id,
                    "source": "kijiji",
                }

                found_deals.append(listing_data)
                count += 1
        except Exception as e:
            self.logger.error(f"❌ Erreur scan Kijiji: {e}", exc_info=True)
        finally:
            page.close()
        return found_deals

    def scan_specific_url(self, url: str, on_deal_found):
        """Scrape une seule annonce Kijiji. Utile pour valider l'extraction isolément
        (voir note de validation en tête de classe) sans dépendre de la recherche/scroll."""
        self._ensure_session()

        self.logger.info(f"\n🔗 Scan URL Kijiji: {url}")
        kijiji_id = KijijiListingParser.extract_kijiji_id(url)

        page = self.context.new_page()
        try:
            page.goto(url, timeout=self.config.timeout_navigation)
            self._accept_cookies(page)

            if not kijiji_id:
                kijiji_id = KijijiListingParser.extract_kijiji_id(page.url)
            if not kijiji_id:
                self.logger.error("❌ ID Kijiji introuvable.")
                return

            if "/login" in page.url or "captcha" in page.url.lower():
                self.logger.error(f"🚨 BLOCAGE ANTI-BOT DÉTECTÉ (Redirection {page.url}).")
                return

            try:
                page.wait_for_load_state("networkidle", timeout=self.config.timeout_navigation)
            except Exception as e:
                self.logger.debug(f"Timeout networkidle scan_url Kijiji: {e}")
            time.sleep(1.5)

            if not self._is_valid_detail_page(page, kijiji_id):
                self.logger.error(f"❌ Fiche détail non chargée correctement pour {url} — annonce ignorée.")
                return

            title = "Titre Inconnu"
            try:
                og_title = page.locator('meta[property="og:title"]').get_attribute("content")
                if og_title:
                    title = og_title.split(" | ")[0].strip()
            except Exception as e:
                self.logger.debug(f"Erreur extraction og:title: {e}")

            details = KijijiListingParser.parse_details_page(page, title, kijiji_id, logger=self.logger)
            clean_link = page.url.split("?")[0]

            listing_data = {
                "title": title,
                "price": details["price"],
                "description": details["description"],
                "imageUrl": details["imageUrls"][0] if details["imageUrls"] else "",
                "imageUrls": details["imageUrls"],
                "link": clean_link,
                "location": details["location"],
                "id": kijiji_id,
                "source": "kijiji",
            }

            on_deal_found(listing_data)
            self.logger.info(f"✅ Scan URL Kijiji terminé: {title}")
        except Exception as e:
            self.logger.error(f"❌ Erreur scan URL Kijiji: {e}", exc_info=True)
        finally:
            page.close()

    def check_listing_availability(self, url: str) -> bool:
        """Vérifie si une annonce Kijiji est toujours active, pour la tâche de nettoyage
        périodique. Miroir de `FacebookScraper.check_listing_availability` : repli
        optimiste (annonce considérée disponible) en cas d'erreur/timeout."""
        self._ensure_session()
        is_available = True
        page = self.context.new_page()
        try:
            clean_url = url.split("?")[0]
            self.logger.info(f"   🔍 Vérification disponibilité Kijiji: {clean_url}")

            response = page.goto(clean_url, timeout=30000, wait_until="domcontentloaded")

            if response and response.status in (404, 410):
                self.logger.info(f"   🚫 Annonce supprimée (HTTP {response.status})")
                return False

            if "/v-" not in page.url:
                self.logger.info(f"   🚫 Redirection détectée (URL actuelle: {page.url}) - Annonce supprimée.")
                return False

            unavailable_patterns = [
                r"cette annonce n.est plus disponible",
                r"this ad is no longer available",
                r"^(?:est )?vendu\s*!?$",
                r"^(?:is )?sold\s*!?$",
                r"plus disponible",
                r"no longer available",
                r"^expired$",
                r"^expir[ée]e?$",
            ]
            patterns_json = json.dumps(unavailable_patterns)

            found_marker = page.evaluate(f"""() => {{
                const patterns = {patterns_json}.map(p => new RegExp(p, 'i'));
                const elements = document.querySelectorAll('span, div, h1, h2');
                for (const el of elements) {{
                    const text = el.innerText ? el.innerText.trim() : '';
                    if (!text) continue;

                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {{
                        continue;
                    }}
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;

                    for (const regex of patterns) {{
                        if (regex.test(text)) return text;
                    }}
                }}
                return null;
            }}""")

            if found_marker:
                self.logger.info(f"   🚫 Marqueur d'indisponibilité trouvé: '{found_marker}'")
                return False

        except Exception as e:
            self.logger.warning(f"   ⚠️ Erreur durant le check availability Kijiji: {e}")
            return True
        finally:
            page.close()
        return is_available
