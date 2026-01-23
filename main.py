import os
import time
import json
import random
import requests
import warnings
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

# Suppression des avertissements de dépréciation (Gemini)
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

# --- Librairies Externes ---
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from playwright.sync_api import sync_playwright

# Chargement des variables d'environnement (.env)
load_dotenv()

# --- CONFIGURATION ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FIREBASE_KEY_PATH = "serviceAccountKey.json"  # Doit être à la racine du projet
PROMPT_INSTRUCTION = "Evalue cette guitare Au quebec (avec le prix)."  # Instruction principale pour l'analyse IA

# ==================================================================================
# ⚠️ IMPORTANT : CES IDs DOIVENT CORRESPONDRE À CEUX DE VOTRE APP REACT ⚠️
# Regardez dans l'en-tête de l'application React ou dans la section "Vérification du chemin Python"
# ==================================================================================
APP_ID_TARGET = "c_5d118e719dbddbfc_index.html-217"  # À remplacer par l'App ID affiché dans React
USER_ID_TARGET = "00737242777130596039"           # À remplacer par le User ID affiché dans React
# ==================================================================================

# Initialisation Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
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
    def __init__(self, prompt_instruction=PROMPT_INSTRUCTION):
        global offline_mode
        self.prompt_instruction = prompt_instruction
        # Configuration par défaut
        self.scan_config = {
            "max_ads": 5,
            "frequency": 60, # minutes
            "location": "montreal",
            "distance": 60, # km
            "min_price": 0,
            "max_price": 10000
        }
        self.last_refresh_timestamp = 0

        # Construction du chemin pour vérification
        self.collection_path = f"artifacts/{APP_ID_TARGET}/users/{USER_ID_TARGET}/guitar_deals"
        
        print(f"\n🔧 CONFIGURATION DU BOT :")
        print(f"   - APP ID  : {APP_ID_TARGET}")
        print(f"   - USER ID : {USER_ID_TARGET}")
        print(f"   - CHEMIN  : {self.collection_path}")
        print(f"   - PROMPT  : {self.prompt_instruction}")
        
        if offline_mode:
            print("⚠️ ATTENTION : MODE HORS-LIGNE ACTIVÉ. Aucune donnée ne sera sauvegardée dans Firebase.")
            return

        # Référence à la collection spécifique suivie par l'App React
        self.collection_ref = db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET) \
            .collection('guitar_deals')
            
        # Référence au document utilisateur pour écouter les changements de prompt et config
        self.user_ref = db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET)

        # --- CORRECTION : CRÉATION EXPLICITE DES PARENTS (Pour éviter l'italique/fantôme) ---
        print("   ⏳ Vérification de l'accès Firestore (Timeout 10s)...")
        try:
            # 1. Création du document App (artifacts/{APP_ID})
            app_ref = db.collection('artifacts').document(APP_ID_TARGET)
            
            # Vérification de la connexion avant de tenter des écritures
            try:
                # Ajout d'un timeout pour éviter le blocage infini si le réseau/auth déconne
                doc_snapshot = app_ref.get(timeout=10)
                
                if not doc_snapshot.exists:
                    app_ref.set({'created_at': firestore.SERVER_TIMESTAMP, 'type': 'app_root'})
                    print(f"📁 Document parent créé : artifacts/{APP_ID_TARGET}")
                else:
                    print("   ✅ Connexion Firestore OK.")
                    
            except Exception as e:
                print(f"❌ Erreur de connexion Firebase lors de l'init : {e}")
                print("👉 Passage en MODE HORS-LIGNE temporaire.")
                offline_mode = True
                return

            # 2. Création du document User (artifacts/{APP_ID}/users/{USER_ID})
            user_ref = app_ref.collection('users').document(USER_ID_TARGET)
            if not user_ref.get(timeout=10).exists:
                user_ref.set({
                    'created_at': firestore.SERVER_TIMESTAMP, 
                    'type': 'user_root', 
                    'prompt': self.prompt_instruction,
                    'scanConfig': self.scan_config
                })
                print(f"👤 Document parent créé : users/{USER_ID_TARGET}")
            else:
                # Si le document existe, on récupère le prompt et la config
                self.sync_configuration(initial=True)
                
        except Exception as e:
            print(f"⚠️ Impossible de créer les documents parents (non bloquant) : {e}")

    def sync_configuration(self, initial=False):
        """Synchronise la configuration et vérifie les demandes de refresh."""
        if offline_mode:
            return False

        try:
            doc = self.user_ref.get()
            if doc.exists:
                data = doc.to_dict()
                
                # 1. Prompt
                if 'prompt' in data and data['prompt'] != self.prompt_instruction:
                    self.prompt_instruction = data['prompt']
                    print(f"🔄 Prompt mis à jour : {self.prompt_instruction}")

                # 2. Scan Config
                if 'scanConfig' in data:
                    config = data['scanConfig']
                    self.scan_config['max_ads'] = config.get('maxAds', 5)
                    self.scan_config['frequency'] = config.get('frequency', 60)
                    self.scan_config['location'] = config.get('location', 'montreal')
                    self.scan_config['distance'] = config.get('distance', 60)
                    self.scan_config['min_price'] = config.get('minPrice', 0)
                    self.scan_config['max_price'] = config.get('maxPrice', 10000)
                    # print(f"⚙️ Config chargée : {self.scan_config}")

                # 3. Force Refresh
                if 'forceRefresh' in data:
                    last_refresh = data['forceRefresh']
                    
                    if initial:
                        # Initialisation : on se cale sur le timestamp actuel sans déclencher
                        self.last_refresh_timestamp = last_refresh
                    elif last_refresh != self.last_refresh_timestamp:
                        print(f"⚡ Refresh manuel demandé ! (Timestamp: {last_refresh})")
                        self.last_refresh_timestamp = last_refresh
                        return True # Signal to run scan immediately
            
            return False
        except Exception as e:
            print(f"⚠️ Erreur sync config : {e}")
            return False

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
        # Mise à jour du prompt avant chaque analyse (au cas où)
        self.sync_configuration()

        print(f"🤖 Analyse IA pour : {listing_data['title']}...")

        # Téléchargement des images
        images = []
        # Gestion de plusieurs images (imageUrls) ou d'une seule (imageUrl)
        urls_to_process = listing_data.get('imageUrls', [])
        if not urls_to_process and listing_data.get('imageUrl'):
            urls_to_process = [listing_data['imageUrl']]
            
        # Limite à 5 images pour éviter de surcharger
        urls_to_process = urls_to_process[:5]

        for url in urls_to_process:
            img = self.download_image(url)
            if img:
                images.append(img)
        
        prompt_text = f"""
        {self.prompt_instruction}
        
        Détails de l'annonce :
        Titre: {listing_data['title']}
        Prix: {listing_data['price']} $
        Description: {listing_data['description']}

        Règles strictes pour le verdict :
        - "GOOD_DEAL" : Le prix demandé est INFERIEUR à la valeur estimée.
        - "FAIR" : Le prix demandé est PROCHE de la valeur estimée (à +/- 10%).
        - "BAD_DEAL" : Le prix demandé est SUPERIEUR à la valeur estimée.

        Réponds en JSON uniquement avec cette structure :
        {{
          "verdict": "GOOD_DEAL" | "FAIR" | "BAD_DEAL",
          "estimated_value": number,
          "reasoning": "explication détaillée et complète justifiant le verdict par rapport au prix et à la valeur",
          "confidence": number (0-100)
        }}
        """

        try:
            # Construction du contenu multimodal
            content = [prompt_text]
            content.extend(images)
            
            if images:
                print(f"   📸 {len(images)} images incluses dans l'analyse.")
            else:
                print("   ⚠️ Analyse texte uniquement (pas d'image valide).")

            response = model.generate_content(content)
            clean_text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_text)
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
                "verdict": "FAIR",
                "estimated_value": listing_data['price'],
                "reasoning": "Erreur d'analyse IA (Voir logs console)",
                "confidence": 0
            }

    def save_to_firestore(self, listing_data, analysis, doc_id=None):
        """Sauvegarde les données au chemin exact écouté par React."""
        if offline_mode:
            print(f"🚫 [OFFLINE] Données non sauvegardées : {listing_data['title']}")
            return

        try:
            # Si pas d'ID fourni, on génère un ID de secours (ne devrait pas arriver avec FB)
            if not doc_id:
                doc_id = f"{listing_data['title'][:15]}_{listing_data['price']}".replace(" ", "_").lower()
                doc_id = "".join(c for c in doc_id if c.isalnum() or c in ('_', '-'))

            data = {
                **listing_data,
                "aiAnalysis": analysis,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "status": "analyzed"
            }

            self.collection_ref.document(doc_id).set(data)
            print(f"💾 Envoyé à l'App: {listing_data['title']} (ID: {doc_id})")
        except Exception as e:
            print(f"❌ Erreur Firestore: {e}")

    def scan_facebook_marketplace(self, search_query="electric guitar", location="montreal", distance=60, min_price=0, max_price=10000, max_ads=5):
        """Scrape réellement Facebook Marketplace avec Playwright."""
        print(f"\n🌍 Lancement du scan Facebook pour '{search_query}' à {location} (Max: {max_ads}, Prix: {min_price}-{max_price}$)...")
        
        with sync_playwright() as p:

            # --- MODIFICATION : Démarrage minimisé ---
            # args=["--start-minimized"] demande à Chrome de démarrer réduit dans la barre des tâches
            browser = p.chromium.launch(
                headless=False,
                args=["--start-minimized"] 
            )
            
            # Configuration du contexte
            # viewport=None est CRUCIAL pour que --start-minimized fonctionne (sinon Playwright redimensionne la fenêtre)
            context = browser.new_context(
                viewport=None,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()

            # URL de recherche Marketplace
            # Note: L'URL peut varier selon la région. 
            url = f"https://www.facebook.com/marketplace/{location}/search?query={search_query}&minPrice={min_price}&maxPrice={max_price}"
            
            try:
                print(f"   ➡️ Navigation vers : {url}")
                page.goto(url, timeout=60000)
                
                # Gestion des popups cookies (Europe/Canada)
                try:
                    # Sélecteurs génériques pour les boutons de cookies
                    page.get_by_role("button", name="Allow all cookies").click(timeout=3000)
                    print("   🍪 Cookies acceptés.")
                except:
                    pass
                
                try:
                    page.get_by_role("button", name="Decline optional cookies").click(timeout=3000)
                    print("   🍪 Cookies optionnels refusés.")
                except:
                    pass

                # Attente du chargement de la grille de résultats
                # On attend un élément qui ressemble à une annonce ou le conteneur principal
                try:
                    page.wait_for_selector("div[role='main']", timeout=15000)
                except:
                    print("⚠️ Timeout en attendant le contenu principal. La page a peut-être changé.")

                # Scroll progressif pour charger plus d'annonces (lazy loading)
                print("   📜 Défilement pour charger les annonces...")
                for _ in range(3):
                    page.mouse.wheel(0, 1000)
                    time.sleep(2)

                # Extraction des liens d'annonces
                # Les annonces Marketplace ont généralement des liens contenant '/marketplace/item/'
                print("   🔍 Recherche des éléments d'annonce...")
                listings_locators = page.locator("a[href*='/marketplace/item/']").all()
                
                print(f"   👀 {len(listings_locators)} éléments trouvés (certains peuvent être des doublons).")
                
                processed_count = 0
                seen_urls = set()

                for link_loc in listings_locators:
                    if processed_count >= max_ads: 
                        print(f"   🛑 Limite de {max_ads} annonces atteinte.")
                        break
                        
                    href = link_loc.get_attribute("href")
                    if not href:
                        continue
                        
                    # Nettoyage de l'URL (parfois relative)
                    if href.startswith("/"):
                        full_link = f"https://www.facebook.com{href}"
                    else:
                        full_link = href
                        
                    # On retire les paramètres de tracking FB pour l'unicité
                    clean_link = full_link.split('?')[0]
                    
                    if clean_link in seen_urls:
                        continue
                    seen_urls.add(clean_link)

                    # --- Extraction de l'ID Facebook ---
                    fb_id = self.extract_facebook_id(clean_link)
                    if not fb_id:
                        continue

                    # --- Extraction des données brutes ---
                    text_content = link_loc.inner_text()
                    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                    
                    # Extraction de l'image (miniature)
                    img_loc = link_loc.locator("img").first
                    image_url = "https://via.placeholder.com/400?text=No+Image"
                    
                    # --- MODIFICATION : Extraction du titre via l'attribut ALT de l'image ---
                    # C'est beaucoup plus fiable que de deviner dans le texte
                    title = ""
                    if img_loc.count() > 0:
                        src = img_loc.get_attribute("src")
                        if src:
                            image_url = src
                        
                        # Le titre complet est souvent dans le alt de l'image
                        alt_text = img_loc.get_attribute("alt")
                        if alt_text and len(alt_text) > 3:
                            title = alt_text

                    # Fallback si pas de alt text (rare)
                    if not title:
                        # On essaie de trouver une ligne qui n'est PAS un prix
                        for line in lines:
                            if not any(c in line for c in ['$', '€', '£', 'Free', 'Gratuit']) and len(line) > 3:
                                title = line
                                break
                        if not title:
                            title = "Titre Inconnu"

                    # Extraction du prix
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

                    # On ignore les annonces sans prix détecté
                    if (price > 0 or "Gratuit" in text_content or "Free" in text_content):
                        print(f"   ✨ Annonce trouvée : {title} ({price} $)")
                        
                        # --- VERIFICATION INTELLIGENTE (ID + PRIX) ---
                        if not offline_mode:
                            try:
                                doc_ref = self.collection_ref.document(fb_id)
                                doc_snap = doc_ref.get()
                                
                                if doc_snap.exists:
                                    existing_data = doc_snap.to_dict()
                                    old_price = existing_data.get('price')
                                    
                                    if old_price == price:
                                        print(f"   ⏭️ Annonce existante et prix inchangé ({price} $). On passe.")
                                        continue
                                    else:
                                        print(f"   🔄 Le prix a changé ! (Ancien: {old_price} $ -> Nouveau: {price} $). Mise à jour...")
                            except Exception as e:
                                print(f"   ⚠️ Erreur vérification doublon (Firestore): {e}")
                        
                        # --- Scraping détaillé de la page ---
                        description = f"Annonce Marketplace. {title}. Localisation: {location}"
                        image_urls = [image_url] 
                        
                        try:
                            print(f"   ➡️  Ouverture de l'annonce pour détails : {clean_link}")
                            detail_page = context.new_page()
                            detail_page.goto(clean_link, timeout=45000)
                            
                            time.sleep(2) 
                            
                            potential_images = detail_page.locator("img").all()
                            found_urls = []
                            for img in potential_images:
                                try:
                                    src = img.get_attribute("src")
                                    if src and src.startswith("http") and "scontent" in src:
                                        if src not in found_urls:
                                            found_urls.append(src)
                                except:
                                    pass
                            
                            if found_urls:
                                image_urls = list(dict.fromkeys(found_urls)) # Dedup
                                print(f"   📸 {len(image_urls)} images trouvées sur la page.")

                            try:
                                detail_page.get_by_role("button", name="Plus").click(timeout=1000)
                            except:
                                try:
                                    detail_page.get_by_role("button", name="See more").click(timeout=1000)
                                except:
                                    pass
                                
                            full_text = detail_page.locator("body").inner_text()
                            description = full_text[:3000]

                            detail_page.close()
                        except Exception as e:
                            print(f"   ⚠️ Impossible de récupérer les détails (fallback) : {e}")
                            if 'detail_page' in locals():
                                try: detail_page.close()
                                except: pass

                        listing_data = {
                            "title": title,
                            "price": price,
                            "description": description,
                            "imageUrl": image_urls[0] if image_urls else image_url,
                            "imageUrls": image_urls,
                            "link": clean_link,
                            "location": location,
                            "searchDistance": distance
                        }
                        
                        # Analyse IA
                        analysis = self.analyze_deal_with_gemini(listing_data)
                        
                        # Sauvegarde avec l'ID Facebook
                        self.save_to_firestore(listing_data, analysis, doc_id=fb_id)
                        
                        processed_count += 1
                        
            except Exception as e:
                print(f"❌ Erreur durant le scraping : {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()
                print("🏁 Session de scraping terminée.")

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


if __name__ == "__main__":
    # Demande du prompt personnalisé au démarrage
    print(f"Prompt par défaut: {PROMPT_INSTRUCTION}")
    
    bot = GuitarHunterBot()
    
    print("\n--- MODE AUTOMATIQUE ---")
    print("Le bot va surveiller la configuration et scanner périodiquement.")
    print("Appuyez sur Ctrl+C pour arrêter.")
    
    last_scan_time = 0
    
    try:
        while True:
            # 1. Synchronisation de la config et vérification du refresh manuel
            should_refresh = bot.sync_configuration()
            
            # 2. Vérification du temps écoulé
            current_time = time.time()
            frequency_seconds = bot.scan_config['frequency'] * 60
            
            # Si refresh demandé OU temps écoulé
            if should_refresh or (current_time - last_scan_time > frequency_seconds):
                if should_refresh:
                    print("⚡ Lancement du scan (Manuel)...")
                else:
                    print(f"⏰ Lancement du scan (Auto - {bot.scan_config['frequency']} min)...")
                
                # Lancement du scan
                bot.scan_facebook_marketplace(
                    search_query="electric guitar", 
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