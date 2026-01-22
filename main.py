import os
import time
import json
import random
import requests
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

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
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
        # Utilisation de la base de données par défaut (plus de 'guitarhunterdb')
        db = firestore.client()
        print("✅ Firebase connecté avec succès (Database: Default).")
    except Exception as e:
        print(f"❌ Erreur critique Firebase: {e}")
        exit(1)


class GuitarHunterBot:
    def __init__(self):
        # Construction du chemin pour vérification
        self.collection_path = f"artifacts/{APP_ID_TARGET}/users/{USER_ID_TARGET}/guitar_deals"
        
        print(f"\n🔧 CONFIGURATION DU BOT :")
        print(f"   - APP ID  : {APP_ID_TARGET}")
        print(f"   - USER ID : {USER_ID_TARGET}")
        print(f"   - CHEMIN  : {self.collection_path}")
        print(f"👉 Assurez-vous que ce chemin est IDENTIQUE à celui affiché dans l'encadré jaune de l'application React.\n")

        # Référence à la collection spécifique suivie par l'App React
        self.collection_ref = db.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(USER_ID_TARGET) \
            .collection('guitar_deals')

        # --- CORRECTION : CRÉATION EXPLICITE DES PARENTS (Pour éviter l'italique/fantôme) ---
        try:
            # 1. Création du document App (artifacts/{APP_ID})
            app_ref = db.collection('artifacts').document(APP_ID_TARGET)
            if not app_ref.get().exists:
                app_ref.set({'created_at': firestore.SERVER_TIMESTAMP, 'type': 'app_root'})
                print(f"📁 Document parent créé : artifacts/{APP_ID_TARGET}")

            # 2. Création du document User (artifacts/{APP_ID}/users/{USER_ID})
            user_ref = app_ref.collection('users').document(USER_ID_TARGET)
            if not user_ref.get().exists:
                user_ref.set({'created_at': firestore.SERVER_TIMESTAMP, 'type': 'user_root'})
                print(f"👤 Document parent créé : users/{USER_ID_TARGET}")
                
        except Exception as e:
            print(f"⚠️ Impossible de créer les documents parents (non bloquant) : {e}")

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
        print(f"🤖 Analyse IA pour : {listing_data['title']}...")

        # Téléchargement de l'image pour l'analyse
        image = self.download_image(listing_data['imageUrl'])
        
        prompt_text = f"""
        Evalue cette guitare Au quebec (avec le prix).
        
        Détails de l'annonce :
        Titre: {listing_data['title']}
        Prix: {listing_data['price']} $
        Description: {listing_data['description']}

        Réponds en JSON uniquement avec cette structure :
        {{
          "verdict": "GOOD_DEAL" | "FAIR" | "BAD_DEAL",
          "estimated_value": number,
          "reasoning": "explication courte",
          "confidence": number (0-100)
        }}
        """

        try:
            # Construction du contenu multimodal
            content = [prompt_text]
            if image:
                content.append(image)
                print("   📸 Image incluse dans l'analyse.")
            else:
                print("   ⚠️ Analyse texte uniquement (pas d'image valide).")

            response = model.generate_content(content)
            clean_text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_text)
        except Exception as e:
            print(f"❌ Erreur Gemini: {e}")
            return {
                "verdict": "FAIR",
                "estimated_value": listing_data['price'],
                "reasoning": "Erreur d'analyse IA",
                "confidence": 0
            }

    def save_to_firestore(self, listing_data, analysis):
        """Sauvegarde les données au chemin exact écouté par React."""
        try:
            # ID unique basé sur le titre et le prix
            doc_id = f"{listing_data['title'][:15]}_{listing_data['price']}".replace(" ", "_").lower()
            # Nettoyage des caractères invalides pour un ID Firestore
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

    def scan_facebook_marketplace(self, search_query="electric guitar", location="montreal"):
        """Scrape réellement Facebook Marketplace avec Playwright."""
        print(f"\n🌍 Lancement du scan Facebook pour '{search_query}' à {location}...")
        
        with sync_playwright() as p:
            # Headless=False est souvent nécessaire pour FB pour éviter d'être bloqué immédiatement
            # et pour le débogage visuel.
            browser = p.chromium.launch(headless=False)
            
            # Configuration du contexte pour ressembler à un vrai utilisateur
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()

            # URL de recherche Marketplace
            # Note: L'URL peut varier selon la région. 
            url = f"https://www.facebook.com/marketplace/{location}/search?query={search_query}"
            
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
                    if processed_count >= 5: # Limite pour éviter de spammer l'API Gemini/Firestore pendant les tests
                        print("   🛑 Limite de 5 annonces atteinte pour ce test.")
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

                    # Extraction des données brutes (Titre, Prix, Image)
                    # On essaie de parser le texte contenu dans le lien (souvent structuré en lignes)
                    text_content = link_loc.inner_text()
                    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                    
                    # Heuristique simple pour identifier Prix et Titre
                    price = 0
                    title = ""
                    
                    # Souvent : Prix en premier ou deuxième, Titre ensuite
                    # Exemple: "150 $", "Guitare Fender", "Montréal, QC"
                    
                    found_price = False
                    for line in lines:
                        # Détection basique de prix
                        if not found_price and any(c in line for c in ['$', '€', '£', 'Free', 'Gratuit']):
                            # Nettoyage du prix
                            digits = ''.join(filter(str.isdigit, line))
                            if digits:
                                price = int(digits)
                                found_price = True
                            elif "Free" in line or "Gratuit" in line:
                                price = 0
                                found_price = True
                        elif not title and len(line) > 3:
                            # On suppose que la première ligne de texte substantielle qui n'est pas le prix est le titre
                            title = line

                    # Si on n'a pas trouvé de titre clair, on prend tout le texte
                    if not title:
                        title = " ".join(lines[:2]) if lines else "Titre Inconnu"

                    # Extraction de l'image
                    img_loc = link_loc.locator("img").first
                    image_url = "https://via.placeholder.com/400?text=No+Image"
                    if img_loc.count() > 0:
                        src = img_loc.get_attribute("src")
                        if src:
                            image_url = src

                    # On ignore les annonces sans prix détecté ou sans titre
                    if title and (price > 0 or "Gratuit" in text_content or "Free" in text_content):
                        print(f"   ✨ Annonce trouvée : {title} ({price} $)")
                        
                        listing_data = {
                            "title": title,
                            "price": price,
                            "description": f"Annonce Marketplace. {title}. Localisation: {location}", # Description placeholder car on ne clique pas sur l'annonce
                            "imageUrl": image_url,
                            "link": clean_link
                        }
                        
                        # Analyse IA
                        analysis = self.analyze_deal_with_gemini(listing_data)
                        
                        # Sauvegarde
                        self.save_to_firestore(listing_data, analysis)
                        
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
                "link": "https://facebook.com/marketplace/item/test1"
            },
            {
                "title": "Squier Strat Classic Vibe 60s",
                "price": 250,
                "description": "Excellent état, parfaite pour débuter ou upgrade.",
                "imageUrl": "https://images.unsplash.com/photo-1550291652-6ea9114a47b1?q=80&w=400",
                "link": "https://facebook.com/marketplace/item/test2"
            }
        ]

        for listing in mock_listings:
            analysis = self.analyze_deal_with_gemini(listing)
            self.save_to_firestore(listing, analysis)
            time.sleep(1)


if __name__ == "__main__":
    bot = GuitarHunterBot()
    
    # Choix du mode
    print("1. Lancer le scan réel (Facebook Marketplace)")
    print("2. Lancer le test (Données fictives)")
    choice = input("Votre choix (1/2) [défaut: 1]: ").strip()
    
    if choice == "2":
        bot.run_test_scan()
    else:
        # Vous pouvez changer la requête et la localisation ici
        bot.scan_facebook_marketplace(search_query="electric guitar", location="montreal")