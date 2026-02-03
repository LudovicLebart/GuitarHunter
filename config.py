import os
import sys
import json
import warnings
from dotenv import load_dotenv

# --- CONFIGURATION GLOBALE ---

# Ignorer les avertissements de dépréciation (ils sont gérés par le bon import)
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# --- CLÉS API ET IDENTIFIANTS ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
APP_ID_TARGET = os.getenv("APP_ID_TARGET")
USER_ID_TARGET = os.getenv("USER_ID_TARGET")

# Chemin vers la clé de service Firebase
FIREBASE_KEY_PATH = "serviceAccountKey.json"

# --- VALIDATION AU DÉMARRAGE ---
if not APP_ID_TARGET or not USER_ID_TARGET:
    print("❌ ERREUR: APP_ID_TARGET et USER_ID_TARGET doivent être définis dans le fichier .env")
    sys.exit(1)

# --- CHARGEMENT DES PROMPTS ---
try:
    with open('prompts.json', 'r', encoding='utf-8') as f:
        prompts_data = json.load(f)
        
    def _join_if_list(value):
        """Helper pour joindre les listes de lignes en une seule chaîne."""
        return "\n".join(value) if isinstance(value, list) else value

    # Récupération et injection de la taxonomie
    taxonomy_data = prompts_data.get('taxonomy_guitares', {})
    taxonomy_str = json.dumps(taxonomy_data, indent=2, ensure_ascii=False)

    raw_system_prompt = _join_if_list(prompts_data.get('system_prompt', ""))
    SYSTEM_PROMPT = raw_system_prompt.replace("{taxonomy}", taxonomy_str)

    DEFAULT_VERDICT_RULES = _join_if_list(prompts_data.get('verdict_rules', ""))
    DEFAULT_REASONING_INSTRUCTION = _join_if_list(prompts_data.get('reasoning_instruction', ""))
    
    raw_user_prompt = _join_if_list(prompts_data.get('user_prompt', ""))
    DEFAULT_USER_PROMPT = raw_user_prompt.replace("{taxonomy}", taxonomy_str)
    
    print("✅ Prompts chargés avec succès depuis prompts.json.")

except Exception as e:
    print(f"⚠️ ERREUR: Impossible de charger prompts.json : {e}")
    print("👉 Utilisation de valeurs par défaut pour les prompts.")
    SYSTEM_PROMPT = "Tu es un expert en guitares."
    DEFAULT_VERDICT_RULES = ""
    DEFAULT_REASONING_INSTRUCTION = ""
    DEFAULT_USER_PROMPT = "Analyse cette guitare : {title}, {price}, {description}"

# --- CHARGEMENT DES DONNÉES GÉOGRAPHIQUES ---
try:
    with open('city_coordinates.json', 'r', encoding='utf-8') as f:
        CITY_COORDINATES = json.load(f)
    print(f"✅ {len(CITY_COORDINATES)} coordonnées de villes chargées.")
except Exception as e:
    print(f"⚠️ ERREUR: Impossible de charger city_coordinates.json : {e}")
    CITY_COORDINATES = {}

# --- INSTRUCTION PRINCIPALE (Legacy, à conserver pour l'instant) ---
PROMPT_INSTRUCTION = "Evalue cette guitare Au quebec (avec le prix)."
