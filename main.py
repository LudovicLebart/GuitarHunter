import os
import sys
import time
import json
import random
import requests
import warnings
import unicodedata
import urllib.parse
import threading
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
import re # Importation de la bibliothèque re pour les expressions régulières

# Suppression des avertissements de dépréciation (Gemini)
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

# --- Librairies Externes ---
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from google.cloud.firestore_v1.base_query import FieldFilter

# Chargement des variables d'environnement (.env)
load_dotenv()

# --- CONFIGURATION ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
FIREBASE_KEY_PATH = "serviceAccountKey.json"  # Doit être à la racine du projet
PROMPT_INSTRUCTION = "Evalue cette guitare Au quebec (avec le prix)."  # Instruction principale pour l'analyse IA
APP_ID_TARGET = os.getenv("APP_ID_TARGET")
USER_ID_TARGET = os.getenv("USER_ID_TARGET")

if not APP_ID_TARGET or not USER_ID_TARGET:
    print("❌ ERREUR: APP_ID_TARGET et USER_ID_TARGET doivent être définis dans le fichier .env")
    sys.exit(1)

# --- NOUVELLES INSTRUCTIONS SYSTÈME ---
SYSTEM_PROMPT = """Tu es un luthier expert et un négociant de guitares chevronné pour le marché du Québec (MTL/QC).
Ton but : Analyser les photos pour protéger l'acheteur contre les arnaques et les mauvais prix.

TA MISSION D'ANALYSE :
1.  **REJET (REJECTED)** : Si l'objet n'est pas une guitare/basse (ex: ampli, pédale, jouet, montre, guitare de jeu video). 
2.  **Authentification** : Vérifie la forme de la tête (Headstock), le logo, le placement des boutons. Repère les 'Chibson' ou contrefaçons.
3.  **État** : Zoome sur les frettes (usure ?), le chevalet (oxydation ?), le manche (fissures ?).
4.  **Valeur** : Estime le prix de revente RÉALISTE au Québec (pas le prix neuf, le prix Kijiji/Marketplace).

FORMAT DE RÉPONSE ATTENDU (JSON) :
{
  "verdict": "GOOD_DEAL" | "FAIR" | "BAD_DEAL" | "REJECTED",
  "estimated_value": 1200,
  "confidence": 90,
  "reasoning": "Modèle 2018 authentique. Le prix demandé (800$) est bien sous la cote habituelle (1100$). Attention : légère scratch au dos.",
  "red_flags": ["Frettes très usées", "Bouton de volume non original"]
}
"""

# Initialisation Gemini
model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name='gemini-2.5-pro',
        system_instruction=SYSTEM_PROMPT,
        generation_config={
            "response_mime_type": "application/json", # Force le format JSON
            "temperature": 0.1 # Très bas pour une analyse froide et factuelle
        }
    )
else:
    print("⚠️ ATTENTION: Pas de clé API Gemini trouvée dans le fichier .env")

# Initialisation Firebase
db = None
offline_mode = False

if not firebase_admin._apps:
    try:
        if os.path.exists(FIREBASE_KEY_PATH):
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            print(f"🔑 Projet ID détecté : {cred.project_id}")
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ Firebase connecté avec succès (Database: Default).")
            
            # Test de permissions immédiat
            try:
                list(db.collections())
                print("✅ Permissions de lecture confirmées sur la base.")
            except Exception as e:
                print(f"❌ ERREUR PERMISSIONS : {e}")
                print("👉 Le compte de service n'a pas les droits. Passage en MODE HORS-LIGNE (Simulation).")
                offline_mode = True
        else:
            print(f"⚠️ Fichier {FIREBASE_KEY_PATH} introuvable. Passage en MODE HORS-LIGNE.")
            offline_mode = True

    except Exception as e:
        print(f"❌ Erreur critique Firebase: {e}")
        offline_mode = True


