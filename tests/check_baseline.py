import os
import sys
import json
from dotenv import load_dotenv

# --- Correction 1: Définir le répertoire racine du projet ---
# Cela rend le script indépendant du répertoire depuis lequel il est lancé.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

# --- Correction 2: Utiliser le bon module d'import pour le paquet google-genai ---
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai # Le nom du module reste le même

def run_checks():
    """Exécute une série de vérifications pour valider la configuration de base."""
    print("--- Lancement des tests de configuration de base (v3) ---")
    all_ok = True

    # --- 1. Chargement des variables d'environnement ---
    print("\n[1/4] Vérification des variables d'environnement (.env)...")
    try:
        # --- Utiliser un chemin absolu pour .env ---
        load_dotenv(dotenv_path=os.path.join(ROOT_DIR, '.env'))
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        APP_ID_TARGET = os.getenv("APP_ID_TARGET")
        USER_ID_TARGET = os.getenv("USER_ID_TARGET")

        if GEMINI_API_KEY and "..." not in GEMINI_API_KEY:
            print("  ✅ Clé API Gemini trouvée.")
        else:
            print("  ❌ ERREUR: GEMINI_API_KEY est manquante ou invalide dans .env")
            all_ok = False

        if APP_ID_TARGET and USER_ID_TARGET:
            print(f"  ✅ APP_ID_TARGET ({APP_ID_TARGET}) et USER_ID_TARGET ({USER_ID_TARGET}) trouvés.")
        else:
            print("  ❌ ERREUR: APP_ID_TARGET ou USER_ID_TARGET manquant dans .env")
            all_ok = False
    except Exception as e:
        print(f"  ❌ ERREUR critique lors du chargement de .env: {e}")
        all_ok = False
        return False

    # --- 2. Initialisation de Gemini ---
    print("\n[2/4] Vérification de l'initialisation de Gemini...")
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            # Note: Le modèle est juste pour tester l'init, pas pour générer du contenu ici.
            model = genai.GenerativeModel(model_name='gemini-1.5-flash')
            print("  ✅ Initialisation de Gemini réussie.")
        except Exception as e:
            print(f"  ❌ ERREUR: Impossible d'initialiser Gemini: {e}")
            all_ok = False
    else:
        print("  ⚠️ ATTENTION: Pas de clé API Gemini, test sauté.")
        all_ok = False

    # --- 3. Initialisation de Firebase ---
    print("\n[3/4] Vérification de l'initialisation de Firebase...")
    # --- Utiliser un chemin absolu pour la clé Firebase ---
    FIREBASE_KEY_PATH = os.path.join(ROOT_DIR, "serviceAccountKey.json")
    db = None
    if not firebase_admin._apps:
        try:
            if os.path.exists(FIREBASE_KEY_PATH):
                cred = credentials.Certificate(FIREBASE_KEY_PATH)
                firebase_admin.initialize_app(cred)
                db = firestore.client()
                print("  ✅ Initialisation de Firebase réussie.")
                
                try:
                    list(db.collections())
                    print("  ✅ Accès en lecture à la base de données confirmé.")
                except Exception as e:
                    print(f"  ❌ ERREUR PERMISSIONS: {e}")
                    all_ok = False
            else:
                print(f"  ❌ ERREUR: Fichier {FIREBASE_KEY_PATH} introuvable.")
                print("  👉 Assurez-vous que votre fichier de clé de service Firebase est à la racine du projet.")
                all_ok = False
        except Exception as e:
            print(f"  ❌ ERREUR critique Firebase: {e}")
            all_ok = False
    else:
        print("  ✅ Firebase déjà initialisé.")
        db = firestore.client()
        try:
            list(db.collections())
            print("  ✅ Accès en lecture à la base de données confirmé.")
        except Exception as e:
            print(f"  ❌ ERREUR PERMISSIONS: {e}")
            all_ok = False

    # --- 4. Chargement des fichiers de configuration locaux ---
    print("\n[4/4] Vérification des fichiers de configuration locaux...")
    try:
        # --- Utiliser un chemin absolu pour les JSON ---
        with open(os.path.join(ROOT_DIR, 'prompts.json'), 'r', encoding='utf-8') as f:
            prompts_data = json.load(f)
            if 'system_prompt' in prompts_data:
                print("  ✅ `prompts.json` chargé avec succès.")
            else:
                print("  ❌ ERREUR: `prompts.json` semble invalide (clé 'system_prompt' manquante).")
                all_ok = False
    except Exception as e:
        print(f"  ❌ ERREUR: Impossible de charger `prompts.json`: {e}")
        all_ok = False

    try:
        with open(os.path.join(ROOT_DIR, 'city_coordinates.json'), 'r', encoding='utf-8') as f:
            cities_data = json.load(f)
            if 'montreal' in cities_data:
                print("  ✅ `city_coordinates.json` chargé avec succès.")
            else:
                print("  ❌ ERREUR: `city_coordinates.json` semble invalide (clé 'montreal' manquante).")
                all_ok = False
    except Exception as e:
        print(f"  ❌ ERREUR: Impossible de charger `city_coordinates.json`: {e}")
        all_ok = False

    # --- Résultat final ---
    print("\n--- FIN DES TESTS ---")
    if all_ok:
        print("✅ Tous les tests de base ont réussi. L'environnement semble sain.")
    else:
        print("❌ Des erreurs ont été détectées. Veuillez corriger les problèmes ci-dessus avant de continuer.")
    
    return all_ok

if __name__ == "__main__":
    run_checks()
