import sys
import time
import threading
import logging
from firebase_admin import firestore

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)
# --- End Logging Configuration ---

# --- IMPORT DE LA CONFIGURATION CENTRALISÉE ---
from config import (
    FIREBASE_KEY_PATH, APP_ID_TARGET, USER_ID_TARGET, CITY_COORDINATES,
    PROMPT_INSTRUCTION, DEFAULT_VERDICT_RULES, DEFAULT_REASONING_INSTRUCTION,
    DEFAULT_USER_PROMPT, DEFAULT_EXCLUSION_KEYWORDS,
    DEFAULT_MAIN_PROMPT, DEFAULT_GATEKEEPER_INSTRUCTION, DEFAULT_EXPERT_CONTEXT
)
from backend.database import DatabaseService
from backend.analyzer import DealAnalyzer
from backend.scraping import FacebookScraper, ListingParser
from backend.scraping.city_finder import CityFinder
from backend.repository import FirestoreRepository
from backend.services import ConfigManager, TaskScheduler
from backend.notifications import NotificationService

# --- INITIALISATION DE LA DB ---
db_service = DatabaseService(FIREBASE_KEY_PATH)
db = db_service.db
offline_mode = db_service.offline_mode
# --- FIN DE L'INITIALISATION ---

class GuitarHunterBot:
    def __init__(self, db_client, is_offline):
        self.offline_mode = is_offline
        self.session_processed_ids = set() # Cache pour éviter les doublons durant un scan

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
            'prompt': PROMPT_INSTRUCTION, # Legacy
            'verdictRules': DEFAULT_VERDICT_RULES, # Legacy
            'reasoningInstruction': DEFAULT_REASONING_INSTRUCTION, # Legacy
            'userPrompt': DEFAULT_USER_PROMPT, # Legacy
            'exclusionKeywords': DEFAULT_EXCLUSION_KEYWORDS,
            'scanConfig': initial_scan_config,
            'botStatus': 'idle',
            'analysisConfig': {
                'gatekeeperModel': 'gemini-3-flash',
                'expertModel': 'gemini-2.5-flash',
                'mainAnalysisPrompt': DEFAULT_MAIN_PROMPT,
                'gatekeeperVerbosityInstruction': DEFAULT_GATEKEEPER_INSTRUCTION,
                'expertContextInstruction': DEFAULT_EXPERT_CONTEXT
            }
        }
        self.repo.ensure_initial_structure(initial_config)

    def sync_and_apply_config(self, initial=False):
        """Synchronise la configuration et met à jour les composants dépendants."""
        if self.offline_mode: return
        
        sync_result = self.config_manager.sync_with_firestore(initial=initial)
        return sync_result

    def load_cities_from_firestore(self):
        if self.offline_mode: return
        docs = self.repo.get_cities()
        
        self.city_mapping = {}
        self.allowed_cities = []
        
        for doc in docs:
            data = doc.to_dict()
            name = data.get('name')
            city_id = data.get('id')
            is_scannable = data.get('isScannable')

            if name and city_id and is_scannable:
                norm_name = ListingParser.normalize_city_name(name)
                self.city_mapping[norm_name] = city_id
                self.allowed_cities.append(norm_name)

        self.scraper.city_mapping = self.city_mapping
        self.scraper.allowed_cities = self.allowed_cities
        
        logger.info(f"{len(self.city_mapping)} scannable cities loaded. {len(self.allowed_cities)} total allowed cities (whitelist).")

    def should_skip_deal(self, deal_id, price):
        """Vérifie si une annonce doit être ignorée (déjà traitée et inchangée)."""
        # 1. Vérification rapide dans le cache de session (évite les doublons inter-villes immédiats)
        if deal_id in self.session_processed_ids:
            return True

        if self.offline_mode: return False
        
        # 2. Vérification dans la base de données
        existing_deal = self.repo.get_deal_by_id(deal_id)
        if not existing_deal:
            return False
            
        # Si l'annonce a été rejetée, on l'ignore
        if existing_deal.get('status') == 'rejected':
            self.session_processed_ids.add(deal_id)
            return True
            
        # Si le prix est identique, on l'ignore (pas de mise à jour nécessaire)
        try:
            if int(existing_deal.get('price', -1)) == int(price):
                self.session_processed_ids.add(deal_id)
                return True
        except (ValueError, TypeError):
            pass
            
        return False

    def _check_exclusion(self, listing_data, config):
        """
        Vérifie si l'annonce doit être exclue selon les mots-clés.
        Retourne le mot-clé trouvé ou None.
        """
        exclusion_keywords = config.get('exclusionKeywords', DEFAULT_EXCLUSION_KEYWORDS)
        
        if isinstance(exclusion_keywords, str):
             exclusion_keywords = [k.strip() for k in exclusion_keywords.split('\n') if k.strip()]
        
        if not exclusion_keywords:
            return None

        title = listing_data.get('title', '')
        description = listing_data.get('description', '')
        text_to_check = (title + " " + description).lower()
        
        for keyword in exclusion_keywords:
            if keyword.lower() in text_to_check:
                return keyword
        return None

    def _create_rejection_analysis(self, keyword):
        """Crée un objet d'analyse pour un rejet automatique."""
        return {
            "verdict": "rejected",
            "score": 0,
            "reason": f"REJET AUTOMATIQUE : Le mot-clé '{keyword}' a été détecté dans l'annonce.",
            "model_used": "pre-filter"
        }

    def handle_deal_found(self, listing_data):
        logger.info(f"Processing new deal: {listing_data['title']}")
        
        self.session_processed_ids.add(listing_data['id'])
        
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

        current_config = self.config_manager.current_config_snapshot
        
        # --- PRÉ-FILTRAGE ---
        found_keyword = self._check_exclusion(listing_data, current_config)
        
        if found_keyword:
            logger.info(f"Deal rejected by pre-filter. Keyword found: '{found_keyword}' in '{listing_data['title']}'")
            rejection_analysis = self._create_rejection_analysis(found_keyword)
            
            if not self.offline_mode:
                self.repo.save_deal(listing_data['id'], listing_data, rejection_analysis)
            return 

        analysis = self.analyzer.analyze_deal(listing_data, firestore_config=current_config)
        
        NotificationService.notify_deal(listing_data, analysis)
        
        if not self.offline_mode:
            self.repo.save_deal(listing_data['id'], listing_data, analysis)

    def run_scan(self):
        if not self.offline_mode:
            self.repo.update_bot_status('scanning')
        
        self.session_processed_ids = set()
        
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
                    city_specific_config['location'] = city_norm_name
                    
                    logger.info(f"--- Scanning city: {city_norm_name} ---")
                    self.scraper.scan_marketplace(
                        city_specific_config, 
                        self.handle_deal_found,
                        should_skip_callback=self.should_skip_deal
                    )
                    time.sleep(2)

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
            
            current_config = self.config_manager.current_config_snapshot
            
            # --- PRÉ-FILTRAGE ---
            found_keyword = self._check_exclusion(listing_data, current_config)
            
            if found_keyword:
                logger.info(f"Retry deal rejected by pre-filter. Keyword found: '{found_keyword}'")
                rejection_analysis = self._create_rejection_analysis(found_keyword)
                self.repo.save_deal(doc.id, listing_data, rejection_analysis)
                continue 

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

    def add_city_auto(self, city_name):
        """Tente de trouver l'ID d'une ville et de l'ajouter à Firestore."""
        if self.offline_mode: return
        
        logger.info(f"Tentative d'ajout automatique de la ville: {city_name}")
        
        city_id = CityFinder.find_city_id(self.scraper, city_name)
        
        if city_id:
            logger.info(f"ID trouvé pour {city_name}: {city_id}. Ajout à Firestore...")
            try:
                self.repo.cities_ref.add({
                    'name': city_name,
                    'id': city_id,
                    'isScannable': True,
                    'createdAt': firestore.SERVER_TIMESTAMP
                })
                logger.info(f"Ville {city_name} ajoutée avec succès.")
                return True
            except Exception as e:
                logger.error(f"Erreur lors de l'ajout de la ville {city_name}: {e}")
                raise e 
        else:
            logger.warning(f"Impossible de trouver l'ID pour la ville {city_name}.")
            raise Exception(f"Impossible de trouver l'ID Facebook pour la ville '{city_name}'.")

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
    
    bot.scraper.start_session()
    
    command_handlers = {
        'REFRESH': lambda _: bot.run_scan(),
        'CLEANUP': lambda _: bot.cleanup_sold_listings(),
        'REANALYZE_ALL': lambda _: bot.reanalyze_all_listings(),
        'SCAN_URL': lambda url: bot.scan_specific_url(url),
        'ADD_CITY': lambda city_name: bot.add_city_auto(city_name)
    }

    try:
        scheduler = TaskScheduler(
            scan_func=bot.run_scan,
            cleanup_func=bot.cleanup_sold_listings,
            initial_frequency=bot.config_manager.get_valid_scan_frequency()
        )

        while True:
            try:
                scheduler.run_pending()
                
                sync_result = bot.sync_and_apply_config()
                
                for command in sync_result.commands:
                    logger.info(f"Received command: {command.type} (ID: {command.command_id})")
                    handler = command_handlers.get(command.type)
                    
                    if handler:
                        try:
                            handler(command.payload)
                            
                            if command.command_id:
                                bot.repo.mark_command_completed(command.command_id)
                            elif command.firestore_field:
                                bot.repo.consume_command(command.firestore_field)
                                
                        except Exception as e:
                            logger.error(f"Error executing command {command.type}: {e}", exc_info=True)
                            if command.command_id:
                                bot.repo.mark_command_failed(command.command_id, str(e))
                    else:
                        logger.warning(f"Unknown command type: {command.type}")
                        if command.command_id:
                            bot.repo.mark_command_failed(command.command_id, f"Unknown command type: {command.type}")

                if sync_result.new_scan_frequency is not None:
                    scheduler.update_scan_frequency(sync_result.new_scan_frequency)

                time.sleep(5)
            except Exception as e:
                logger.error(f"An error occurred in the main loop: {e}", exc_info=True)
                time.sleep(15)
    finally:
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
