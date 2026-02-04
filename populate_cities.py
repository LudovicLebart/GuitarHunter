import json
import time
import logging
import sys
import re
from dotenv import load_dotenv
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

# --- Configuration des Couleurs de Log ---
class CustomFormatter(logging.Formatter):
    white = "\033[97m"
    yellow = "\033[93m"
    red = "\033[91m"
    reset = "\033[0m"
    format_str = "%(asctime)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: white + format_str + reset,
        logging.INFO: white + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%H:%M:%S')
        return formatter.format(record)

# Configuration du logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(CustomFormatter())
logger.addHandler(ch)
logger.propagate = False

load_dotenv()

# --- Imports du Projet ---
from backend.database import DatabaseService
from backend.repository import FirestoreRepository
from backend.scraping import FacebookScraper, ListingParser
from config import FIREBASE_KEY_PATH, APP_ID_TARGET, USER_ID_TARGET, CITY_COORDINATES

def get_facebook_city_id(page: Page, city_name: str) -> str | None:
    """
    Utilise l'interface de Marketplace pour trouver l'ID (ou le slug) d'une ville.
    """
    try:
        logger.info(f"--- Début de la recherche pour: {city_name} ---")
        
        # 1. Cliquer sur le bouton de localisation
        loc_button_selector = "div[role='button']:has-text('km')"
        logger.info(f"   1. Clic sur le bouton de localisation...")
        
        try:
            page.locator(loc_button_selector).first.click(timeout=5000)
        except:
            page.locator("div[role='button']").filter(has_text="km").first.click()
            
        page.wait_for_selector("div[role='dialog']", timeout=10000)
        logger.info("      -> Modal ouvert.")

        # 2. Taper le nom de la ville
        location_input_selector = "input[aria-label='Lieu'], input[aria-label='Location']"
        logger.info(f"   2. Recherche de '{city_name}'...")
        location_input = page.locator(location_input_selector).first
        location_input.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        time.sleep(0.5)
        location_input.fill(city_name)
        
        # 3. Attendre et sélectionner la première suggestion
        logger.info("   3. Attente des suggestions...")
        try:
            page.wait_for_selector("div[role='option']", timeout=5000)
        except:
            logger.warning("      Pas de suggestions détectées via le sélecteur standard.")
        
        time.sleep(2)

        suggestions = page.locator("div[role='option']").all()
        
        if len(suggestions) > 0:
            first_suggestion = suggestions[0]
            suggestion_text = first_suggestion.inner_text()
            logger.info(f"      -> Clic sur la 1ère suggestion: '{suggestion_text}'")
            first_suggestion.click()
        else:
            logger.warning("      ⚠️ Aucune suggestion trouvée. Tentative d'appui sur Entrée.")
            page.keyboard.press("Enter")
        
        time.sleep(1)

        # 4. Appliquer et attendre la navigation
        apply_button_selector = "div[aria-label='Appliquer'], div[aria-label='Apply']"
        logger.info("   4. Clic sur 'Appliquer' et attente de la navigation...")
        
        apply_btn = page.locator(apply_button_selector).first
        if apply_btn.is_visible():
            with page.expect_navigation(timeout=15000):
                apply_btn.click()
        else:
            logger.warning("      Bouton Appliquer non visible, tentative Entrée...")
            with page.expect_navigation(timeout=15000):
                page.keyboard.press("Enter")
        
        new_url = page.url
        logger.info(f"      -> Nouvelle URL: {new_url}")

        # 5. Extraire l'ID ou le Slug de la nouvelle URL
        match = re.search(r"/marketplace/([^/]+)/", new_url)
        if match:
            city_id = match.group(1)
            if city_id in ["search", "category", "item"]:
                 logger.warning(f"   ⚠️ ID extrait invalide ('{city_id}').")
                 return None
                 
            logger.info(f"   ✅ ID trouvé pour {city_name}: {city_id}")
            return city_id
        else:
            logger.warning(f"   ⚠️ Impossible d'extraire l'ID de l'URL pour {city_name}.")
            return None

    except PlaywrightTimeoutError:
        logger.error(f"   ❌ Timeout lors de la recherche pour {city_name}.")
        page.keyboard.press("Escape")
        time.sleep(1)
        return None
    except Exception as e:
        logger.error(f"   ❌ Erreur inattendue pour {city_name}: {e}")
        try:
            page.keyboard.press("Escape")
        except:
            pass
        return None

def main():
    logger.info("--- Démarrage du script de peuplement des villes ---")
    
    # 1. Initialisation DB
    db_service = DatabaseService(FIREBASE_KEY_PATH)
    if db_service.offline_mode:
        logger.error("Ce script ne peut pas fonctionner en mode hors ligne.")
        sys.exit(1)
    repo = FirestoreRepository(db_service.db, APP_ID_TARGET, USER_ID_TARGET)

    # 2. Récupération des villes existantes
    existing_cities_docs = repo.get_cities()
    existing_cities = {ListingParser.normalize_city_name(doc.to_dict()['name']): doc.id for doc in existing_cities_docs}
    logger.info(f"{len(existing_cities)} villes déjà présentes dans Firestore.")

    # 3. Initialisation du Scraper
    scraper = FacebookScraper(city_coordinates={}, city_mapping={})
    scraper.config.headless = False 
    
    try:
        scraper.start_session()
        page = scraper.context.new_page()
        
        start_url = "https://www.facebook.com/marketplace/montreal/search/?query=guitare"
        logger.info(f"Navigation vers l'URL de départ: {start_url}")
        page.goto(start_url, timeout=60000)
        scraper._close_login_popup(page)

        # 4. Boucle sur les villes
        count_added = 0
        for city_name, coords in CITY_COORDINATES.items():
            normalized_name = ListingParser.normalize_city_name(city_name)
            
            if normalized_name in existing_cities:
                logger.info(f"Ville '{city_name}' déjà présente, ignorée.")
                continue

            city_id = get_facebook_city_id(page, city_name)

            if city_id:
                city_data = {
                    'name': city_name,
                    'id': city_id,
                    'latitude': coords['lat'],
                    'longitude': coords['lng'],
                    'createdAt': time.time(),
                    'isScannable': False  # Ajout du champ pour la whitelist
                }
                
                try:
                    repo.cities_ref.add(city_data)
                    logger.info(f"   -> 🎉 Ville '{city_name}' ajoutée à Firestore.")
                    count_added += 1
                except Exception as e:
                    logger.error(f"   -> ❌ Erreur lors de l'ajout de '{city_name}' à Firestore: {e}")
            else:
                logger.warning(f"Échec de la récupération de l'ID pour '{city_name}'. Elle ne sera pas ajoutée.")
            
            time.sleep(3)

        logger.info(f"--- Script terminé. {count_added} nouvelles villes ajoutées. ---")

    finally:
        if scraper:
            scraper.close_session()
            logger.info("Session Playwright fermée.")

if __name__ == "__main__":
    main()
