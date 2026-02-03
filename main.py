import os
import sys
import time
import json
import threading
import re

# --- IMPORT DE LA CONFIGURATION CENTRALISÉE ---
from config import *
from backend.database import DatabaseService
from backend.analyzer import DealAnalyzer
from backend.scraper import FacebookScraper # <-- NOUVEL IMPORT

# --- Librairies Externes ---
import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

# --- NOUVELLE INITIALISATION DE LA DB ---
db_service = DatabaseService(FIREBASE_KEY_PATH)
db = db_service.db
offline_mode = db_service.offline_mode
# --- FIN DE LA NOUVELLE INITIALISATION ---

class GuitarHunterBot:
    def __init__(self, db_client, is_offline, prompt_instruction=PROMPT_INSTRUCTION):
        self.db = db_client
        self.offline_mode = is_offline
        self.prompt_instruction = prompt_instruction
        
        # --- INITIALISATION DES MODULES ---
        self.analyzer = DealAnalyzer()
        self.scraper = FacebookScraper(CITY_COORDINATES, {}) # Mapping sera mis à jour plus tard
        
        # Configuration par défaut
        self.verdict_rules = DEFAULT_VERDICT_RULES
        self.reasoning_instruction = DEFAULT_REASONING_INSTRUCTION
        self.user_prompt_template = DEFAULT_USER_PROMPT
        
        self.analyzer.update_prompt_template(self.user_prompt_template)

        # Configuration du scan
        self.scan_config = {
            "max_ads": 5,
            "frequency": 60,
            "location": "montreal",
            "distance": 60,
            "min_price": 0,
            "max_price": 10000,
            "search_query": "electric guitar"
        }
        self.last_refresh_timestamp = 0
        self.last_cleanup_timestamp = 0
        self.last_reanalyze_all_timestamp = 0
        self.city_mapping = {}
        
        self.is_cleaning = False
        self.cleanup_lock = threading.Lock()

        self.collection_path = f"artifacts/{APP_ID_TARGET}/users/{USER_ID_TARGET}/guitar_deals"
        
        print(f"\n🔧 CONFIGURATION DU BOT :")
        print(f"   - APP ID  : {APP_ID_TARGET}")
        print(f"   - USER ID : {USER_ID_TARGET}")
        
        if CITY_COORDINATES:
             print(f"   🗺️ {len(CITY_COORDINATES)} coordonnées de villes chargées.")

        if self.offline_mode:
            print("⚠️ ATTENTION : MODE HORS-LIGNE ACTIVÉ.")
            return

        # Références Firestore
        self.collection_ref = self.db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET) \
            .collection('guitar_deals')
        self.user_ref = self.db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET)
        self.cities_ref = self.db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET) \
            .collection('cities')

        self._init_firestore_structure()

    def _init_firestore_structure(self):
        print("   ⏳ Vérification de l'accès Firestore...")
        try:
            app_ref = self.db.collection('artifacts').document(APP_ID_TARGET)
            if not app_ref.get().exists:
                app_ref.set({'created_at': firestore.SERVER_TIMESTAMP, 'type': 'app_root'})
            
            user_ref = app_ref.collection('users').document(USER_ID_TARGET)
            if not user_ref.get().exists:
                user_ref.set({
                    'created_at': firestore.SERVER_TIMESTAMP, 
                    'type': 'user_root', 
                    'prompt': self.prompt_instruction,
                    'verdictRules': self.verdict_rules,
                    'reasoningInstruction': self.reasoning_instruction,
                    'userPrompt': self.user_prompt_template,
                    'scanConfig': self.scan_config
                })
            else:
                self.sync_configuration(initial=True)
        except Exception as e:
            print(f"⚠️ Erreur init Firestore: {e}")

    def load_cities_from_firestore(self):
        if self.offline_mode: return
        try:
            docs = self.cities_ref.stream()
            new_mapping = {}
            count = 0
            for doc in docs:
                data = doc.to_dict()
                if 'name' in data and 'id' in data:
                    norm_name = self.scraper._normalize_city_name(data['name'])
                    new_mapping[norm_name] = data['id']
                    count += 1
            
            self.city_mapping = new_mapping
            self.scraper.city_mapping = new_mapping # Mise à jour du scraper
            print(f"   🏙️ {count} villes chargées.")
        except Exception as e:
            print(f"⚠️ Erreur chargement villes: {e}")

    def sync_configuration(self, initial=False):
        if self.offline_mode: return False, False, False, None
        try:
            doc = self.user_ref.get()
            should_refresh = False
            should_cleanup = False
            should_reanalyze_all = False
            specific_url = None

            if doc.exists:
                data = doc.to_dict()
                
                def join_if_list(value):
                    return "\n".join(value) if isinstance(value, list) else value

                if 'userPrompt' in data:
                    new_template = join_if_list(data['userPrompt'])
                    if new_template != self.user_prompt_template:
                        self.user_prompt_template = new_template
                        self.analyzer.update_prompt_template(new_template)
                        print("🔄 Template prompt mis à jour.")

                if 'scanConfig' in data:
                    self.scan_config.update(data['scanConfig'])

                if 'forceRefresh' in data:
                    lr = data['forceRefresh']
                    if not initial and lr != self.last_refresh_timestamp:
                        self.last_refresh_timestamp = lr
                        should_refresh = True
                    elif initial: self.last_refresh_timestamp = lr

                if 'forceCleanup' in data:
                    lc = data['forceCleanup']
                    if not initial and lc != self.last_cleanup_timestamp:
                        self.last_cleanup_timestamp = lc
                        should_cleanup = True
                    elif initial: self.last_cleanup_timestamp = lc
                
                if 'forceReanalyzeAll' in data:
                    lra = data['forceReanalyzeAll']
                    if not initial and lra != self.last_reanalyze_all_timestamp:
                        self.last_reanalyze_all_timestamp = lra
                        should_reanalyze_all = True
                    elif initial: self.last_reanalyze_all_timestamp = lra

                if 'scanSpecificUrl' in data:
                    specific_url = data['scanSpecificUrl']

            return should_refresh, should_cleanup, should_reanalyze_all, specific_url
        except Exception as e:
            print(f"⚠️ Erreur sync config: {e}")
            return False, False, False, None

    def handle_deal_found(self, listing_data):
        """Callback appelé quand une annonce est trouvée."""
        print(f"   ✨ Traitement de : {listing_data['title']}")
        
        if not self.offline_mode:
            try:
                doc_snap = self.collection_ref.document(listing_data['id']).get()
                if doc_snap.exists:
                    existing = doc_snap.to_dict()
                    if existing.get('status') == 'rejected':
                        print(f"   🚫 Déjà rejetée.")
                        return
                    if existing.get('price') == listing_data['price']:
                        print(f"   ⏭️ Déjà existante (prix inchangé).")
                        return
                    print(f"   🔄 Mise à jour (prix changé).")
            except: pass

        analysis = self.analyzer.analyze_deal(listing_data)
        self.save_to_firestore(listing_data, analysis, doc_id=listing_data['id'])

    def save_to_firestore(self, listing_data, analysis, doc_id=None):
        if self.offline_mode: return
        try:
            status = "analyzed"
            if analysis.get('verdict') == 'REJECTED': status = "rejected"

            data = {
                **listing_data,
                "aiAnalysis": analysis,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "status": status
            }
            self.collection_ref.document(doc_id).set(data, merge=True)
            print(f"💾 Sauvegardé: {listing_data['title']} ({status})")
        except Exception as e:
            print(f"❌ Erreur Firestore: {e}")

    def scan_facebook_marketplace(self, **kwargs):
        """Lance le scan via le scraper."""
        self.scraper.scan_marketplace(self.scan_config, self.handle_deal_found)

    def scan_specific_url(self, url):
        """Lance le scan d'URL via le scraper."""
        try: self.user_ref.update({'scanSpecificUrl': firestore.DELETE_FIELD})
        except: pass
        self.scraper.scan_specific_url(url, self.handle_deal_found)

    def cleanup_sold_listings(self):
        if self.offline_mode or self.is_cleaning: return
        print("\n🧹 Nettoyage...")
        threading.Thread(target=self._perform_cleanup, daemon=True).start()

    def _perform_cleanup(self):
        with self.cleanup_lock:
            self.is_cleaning = True
            try:
                docs = self.collection_ref.where(filter=FieldFilter('status', '!=', 'rejected')).stream()
                listings = [{'id': d.id, 'url': d.to_dict().get('link')} for d in docs]
                
                print(f"   🔍 Vérification de {len(listings)} annonces...")
                deleted = 0
                
                for item in listings:
                    if not item['url']: continue
                    if not self.scraper.check_listing_availability(item['url']):
                        print(f"   🗑️ Suppression: {item['id']}")
                        self.collection_ref.document(item['id']).delete()
                        deleted += 1
                    time.sleep(0.5)
                
                print(f"🏁 Nettoyage terminé. {deleted} supprimés.")
            except Exception as e:
                print(f"❌ Erreur nettoyage: {e}")
            finally:
                self.is_cleaning = False

    def process_retry_queue(self):
        if self.offline_mode: return
        try:
            docs = self.collection_ref.where(filter=FieldFilter('status', '==', 'retry_analysis')).stream()
            for doc in docs:
                data = doc.to_dict()
                print(f"🔄 Ré-analyse: {data.get('title')}")
                
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
                self.save_to_firestore(listing_data, analysis, doc_id=doc.id)
        except Exception as e:
            print(f"❌ Erreur retry queue: {e}")

    def reanalyze_all_listings(self):
        if self.offline_mode: return
        print("🧠 Ré-analyse globale...")
        try:
            docs = self.collection_ref.where(filter=FieldFilter('status', '!=', 'rejected')).stream()
            batch = self.db.batch()
            count = 0
            for doc in docs:
                batch.update(doc.reference, {'status': 'retry_analysis'})
                count += 1
            if count > 0:
                batch.commit()
                print(f"✅ {count} annonces marquées.")
        except Exception as e:
            print(f"❌ Erreur ré-analyse: {e}")

