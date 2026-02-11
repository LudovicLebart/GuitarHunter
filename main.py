import sys
import time
import threading
import logging
from firebase_admin import firestore

# --- IMPORT DE LA CONFIGURATION CENTRALISÉE ---
from config import (
    FIREBASE_KEY_PATH, APP_ID_TARGET, USER_ID_TARGET, CITY_COORDINATES,
    DEFAULT_EXCLUSION_KEYWORDS, DEFAULT_MAIN_PROMPT, 
    DEFAULT_GATEKEEPER_INSTRUCTION, DEFAULT_EXPERT_CONTEXT,
    GEMINI_MODELS
)
from backend.database import DatabaseService
from backend.analyzer import DealAnalyzer
from backend.scraping import FacebookScraper, ListingParser
from backend.scraping.city_finder import CityFinder
from backend.repository import FirestoreRepository
from backend.services import ConfigManager, TaskScheduler
from backend.notifications import NotificationService

# --- 1. INITIALISATION DE LA DB ---
db_service = DatabaseService(FIREBASE_KEY_PATH)
db = db_service.db
offline_mode = db_service.offline_mode

# --- 2. CONFIGURATION DU LOGGING ---
class FirestoreHandler(logging.Handler):
    def __init__(self, db_client, app_id, user_id):
        super().__init__()
        self.internal_logger = logging.getLogger('FirestoreHandlerInternal')
        self.internal_logger.propagate = False
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - [FirestoreHandler] - %(levelname)s - %(message)s'))
        self.internal_logger.addHandler(console_handler)
        self.internal_logger.setLevel(logging.INFO)

        if not db_client:
            self.db = None
            self.internal_logger.warning("Database client is not initialized. Handler will be disabled.")
            return
        self.db = db_client
        self.logs_ref = self.db.collection('artifacts').document(app_id) \
            .collection('users').document(user_id).collection('logs')
        
        self.buffer = []
        self.buffer_lock = threading.Lock()
        self.flush_interval = 3.0
        self.stop_event = threading.Event()
        self.flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.flush_thread.start()
        self.internal_logger.info("Handler initialized and flush thread started.")

    def emit(self, record):
        if not self.db:
            return
        try:
            log_entry = self.format(record)
            data = {
                'message': log_entry,
                'level': record.levelname,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'createdAt': time.time()
            }
            with self.buffer_lock:
                self.buffer.append(data)
        except Exception:
            self.handleError(record)

    def _flush_loop(self):
        while not self.stop_event.is_set():
            try:
                time.sleep(self.flush_interval)
                self.flush()
            except Exception as e:
                self.internal_logger.critical(f"Unhandled exception in flush loop: {e}", exc_info=True)

    def flush(self):
        if not self.db: return
        
        with self.buffer_lock:
            if not self.buffer:
                return
            logs_to_send = self.buffer[:]
            self.buffer = []
        
        if logs_to_send:
            self.internal_logger.info(f"Flushing {len(logs_to_send)} log(s) to Firestore.")
            batch_size = 450 
            for i in range(0, len(logs_to_send), batch_size):
                batch = self.db.batch()
                chunk = logs_to_send[i:i + batch_size]
                for log_data in chunk:
                    doc_ref = self.logs_ref.document()
                    batch.set(doc_ref, log_data)
                
                try:
                    batch.commit()
                except Exception as e:
                    self.internal_logger.error(f"Failed to flush logs to Firestore: {e}")

    def close(self):
        self.internal_logger.info("Close called. Stopping flush thread and performing final flush.")
        self.stop_event.set()
        if self.flush_thread.is_alive():
            self.flush_thread.join(timeout=1.0)
        self.flush()
        super().close()

# Configure the root logger to capture logs from the entire application
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.handlers = [] 

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Firestore handler
if not offline_mode:
    firestore_handler = FirestoreHandler(db, APP_ID_TARGET, USER_ID_TARGET)
    firestore_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(firestore_handler)
else:
    logger.warning("Mode hors ligne, le logger Firestore n'est pas activé.")


