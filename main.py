import os
import time
import json
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


    def analyze_deal_with_gemini(self, listing_data):
        """Utilise Gemini pour évaluer si l'annonce est une bonne affaire."""
        print(f"🤖 Analyse IA pour : {listing_data['title']}...")

        prompt = f"""
        Expert en guitares, analyse cette annonce :
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
            response = model.generate_content(prompt)
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

    def run_test_scan(self):
        """Génère des données de test pour vérifier la synchronisation."""
        print(f"🔎 Démarrage du scan de test...")

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
    bot.run_test_scan()