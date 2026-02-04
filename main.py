import sys
import time
import threading
import logging
import schedule

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

# --- Librairies Externes ---
from firebase_admin import firestore

# --- NOUVELLE INITIALISATION DE LA DB ---
db_service = DatabaseService(FIREBASE_KEY_PATH)
db = db_service.db
offline_mode = db_service.offline_mode
# --- FIN DE LA NOUVELLE INITIALISATION ---

class GuitarHunterBot:
    def __init__(self, db_client, is_offline, prompt_instruction=PROMPT_INSTRUCTION):
        self.offline_mode = is_offline
        if self.offline_mode:
            logger.warning("Offline mode is enabled. Bot will not connect to Firestore.")
            self.analyzer = DealAnalyzer()
            self.scraper = FacebookScraper(CITY_COORDINATES, {})
            self.scan_config = {}
            return

        self.db = db_client
        self.repo = FirestoreRepository(db, APP_ID_TARGET, USER_ID_TARGET)
        
        self.analyzer = DealAnalyzer()
        self.scraper = FacebookScraper(CITY_COORDINATES, {})
        
        # Default configurations
        self.prompt_instruction = prompt_instruction
        self.verdict_rules = DEFAULT_VERDICT_RULES
        self.reasoning_instruction = DEFAULT_REASONING_INSTRUCTION
        self.user_prompt_template = DEFAULT_USER_PROMPT
        self.analyzer.update_prompt_template(self.user_prompt_template)

        self.scan_config = {
            "max_ads": 5, "frequency": 60, "location": "montreal", "distance": 60,
            "min_price": 0, "max_price": 150, "search_query": "electric guitar"
        }
        self.last_refresh_timestamp = 0
        self.last_cleanup_timestamp = 0
        self.last_reanalyze_all_timestamp = 0
        self.city_mapping = {}
        
        self.is_cleaning = False
        self.cleanup_lock = threading.Lock()

        logger.info("--- Bot Configuration ---")
        logger.info(f"APP ID: {APP_ID_TARGET}")
        logger.info(f"USER ID: {USER_ID_TARGET}")
        
        if CITY_COORDINATES:
             logger.info(f"{len(CITY_COORDINATES)} city coordinates loaded.")

        self._init_firestore_structure()
        self.sync_configuration(initial=True)

    def _init_firestore_structure(self):
        initial_config = {
            'prompt': self.prompt_instruction,
            'verdictRules': self.verdict_rules,
            'reasoningInstruction': self.reasoning_instruction,
            'userPrompt': self.user_prompt_template,
            'scanConfig': self.scan_config
        }
        self.repo.ensure_initial_structure(initial_config)

    def load_cities_from_firestore(self):
        if self.offline_mode: return
        docs = self.repo.get_cities()
        new_mapping = {}
        count = 0
        for doc in docs:
            data = doc.to_dict()
            if 'name' in data and 'id' in data:
                norm_name = self.scraper._normalize_city_name(data['name'])
                new_mapping[norm_name] = data['id']
                count += 1
        
        self.city_mapping = new_mapping
        self.scraper.city_mapping = new_mapping
        logger.info(f"{count} cities loaded from Firestore.")

    def sync_configuration(self, initial=False):
        if self.offline_mode: return False, False, False, None
        
        config_data = self.repo.get_user_config()
        if not config_data:
            return False, False, False, None

        should_refresh, should_cleanup, should_reanalyze_all = False, False, False
        
        def join_if_list(value):
            return "\n".join(value) if isinstance(value, list) else value

        if 'userPrompt' in config_data:
            new_template = join_if_list(config_data['userPrompt'])
            if new_template != self.user_prompt_template:
                self.user_prompt_template = new_template
                self.analyzer.update_prompt_template(new_template)
                logger.info("User prompt template updated.")

        if 'scanConfig' in config_data:
            self.scan_config.update(config_data['scanConfig'])

        if 'forceRefresh' in config_data:
            lr = config_data['forceRefresh']
            if not initial and lr != self.last_refresh_timestamp:
                self.last_refresh_timestamp = lr
                should_refresh = True
            elif initial: self.last_refresh_timestamp = lr

        if 'forceCleanup' in config_data:
            lc = config_data['forceCleanup']
            if not initial and lc != self.last_cleanup_timestamp:
                self.last_cleanup_timestamp = lc
                should_cleanup = True
            elif initial: self.last_cleanup_timestamp = lc
        
        if 'forceReanalyzeAll' in config_data:
            lra = config_data['forceReanalyzeAll']
            if not initial and lra != self.last_reanalyze_all_timestamp:
                self.last_reanalyze_all_timestamp = lra
                should_reanalyze_all = True
            elif initial: self.last_reanalyze_all_timestamp = lra

        specific_url = config_data.get('scanSpecificUrl')

        return should_refresh, should_cleanup, should_reanalyze_all, specific_url

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
        logger.info(f"Starting scheduled scan (frequency: {self.scan_config.get('frequency', 'N/A')} min)...")
        self.load_cities_from_firestore()
        self.scraper.scan_marketplace(self.scan_config, self.handle_deal_found)
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
                "link": data.get('link'), "id": doc.id
            }
            if data.get('latitude'):
                listing_data['latitude'] = data['latitude']
                listing_data['longitude'] = data['longitude']
            
            analysis = self.analyzer.analyze_deal(listing_data)
            self.repo.save_deal(doc.id, listing_data, analysis)

    def reanalyze_all_listings(self):
        if self.offline_mode: return
        self.repo.mark_all_for_reanalysis()

def get_valid_scan_frequency(bot):
    """Gets a validated scan frequency from the bot's config."""
    try:
        freq = int(bot.scan_config.get('frequency', 60))
        if freq > 0:
            return freq
    except (ValueError, TypeError):
        pass
    logger.warning("Invalid scan frequency detected. Using default of 60 minutes.")
    return 60

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
    bot.run_scan()

    scan_frequency = get_valid_scan_frequency(bot)
    schedule.every(scan_frequency).minutes.do(bot.run_scan).tag('scan')
    schedule.every(24).hours.do(bot.cleanup_sold_listings)

    while True:
        try:
            schedule.run_pending()
            
            should_refresh, should_cleanup, should_reanalyze_all, specific_url = bot.sync_configuration()
            
            if specific_url:
                logger.info(f"Received command to scan specific URL: {specific_url}")
                bot.scan_specific_url(specific_url)

            if should_cleanup:
                logger.info("Received command to force cleanup.")
                bot.cleanup_sold_listings()
                bot.repo.consume_command('forceCleanup')

            if should_reanalyze_all:
                logger.info("Received command to force re-analyze all.")
                bot.reanalyze_all_listings()
                bot.repo.consume_command('forceReanalyzeAll')
                
            if should_refresh:
                logger.info("Received command to force refresh.")
                bot.run_scan()
                bot.repo.consume_command('forceRefresh')
                
                new_scan_frequency = get_valid_scan_frequency(bot)
                if new_scan_frequency != scan_frequency:
                    scan_frequency = new_scan_frequency
                    schedule.clear('scan')
                    schedule.every(scan_frequency).minutes.do(bot.run_scan).tag('scan')
                    logger.info(f"Rescheduled scan to every {scan_frequency} minutes.")

            time.sleep(5)
        except Exception as e:
            logger.error(f"An error occurred in the main loop: {e}", exc_info=True)
            # Don't exit on non-critical errors, just log and continue
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