# --- 3. CLASSE PRINCIPALE DU BOT ---
class GuitarHunterBot:
    def __init__(self, db_client, is_offline):
        self.offline_mode = is_offline
        self.session_processed_ids = set()

        if self.offline_mode:
            logger.warning("Le bot est en mode hors ligne.")
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
        
        self.is_cleaning = False
        self.cleanup_lock = threading.Lock()

        logger.info("--- Configuration du Bot Terminée ---")
        logger.info(f"APP ID: {APP_ID_TARGET}")
        logger.info(f"USER ID: {USER_ID_TARGET}")
        
        if CITY_COORDINATES:
             logger.info(f"{len(CITY_COORDINATES)} city coordinates loaded.")

        self._init_firestore_structure(initial_scan_config)
        self.sync_and_apply_config(initial=True)

    def _init_firestore_structure(self, initial_scan_config):
        initial_config = {
            'exclusionKeywords': DEFAULT_EXCLUSION_KEYWORDS,
            'scanConfig': initial_scan_config,
            'botStatus': 'idle',
            'analysisConfig': {
                'gatekeeperModel': GEMINI_MODELS["default_gatekeeper"],
                'expertModel': GEMINI_MODELS["default_expert"],
                'mainAnalysisPrompt': DEFAULT_MAIN_PROMPT,
                'gatekeeperVerbosityInstruction': DEFAULT_GATEKEEPER_INSTRUCTION,
                'expertContextInstruction': DEFAULT_EXPERT_CONTEXT
            },
            'availableModels': GEMINI_MODELS["available"]
        }
        self.repo.ensure_initial_structure(initial_config)

    def sync_and_apply_config(self, initial=False):
        if self.offline_mode: return
        sync_result = self.config_manager.sync_with_firestore(initial=initial)
        return sync_result

    def should_skip_deal(self, deal_id, price):
        if deal_id in self.session_processed_ids: return True
        if self.offline_mode: return False
        existing_deal = self.repo.get_deal_by_id(deal_id)
        if not existing_deal: return False
        if existing_deal.get('status') == 'rejected':
            self.session_processed_ids.add(deal_id)
            return True
        try:
            if int(existing_deal.get('price', -1)) == int(price):
                self.session_processed_ids.add(deal_id)
                return True
        except (ValueError, TypeError): pass
        return False

    def _check_exclusion(self, listing_data, config):
        exclusion_keywords = config.get('exclusionKeywords', DEFAULT_EXCLUSION_KEYWORDS)
        if isinstance(exclusion_keywords, str):
             exclusion_keywords = [k.strip() for k in exclusion_keywords.split('\n') if k.strip()]
        if not exclusion_keywords: return None
        text_to_check = (listing_data.get('title', '') + " " + listing_data.get('description', '')).lower()
        for keyword in exclusion_keywords:
            if keyword.lower() in text_to_check: return keyword
        return None

    def _create_rejection_analysis(self, keyword):
        return {"verdict": "rejected", "score": 0, "reason": f"REJET AUTOMATIQUE : Mot-clé '{keyword}' détecté.", "model_used": "pre-filter"}

    def handle_deal_found(self, listing_data):
        logger.info(f"Traitement de la nouvelle annonce : {listing_data['title']}")
        self.session_processed_ids.add(listing_data['id'])
        
        is_update = False
        if not self.offline_mode:
            existing_deal = self.repo.get_deal_by_id(listing_data['id'])
            if existing_deal:
                if existing_deal.get('status') == 'rejected':
                    logger.info("Annonce déjà rejetée. Ignorée.")
                    return
                if existing_deal.get('price') == listing_data['price']:
                    logger.info("Annonce déjà existante avec le même prix. Ignorée.")
                    return
                logger.info("Annonce existante mais prix différent. Mise à jour.")
                is_update = True

        current_config = self.config_manager.current_config_snapshot
        found_keyword = self._check_exclusion(listing_data, current_config)
        
        if found_keyword:
            logger.info(f"Annonce rejetée par pré-filtrage. Mot-clé : '{found_keyword}'")
            rejection_analysis = self._create_rejection_analysis(found_keyword)
            if not self.offline_mode:
                if is_update:
                    self.repo.update_deal_analysis(listing_data['id'], rejection_analysis)
                else:
                    self.repo.create_new_deal(listing_data['id'], listing_data, rejection_analysis)
            return

        analysis = self.analyzer.analyze_deal(listing_data, firestore_config=current_config)
        NotificationService.notify_deal(listing_data, analysis)
        
        if not self.offline_mode:
            if is_update:
                self.repo.update_deal_analysis(listing_data['id'], analysis)
            else:
                self.repo.create_new_deal(listing_data['id'], listing_data, analysis)

    def run_scan(self):
        if self.offline_mode: return
        self.repo.update_bot_status('scanning')
        self.session_processed_ids = set()
        try:
            scan_config = self.config_manager.scan_config
            logger.info(f"Démarrage du scan planifié (fréq: {scan_config.get('frequency', 'N/A')} min)...")
            
            cities_docs = self.repo.get_cities()
            cities_to_scan = []
            for doc in cities_docs:
                data = doc.to_dict()
                if data.get('isScannable') and data.get('name') and data.get('id'):
                    cities_to_scan.append(data)

            if not cities_to_scan:
                logger.warning("Aucune ville scannable configurée. Scan ignoré.")
            else:
                logger.info(f"Scan de {len(cities_to_scan)} villes : {', '.join([c['name'] for c in cities_to_scan])}")
                for city_data in cities_to_scan:
                    city_name = city_data['name']
                    city_id = city_data['id']
                    city_norm_name = ListingParser.normalize_city_name(city_name)
                    
                    self.scraper.city_mapping = {city_norm_name: city_id}
                    self.scraper.allowed_cities = [city_norm_name]

                    city_specific_config = scan_config.copy()
                    city_specific_config['location'] = city_norm_name
                    logger.info(f"--- Scan de la ville : {city_name} ({city_id}) ---")
                    self.scraper.scan_marketplace(city_specific_config, self.handle_deal_found, self.should_skip_deal)
                    time.sleep(2)
            logger.info("Scan planifié terminé.")
        finally:
            if not self.offline_mode: self.repo.update_bot_status('idle')

    def scan_specific_url(self, url):
        if self.offline_mode: return
        self.repo.update_bot_status('scanning_url')
        try:
            self.scraper.scan_specific_url(url, self.handle_deal_found)
            if not self.offline_mode: self.repo.consume_command('scanSpecificUrl')
        finally:
            if not self.offline_mode: self.repo.update_bot_status('idle')

    def cleanup_sold_listings(self):
        if self.offline_mode or self.is_cleaning: return
        logger.info("Démarrage du nettoyage des annonces vendues...")
        threading.Thread(target=self._perform_cleanup, daemon=True).start()

    def _perform_cleanup(self):
        with self.cleanup_lock:
            self.is_cleaning = True
            if not self.offline_mode: self.repo.update_bot_status('cleaning')
            try:
                docs = self.repo.get_active_listings()
                listings = [{'id': d.id, 'url': d.to_dict().get('link')} for d in docs]
                logger.info(f"Vérification de la disponibilité de {len(listings)} annonces actives.")
                deleted_count = 0
                for item in listings:
                    if not item['url']: continue
                    if not self.scraper.check_listing_availability(item['url']):
                        self.repo.delete_listing(item['id'])
                        deleted_count += 1
                    time.sleep(0.5)
                logger.info(f"Nettoyage terminé. {deleted_count} annonces supprimées.")
            except Exception as e:
                logger.error(f"Erreur durant le nettoyage : {e}", exc_info=True)
            finally:
                self.is_cleaning = False
                if not self.offline_mode: self.repo.update_bot_status('idle')

    def analyze_single_deal(self, payload):
        deal_id = payload.get('dealId')
        force_expert = payload.get('forceExpert', False)

        if not deal_id:
            raise ValueError("dealId manquant dans le payload de la commande ANALYZE_DEAL")

        deal_data = self.repo.get_deal_by_id(deal_id)
        if not deal_data:
            raise FileNotFoundError(f"Annonce {deal_id} non trouvée pour l'analyse.")

        logger.info(f"--- ANALYSE DÉMARRÉE pour {deal_data.get('title')} ---")
        
        try:
            new_status = 'analyzing_expert' if force_expert else 'analyzing'
            self.repo.update_deal_status(deal_id, new_status)

            current_config = self.config_manager.current_config_snapshot
            
            found_keyword = self._check_exclusion(deal_data, current_config)
            if found_keyword:
                logger.info(f"Annonce rejetée par pré-filtrage. Mot-clé : '{found_keyword}'")
                rejection_analysis = self._create_rejection_analysis(found_keyword)
                self.repo.update_deal_analysis(deal_id, rejection_analysis)
                return

            analysis_result = self.analyzer.analyze_deal(deal_data, firestore_config=current_config, force_expert=force_expert)
            
            self.repo.update_deal_analysis(deal_id, analysis_result)

        except Exception as e:
            logger.error(f"CRITIQUE: Échec de l'analyse de {deal_id}. Erreur: {e}", exc_info=True)
            self.repo.update_deal_status(deal_id, 'analysis_failed', str(e))
            raise
        finally:
            logger.info(f"--- ANALYSE TERMINÉE pour {deal_id} ---")

    def reanalyze_all_listings(self):
        if self.offline_mode: return
        self.repo.update_bot_status('reanalyzing_all')
        try:
            self.repo.mark_all_for_reanalysis()
        finally:
            if not self.offline_mode: self.repo.update_bot_status('idle')

    def add_city_auto(self, city_name):
        if self.offline_mode: return
        logger.info(f"Tentative d'ajout automatique de la ville: {city_name}")
        
        existing_cities = self.repo.get_cities()
        for doc in existing_cities:
            data = doc.to_dict()
            if data.get('name', '').lower() == city_name.lower():
                raise Exception(f"La ville '{city_name}' existe déjà.")

        city_id = CityFinder.find_city_id(self.scraper, city_name)
        if city_id:
            for doc in existing_cities:
                if str(doc.to_dict().get('id')) == str(city_id):
                     raise Exception(f"Une ville avec l'ID {city_id} existe déjà ({doc.to_dict().get('name')}).")

            logger.info(f"ID trouvé pour {city_name}: {city_id}. Ajout à Firestore...")
            try:
                self.repo.cities_ref.add({'name': city_name, 'id': city_id, 'isScannable': True, 'createdAt': firestore.SERVER_TIMESTAMP})
                logger.info(f"Ville {city_name} ajoutée avec succès.")
                return True
            except Exception as e:
                logger.error(f"Erreur lors de l'ajout de la ville {city_name}: {e}")
                raise e 
        else:
            logger.warning(f"Impossible de trouver l'ID pour la ville {city_name}.")
            raise Exception(f"Impossible de trouver l'ID Facebook pour la ville '{city_name}'.")

    def clear_logs(self, _=None):
        if self.offline_mode:
            logger.warning("Cannot clear logs in offline mode.")
            return
        logger.info("--- COMMANDE REÇUE : Effacement des logs ---")
        try:
            deleted_count = self.repo.delete_all_logs()
            logger.info(f"--- {deleted_count} logs ont été supprimés avec succès. ---")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression des logs: {e}", exc_info=True)
            raise

