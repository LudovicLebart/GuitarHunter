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

# Support multi-utilisateurs : liste d'UIDs séparés par des virgules
_user_ids_raw = os.getenv("USER_IDS_TARGET", os.getenv("USER_ID_TARGET", ""))
USER_IDS_TARGET = [uid.strip() for uid in _user_ids_raw.split(",") if uid.strip()]
# Rétro-compatibilité : USER_ID_TARGET pointe vers le premier UID de la liste
USER_ID_TARGET = USER_IDS_TARGET[0] if USER_IDS_TARGET else ""

NTFY_TOPIC = os.getenv("NTFY_TOPIC")

# --- CONFIGURATION SMTP (Notifications Email) ---
# Compatible Gmail (port 587 + STARTTLS) et tout autre SMTP.
# Si non configuré, les notifications email sont silencieusement désactivées.
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER", "")       # ex: monbot@gmail.com
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")   # Mot de passe d'application Gmail

# CORRECTION : Utilisation d'un chemin absolu pour la clé Firebase
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "backend", "config", "serviceAccountKey.json")
FIREBASE_STORAGE_BUCKET = os.getenv("VITE_FIREBASE_STORAGE_BUCKET", "guitarehunter-d6e35.firebasestorage.app")

# --- POLITIQUE DE CYCLE DE VIE DES IMAGES ---
# Nombre de jours après lequel les images des annonces rejetées sont purgées de Firebase Storage.
IMAGE_RETENTION_REJECTED_DAYS = int(os.getenv("IMAGE_RETENTION_REJECTED_DAYS", 30))

# --- PROXIES ---
# Liste des serveurs proxy à utiliser pour la rotation d'IP dans le scraper.
# Format : "http://user:password@host:port" ou "http://host:port"
PROXIES = [
    # "http://proxy1.com:8000",
    # "http://proxy2.com:8000",
]

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
if not APP_ID_TARGET or not USER_IDS_TARGET:
    print("ERREUR: APP_ID_TARGET et USER_IDS_TARGET (ou USER_ID_TARGET pour mono-user) doivent etre definis dans le fichier .env")
    sys.exit(1)

print(f"[OK] Multi-utilisateurs : {len(USER_IDS_TARGET)} utilisateur(s) configure(s) : {USER_IDS_TARGET}")

# --- CHARGEMENT DES PROMPTS PAR DÉFAUT ---
try:
    with open(os.path.join(BASE_DIR, 'prompts.json'), 'r', encoding='utf-8') as f:
        prompts_data = json.load(f)
    print("[OK] Prompts par defaut charges depuis prompts.json")
except Exception as e:
    print(f"[WARN] Impossible de charger prompts.json : {e}")
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

