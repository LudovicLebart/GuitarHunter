import time
import threading
import logging
from firebase_admin import firestore

from config import (
    APP_ID_TARGET, USER_ID_TARGET, CITY_COORDINATES,
    DEFAULT_EXCLUSION_KEYWORDS, DEFAULT_MAIN_PROMPT, 
    DEFAULT_GATEKEEPER_INSTRUCTION, DEFAULT_EXPERT_CONTEXT,
    GEMINI_MODELS
)
from backend.analyzer import DealAnalyzer
from backend.scraping import FacebookScraper, ListingParser
from backend.scraping.city_finder import CityFinder
from backend.repository import FirestoreRepository
from backend.services import ConfigManager
from backend.notifications import NotificationService

logger = logging.getLogger(__name__)

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
        return {"verdict": "REJECTED", "reasoning": f"REJET AUTOMATIQUE : Mot-clé '{keyword}' détecté.", "model_used": "pre-filter"}

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
            cities_to_scan = [doc.to_dict() for doc in cities_docs if doc.to_dict().get('isScannable')]

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
