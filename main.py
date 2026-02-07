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
# Changement ici : import depuis le nouveau package
from backend.scraping import FacebookScraper, ListingParser
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
        self.repo.update_bot_status('idle')
        self.analyzer = DealAnalyzer()
        self.scraper = FacebookScraper(CITY_COORDINATES, {})
        
        initial_scan_config = {
            "max_ads": 5, "frequency": 60, "location": "montreal",
            "min_price": 0, "max_price": 150, "search_query": "electric guitar"
        }
        
        self.config_manager = ConfigManager(self.repo, initial_scan_config)
        
        self.city_mapping = {}
        self.allowed_cities = [] # Liste des noms de villes autorisées
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
            'scanConfig': initial_scan_config,
            'botStatus': 'idle'
        }
        self.repo.ensure_initial_structure(initial_config)

    def sync_and_apply_config(self, initial=False):
        """Synchronise la configuration et met à jour les composants dépendants."""
        if self.offline_mode: return
        
        sync_result = self.config_manager.sync_with_firestore(initial=initial)
        
        # Note: Plus besoin de mettre à jour manuellement l'analyzer ici,
        # car on lui passera la config complète lors de l'appel à analyze_deal.
        
        return sync_result

    def load_cities_from_firestore(self):
        if self.offline_mode: return
        docs = self.repo.get_cities()
        
        scannable_cities = {}
        all_allowed_cities = []
        
        for doc in docs:
            data = doc.to_dict()
            if 'name' in data:
                all_allowed_cities.append(data['name'])
                
                # Une ville est scannable si elle a un ID et isScannable est True
                if data.get('isScannable') and data.get('id'):
                    norm_name = ListingParser.normalize_city_name(data['name'])
                    scannable_cities[norm_name] = data['id']

        self.city_mapping = scannable_cities
        self.allowed_cities = all_allowed_cities
        
        self.scraper.city_mapping = scannable_cities
        self.scraper.allowed_cities = all_allowed_cities
        
        logger.info(f"{len(scannable_cities)} scannable cities loaded. {len(all_allowed_cities)} total allowed cities.")

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

        # On passe la configuration actuelle (snapshot) à l'analyzer
        current_config = self.config_manager.current_config_snapshot
        analysis = self.analyzer.analyze_deal(listing_data, firestore_config=current_config)
        
        if not self.offline_mode:
            self.repo.save_deal(listing_data['id'], listing_data, analysis)

    def run_scan(self):
        if not self.offline_mode:
            self.repo.update_bot_status('scanning')
        
        try:
            scan_config = self.config_manager.scan_config
            logger.info(f"Starting scheduled scan (frequency: {scan_config.get('frequency', 'N/A')} min)...")
            
            self.load_cities_from_firestore()
            
            cities_to_scan = list(self.city_mapping.keys())
            
            if not cities_to_scan:
                logger.warning("No scannable cities configured. Scan will be skipped.")
            else:
                logger.info(f"Scanning {len(cities_to_scan)} cities: {', '.join(cities_to_scan)}")
                for city_norm_name in cities_to_scan:
                    city_specific_config = scan_config.copy()
                    # Le scraper utilise le nom normalisé pour trouver l'ID dans son mapping
                    city_specific_config['location'] = city_norm_name
                    
                    logger.info(f"--- Scanning city: {city_norm_name} ---")
                    self.scraper.scan_marketplace(city_specific_config, self.handle_deal_found)
                    time.sleep(2) # Pause entre les villes

            logger.info("Scheduled scan finished.")
        finally:
            if not self.offline_mode:
                self.repo.update_bot_status('idle')

    def scan_specific_url(self, url):
        if not self.offline_mode:
            self.repo.update_bot_status('scanning_url')
        
        try:
            self.scraper.scan_specific_url(url, self.handle_deal_found)
            if not self.offline_mode:
                self.repo.consume_command('scanSpecificUrl')
        finally:
            if not self.offline_mode:
                self.repo.update_bot_status('idle')

    def cleanup_sold_listings(self):
        if self.offline_mode or self.is_cleaning: return
        logger.info("Starting cleanup of sold listings...")
        threading.Thread(target=self._perform_cleanup, daemon=True).start()

    def _perform_cleanup(self):
        with self.cleanup_lock:
            self.is_cleaning = True
            if not self.offline_mode:
                self.repo.update_bot_status('cleaning')
            
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
                if not self.offline_mode:
                    self.repo.update_bot_status('idle')

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
            
            # On passe la config actuelle pour la réanalyse
            current_config = self.config_manager.current_config_snapshot
            analysis = self.analyzer.analyze_deal(listing_data, firestore_config=current_config)
            self.repo.save_deal(doc.id, listing_data, analysis)

    def reanalyze_all_listings(self):
        if self.offline_mode: return
        if not self.offline_mode:
            self.repo.update_bot_status('reanalyzing_all')
        
        try:
            self.repo.mark_all_for_reanalysis()
        finally:
            if not self.offline_mode:
                self.repo.update_bot_status('idle')

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
    
    # Démarrage de la session Playwright
    bot.scraper.start_session()
    
    # Command handlers mapping
    command_handlers = {
        'REFRESH': lambda _: bot.run_scan(),
        'CLEANUP': lambda _: bot.cleanup_sold_listings(),
        'REANALYZE_ALL': lambda _: bot.reanalyze_all_listings(),
        'SCAN_URL': lambda url: bot.scan_specific_url(url)
    }

    try:
        # bot.run_scan() # Run initial scan

        scheduler = TaskScheduler(
            scan_func=bot.run_scan,
            cleanup_func=bot.cleanup_sold_listings,
            initial_frequency=bot.config_manager.get_valid_scan_frequency()
        )

        while True:
            try:
                scheduler.run_pending()
                
                sync_result = bot.sync_and_apply_config()
                
                # Traitement des commandes
                for command in sync_result.commands:
                    logger.info(f"Received command: {command.type}")
                    handler = command_handlers.get(command.type)
                    if handler:
                        handler(command.payload)
                        if command.firestore_field:
                            bot.repo.consume_command(command.firestore_field)
                    else:
                        logger.warning(f"Unknown command type: {command.type}")

                if sync_result.new_scan_frequency is not None:
                    scheduler.update_scan_frequency(sync_result.new_scan_frequency)

                time.sleep(5)
            except Exception as e:
                logger.error(f"An error occurred in the main loop: {e}", exc_info=True)
                time.sleep(15)
    finally:
        # Fermeture propre de la session Playwright
        bot.scraper.close_session()

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
