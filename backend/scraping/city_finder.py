import time
import logging
import re
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

class CityFinder:
    """
    Classe utilitaire pour trouver l'ID Facebook d'une ville via le scraper.
    """
    
    @staticmethod
    def find_city_id(scraper, city_name):
        """
        Utilise une session scraper existante pour trouver l'ID d'une ville.
        """
        scraper._ensure_session()
        page = scraper.context.new_page()
        city_id = None
        
        try:
            # On va sur une page neutre ou marketplace pour commencer
            start_url = "https://www.facebook.com/marketplace/"
            logger.info(f"Recherche de l'ID pour la ville: {city_name}")
            
            page.goto(start_url, timeout=30000)
            scraper._close_login_popup(page)
            
            # Attendre que l'interface charge
            try:
                page.wait_for_selector("div[role='main']", timeout=10000)
            except:
                pass

            # 1. Cliquer sur le bouton de localisation
            loc_button = page.locator("div[role='button']").filter(has_text=re.compile(r"km|mi", re.IGNORECASE)).first
            
            if not loc_button.is_visible():
                loc_button = page.locator("div[aria-label*='Lieu'], div[aria-label*='Location']").first
            
            if loc_button.is_visible():
                loc_button.click()
            else:
                logger.warning("Bouton de localisation introuvable.")
                return None

            # Attendre le modal
            page.wait_for_selector("div[role='dialog']", timeout=5000)
            
            # 2. Remplir le champ de recherche
            input_loc = page.locator("input[aria-label='Lieu'], input[aria-label='Location']").first
            input_loc.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            time.sleep(0.5)
            input_loc.fill(city_name)
            time.sleep(2) # Attendre les suggestions
            
            # 3. Sélectionner la première suggestion
            first_suggestion = page.locator("div[role='option']").first
            if first_suggestion.is_visible(timeout=5000):
                logger.info(f"Suggestion trouvée: {first_suggestion.inner_text()}")
                first_suggestion.click()
            else:
                logger.warning("Aucune suggestion trouvée.")
                page.keyboard.press("Enter")
            
            time.sleep(1)
            
            # 4. Cliquer sur Appliquer
            apply_btn = page.locator("div[aria-label='Appliquer'], div[aria-label='Apply']").first
            if apply_btn.is_visible():
                with page.expect_navigation(timeout=10000):
                    apply_btn.click()
            else:
                with page.expect_navigation(timeout=10000):
                    page.keyboard.press("Enter")
            
            # 5. Extraire l'ID de l'URL
            current_url = page.url
            match = re.search(r"/marketplace/(\d+)/", current_url)
            if match:
                city_id = match.group(1)
                logger.info(f"ID trouvé: {city_id}")
            else:
                logger.warning(f"Impossible d'extraire l'ID de l'URL: {current_url}")
                
        except Exception as e:
            logger.error(f"Erreur lors de la recherche de ville: {e}")
        finally:
            page.close()
            
        return city_id
