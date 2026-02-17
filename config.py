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
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "serviceAccountKey.json")

# --- CONFIGURATION DES MODÈLES GEMINI ---
GEMINI_MODELS = {
    "available": [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ],
    "default_gatekeeper": "gemini-2.5-flash-lite",
    "default_expert": "gemini-2.5-flash"
}

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

# --- EXPORTATION DES DONNÉES BRUTES ---
# C'est ce dictionnaire qui sera utilisé par analyzer.py pour l'assemblage dynamique
DEFAULT_PROMPTS = prompts_data

# --- MOTS-CLÉS D'EXCLUSION ---
DEFAULT_EXCLUSION_KEYWORDS = [
    "First Act", "Esteban", "Rogue", "Silvertone", "Spectrum", 
    "Denver", "Groove", "Stagg", "Maestro by Gibson", "Beaver Creek", "kmise"
]

# --- CONSTANTES LEGACY (Restaurées pour compatibilité UI/Reset) ---
DEFAULT_MAIN_PROMPT = prompts_data.get('main_analysis_prompt', [])
DEFAULT_GATEKEEPER_INSTRUCTION = prompts_data.get('gatekeeper_verbosity_instruction', "")
DEFAULT_EXPERT_CONTEXT = prompts_data.get('expert_context_instruction', "")
DEFAULT_TAXONOMY = prompts_data.get('taxonomy_guitares', {})

# --- CONSTANTES MODULAIRES (Pour compatibilité si nécessaire) ---
PROMPT_INSTRUCTION = prompts_data.get('persona', [])
DEFAULT_VERDICT_RULES = prompts_data.get('verdict_rules', [])
DEFAULT_REASONING_INSTRUCTION = prompts_data.get('reasoning_instruction', [])
DEFAULT_USER_PROMPT = prompts_data.get('user_prompt', [])
