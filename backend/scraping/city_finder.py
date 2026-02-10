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
            
            # Gestion agressive des popups
            scraper._close_login_popup(page)
            try: page.get_by_role("button", name="Allow all cookies").click(timeout=2000)
            except: pass
            try: page.get_by_role("button", name="Decline optional cookies").click(timeout=2000)
            except: pass
            
            # Attendre que l'interface charge un minimum
            try:
                page.wait_for_selector("div[role='main']", timeout=5000)
            except:
                pass

            # 1. Trouver et cliquer sur le bouton de localisation
            # Stratégie 1 : Bouton contenant "km" ou "mi" (ex: "Montréal · 40 km")
            loc_button = page.locator("div[role='button']").filter(has_text=re.compile(r"\d+\s*(km|mi)", re.IGNORECASE)).first
            
            # Stratégie 2 : Bouton avec aria-label explicite
            if not loc_button.is_visible():
                loc_button = page.locator("div[aria-label*='Lieu'], div[aria-label*='Location'], div[aria-label*='Changer de lieu']").first
            
            # Stratégie 3 : Recherche plus large dans la barre latérale gauche
            if not loc_button.is_visible():
                 loc_button = page.locator('span:has-text("Rayon"), span:has-text("Radius")').locator("..").locator("..").first

            if loc_button.is_visible():
                logger.info("Bouton de localisation trouvé, tentative de clic...")
                # Parfois un simple click ne suffit pas si un overlay est présent
                try:
                    loc_button.click(timeout=2000)
                except:
                    logger.warning("Clic standard échoué, tentative de clic forcé.")
                    loc_button.click(force=True)
            else:
                logger.warning("Bouton de localisation introuvable. Tentative d'accès direct via URL de recherche.")
                # Fallback : Tenter une recherche directe qui pourrait rediriger ou afficher l'ID
                # Mais sans ID, on ne peut pas construire l'URL parfaite.
                # On retourne None pour l'instant.
                return None

            # Attendre le modal avec un timeout un peu plus long
            try:
                page.wait_for_selector("div[role='dialog']", timeout=8000)
            except PlaywrightTimeoutError:
                logger.error("Le modal de localisation ne s'est pas ouvert.")
                return None
            
            # 2. Remplir le champ de recherche
            input_loc = page.locator("input[aria-label='Lieu'], input[aria-label='Location']").first
            if not input_loc.is_visible():
                 # Parfois le focus est déjà dedans ou le sélecteur diffère
                 input_loc = page.locator("div[role='dialog'] input[type='text']").first

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
                logger.warning("Aucune suggestion trouvée. Tentative avec Entrée.")
                page.keyboard.press("Enter")
            
            time.sleep(1)
            
            # 4. Cliquer sur Appliquer
            apply_btn = page.locator("div[aria-label='Appliquer'], div[aria-label='Apply']").first
            
            # Parfois le bouton est "Enregistrer" ou "Save"
            if not apply_btn.is_visible():
                 apply_btn = page.locator("div[role='dialog'] div[role='button']").filter(has_text=re.compile(r"Appliquer|Apply|Save|Enregistrer", re.IGNORECASE)).first

            if apply_btn.is_visible():
                # On attend la navigation qui suit le clic
                with page.expect_navigation(timeout=10000):
                    apply_btn.click()
            else:
                # Parfois juste Entrée suffit si le bouton n'est pas là
                logger.info("Bouton Appliquer non trouvé, appui sur Entrée.")
                with page.expect_navigation(timeout=10000):
                    page.keyboard.press("Enter")
            
            # 5. Extraire l'ID de l'URL
            # URL attendue: https://www.facebook.com/marketplace/123456789/
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
