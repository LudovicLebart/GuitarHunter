import os
import sys
import warnings
import json
from dotenv import load_dotenv

# --- CONFIGURATION GLOBALE ---

# Ignorer les avertissements de dépréciation
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

# Charger les variables d'environnement
load_dotenv()

# --- CLÉS API ET IDENTIFIANTS ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
APP_ID_TARGET = os.getenv("APP_ID_TARGET")
USER_ID_TARGET = os.getenv("USER_ID_TARGET")
NTFY_TOPIC = os.getenv("NTFY_TOPIC") # Nouveau : Topic ntfy pour les notifications

# Chemin vers la clé de service Firebase
FIREBASE_KEY_PATH = "serviceAccountKey.json"

# --- VALIDATION AU DÉMARRAGE ---
if not APP_ID_TARGET or not USER_ID_TARGET:
    print("❌ ERREUR: APP_ID_TARGET et USER_ID_TARGET doivent être définis dans le fichier .env")
    sys.exit(1)

# --- CHARGEMENT DES DONNÉES GÉOGRAPHIQUES ---
try:
    with open('city_coordinates.json', 'r', encoding='utf-8') as f:
        CITY_COORDINATES = json.load(f)
    print(f"✅ {len(CITY_COORDINATES)} coordonnées de villes chargées.")
except Exception as e:
    print(f"⚠️ ERREUR: Impossible de charger city_coordinates.json : {e}")
    CITY_COORDINATES = {}

# --- CHARGEMENT DES PROMPTS PAR DÉFAUT ---
try:
    with open('prompts.json', 'r', encoding='utf-8') as f:
        prompts_data = json.load(f)
    print("✅ Prompts par défaut chargés depuis prompts.json")
except Exception as e:
    print(f"⚠️ ERREUR: Impossible de charger prompts.json : {e}")
    prompts_data = {}

# --- CONSTANTES LEGACY (Pour compatibilité temporaire) ---
# Ces valeurs sont chargées depuis prompts.json pour assurer la cohérence
PROMPT_INSTRUCTION = prompts_data.get('persona', ["Legacy Prompt Placeholder"])
DEFAULT_VERDICT_RULES = prompts_data.get('verdict_rules', [])
DEFAULT_REASONING_INSTRUCTION = prompts_data.get('reasoning_instruction', [])
DEFAULT_USER_PROMPT = prompts_data.get('user_prompt', [])
