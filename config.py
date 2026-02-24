import os
import sys
import warnings
import json
from dotenv import load_dotenv

# --- CONFIGURATION GLOBALE ---
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
load_dotenv()

# --- CLÉS API ET IDENTIFIANTS ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
APP_ID_TARGET = os.getenv("APP_ID_TARGET")
USER_ID_TARGET = os.getenv("USER_ID_TARGET")
NTFY_TOPIC = os.getenv("NTFY_TOPIC")

# CORRECTION : Utilisation d'un chemin absolu pour la clé Firebase
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "backend", "config", "serviceAccountKey.json")

# --- CONFIGURATION DES MODÈLES GEMINI ---
GEMINI_MODELS = {
    "available": [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-pro"
    ],
    "default_gatekeeper": "gemini-2.5-flash-lite",
    "default_analyst": "gemini-2.5-flash",
    "default_expert": "gemini-2.5-pro"
}

# --- SEUILS DE DÉCLENCHEMENT EXPERT PRO (TIER 3) ---
DEFAULT_PRO_PRICE_THRESHOLD = 1000
DEFAULT_PRO_DEAL_SCORE_THRESHOLD = 8
DEFAULT_PRO_RESTO_SCORE_THRESHOLD = 7
DEFAULT_PRO_COMBINED_DEAL_SCORE = 6
DEFAULT_PRO_AUTH_SCORE_THRESHOLD = 7
DEFAULT_PRO_CONFIDENCE_THRESHOLD = 0.75

# --- VALIDATION AU DÉMARRAGE ---
if not APP_ID_TARGET or not USER_ID_TARGET:
    print("❌ ERREUR: APP_ID_TARGET et USER_ID_TARGET doivent être définis dans le fichier .env")
    sys.exit(1)

# --- CHARGEMENT DES PROMPTS PAR DÉFAUT ---
try:
    with open(os.path.join(BASE_DIR, 'prompts.json'), 'r', encoding='utf-8') as f:
        prompts_data = json.load(f)
    print("✅ Prompts par défaut chargés depuis prompts.json")
except Exception as e:
    print(f"⚠️ ERREUR: Impossible de charger prompts.json : {e}")
    prompts_data = {}

# --- NOUVELLES CONSTANTES POUR LA CASCADE ---
DEFAULT_MAIN_PROMPT = prompts_data.get('main_analysis_prompt', [])
DEFAULT_GATEKEEPER_INSTRUCTION = prompts_data.get('gatekeeper_verbosity_instruction', "")
DEFAULT_ANALYST_INSTRUCTION = prompts_data.get('analyst_verbosity_instruction', "")
DEFAULT_EXPERT_CONTEXT = prompts_data.get('expert_pro_context_instruction', "")
DEFAULT_TAXONOMY = prompts_data.get('taxonomy_master', {})
DEFAULT_FEW_SHOT_EXAMPLES = prompts_data.get('few_shot_examples', [])
DEFAULT_REJECTION_VERDICTS = prompts_data.get('rejection_verdicts', ["BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE", "INCOMPLETE_DATA"])

# --- MOTS-CLÉS D'EXCLUSION ---
DEFAULT_EXCLUSION_KEYWORDS = [
    "First Act", "Esteban", "Rogue", "Silvertone", "Spectrum", 
    "Denver", "Groove", "Stagg", "Maestro by Gibson", "Beaver Creek", "kmise"
]