class GuitarHunterBot:
    def __init__(self, db_client, gemini_model, is_offline, prompt_instruction=PROMPT_INSTRUCTION):
        self.db = db_client
        self.model = gemini_model
        self.offline_mode = is_offline
        self.prompt_instruction = prompt_instruction
        
        # Configuration par défaut des règles et du raisonnement
        self.verdict_rules = """- "GOOD_DEAL" : Le prix demandé est INFERIEUR à la valeur estimée.
- "FAIR" : Le prix demandé est PROCHE de la valeur estimée (à +/- 10%).
- "BAD_DEAL" : Le prix demandé est SUPERIEUR à la valeur estimée.
- "REJECTED" : L'objet n'est PAS ce que l'on recherche (ex: une montre guitare, un accessoire seul si on cherche une guitare, une guitare jouet, etc.)."""
        
        self.reasoning_instruction = "explication détaillée et complète justifiant le verdict par rapport au prix et à la valeur"

        # Configuration par défaut du scan
        self.scan_config = {
            "max_ads": 5,
            "frequency": 60, # minutes
            "location": "montreal",
            "distance": 60, # km
            "min_price": 0,
            "max_price": 10000,
            "search_query": "electric guitar"
        }
        self.last_refresh_timestamp = 0
        self.last_cleanup_timestamp = 0
        self.last_reanalyze_all_timestamp = 0 # Pour la nouvelle fonctionnalité
        self.city_mapping = {} # Sera rempli depuis Firestore

        # Construction du chemin pour vérification
        self.collection_path = f"artifacts/{APP_ID_TARGET}/users/{USER_ID_TARGET}/guitar_deals"
        
        print(f"\n🔧 CONFIGURATION DU BOT :")
        print(f"   - APP ID  : {APP_ID_TARGET}")
        print(f"   - USER ID : {USER_ID_TARGET}")
        print(f"   - CHEMIN  : {self.collection_path}")
        print(f"   - PROMPT  : {self.prompt_instruction}")
        
        if self.offline_mode:
            print("⚠️ ATTENTION : MODE HORS-LIGNE ACTIVÉ. Aucune donnée ne sera sauvegardée dans Firebase.")
            return

        # Référence à la collection spécifique suivie par l'App React
        self.collection_ref = self.db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET) \
            .collection('guitar_deals')
            
        # Référence au document utilisateur pour écouter les changements de prompt et config
        self.user_ref = self.db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET)
            
        # Référence à la collection des villes
        self.cities_ref = self.db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET) \
            .collection('cities')

        self._init_firestore_structure()

    def _init_firestore_structure(self):
        """Initialise la structure Firestore si elle n'existe pas."""
        print("   ⏳ Vérification de l'accès Firestore (Timeout 10s)...")
        try:
            # 1. Création du document App (artifacts/{APP_ID})
            app_ref = self.db.collection('artifacts').document(APP_ID_TARGET)
            
            # Vérification de la connexion avant de tenter des écritures
            try:
                doc_snapshot = app_ref.get(timeout=10)
                
                if not doc_snapshot.exists:
                    app_ref.set({'created_at': firestore.SERVER_TIMESTAMP, 'type': 'app_root'})
                    print(f"📁 Document parent créé : artifacts/{APP_ID_TARGET}")
                else:
                    print("   ✅ Connexion Firestore OK.")
                    
            except Exception as e:
                print(f"❌ Erreur de connexion Firebase lors de l'init : {e}")
                print("👉 Passage en MODE HORS-LIGNE temporaire.")
                self.offline_mode = True
                return

            # 2. Création du document User (artifacts/{APP_ID}/users/{USER_ID})
            user_ref = app_ref.collection('users').document(USER_ID_TARGET)
            if not user_ref.get(timeout=10).exists:
                user_ref.set({
                    'created_at': firestore.SERVER_TIMESTAMP, 
                    'type': 'user_root', 
                    'prompt': self.prompt_instruction,
                    'verdictRules': self.verdict_rules,
                    'reasoningInstruction': self.reasoning_instruction,
                    'scanConfig': self.scan_config
                })
                print(f"👤 Document parent créé : users/{USER_ID_TARGET}")
            else:
                # Si le document existe, on récupère le prompt et la config
                self.sync_configuration(initial=True)
                
            # Chargement initial des villes
            # self.load_cities_from_firestore() # Moved to main loop
                
        except Exception as e:
            print(f"⚠️ Impossible de créer les documents parents (non bloquant) : {e}")

    def load_cities_from_firestore(self):
        """Charge la liste des villes configurées par l'utilisateur depuis Firestore."""
        if self.offline_mode:
            return

        try:
            docs = self.cities_ref.stream()
            new_mapping = {}
            count = 0
            for doc in docs:
                data = doc.to_dict()
                if 'name' in data and 'id' in data:
                    # Normalisation du nom pour la recherche (minuscules, sans accents)
                    normalized_name = data['name'].lower().strip()
                    normalized_name = unicodedata.normalize('NFD', normalized_name).encode('ascii', 'ignore').decode("utf-8")
                    new_mapping[normalized_name] = data['id']
                    count += 1
            
            self.city_mapping = new_mapping
            print(f"   🏙️ {count} villes chargées depuis Firestore.")
            
        except Exception as e:
            print(f"⚠️ Erreur chargement des villes : {e}")

    def sync_configuration(self, initial=False):
        """Synchronise la configuration et vérifie les demandes de refresh."""
        if self.offline_mode:
            return False, False, False, None # Added None for specific_url_to_scan

        try:
            # Removed: self.load_cities_from_firestore()

            doc = self.user_ref.get()
            should_refresh = False
            should_cleanup = False
            should_reanalyze_all = False
            specific_url_to_scan = None # New variable

            if doc.exists:
                data = doc.to_dict()
                
                # --- MISE À JOUR : Ajout des champs manquants ---
                update_payload = {}
                if 'verdictRules' not in data:
                    update_payload['verdictRules'] = self.verdict_rules
                if 'reasoningInstruction' not in data:
                    update_payload['reasoningInstruction'] = self.reasoning_instruction
                
                if update_payload:
                    print("🔧 Mise à jour du document utilisateur avec les nouveaux champs de configuration...")
                    self.user_ref.update(update_payload)
                    data.update(update_payload) # Met à jour la copie locale des données
                # --- FIN MISE À JOUR ---

                # 1. Prompt
                if 'prompt' in data and data['prompt'] != self.prompt_instruction:
                    self.prompt_instruction = data['prompt']
                    print(f"🔄 Prompt mis à jour : {self.prompt_instruction}")

                # 2. Verdict Rules
                if 'verdictRules' in data and data['verdictRules'] != self.verdict_rules:
                    self.verdict_rules = data['verdictRules']
                    print(f"🔄 Règles de verdict mises à jour.")

                # 3. Reasoning Instruction
                if 'reasoningInstruction' in data and data['reasoningInstruction'] != self.reasoning_instruction:
                    self.reasoning_instruction = data['reasoningInstruction']
                    print(f"🔄 Instruction de raisonnement mise à jour.")

                # 4. Scan Config
                if 'scanConfig' in data:
                    config = data['scanConfig']
                    self.scan_config['max_ads'] = config.get('maxAds', 5)
                    self.scan_config['frequency'] = config.get('frequency', 60)
                    self.scan_config['location'] = config.get('location', 'montreal')
                    self.scan_config['distance'] = config.get('distance', 60)
                    self.scan_config['min_price'] = config.get('minPrice', 0)
                    self.scan_config['max_price'] = config.get('maxPrice', 10000)
                    self.scan_config['search_query'] = config.get('searchQuery', 'electric guitar')

                # 5. Force Refresh
                if 'forceRefresh' in data:
                    last_refresh = data['forceRefresh']
                    
                    if initial:
                        # Initialisation : on se cale sur le timestamp actuel sans déclencher
                        self.last_refresh_timestamp = last_refresh
                    elif last_refresh != self.last_refresh_timestamp:
                        print(f"⚡ Refresh manuel demandé ! (Timestamp: {last_refresh})")
                        self.last_refresh_timestamp = last_refresh
                        should_refresh = True

                # 6. Force Cleanup
                if 'forceCleanup' in data:
                    last_cleanup = data['forceCleanup']
                    
                    if initial:
                        self.last_cleanup_timestamp = last_cleanup
                    elif last_cleanup != self.last_cleanup_timestamp:
                        print(f"🧹 Nettoyage manuel demandé ! (Timestamp: {last_cleanup})")
                        self.last_cleanup_timestamp = last_cleanup
                        should_cleanup = True
                
                # 7. Force Reanalyze All
                if 'forceReanalyzeAll' in data:
                    last_reanalyze = data['forceReanalyzeAll']
                    if initial:
                        self.last_reanalyze_all_timestamp = last_reanalyze
                    elif last_reanalyze != self.last_reanalyze_all_timestamp:
                        print(f"🧠 Ré-analyse globale demandée ! (Timestamp: {last_reanalyze})")
                        self.last_reanalyze_all_timestamp = last_reanalyze
                        should_reanalyze_all = True
                
                # 8. Scan Specific URL
                if 'scanSpecificUrl' in data and data['scanSpecificUrl']:
                    specific_url_to_scan = data['scanSpecificUrl']
                    print(f"🔗 Scan d'URL spécifique demandé : {specific_url_to_scan}")

            return should_refresh, should_cleanup, should_reanalyze_all, specific_url_to_scan
        except Exception as e:
            print(f"⚠️ Erreur sync config : {e}")
            return False, False, False, None

    def extract_facebook_id(self, url):
        """Extrait l'ID numérique unique de l'annonce Facebook depuis l'URL."""
        try:
            # Format typique: https://www.facebook.com/marketplace/item/1234567890/
            if "/item/" in url:
                # On coupe après /item/
                segment = url.split("/item/")[1]
                # On prend ce qu'il y a avant le prochain / ou ?
                fb_id = segment.split("/")[0].split("?")[0]
                if fb_id.isdigit():
                    return fb_id
            return None
        except Exception as e:
            print(f"⚠️ Erreur extraction ID: {e}")
            return None

    def download_image(self, url):
        """Télécharge l'image depuis l'URL et la convertit en objet PIL Image."""
        try:
            if not url or "via.placeholder.com" in url:
                return None
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return Image.open(BytesIO(response.content))
            return None
        except Exception as e:
            print(f"⚠️ Impossible de télécharger l'image : {e}")
            return None

    def analyze_deal_with_gemini(self, listing_data):
        """Utilise Gemini pour évaluer si l'annonce est une bonne affaire (Multimodal)."""
        # Removed: self.sync_configuration()

        if not self.model:
             print("⚠️ Modèle Gemini non initialisé (Clé API manquante ?)")
             return {
                "verdict": "ERROR",
                "estimated_value": listing_data['price'],
                "reasoning": "Analyse IA impossible : Modèle non initialisé.",
                "confidence": 0
            }

        print(f"🤖 Analyse IA pour : {listing_data['title']}...")

        # Téléchargement des images
        images = []
        # Gestion de plusieurs images (imageUrls) ou d'une seule (imageUrl)
        urls_to_process = listing_data.get('imageUrls', [])
        if not urls_to_process and listing_data.get('imageUrl'):
            urls_to_process = [listing_data['imageUrl']]
            
        # Limite à 8 images pour éviter de surcharger
        urls_to_process = urls_to_process[:8] # Changed from 5 to 8

        for url in urls_to_process:
            img = self.download_image(url)
            if img:
                images.append(img)
        
        # Le prompt devient une simple fiche technique
        user_message = f"""
        Évalue cette annonce :
        Titre : {listing_data['title']}
        Prix affiché : {listing_data['price']}$
        Description : {listing_data['description']}
        Localisation : {listing_data['location']}
        
        Règles de verdict à appliquer :
        {self.verdict_rules}
        """

        try:
            # Construction du contenu multimodal
            content = [user_message]
            content.extend(images)
            
            if images:
                print(f"   📸 {len(images)} images incluses dans l'analyse.")
            else:
                print("   ⚠️ Analyse texte uniquement (pas d'image valide).")

            response = self.model.generate_content(content)
            # Pas besoin de nettoyer le markdown, response_mime_type est JSON
            result = json.loads(response.text)
            
            # --- CORRECTION : GESTION DU CAS OÙ GEMINI RENVOIE UNE LISTE ---
            if isinstance(result, list):
                if len(result) > 0:
                    return result[0]
                else:
                    return {
                        "verdict": "ERROR",
                        "estimated_value": listing_data['price'],
                        "reasoning": "L'IA a renvoyé une liste vide.",
                        "confidence": 0
                    }
            return result

        except Exception as e:
            error_str = str(e)
            if "403" in error_str and "leaked" in error_str:
                print("\n" + "!"*60)
                print("❌ ERREUR CRITIQUE : VOTRE CLÉ API GEMINI A FUITÉ ET EST BLOQUÉE.")
                print("👉 Google a désactivé cette clé par sécurité.")
                print("👉 Générez-en une nouvelle ici : https://aistudio.google.com/app/apikey")
                print("👉 Mettez à jour GEMINI_API_KEY dans votre fichier .env")
                print("!"*60 + "\n")
            else:
                print(f"❌ Erreur Gemini: {e}")

            return {
                "verdict": "ERROR",
                "estimated_value": listing_data['price'],
                "reasoning": "Erreur d'analyse IA (Voir logs console)",
                "confidence": 0
            }

    def save_to_firestore(self, listing_data, analysis, doc_id=None):
        """Sauvegarde les données au chemin exact écouté par React."""
        if self.offline_mode:
            print(f"🚫 [OFFLINE] Données non sauvegardées : {listing_data['title']}")
            return

        try:
            # Si pas d'ID fourni, on génère un ID de secours (ne devrait pas arriver avec FB)
            if not doc_id:
                doc_id = f"{listing_data['title'][:15]}_{listing_data['price']}".replace(" ", "_").lower()
                doc_id = "".join(c for c in doc_id if c.isalnum() or c in ('_', '-'))

            # --- AJOUT LOGGING ---
            num_images_payload = len(listing_data.get('imageUrls', []))
            print(f"   💾 Préparation pour sauvegarde : {num_images_payload} images dans le payload.")

            # Si le verdict est REJECTED, on met le statut à 'rejected'
            status = "analyzed"
            if analysis.get('verdict') == 'REJECTED':
                status = "rejected"

            data = {
                **listing_data,
                "aiAnalysis": analysis,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "status": status
            }

            self.collection_ref.document(doc_id).set(data, merge=True) # Utiliser merge=True pour ne pas écraser isFavorite
            print(f"💾 Envoyé à l'App: {listing_data['title']} (ID: {doc_id}) - Status: {status}")
        except Exception as e:
            print(f"❌ Erreur Firestore: {e}")

    def cleanup_sold_listings(self):
        """Vérifie si les annonces en base sont toujours disponibles et supprime les vendues."""
        if self.offline_mode:
            return

        print("\n🧹 Lancement du nettoyage des annonces vendues...")
        try:
            # 1. Get all non-rejected listings
            docs = self.collection_ref.where(filter=FieldFilter('status', '!=', 'rejected')).stream()
            
            listings_to_check = []
            for doc in docs:
                listings_to_check.append({'id': doc.id, 'data': doc.to_dict()})

            if not listings_to_check:
                print("   ✅ Aucune annonce active à vérifier.")
                return
                
            print(f"   🔍 {len(listings_to_check)} annonces à vérifier...")

            deleted_count = 0
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                
                # Utilisation d'un contexte similaire au scan pour éviter les blocages
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    locale="fr-CA",
                    timezone_id="America/Montreal"
                )
                
                for listing in listings_to_check:
                    listing_id = listing['id']
                    listing_data = listing['data']
                    url = listing_data.get('link')

                    if not url:
                        continue

                    page = context.new_page()
                    try:
                        print(f"   - Vérification de : {listing_data.get('title', listing_id)}...")
                        page.goto(url, timeout=30000)
                        
                        # Check for "This listing is no longer available"
                        # The text is "Cette annonce n’est plus disponible" in French
                        sold_indicator = page.locator('span:has-text("Cette annonce n’est plus disponible"), span:has-text("This listing is no longer available")')
                        
                        if sold_indicator.count() > 0:
                            print(f"   🗑️ Annonce vendue/supprimée. Suppression de la base de données...")
                            self.collection_ref.document(listing_id).delete()
                            deleted_count += 1
                        else:
                            # print(f"   👍 Annonce toujours active.")
                            pass

                    except Exception as e:
                        print(f"   ⚠️ Erreur lors de la vérification de {listing_id}: {e}")
                    finally:
                        page.close()
                        time.sleep(1) # Petite pause pour être gentil avec le serveur

                browser.close()
            
            print(f"🏁 Nettoyage terminé. {deleted_count} annonce(s) supprimée(s).")

        except Exception as e:
            print(f"❌ Erreur durant le processus de nettoyage : {e}")

    def _close_login_popup(self, page):
        """Tente de fermer le popup de connexion qui peut apparaître."""
        try:
            # On attend un peu que le popup se charge s'il doit apparaître
            time.sleep(1) # Réduit le délai pour être plus réactif
            close_login_btn = page.locator("div[aria-label='Fermer'], div[aria-label='Close'], div[role='button'][aria-label*='Fermer']").first
            
            if close_login_btn.count() > 0 and close_login_btn.is_visible(timeout=2000):
                print("   🔐 Popup de connexion détecté, tentative de fermeture...")
                close_login_btn.click()
                print("   ✅ Popup de connexion fermé.")
                time.sleep(1)
        except Exception as e:
            # Non bloquant, on continue
            pass

    def _setup_browser(self, p):
        """Initialise le navigateur et le contexte Playwright."""
        browser = p.chromium.launch(
            headless=False,
            args=["--start-minimized"] 
        )
        
        # Coordonnées de Montréal pour forcer la géolocalisation
        montreal_geo = {"latitude": 45.5017, "longitude": -73.5673}

        context = browser.new_context(
            viewport=None,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="fr-CA",
            timezone_id="America/Montreal",
            geolocation=montreal_geo,
            permissions=["geolocation"],
            extra_http_headers={"Referer": "https://www.google.com/"}
        )
        return browser, context

    def _apply_filters(self, page, distance, max_price):
        """Applique les filtres de rayon et de prix sur la page de recherche."""
        # --- APPLICATION DU RAYON VIA UI ---
        try:
            print(f"   📍 Tentative d'application du rayon de {distance} km via l'interface...")
            time.sleep(2)
            
            loc_btn = page.locator("div[role='button']").filter(has_text="km").first
            
            if loc_btn.count() > 0 and loc_btn.is_visible():
                loc_btn.click()
                time.sleep(2)
                
                modal = page.locator("div[role='dialog']").first
                if modal.count() > 0:
                    radius_dropdown = modal.locator("div, span").filter(has_text="kilomètres").last
                    if radius_dropdown.count() == 0:
                        radius_dropdown = modal.locator("div, span").filter(has_text="km").last
                    
                    if radius_dropdown.count() > 0:
                        radius_dropdown.click()
                        try: page.wait_for_selector("div[role='option']", timeout=5000)
                        except: pass

                        available_options = page.locator("div[role='option']").all()
                        best_option = None
                        min_diff = float('inf')
                        
                        visible_options = [opt for opt in available_options if opt.is_visible()]
                        
                        for option in visible_options:
                            text = option.inner_text()
                            digits = ''.join(filter(str.isdigit, text))
                            if digits:
                                val = int(digits)
                                diff = abs(val - distance)
                                if diff < min_diff:
                                    min_diff = diff
                                    best_option = option
                        
                        if best_option:
                            best_option.click()
                            time.sleep(1)
                    
                    apply_btn = modal.locator("div[aria-label*='Appliquer'], div[aria-label*='Apply'], span:has-text('Appliquer'), span:has-text('Apply')").first
                    if apply_btn.count() > 0:
                        apply_btn.click()
                        time.sleep(5)
                        try: page.wait_for_load_state("networkidle", timeout=5000)
                        except: pass
                    else:
                        page.keyboard.press("Escape")
        except Exception as e:
            print(f"   ⚠️ Erreur lors de l'application du rayon (UI) : {e}")

        # --- FORÇAGE DE LA MISE À JOUR VIA LE PRIX ---
        try:
            print(f"   💰 Application du prix final ({max_price} $) pour forcer la mise à jour...")
            max_price_input = page.locator("input[aria-label='Prix maximum'], input[aria-label='Maximum price']").first
            
            if max_price_input.is_visible(timeout=5000):
                max_price_input.fill(str(max_price))
                time.sleep(0.5)
                max_price_input.press("Enter")
                print("   ✅ Prix final appliqué. Attente du rechargement...")
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(3)
            else:
                print("   ⚠️ Champ 'Prix maximum' non trouvé (timeout).")
        except Exception as e:
            print(f"   ⚠️ Erreur lors de l'application du prix final : {e}")

    def _extract_listing_details(self, context, clean_link, title, price, location):
        """Ouvre une annonce et extrait les détails (images, description, et coordonnées)."""
        description = f"Annonce Marketplace. {title}. Localisation: {location}"
        image_urls = []
        coordinates = None # Initialisation des coordonnées à None
        
        try:
            print(f"   ➡️  Ouverture de l'annonce pour détails : {clean_link}")
            detail_page = context.new_page()
            detail_page.goto(clean_link, timeout=45000)
            self._close_login_popup(detail_page)
            
            try: detail_page.wait_for_selector("div[role='main']", timeout=10000)
            except: pass
            time.sleep(2) 
            
            # --- RECUPERATION DES IMAGES ---
            collected_urls = []
            seen_srcs = set()
            
            for i in range(10): 
                try:
                    imgs = detail_page.locator("div[role='main'] img").all()
                    found_new = False
                    for img in imgs:
                        if not img.is_visible(): continue
                        box = img.bounding_box()
                        if box and box['width'] > 300 and box['height'] > 300:
                            src = img.get_attribute("src")
                            if src and "scontent" in src and src not in seen_srcs:
                                collected_urls.append(src)
                                seen_srcs.add(src)
                                found_new = True
                except: pass
                
                if not found_new and len(collected_urls) > 0: break
                if len(collected_urls) >= 10: break

                try:
                    detail_page.keyboard.press("ArrowRight")
                    time.sleep(0.8) 
                except: pass # Changed from `break` to `pass` to allow trying other image extraction methods
            
            image_urls = collected_urls
            
            # --- EXTRACTION DES COORDONNÉES DE LA CARTE ---
            try:
                map_image_locator = detail_page.locator('img[src*="staticmap"]').first
                if map_image_locator.is_visible(timeout=5000): # Attendre que l'image de la carte soit visible
                    src = map_image_locator.get_attribute('src')
                    if src:
                        # Utiliser une regex pour extraire les coordonnées dans l'URL
                        match = re.search(r'center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', src)
                        if match:
                            coordinates = {"lat": float(match.group(1)), "lng": float(match.group(2))}
                            print(f"   🗺️ Coordonnées extraites: {coordinates['lat']}, {coordinates['lng']}")
                        else:
                            print("   ⚠️ Coordonnées non trouvées dans l'URL de la carte statique.")
                else:
                    print("   ⚠️ Image de carte statique non trouvée sur la page de détails.")
            except Exception as e:
                print(f"   ❌ Erreur lors de l'extraction des coordonnées de la carte: {e}")

            # --- RECUPERATION DESCRIPTION ---
            extracted_description = None
            try:
                og_desc = detail_page.locator('meta[property="og:description"]').get_attribute('content')
                if og_desc and len(og_desc.strip()) > 10:
                    extracted_description = og_desc.strip()
                else:
                    name_desc = detail_page.locator('meta[name="description"]').get_attribute('content')
                    if name_desc and len(name_desc.strip()) > 10:
                        extracted_description = name_desc.strip()

                if not extracted_description:
                    try:
                        see_more = detail_page.locator('div[role="button"]:has-text("Voir plus"), div[role="button"]:has-text("See more")').first
                        if see_more.is_visible(timeout=2000):
                            see_more.click()
                            time.sleep(0.5)

                        details_heading = detail_page.locator('h2:has-text("Détails"), h2:has-text("Details")').first
                        if details_heading.is_visible(timeout=1000):
                            parent = details_heading.locator('xpath=..')
                            all_texts = parent.locator('span[dir="auto"]').all_inner_texts()
                            long_texts = [t.strip() for t in all_texts if len(t.strip()) > 50]
                            if long_texts: extracted_description = max(long_texts, key=len)

                        if not extracted_description:
                            all_texts = detail_page.locator('div[role="main"] span[dir="auto"]').all_inner_texts()
                            excluded = {title, f"{price} $", location}
                            long_texts = [t.strip() for t in all_texts if len(t.strip()) > 50 and t not in excluded]
                            if long_texts: extracted_description = max(long_texts, key=len)

                    except: pass

            except: pass

            if extracted_description:
                description = extracted_description
            
            description = description[:3000]
            detail_page.close()
            
        except Exception as e:
            print(f"   ❌ Erreur détails annonce : {e}")
            if 'detail_page' in locals():
                try: detail_page.close()
                except: pass
        
        return description, image_urls, coordinates # Modification de la valeur de retour

    def _process_listing(self, link_loc, context, location, distance, max_ads, processed_count, seen_urls):
        """Traite un élément d'annonce individuel."""
        if processed_count >= max_ads:
            return processed_count

        href = link_loc.get_attribute("href")
        if not href: return processed_count
        full_link = f"https://www.facebook.com{href}" if href.startswith("/") else href
        clean_link = full_link.split('?')[0]
        
        if clean_link in seen_urls: return processed_count
        seen_urls.add(clean_link)

        fb_id = self.extract_facebook_id(clean_link)
        if not fb_id: return processed_count

        # Extraction basique
        text_content = link_loc.inner_text()
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        
        img_loc = link_loc.locator("img").first
        image_url = "https://via.placeholder.com/400?text=No+Image"
        title = ""
        
        if img_loc.count() > 0:
            src = img_loc.get_attribute("src")
            if src: image_url = src
            alt_text = img_loc.get_attribute("alt")
            if alt_text and len(alt_text) > 3: title = alt_text

        if not title:
            for line in lines:
                if not any(c in line for c in ['$', '€', '£', 'Free', 'Gratuit']) and len(line) > 3:
                    title = line
                    break
            if not title: title = "Titre Inconnu"

        price = 0
        found_price = False
        for line in lines:
            if not found_price and any(c in line for c in ['$', '€', '£', 'Free', 'Gratuit']):
                digits = ''.join(filter(str.isdigit, line))
                if digits:
                    price = int(digits)
                    found_price = True
                elif "Free" in line or "Gratuit" in line:
                    price = 0
                    found_price = True
        
        # --- TENTATIVE D'EXTRACTION DE LA LOCALISATION SPÉCIFIQUE ---
        specific_location = location # Fallback
        if len(lines) >= 3:
            # Souvent la dernière ligne est la ville
            potential_loc = lines[-1]
            # Filtre basique pour éviter de prendre un prix ou un statut
            if len(potential_loc) < 40 and not any(c in potential_loc for c in ['$', '€']):
                specific_location = potential_loc

        if (price > 0 or "Gratuit" in text_content or "Free" in text_content):
            print(f"   ✨ Annonce trouvée : {title} ({price} $) @ {specific_location}")
            
            # Vérification doublon
            if not self.offline_mode:
                try:
                    doc_snap = self.collection_ref.document(fb_id).get()
                    if doc_snap.exists:
                        existing = doc_snap.to_dict()
                        if existing.get('status') == 'rejected':
                            print(f"   🚫 Annonce déjà rejetée. On passe.")
                            return processed_count
                        if existing.get('price') == price:
                            print(f"   ⏭️ Annonce existante et prix inchangé. On passe.")
                            return processed_count
                        print(f"   🔄 Le prix a changé ! Mise à jour...")
                except: pass
            
            # Extraction détaillée
            description, image_urls, coordinates = self._extract_listing_details(context, clean_link, title, price, location) # Récupération des coordonnées
            final_image_url = image_urls[0] if image_urls else image_url

            listing_data = {
                "title": title,
                "price": price,
                "description": description,
                "imageUrl": final_image_url,
                "imageUrls": image_urls,
                "link": clean_link,
                "location": specific_location, # Utilisation de la localisation spécifique
                "searchDistance": distance
            }
            if coordinates: # Ajout des coordonnées si elles ont été trouvées
                listing_data["latitude"] = coordinates["lat"]
                listing_data["longitude"] = coordinates["lng"]
            
            analysis = self.analyze_deal_with_gemini(listing_data)
            self.save_to_firestore(listing_data, analysis, doc_id=fb_id)
            return processed_count + 1
        
        return processed_count

    def scan_facebook_marketplace(self, search_query="electric guitar", location="montreal", distance=60, min_price=0, max_price=10000, max_ads=5):
        """Scrape réellement Facebook Marketplace avec Playwright."""
        print(f"\n🌍 Lancement du scan Facebook pour '{search_query}' à {location} (Max: {max_ads}, Prix: {min_price}-{max_price}$)...")
        
        # --- VALIDATION DE LA VILLE ---
        normalized_loc = location.lower().strip()
        normalized_loc = unicodedata.normalize('NFD', normalized_loc).encode('ascii', 'ignore').decode("utf-8")
        city_id = self.city_mapping.get(normalized_loc)
        
        if not city_id:
            if location.isdigit(): city_id = location
            else:
                error_msg = f"Ville '{location}' inconnue. Ajoutez-la dans l'onglet Configuration."
                print(f"❌ {error_msg}")
                if not self.offline_mode:
                    try: self.user_ref.update({'scanStatus': 'error', 'scanError': error_msg})
                    except: pass
                return
        
        if not self.offline_mode:
            try: self.user_ref.update({'scanStatus': 'running', 'scanError': firestore.DELETE_FIELD})
            except: pass

        print(f"   📍 Ville identifiée : ID {city_id}")

        with sync_playwright() as p:
            browser, context = self._setup_browser(p)
            page = context.new_page()
            
            encoded_query = urllib.parse.quote(search_query)
            temp_max_price = max_price - 1 if max_price > min_price and max_price > 0 else max_price
            url = f"https://www.facebook.com/marketplace/{city_id}/search/?minPrice={min_price}&maxPrice={temp_max_price}&query={encoded_query}&exact=false"
            
            try:
                print(f"   ➡️ Navigation vers : {url}")
                page.goto(url, timeout=60000)
                
                try: page.evaluate("document.body.style.zoom = '0.5'")
                except: pass
                
                # Cookies
                try: page.get_by_role("button", name="Allow all cookies").click(timeout=3000)
                except: pass
                try: page.get_by_role("button", name="Decline optional cookies").click(timeout=3000)
                except: pass

                self._close_login_popup(page)
                self._apply_filters(page, distance, max_price)

                # Scroll
                try: page.wait_for_selector("div[role='main']", timeout=15000)
                except: pass
                print("   📜 Défilement...")
                for _ in range(3):
                    page.mouse.wheel(0, 1000)
                    time.sleep(2)

                # Extraction
                print("   🔍 Recherche des éléments d'annonce...")
                listings_locators = page.locator("a[href*='/marketplace/item/']").all()
                print(f"   👀 {len(listings_locators)} éléments trouvés.")
                
                processed_count = 0
                seen_urls = set()

                for link_loc in listings_locators:
                    processed_count = self._process_listing(link_loc, context, location, distance, max_ads, processed_count, seen_urls)
                    if processed_count >= max_ads: break
                        
            except Exception as e:
                print(f"❌ Erreur durant le scraping : {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()
                print("🏁 Session de scraping terminée.")

    def scan_specific_url(self, url_to_scan):
        """Scanne une URL Facebook Marketplace spécifique, extrait les détails, analyse et sauvegarde."""
        if self.offline_mode:
            print(f"🚫 [OFFLINE] Impossible de scanner l'URL spécifique : {url_to_scan}")
            return

        print(f"\n🔗 Lancement du scan d'URL spécifique : {url_to_scan}")

        # Clear the specific URL request in Firestore immediately
        try:
            self.user_ref.update({'scanSpecificUrl': firestore.DELETE_FIELD})
            print("   ✅ Requête d'URL spécifique effacée de Firestore.")
        except Exception as e:
            print(f"   ⚠️ Erreur lors de l'effacement de scanSpecificUrl dans Firestore : {e}")

        fb_id = self.extract_facebook_id(url_to_scan)
        if not fb_id:
            print(f"❌ Impossible d'extraire l'ID Facebook de l'URL : {url_to_scan}")
            return

        with sync_playwright() as p:
            browser, context = self._setup_browser(p)
            try:
                detail_page = context.new_page()
                detail_page.goto(url_to_scan, timeout=60000)
                self._close_login_popup(detail_page)
                try: detail_page.wait_for_selector("div[role='main']", timeout=15000)
                except: pass
                time.sleep(2)

                # Extract title, price, location from the detail page
                title = "Titre Inconnu"
                price = 0
                location = "Localisation Inconnue"

                # Try to get title from meta tag first
                og_title = detail_page.locator('meta[property="og:title"]').get_attribute('content')
                if og_title:
                    title = og_title.split(' - ')[0] # Often "Title - Price - Location"

                # Try to get price
                price_locator = detail_page.locator('div[role="main"] span:has-text("$"]').first
                if price_locator.count() > 0:
                    price_text = price_locator.inner_text()
                    digits = ''.join(filter(str.isdigit, price_text))
                    if digits:
                        price = int(digits)

                # Try to get location
                location_locator = detail_page.locator('div[role="main"] span:has-text("·")').first # Often "City · Time"
                if location_locator.count() > 0:
                    location_text = location_locator.inner_text()
                    location = location_text.split('·')[0].strip()


                description, image_urls, coordinates = self._extract_listing_details(context, url_to_scan, title, price, location)
                final_image_url = image_urls[0] if image_urls else "https://via.placeholder.com/400?text=No+Image"

                listing_data = {
                    "title": title,
                    "price": price,
                    "description": description,
                    "imageUrl": final_image_url,
                    "imageUrls": image_urls,
                    "link": url_to_scan,
                    "location": location,
                    "searchDistance": 0 # Not applicable for specific URL scan
                }
                if coordinates:
                    listing_data["latitude"] = coordinates["lat"]
                    listing_data["longitude"] = coordinates["lng"]

                analysis = self.analyze_deal_with_gemini(listing_data)
                self.save_to_firestore(listing_data, analysis, doc_id=fb_id)
                print(f"✅ Scan d'URL spécifique terminé pour : {title}")

            except Exception as e:
                print(f"❌ Erreur lors du scan d'URL spécifique {url_to_scan}: {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()

    def process_retry_queue(self):
        """Traite les annonces marquées pour ré-analyse."""
        if self.offline_mode: return

        try:
            # On cherche les annonces avec status='retry_analysis'
            docs = self.collection_ref.where(filter=FieldFilter('status', '==', 'retry_analysis')).stream()
            count = 0
            
            for doc in docs:
                data = doc.to_dict()
                print(f"🔄 Ré-analyse demandée pour : {data.get('title', 'Sans titre')}")
                
                # On reconstruit listing_data à partir de Firestore
                # On s'assure d'avoir les champs minimaux
                if not data.get('title'):
                    print("   ⚠️ Données incomplètes, impossible de ré-analyser.")
                    continue
                    
                listing_data = {
                    "title": data.get('title'),
                    "price": data.get('price'),
                    "description": data.get('description', ''),
                    "location": data.get('location', 'Inconnue'),
                    "imageUrls": data.get('imageUrls', []),
                    "imageUrl": data.get('imageUrl'),
                    "link": data.get('link')
                }
                # Si les coordonnées existent déjà, on les garde
                if data.get('latitude') is not None and data.get('longitude') is not None:
                    listing_data['latitude'] = data['latitude']
                    listing_data['longitude'] = data['longitude']
                
                # Analyse IA
                analysis = self.analyze_deal_with_gemini(listing_data)
                
                # Sauvegarde (mettra à jour le status)
                self.save_to_firestore(listing_data, analysis, doc_id=doc.id)
                count += 1
                
            if count > 0:
                print(f"✅ {count} annonces ré-analysées.")
                
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la file d'attente : {e}")

    def reanalyze_all_listings(self):
        """Marque toutes les annonces non rejetées pour une ré-analyse."""
        if self.offline_mode:
            print("🚫 [OFFLINE] Impossible de lancer la ré-analyse globale.")
            return

        print("🧠 Lancement du processus de ré-analyse globale...")
        try:
            docs = self.collection_ref.where(filter=FieldFilter('status', '!=', 'rejected')).stream()
            
            batch = self.db.batch()
            count = 0
            for doc in docs:
                batch.update(doc.reference, {'status': 'retry_analysis'})
                count += 1
            
            if count > 0:
                batch.commit()
                print(f"✅ {count} annonces marquées pour ré-analyse. Le thread de surveillance va les traiter.")
            else:
                print("✅ Aucune annonce active à ré-analyser.")

        except Exception as e:
            print(f"❌ Erreur lors du marquage pour ré-analyse globale : {e}")

    def run_test_scan(self):
        """Génère des données de test pour vérifier la synchronisation."""
        print(f"🔎 Démarrage du scan de test (MOCK)...")

        mock_listings = [
            {
                "title": "Gibson Les Paul Standard 2021",
                "price": 1600,
                "description": "État neuf, micros Burstbucker, étui original. Urgent.",
                "imageUrl": "https://images.unsplash.com/photo-1516924962500-2b4b3b99ea02?q=80&w=400",
                "imageUrls": [
                    "https://images.unsplash.com/photo-1516924962500-2b4b3b99ea02?q=80&w=400",
                    "https://images.unsplash.com/photo-1564186763535-ebb21ef5277f?q=80&w=400"
                ],
                "link": "https://facebook.com/marketplace/item/1234567890"
            },
            {
                "title": "Squier Strat Classic Vibe 60s",
                "price": 250,
                "description": "Excellent état, parfaite pour débuter ou upgrade.",
                "imageUrl": "https://images.unsplash.com/photo-1550291652-6ea9114a47b1?q=80&w=400",
                "imageUrls": [
                    "https://images.unsplash.com/photo-1550291652-6ea9114a47b1?q=80&w=400"
                ],
                "link": "https://facebook.com/marketplace/item/0987654321"
            }
        ]

        for listing in mock_listings:
            # Extraction ID fictif
            fb_id = self.extract_facebook_id(listing['link'])
            analysis = self.analyze_deal_with_gemini(listing)
            self.save_to_firestore(listing, analysis, doc_id=fb_id)
            time.sleep(1)

def monitor_retries(bot):
    """Fonction exécutée dans un thread séparé pour surveiller les demandes de ré-analyse."""
    print("🧵 Démarrage du thread de surveillance des ré-analyses...")
    while True:
        try:
            # On vérifie la file d'attente
            bot.process_retry_queue()
            # Pause courte pour ne pas spammer Firestore (5 secondes)
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ Erreur dans le thread de surveillance : {e}")
            time.sleep(10) # Pause plus longue en cas d'erreur

if __name__ == "__main__":
    # Demande du prompt personnalisé au démarrage
    print(f"Prompt par défaut: {PROMPT_INSTRUCTION}")
    
    bot = GuitarHunterBot(db, model, offline_mode)

    # --- SÉCURITÉ AU DÉMARRAGE ---
    if bot.offline_mode:
        print("\n❌ Le bot n'a pas pu s'initialiser correctement (mode hors-ligne). Arrêt du script.")
        sys.exit(1)
    
    # --- DÉMARRAGE DU THREAD DE SURVEILLANCE ---
    retry_thread = threading.Thread(target=monitor_retries, args=(bot,), daemon=True)
    retry_thread.start()
    
    print("\n--- MODE AUTOMATIQUE ---")
    print("Le bot va surveiller la configuration et scanner périodiquement.")
    print("Appuyez sur Ctrl+C pour arrêter.")
    
    last_scan_time = 0
    last_auto_cleanup_time = 0
    
    try:
        while True:
            # 1. Synchronisation de la config et vérification du refresh manuel
            should_refresh, should_cleanup, should_reanalyze_all, specific_url_to_scan = bot.sync_configuration()
            
            # NOTE: bot.process_retry_queue() est maintenant géré par le thread monitor_retries

            # --- GESTION DU SCAN D'URL SPÉCIFIQUE ---
            if specific_url_to_scan:
                bot.scan_specific_url(specific_url_to_scan)

            # 2. Vérification du temps écoulé
            current_time = time.time()
            frequency_seconds = bot.scan_config['frequency'] * 60
            
            # --- GESTION DU NETTOYAGE (MANUEL OU QUOTIDIEN) ---
            # Nettoyage automatique une fois par jour (24h = 86400s)
            if should_cleanup or (current_time - last_auto_cleanup_time > 86400):
                if should_cleanup:
                    print("🧹 Lancement du nettoyage (Manuel)...")
                else:
                    print("🧹 Lancement du nettoyage quotidien (Auto)...")
                
                bot.cleanup_sold_listings()
                last_auto_cleanup_time = time.time()

            # --- GESTION DE LA RÉ-ANALYSE GLOBALE ---
            if should_reanalyze_all:
                bot.reanalyze_all_listings()

            # --- GESTION DU SCAN PÉRIODIQUE ---
            # Si refresh demandé OU temps écoulé
            if should_refresh or (current_time - last_scan_time > frequency_seconds):
                if should_refresh:
                    print("⚡ Lancement du scan (Manuel)...")
                else:
                    print(f"⏰ Lancement du scan (Auto - {bot.scan_config['frequency']} min)...")
                
                # Load cities before every scan
                bot.load_cities_from_firestore() # Moved here

                # Lancement du scan
                bot.scan_facebook_marketplace(
                    search_query=bot.scan_config['search_query'],
                    location=bot.scan_config['location'],
                    distance=bot.scan_config['distance'],
                    min_price=bot.scan_config['min_price'],
                    max_price=bot.scan_config['max_price'],
                    max_ads=bot.scan_config['max_ads']
                )
                
                last_scan_time = time.time()
                print(f"💤 Prochain scan auto dans {bot.scan_config['frequency']} minutes...")
            
            # Pause courte pour éviter de spammer Firestore
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du bot.")