def main_loop(bot):
    logger.info("--- Démarrage de la boucle principale ---")
    bot.scraper.start_session()
    command_handlers = {
        'REFRESH': lambda _: bot.run_scan(),
        'CLEANUP': lambda _: bot.cleanup_sold_listings(),
        'REANALYZE_ALL': lambda _: bot.reanalyze_all_listings(),
        'SCAN_URL': lambda url: bot.scan_specific_url(url),
        'ADD_CITY': lambda city_name: bot.add_city_auto(city_name),
        'ANALYZE_DEAL': lambda payload: bot.analyze_single_deal(payload),
        'CLEAR_LOGS': lambda _: bot.clear_logs()
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
                    logger.info(f"Commande reçue : {command.type} (ID: {command.command_id})")
                    handler = command_handlers.get(command.type)
                    if handler:
                        try:
                            handler(command.payload)
                            if command.command_id: bot.repo.mark_command_completed(command.command_id)
                            elif command.firestore_field: bot.repo.consume_command(command.firestore_field)
                        except Exception as e:
                            logger.error(f"Erreur exécution commande {command.type}: {e}", exc_info=True)
                            if command.command_id: bot.repo.mark_command_failed(command.command_id, str(e))
                    else:
                        logger.warning(f"Type de commande inconnu : {command.type}")
                        if command.command_id: bot.repo.mark_command_failed(command.command_id, f"Type de commande inconnu : {command.type}")
                if sync_result.new_scan_frequency is not None:
                    scheduler.update_scan_frequency(sync_result.new_scan_frequency)
                time.sleep(5)
            except Exception as e:
                logger.error(f"Erreur dans la boucle principale : {e}", exc_info=True)
                time.sleep(15)
    finally:
        bot.scraper.close_session()
        if not bot.offline_mode and 'firestore_handler' in globals():
             firestore_handler.close()

if __name__ == "__main__":
    bot = GuitarHunterBot(db, offline_mode)
    if bot.offline_mode:
        logger.warning("Sortie en raison du mode hors ligne.")
        sys.exit(1)

    try:
        main_loop(bot)
    except KeyboardInterrupt:
        logger.info("Interruption clavier reçue. Arrêt.")
    except Exception as e:
        logger.critical(f"Erreur critique non gérée : {e}", exc_info=True)
        sys.exit(1)
