import time
import threading
import logging
import requests
from firebase_admin import firestore
import firebase_admin.auth as fb_auth

from config import (
    APP_ID_TARGET, USER_ID_TARGET,
    DEFAULT_EXCLUSION_KEYWORDS, DEFAULT_MAIN_PROMPT, 
    DEFAULT_GATEKEEPER_INSTRUCTION, DEFAULT_ANALYST_INSTRUCTION, DEFAULT_EXPERT_CONTEXT,
    GEMINI_MODELS, IMAGE_RETENTION_REJECTED_DAYS
)
from backend.analyzer import DealAnalyzer
from backend.scraping import FacebookScraper, ListingParser
from backend.scraping.city_finder import CityFinder
from backend.scraping.utils import calculate_distance, city_name_variants
from backend.repository import FirestoreRepository
from backend.services import ConfigManager
from backend.notifications import NotificationService

class GuitarHunterBot:
    def __init__(self, db_client, storage_bucket=None, is_offline=False, stop_event=None, scan_stop_event=None,
                 app_id=None, user_id=None, browser_semaphore=None):
        self.stop_event = stop_event
        self.scan_stop_event = scan_stop_event
        self.offline_mode = is_offline

        # Support multi-utilisateurs : utiliser les params explicites si fournis, sinon fallback sur config
        self._app_id = app_id or APP_ID_TARGET
        self._user_id = user_id or USER_ID_TARGET

        # Logger isolé par utilisateur pour ne pas mélanger les logs en multi-user
        self.logger = logging.getLogger(f"bot.{self._user_id[:8]}")

        # session_processed_ids isolé par thread via threading.local()
        self._local = threading.local()

        # Sémaphore global Playwright partagé entre tous les bots (limite les navigateurs simultanés)
        self._browser_semaphore = browser_semaphore

        # Gestionnaire d'état robuste
        self._status_lock = threading.Lock()
        self._current_status = 'idle'
        self._active_tasks = set()

        # Email de destination pour les notifications (résolu après init Firebase)
        self._user_email = ''  # Valeur par défaut : notifications email silencieusement désactivées

        if self.offline_mode:
            self.logger.warning("Le bot est en mode hors ligne.")
            self.analyzer = DealAnalyzer()
            self.scraper = FacebookScraper({}, {})
            return

        self.repo = FirestoreRepository(db_client, self._app_id, self._user_id, bucket=storage_bucket)
        self.set_status('idle')
        self.analyzer = DealAnalyzer()

        initial_scan_config = {
            "max_ads": 5, "frequency": 60, "location": "montreal", "distance": 10,
            "min_price": 0, "max_price": 150, "search_query": "electric guitar"
        }

        self.config_manager = ConfigManager(self.repo, initial_scan_config)

        self.is_cleaning = False
        self.cleanup_lock = threading.Lock()

        # Récupération de l'email Firebase Auth pour les notifications
        self._user_email = self._resolve_user_email()

        self.logger.info("--- Configuration du Bot Terminée ---")
        self.logger.info(f"APP ID: {self._app_id}")
        self.logger.info(f"USER ID: {self._user_id}")
        self.logger.info(f"EMAIL: {self._user_email or 'Non disponible'}") 

        self._init_firestore_structure(initial_scan_config)
        self.sync_and_apply_config(initial=True)

    def _resolve_user_email(self) -> str:
        """Récupère l'email Firebase Auth de l'utilisateur. Retourne '' si indisponible."""
        try:
            fb_user = fb_auth.get_user(self._user_id)
            return fb_user.email or ''
        except Exception as e:
            self.logger.warning(f"Impossible de récupérer l'email pour {self._user_id[:8]}: {e}")
            return ''

    @property
    def session_processed_ids(self):
        """Set isolé par thread — chaque thread (scan, refresh) a sa propre mémoire de session."""
        if not hasattr(self._local, 'processed_ids'):
            self._local.processed_ids = set()
        return self._local.processed_ids

    def set_status(self, new_status, task_name=None):
        """
        Gestionnaire centralisé du statut pour éviter les conflits entre threads.
        """
        if self.offline_mode: return
        
        with self._status_lock:
            # Gestion basique des tâches (si un task_name est fourni, on le traque)
            if task_name:
                if new_status == 'idle':
                    self._active_tasks.discard(task_name)
                else:
                    self._active_tasks.add(task_name)
                    
            # Logique de priorité : le scan est prioritaire sur le nettoyage dans l'affichage UI
            if new_status == 'idle' and len(self._active_tasks) > 0:
                # Si on demande 'idle' mais qu'il reste des tâches, on restaure le statut de la tâche restante (priorité au scan)
                if 'scanning' in self._active_tasks:
                    calculated_status = 'scanning'
                else:
                    calculated_status = list(self._active_tasks)[0] # Prend la première tâche restante
            else:
                calculated_status = new_status
                
            if self._current_status != calculated_status or calculated_status == 'idle':
                self._current_status = calculated_status
                try:
                    self.repo.update_bot_status(calculated_status)
                except Exception as e:
                    self.logger.error(f"Erreur lors de la mise à jour du statut {calculated_status}: {e}")

    def _init_firestore_structure(self, initial_scan_config):
        initial_config = {
            'exclusionKeywords': DEFAULT_EXCLUSION_KEYWORDS,
            'scanConfig': initial_scan_config,
            'botStatus': self._current_status,
            'analysisConfig': {
                'gatekeeperModel': GEMINI_MODELS["default_gatekeeper"],
                'expertModel': GEMINI_MODELS["default_expert"],  # Clé legacy (lue par le frontend)
                'mainAnalysisPrompt': DEFAULT_MAIN_PROMPT,
                'gatekeeperVerbosityInstruction': DEFAULT_GATEKEEPER_INSTRUCTION,
                'analystVerbosityInstruction': DEFAULT_ANALYST_INSTRUCTION,
                'expertProContextInstruction': DEFAULT_EXPERT_CONTEXT,
            },
            'availableModels': GEMINI_MODELS["available"]
        }
        self.logger.info("DEBUG: Calling ensure_initial_structure with defaults...")
        self.repo.ensure_initial_structure(initial_config)

    def sync_and_apply_config(self, initial=False):
        if self.offline_mode: return
        sync_result = self.config_manager.sync_with_firestore(initial=initial)
        return sync_result

    @staticmethod
    def _normalize_price(price):
        """Nettoie une chaîne de prix (ex: ' 150 $ ') pour retourner un float fiable."""
        try:
            num_str = ''.join(c for c in str(price).replace(',', '.') if c.isdigit() or c == '.')
            return float(num_str) if num_str else 0.0
        except Exception:
            return 0.0

    def should_skip_deal(self, deal_id, price):
        if deal_id in self.session_processed_ids: return True
        if self.offline_mode: return False
        existing_deal = self.repo.get_deal_by_id(deal_id)
        if not existing_deal: return False
        if existing_deal.get('status') == 'rejected':
            self.session_processed_ids.add(deal_id)
            return True
            
        old_price = self._normalize_price(existing_deal.get('price', -1))
        new_price = self._normalize_price(price)
        
        if old_price > 0 and old_price == new_price:
            self.session_processed_ids.add(deal_id)
            return True
            
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
        self.logger.info(f"Traitement de la nouvelle annonce : {listing_data['title']}")
        self.session_processed_ids.add(listing_data['id'])
        
        is_update = False
        original_price = None
        
        if not self.offline_mode:
            existing_deal = self.repo.get_deal_by_id(listing_data['id'])
            if existing_deal:
                if existing_deal.get('status') == 'rejected':
                    self.logger.info("Annonce déjà rejetée. Ignorée.")
                    return
                    
                old_p = self._normalize_price(existing_deal.get('price'))
                new_p = self._normalize_price(listing_data['price'])
                
                if old_p > 0 and old_p == new_p:
                    self.logger.info("Annonce déjà existante avec le même prix nettoyé. Ignorée.")
                    return
                    
                # Prix différent !
                original_price = existing_deal.get('price')
                self.logger.info(f"Annonce existante mais prix différent (Ancien: {original_price}$, Nouveau: {listing_data['price']}$). Mise à jour et Réanalyse.")
                is_update = True
                
                # Enrichissement des données avec les infos de baisse de prix
                try:
                    if old_p > new_p > 0:
                        listing_data['original_price'] = original_price
                        listing_data['price_drop_amount'] = old_p - new_p
                except Exception as e:
                    self.logger.warning(f"Erreur lors du calcul de la baisse de prix: {e}")

        current_config = self.config_manager.current_config_snapshot
        found_keyword = self._check_exclusion(listing_data, current_config)
        
        if found_keyword:
            self.logger.info(f"Annonce rejetée par pré-filtrage. Mot-clé : '{found_keyword}'")
            rejection_analysis = self._create_rejection_analysis(found_keyword)
            if not self.offline_mode:
                if is_update:
                    # On met à jour l'analyse ET l'objet entier qui contient désormais le nouveau prix et original_price
                    self.repo.update_deal_data_and_analysis(listing_data['id'], listing_data, rejection_analysis)
                else:
                    self.repo.create_new_deal(listing_data['id'], listing_data, rejection_analysis)
            return

        analysis = self.analyzer.analyze_deal(listing_data, firestore_config=current_config)
        deal_id = listing_data.get('id')
        NotificationService.notify_deal(
            deal_id, listing_data, analysis,
            is_update=is_update,
            user_email=self._user_email
        )
        
        if not self.offline_mode:
            # Upload des images dans Firebase Storage avant la sauvegarde
            image_urls = listing_data.get('imageUrls') or ([listing_data.get('imageUrl')] if listing_data.get('imageUrl') else [])
            if image_urls:
                stable_urls = self.repo.upload_images_to_storage(image_urls, listing_data['id'])
                if stable_urls:
                    listing_data['storageImageUrls'] = stable_urls
            
            if is_update:
                # Appel de la nouvelle méthode pour écraser le prix Firestore et ajouter l'historique
                self.repo.update_deal_data_and_analysis(listing_data['id'], listing_data, analysis)
            else:
                self.repo.create_new_deal(listing_data['id'], listing_data, analysis)

    def _is_stop_requested(self):
        """Vérifie si un arrêt total (STOP_BOT) ou un arrêt de scan (STOP_SCAN) est demandé."""
        if self.stop_event and self.stop_event.is_set():
            return True
        if self.scan_stop_event and self.scan_stop_event.is_set():
            return True
        return False

    def run_scan(self):
        if self._is_stop_requested():
            self.logger.info("🛑 run_scan ignoré car un arrêt est en cours.")
            return

        if not self.offline_mode:
            self.set_status('scanning', task_name='scanning')

        self.session_processed_ids.clear()

        try:
            scan_config = self.config_manager.scan_config
            self.logger.info(f"Démarrage du scan planifié (fréq: {scan_config.get('frequency', 'N/A')} min)...")
            
            # get_cities() retourne directement les villes isScannable du catalogue partagé
            cities_to_scan = self.repo.get_cities()

            self.logger.info(f"Villes scanables ({len(cities_to_scan)}): {', '.join([c['name'] for c in cities_to_scan])}")

            if not cities_to_scan:
                self.logger.warning("Aucune ville scannable configurée. Scan ignoré.")
            else:
                all_allowed_cities_norm = [ListingParser.normalize_city_name(c['name']) for c in cities_to_scan]
                
                self.logger.info(f"Scan de {len(cities_to_scan)} villes : {', '.join([c['name'] for c in cities_to_scan])}")
                for city_data in cities_to_scan:
                    if self._is_stop_requested():
                        self.logger.info("🛑 Interruption de la boucle des villes.")
                        break

                    city_name = city_data.get('name')
                    city_id = city_data.get('id')
                    city_lat = city_data.get('latitude')
                    city_lon = city_data.get('longitude')
                    city_norm_name = ListingParser.normalize_city_name(city_name)
                    
                    if not all([city_name, city_id, city_lat is not None, city_lon is not None]):
                        self.logger.warning(f"Données incomplètes pour la ville {city_name or 'inconnue'}. Scan de cette ville ignoré.")
                        continue

                    city_specific_config = scan_config.copy()
                    city_specific_config['location'] = city_norm_name
                    self.logger.info(f"--- Scan de la ville : {city_name} ({city_id}) ---")

                    if self._browser_semaphore:
                        self._browser_semaphore.acquire()
                    try:
                        temp_scraper = FacebookScraper({}, {})
                        temp_scraper.city_mapping = {city_norm_name: city_id}
                        temp_scraper.allowed_cities = all_allowed_cities_norm

                        try:
                            found_deals = temp_scraper.scan_marketplace(city_specific_config, self.should_skip_deal, stop_event=self.stop_event or self.scan_stop_event)

                            # --- FILTRAGE PAR RAYON ---
                            radius_km = scan_config.get('distance', 0)
                            if radius_km == 0:
                                # Mode nom strict : ne conserver que les annonces dont la localisation correspond à la ville
                                norm_city = ListingParser.normalize_city_name(city_name)
                                strict_filtered = []
                                for deal in found_deals:
                                    norm_deal_loc = ListingParser.normalize_city_name(deal.get('location', ''))
                                    if norm_deal_loc and (norm_deal_loc == norm_city or norm_city in norm_deal_loc or norm_deal_loc.startswith(norm_city)):
                                        strict_filtered.append(deal)
                                    else:
                                        self.logger.info(f"[STRICT] '{deal.get('title', 'N/A')}' rejeté — localisation '{deal.get('location', '')}' ≠ '{city_name}'.")
                                self.logger.info(f"[STRICT] {len(strict_filtered)}/{len(found_deals)} annonces conservées (correspondance exacte ville).")
                                found_deals = strict_filtered
                            elif radius_km > 0:
                                deals_in_radius = []
                                for deal in found_deals:
                                    deal_lat = deal.get('latitude')
                                    deal_lon = deal.get('longitude')
                                    if deal_lat is not None and deal_lon is not None:
                                        distance = calculate_distance(city_lat, city_lon, deal_lat, deal_lon)
                                        if distance <= radius_km:
                                            deals_in_radius.append(deal)
                                        else:
                                            self.logger.info(f"Annonce '{deal.get('title', 'N/A')}' rejetée (distance: {distance:.1f}km > {radius_km}km).")
                                    else:
                                        deals_in_radius.append(deal)

                                self.logger.info(f"{len(deals_in_radius)}/{len(found_deals)} annonces conservées après filtrage par rayon de {radius_km}km.")
                                found_deals = deals_in_radius

                            # --- TRAITEMENT DES ANNONCES FILTRÉES ---
                            for deal in found_deals:
                                if self._is_stop_requested(): break
                                self.handle_deal_found(deal)

                        finally:
                            temp_scraper.close_session()
                    finally:
                        if self._browser_semaphore:
                            self._browser_semaphore.release()
                    
                    time.sleep(2)
            self.logger.info("Scan planifié terminé.")
        finally:
            if not self.offline_mode:
                self.set_status('idle', task_name='scanning')

    def scan_specific_url(self, url):
        if not self.offline_mode:
            self.set_status('scanning_url', task_name='scanning_url')
        if self._browser_semaphore:
            self._browser_semaphore.acquire()
        try:
            temp_scraper = FacebookScraper({}, {})
            try:
                temp_scraper.scan_specific_url(url, self.handle_deal_found)
            finally:
                try:
                    temp_scraper.close_session()
                except Exception as e:
                    self.logger.warning(f"Erreur lors de la fermeture du scraper temporaire URL : {e}")
        finally:
            if self._browser_semaphore:
                self._browser_semaphore.release()
            if not self.offline_mode:
                self.set_status('idle', task_name='scanning_url')

    def cleanup_sold_listings(self):
        if self.offline_mode or self.is_cleaning: return
        self.logger.info("Démarrage du nettoyage des annonces vendues...")
        threading.Thread(target=self._perform_cleanup, daemon=True).start()

    def _perform_cleanup(self):
        with self.cleanup_lock:
            self.is_cleaning = True
            if not self.offline_mode: self.set_status('cleaning', task_name='cleaning')

            if self._browser_semaphore:
                self._browser_semaphore.acquire()
            try:
                temp_scraper = FacebookScraper({}, {})
                try:
                    docs = self.repo.get_active_listings()
                    listings = [{'id': d.id, 'url': d.to_dict().get('link')} for d in docs]
                    self.logger.info(f"Vérification de la disponibilité de {len(listings)} annonces actives.")
                    deleted_count = 0
                    for item in listings:
                        if self._is_stop_requested():
                            self.logger.info("🛑 Nettoyage interrompu.")
                            break

                        if not item['url']: continue
                        if not temp_scraper.check_listing_availability(item['url']):
                            self.logger.info(f"   📉 Marquage de l'annonce {item['id']} comme VENDUE.")
                            self.repo.mark_deal_as_sold(item['id'], 'Annonce indisponible ou vendue (détecté par le bot)')
                            deleted_count += 1
                        time.sleep(0.5)
                    self.logger.info(f"Nettoyage terminé. {deleted_count} annonces supprimées.")
                except Exception as e:
                    self.logger.error(f"Erreur durant le nettoyage : {e}", exc_info=True)
                finally:
                    try:
                        temp_scraper.close_session()
                    except Exception as e:
                        self.logger.warning(f"Erreur lors de la fermeture du scraper temporaire : {e}")
            finally:
                if self._browser_semaphore:
                    self._browser_semaphore.release()
                self.is_cleaning = False
                if not self.offline_mode: self.set_status('idle', task_name='cleaning')

    def process_retry_queue(self):
        """Traite les annonces en attente de réanalyse."""
        if self.offline_mode: return
        
        docs = list(self.repo.get_retry_queue_listings())
        if not docs:
            return

        self.set_status('reanalyzing', task_name='retry_queue')
        
        try:
            for doc in docs:
                if self._is_stop_requested():
                    self.logger.info("🛑 File d'attente interrompue.")
                    break
                    
                data = doc.to_dict()
                self.logger.info(f"Réanalyse de l'annonce en file d'attente : {data.get('title')}")
                
                listing_data = {
                    "title": data.get('title'), "price": data.get('price'),
                    "description": data.get('description', ''), "location": data.get('location', 'Inconnue'),
                    "imageUrls": data.get('imageUrls', []), "imageUrl": data.get('imageUrl'),
                    "link": data.get('link'), "id": doc.id,
                    **({'latitude': data['latitude'], 'longitude': data['longitude']} if 'latitude' in data else {})
                }
                
                current_config = self.config_manager.current_config_snapshot
                
                found_keyword = self._check_exclusion(listing_data, current_config)
                if found_keyword:
                    self.logger.info(f"Annonce rejetée par pré-filtrage lors de la réanalyse. Mot-clé : '{found_keyword}'")
                    rejection_analysis = self._create_rejection_analysis(found_keyword)
                    self.repo.update_deal_analysis(doc.id, rejection_analysis)
                    continue 

                try:
                    analysis = self.analyzer.analyze_deal(listing_data, firestore_config=current_config)
                    self.repo.update_deal_analysis(doc.id, analysis)
                except Exception as e:
                    self.logger.error(f"Erreur lors de la réanalyse de {doc.id}: {e}")
                    self.repo.update_deal_status(doc.id, 'analysis_failed', str(e))
        finally:
            self.set_status('idle', task_name='retry_queue')

    def reanalyze_all_listings(self):
        """Marque toutes les annonces actives pour réanalyse."""
        if self.offline_mode: return
        
        if not self.offline_mode:
            self.set_status('reanalyzing_all', task_name='reanalyzing_all')
        
        try:
            self.logger.info("Démarrage de la réanalyse de TOUTES les annonces...")
            count = self.repo.mark_all_for_reanalysis()
            self.logger.info(f"{count} annonces marquées pour réanalyse. Elles seront traitées par le thread de surveillance.")
        except Exception as e:
            self.logger.error(f"Erreur lors de la demande de réanalyse globale : {e}", exc_info=True)
        finally:
            if not self.offline_mode:
                self.set_status('idle', task_name='reanalyzing_all')

    def _geocode_nominatim(self, city_name: str) -> dict | None:
        """Retourne {'lat': float, 'lon': float} via Nominatim (OSM), ou None.
        Essaie plusieurs variantes du nom (Mc X, Saint→St, accents, tirets...)."""
        headers = {"User-Agent": "GuitarHunter/1.0"}
        # On essaie d'abord avec les suffixes locaux (Canada), puis en mode global
        for variant in city_name_variants(city_name):
            for suffix in [", Quebec, Canada", ", Canada", ""]:
                query = variant + suffix
                params = {"q": query, "format": "json", "limit": 1}
                
                # Si on a un suffixe Canada, on restreint la recherche pour plus de précision
                if suffix:
                    params["countrycodes"] = "ca"
                
                try:
                    resp = requests.get(
                        "https://nominatim.openstreetmap.org/search",
                        params=params,
                        headers=headers,
                        timeout=10,
                    )
                    resp.raise_for_status()
                    results = resp.json()
                    if results:
                        self.logger.info(f"Nominatim: '{query}' → lat={float(results[0]['lat']):.4f}, lon={float(results[0]['lon']):.4f}")
                        return {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}
                except Exception as e:
                    self.logger.warning(f"Nominatim erreur pour '{query}': {e}")
                time.sleep(1)
        return None

    def add_city_auto(self, city_name):
        if self.offline_mode: return
        self.logger.info(f"Tentative d'ajout de la ville: {city_name}")

        # Dédoublonnage sur le catalogue partagé (nom)
        catalog = self.repo.get_all_catalog_cities()
        existing_id_by_name = None
        for city_id_key, data in catalog.items():
            if data.get('name', '').lower() == city_name.lower():
                existing_id_by_name = city_id_key
                break

        # Si ville déjà dans le catalogue par nom ET coords complètes → juste activer
        if existing_id_by_name:
            existing_data = catalog[existing_id_by_name]
            if existing_data.get('latitude') is not None and existing_data.get('longitude') is not None:
                self.logger.info(f"Ville '{city_name}' déjà dans le catalogue (id={existing_id_by_name}). Activation pour cet user.")
                self.repo.set_city_user_pref(existing_id_by_name, True)
                return True
            else:
                self.logger.info(f"Ville '{city_name}' dans le catalogue mais sans coordonnées. Lancement CityFinder pour enrichissement...")

        if self._browser_semaphore:
            self._browser_semaphore.acquire()
        try:
            temp_scraper = FacebookScraper({}, {})
            try:
                city_id, _ = CityFinder.find_city_id_and_coords(temp_scraper, city_name)
            finally:
                temp_scraper.close_session()
        finally:
            if self._browser_semaphore:
                self._browser_semaphore.release()

        if city_id:
            # Dédoublonnage sur l'ID Facebook
            city_id_str = str(city_id)
            in_catalog = city_id_str in catalog or existing_id_by_name is not None
            target_id = city_id_str if city_id_str in catalog else (existing_id_by_name or city_id_str)

            # Coordonnées via Nominatim (fiable, pas dépendant de Facebook)
            city_coords = self._geocode_nominatim(city_name)
            if city_coords:
                self.logger.info(f"Coords Nominatim pour '{city_name}': lat={city_coords['lat']:.4f}, lon={city_coords['lon']:.4f}")
            else:
                self.logger.warning(f"Nominatim n'a pas trouvé de coords pour '{city_name}'. Ville ajoutée sans coordonnées.")

            city_data = {'name': city_name, 'id': city_id_str}
            if city_coords:
                city_data.update({'latitude': city_coords['lat'], 'longitude': city_coords['lon']})

            if in_catalog:
                self.logger.info(f"ID {target_id} déjà dans le catalogue. Mise à jour et activation.")
                self.repo.add_city_to_catalog(target_id, city_data)
            else:
                self.logger.info(f"Nouvelle ville {city_name} (id={city_id_str}). Ajout au catalogue partagé...")
                city_data.update({'createdAt': firestore.SERVER_TIMESTAMP, 'createdBy': self._user_id})
                self.repo.add_city_to_catalog(city_id_str, city_data)

            self.repo.set_city_user_pref(target_id, True)
            self.logger.info(f"Ville {city_name} prete dans le catalogue.")
            return True
        else:
            self.logger.warning(f"Impossible de trouver l'ID pour la ville {city_name}.")
            raise Exception(f"Impossible de trouver l'ID Facebook pour la ville '{city_name}'.")

    def clear_logs(self, _=None):
        if self.offline_mode:
            self.logger.warning("Cannot clear logs in offline mode.")
            return
        self.logger.info("--- COMMANDE REÇUE : Effacement des logs ---")
        try:
            deleted_count = self.repo.delete_all_logs()
            self.logger.info(f"--- {deleted_count} logs ont été supprimés avec succès. ---")
        except Exception as e:
            self.logger.error(f"Erreur lors de la suppression des logs: {e}", exc_info=True)
            raise

    def analyze_single_deal(self, payload):
        """Analyse une annonce spécifique à la demande."""
        if self.offline_mode: return
        
        deal_id = payload.get('dealId')
        force_expert = payload.get('forceExpert', False)
        
        if not deal_id:
            self.logger.error("analyze_single_deal: dealId manquant dans le payload.")
            return

        self.logger.info(f"Demande d'analyse manuelle pour l'annonce {deal_id} (Force Expert: {force_expert})")
        
        deal_data = self.repo.get_deal_by_id(deal_id)
        if not deal_data:
            self.logger.error(f"Annonce {deal_id} introuvable dans Firestore.")
            return

        listing_data = {
            "title": deal_data.get('title'),
            "price": deal_data.get('price'),
            "description": deal_data.get('description', ''),
            "location": deal_data.get('location', 'Inconnue'),
            "imageUrls": deal_data.get('imageUrls', []),
            "imageUrl": deal_data.get('imageUrl'),
            "link": deal_data.get('link'),
            "id": deal_id,
            **({'latitude': deal_data['latitude'], 'longitude': deal_data['longitude']} if 'latitude' in deal_data else {})
        }

        current_config = self.config_manager.current_config_snapshot
        
        try:
            analysis = self.analyzer.analyze_deal(listing_data, firestore_config=current_config, force_expert=force_expert)
            self.repo.update_deal_analysis(deal_id, analysis)
            self.logger.info(f"Analyse manuelle terminée pour {deal_id}.")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse manuelle de {deal_id}: {e}", exc_info=True)
            self.repo.update_deal_status(deal_id, 'analysis_failed', str(e))

    def purge_rejected_images(self):
        """Politique de cycle de vie : purge les images des deals rejetés anciens."""
        if self.offline_mode: return
        self.logger.info(f"--- Démarrage de la purge des images (rétention: {IMAGE_RETENTION_REJECTED_DAYS}j) ---")
        try:
            count = self.repo.purge_rejected_images(retention_days=IMAGE_RETENTION_REJECTED_DAYS)
            self.logger.info(f"--- Purge terminée : {count} image(s) supprimée(s). ---")
        except Exception as e:
            self.logger.error(f"Erreur lors de la purge des images: {e}", exc_info=True)
