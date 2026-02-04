import sys
import time
import threading
import logging

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)
# --- End Logging Configuration ---

# --- IMPORT DE LA CONFIGURATION CENTRALISÉE ---
from config import *
from backend.database import DatabaseService
from backend.analyzer import DealAnalyzer
from backend.scraper import FacebookScraper
from backend.repository import FirestoreRepository
from backend.services import ConfigManager, TaskScheduler

# --- INITIALISATION DE LA DB ---
db_service = DatabaseService(FIREBASE_KEY_PATH)
db = db_service.db
offline_mode = db_service.offline_mode
# --- FIN DE L'INITIALISATION ---

class GuitarHunterBot:
    def __init__(self, db_client, is_offline):
        self.offline_mode = is_offline
        if self.offline_mode:
            logger.warning("Offline mode is enabled. Bot will not connect to Firestore.")
            self.analyzer = DealAnalyzer()
            self.scraper = FacebookScraper(CITY_COORDINATES, {})
            return

        self.repo = FirestoreRepository(db_client, APP_ID_TARGET, USER_ID_TARGET)
        self.analyzer = DealAnalyzer()
        self.scraper = FacebookScraper(CITY_COORDINATES, {})
        
        initial_scan_config = {
            "max_ads": 5, "frequency": 60, "location": "montreal", "distance": 60,
            "min_price": 0, "max_price": 150, "search_query": "electric guitar"
        }
        
        self.config_manager = ConfigManager(self.repo, initial_scan_config)
        
        self.city_mapping = {}
        self.is_cleaning = False
        self.cleanup_lock = threading.Lock()

        logger.info("--- Bot Configuration ---")
        logger.info(f"APP ID: {APP_ID_TARGET}")
        logger.info(f"USER ID: {USER_ID_TARGET}")
        
        if CITY_COORDINATES:
             logger.info(f"{len(CITY_COORDINATES)} city coordinates loaded.")

        self._init_firestore_structure(initial_scan_config)
        self.sync_and_apply_config(initial=True)

    def _init_firestore_structure(self, initial_scan_config):
        """Assure que la structure de base de Firestore existe."""
        initial_config = {
            'prompt': PROMPT_INSTRUCTION, # Legacy, à garder pour l'instant
            'verdictRules': DEFAULT_VERDICT_RULES,
            'reasoningInstruction': DEFAULT_REASONING_INSTRUCTION,
            'userPrompt': DEFAULT_USER_PROMPT,
            'scanConfig': initial_scan_config
        }
        self.repo.ensure_initial_structure(initial_config)

    def sync_and_apply_config(self, initial=False):
        """Synchronise la configuration et met à jour les composants dépendants."""
        if self.offline_mode: return
        
        sync_result = self.config_manager.sync_with_firestore(initial=initial)
        
        if sync_result.config_changed:
            if self.config_manager.user_prompt_template:
                self.analyzer.update_prompt_template(self.config_manager.user_prompt_template)
        
        return sync_result

    def load_cities_from_firestore(self):
        if self.offline_mode: return
        docs = self.repo.get_cities()
        new_mapping = {
            self.scraper._normalize_city_name(doc.to_dict()['name']): doc.to_dict()['id']
            for doc in docs if 'name' in doc.to_dict() and 'id' in doc.to_dict()
        }
        self.city_mapping = new_mapping
        self.scraper.city_mapping = new_mapping
        logger.info(f"{len(new_mapping)} cities loaded from Firestore.")

    def handle_deal_found(self, listing_data):
        logger.info(f"Processing new deal: {listing_data['title']}")
        
        if not self.offline_mode:
            existing_deal = self.repo.get_deal_by_id(listing_data['id'])
            if existing_deal:
                if existing_deal.get('status') == 'rejected':
                    logger.info("Deal already exists and was rejected. Skipping.")
                    return
                if existing_deal.get('price') == listing_data['price']:
                    logger.info("Deal already exists with same price. Skipping.")
                    return
                logger.info("Deal already exists but price has changed. Updating.")

        analysis = self.analyzer.analyze_deal(listing_data)
        if not self.offline_mode:
            self.repo.save_deal(listing_data['id'], listing_data, analysis)

    def run_scan(self):
        scan_config = self.config_manager.scan_config
        logger.info(f"Starting scheduled scan (frequency: {scan_config.get('frequency', 'N/A')} min)...")
        self.load_cities_from_firestore()
        self.scraper.scan_marketplace(scan_config, self.handle_deal_found)
        logger.info("Scheduled scan finished.")

    def scan_specific_url(self, url):
        self.scraper.scan_specific_url(url, self.handle_deal_found)
        if not self.offline_mode:
            self.repo.consume_command('scanSpecificUrl')

    def cleanup_sold_listings(self):
        if self.offline_mode or self.is_cleaning: return
        logger.info("Starting cleanup of sold listings...")
        threading.Thread(target=self._perform_cleanup, daemon=True).start()

    def _perform_cleanup(self):
        with self.cleanup_lock:
            self.is_cleaning = True
            try:
                docs = self.repo.get_active_listings()
                listings = [{'id': d.id, 'url': d.to_dict().get('link')} for d in docs]
                
                logger.info(f"Checking availability of {len(listings)} active listings.")
                deleted_count = 0
                
                for item in listings:
                    if not item['url']: continue
                    if not self.scraper.check_listing_availability(item['url']):
                        self.repo.delete_listing(item['id'])
                        deleted_count += 1
                    time.sleep(0.5)
                
                logger.info(f"Cleanup finished. {deleted_count} listings deleted.")
            except Exception as e:
                logger.error(f"An error occurred during cleanup: {e}", exc_info=True)
            finally:
                self.is_cleaning = False

    def process_retry_queue(self):
        if self.offline_mode: return
        
        docs = self.repo.get_retry_queue_listings()
        for doc in docs:
            data = doc.to_dict()
            logger.info(f"Re-analyzing deal from retry queue: {data.get('title')}")
            
            listing_data = {
                "title": data.get('title'), "price": data.get('price'),
                "description": data.get('description', ''), "location": data.get('location', 'Inconnue'),
                "imageUrls": data.get('imageUrls', []), "imageUrl": data.get('imageUrl'),
                "link": data.get('link'), "id": doc.id,
                **({'latitude': data['latitude'], 'longitude': data['longitude']} if 'latitude' in data else {})
            }
            
            analysis = self.analyzer.analyze_deal(listing_data)
            self.repo.save_deal(doc.id, listing_data, analysis)

    def reanalyze_all_listings(self):
        if self.offline_mode: return
        self.repo.mark_all_for_reanalysis()

