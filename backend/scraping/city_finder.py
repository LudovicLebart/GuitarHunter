import time
import logging
import re
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

class CityFinder:
    @staticmethod
    def find_city_id(scraper, city_name):
        scraper._ensure_session()
        page = scraper.context.new_page()
        city_id = None
        
        try:
            logger.info(f"Début de la recherche d'ID pour la ville: '{city_name}'")
            page.goto("https://www.facebook.com/marketplace/", timeout=30000)
            logger.info("Page Marketplace chargée.")

            scraper._close_login_popup(page)

            # Clic sur le bouton de localisation
            loc_button = page.locator("div[role='button']").filter(has_text=re.compile(r"\d+\s*(km|mi)", re.IGNORECASE)).first
            if not loc_button.is_visible(timeout=5000):
                logger.warning("Bouton de localisation principal non trouvé, essai d'une autre stratégie.")
                loc_button = page.locator("div[aria-label*='Lieu'], div[aria-label*='Location']").first
            
            if not loc_button.is_visible(timeout=1000):
                 logger.error("Bouton de localisation introuvable. Abandon.")
                 return None

            logger.info("Bouton de localisation trouvé. Clic.")
            loc_button.click(force=True)

            # Attente du dialogue
            page.wait_for_selector("div[role='dialog']", timeout=8000)
            logger.info("Dialogue de localisation ouvert.")

            # Remplissage du champ
            input_loc = page.locator("input[aria-label='Lieu'], input[aria-label='Location']").first
            input_loc.fill(city_name)
            logger.info(f"Champ rempli avec '{city_name}'.")
            time.sleep(2) # Attente des suggestions

            # Clic sur la première suggestion
            first_suggestion = page.locator("div[role='option']").first
            if not first_suggestion.is_visible(timeout=5000):
                logger.warning("Aucune suggestion de ville trouvée. Tentative avec la touche Entrée.")
                page.keyboard.press("Enter")
            else:
                suggestion_text = first_suggestion.inner_text()
                logger.info(f"Clic sur la suggestion : {suggestion_text}")
                first_suggestion.click()
            
            time.sleep(0.5)

            # Clic sur Appliquer
            apply_btn = page.locator("div[aria-label='Appliquer'], div[aria-label='Apply']").first
            logger.info("Clic sur le bouton Appliquer.")
            apply_btn.click()

            # Attente du changement d'URL
            try:
                page.wait_for_url(re.compile(r"/marketplace/\d+/"), timeout=10000)
                current_url = page.url
                logger.info(f"Nouvelle URL: {current_url}")
                match = re.search(r"/marketplace/(\d+)/", current_url)
                if match:
                    city_id = match.group(1)
                    logger.info(f"ID de la ville trouvé: {city_id}")
            except PlaywrightTimeoutError:
                logger.error("L'URL n'a pas changé après l'application de la nouvelle ville.")

        except Exception as e:
            logger.critical(f"Erreur critique dans CityFinder: {e}", exc_info=True)
            try:
                # Tentative de prendre une capture d'écran pour le débogage
                screenshot_path = f"city_finder_error_{time.time()}.png"
                page.screenshot(path=screenshot_path)
                logger.info(f"Capture d'écran de l'erreur enregistrée dans {screenshot_path}")
            except Exception as screenshot_error:
                logger.error(f"Impossible de prendre une capture d'écran: {screenshot_error}")
        finally:
            logger.info("Fermeture de la page CityFinder.")
            page.close()
            
        return city_id