def monitor_retries(bot):
    print("🧵 Thread surveillance actif...")
    while True:
        try:
            bot.process_retry_queue()
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ Erreur thread: {e}")
            time.sleep(10)

if __name__ == "__main__":
    print(f"Prompt par défaut: {PROMPT_INSTRUCTION}")
    bot = GuitarHunterBot(db, offline_mode)

    if bot.offline_mode:
        print("\n❌ Mode hors-ligne. Arrêt.")
        sys.exit(1)
    
    threading.Thread(target=monitor_retries, args=(bot,), daemon=True).start()
    
    print("\n--- MODE AUTOMATIQUE ---")
    last_scan_time = 0
    last_auto_cleanup_time = 0
    
    try:
        while True:
            should_refresh, should_cleanup, should_reanalyze_all, specific_url = bot.sync_configuration()
            
            if specific_url: bot.scan_specific_url(specific_url)

            current_time = time.time()
            freq = bot.scan_config['frequency'] * 60
            
            if should_cleanup or (current_time - last_auto_cleanup_time > 86400):
                bot.cleanup_sold_listings()
                last_auto_cleanup_time = time.time()

            if should_reanalyze_all: bot.reanalyze_all_listings()

            if should_refresh or (current_time - last_scan_time > freq):
                print(f"⏰ Scan auto ({bot.scan_config['frequency']} min)...")
                bot.load_cities_from_firestore()
                bot.scan_facebook_marketplace()
                last_scan_time = time.time()
                print(f"💤 Prochain scan dans {bot.scan_config['frequency']} min...")
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n🛑 Arrêt.")