def monitor_retries(bot):
    logger.info("Retry queue monitoring thread started.")
    while True:
        try:
            bot.process_retry_queue()
            time.sleep(5)
        except Exception as e:
            logger.error(f"Error in retry monitoring thread: {e}", exc_info=True)
            time.sleep(10)

def main_loop(bot):
    logger.info("--- Starting Main Loop ---")
    bot.run_scan() # Run initial scan

    scheduler = TaskScheduler(
        scan_func=bot.run_scan,
        cleanup_func=bot.cleanup_sold_listings,
        initial_frequency=bot.config_manager.get_valid_scan_frequency()
    )

    while True:
        try:
            scheduler.run_pending()
            
            sync_result = bot.sync_and_apply_config()
            
            if sync_result.specific_url:
                logger.info(f"Received command to scan specific URL: {sync_result.specific_url}")
                bot.scan_specific_url(sync_result.specific_url)

            if sync_result.should_cleanup:
                logger.info("Received command to force cleanup.")
                bot.cleanup_sold_listings()
                bot.repo.consume_command('forceCleanup')

            if sync_result.should_reanalyze_all:
                logger.info("Received command to force re-analyze all.")
                bot.reanalyze_all_listings()
                bot.repo.consume_command('forceReanalyzeAll')
                
            if sync_result.should_refresh:
                logger.info("Received command to force refresh.")
                bot.run_scan()
                bot.repo.consume_command('forceRefresh')
                
            if sync_result.new_scan_frequency is not None:
                scheduler.update_scan_frequency(sync_result.new_scan_frequency)

            time.sleep(5)
        except Exception as e:
            logger.error(f"An error occurred in the main loop: {e}", exc_info=True)
            time.sleep(15)

if __name__ == "__main__":
    logger.info(f"Default prompt instruction loaded: {PROMPT_INSTRUCTION[:80]}...")
    bot = GuitarHunterBot(db, offline_mode)

    if bot.offline_mode:
        logger.warning("Exiting due to offline mode.")
        sys.exit(1)
    
    threading.Thread(target=monitor_retries, args=(bot,), daemon=True).start()
    
    try:
        main_loop(bot)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down.")
    except Exception as e:
        logger.critical(f"A critical error occurred that could not be handled: {e}", exc_info=True)
        sys.exit(1)
