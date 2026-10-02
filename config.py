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

# --- REDONDANCE SERVEUR (chantier Dell, préparation — voir backend/ha/) ---
# Identifiant de CETTE machine ("serveur"/"dell") pour le bail de leadership Firestore et le
# marquage des annonces scrapées (`scraped_by_node`, voir deal_mapping.py). Vide par défaut :
# aucun comportement HA n'est activé tant que ce n'est pas explicitement configuré — le
# déploiement actuel (nœud unique) n'est pas affecté.
HA_NODE_ID = os.getenv("HA_NODE_ID", "")
# Le reste des réglages HA (résolution de `HaConfig`, voir backend/ha/watchdog.py) n'est lu que
# par backend/scripts/run_ha_watchdog.py, jamais importé par le bot/l'API — ne peut donc jamais
# affecter le déploiement nœud unique actuel même si mal configuré.
HA_PEER_HOST = os.getenv("HA_PEER_HOST", "")
HA_PEER_SSH_USER = os.getenv("HA_PEER_SSH_USER", "")
HA_PEER_SSH_KEY_PATH = os.getenv("HA_PEER_SSH_KEY_PATH", "")
HA_PEER_HEALTH_URL = os.getenv("HA_PEER_HEALTH_URL", "")
HA_LOCAL_SERVICE_NAME = os.getenv("HA_LOCAL_SERVICE_NAME", "")
HA_PEER_SERVICE_NAME = os.getenv("HA_PEER_SERVICE_NAME", "")
HA_LOCAL_PG_DSN = os.getenv("HA_LOCAL_PG_DSN", "")


def _safe_int_env(name: str, default: int) -> int:
    """Comme int(os.getenv(...)), mais ne casse jamais l'import de config.py (importé par le
    bot/l'API/tous les scripts) sur une valeur mal formée — retombe sur le défaut avec un
    avertissement plutôt qu'une ValueError non gérée au chargement du module."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[WARN] {name}={raw!r} invalide (entier attendu) — repli sur la valeur par défaut {default}.")
        return default


HA_LEASE_TTL_SECONDS = _safe_int_env("HA_LEASE_TTL_SECONDS", 60)
HA_HEARTBEAT_INTERVAL_SECONDS = _safe_int_env("HA_HEARTBEAT_INTERVAL_SECONDS", 15)
HA_FAILOVER_CONFIRM_ROUNDS = _safe_int_env("HA_FAILOVER_CONFIRM_ROUNDS", 3)

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
# Liste des serveurs proxy à utiliser pour la rotation d'IP dans le scraper (backend/scraping/core.py,
# un choix aléatoire par session — voir FacebookScraper.start_session()).
# Format de chaque entrée : "http://user:password@host:port" ou "http://host:port".
# Lu depuis `.env` (variable PROXIES, entrées séparées par des virgules) — jamais codé en dur ici,
# contrairement à la liste d'exemples commentés d'avant le 2026-08-24 : une vraie URL de proxy
# embarque souvent des identifiants (user:password), qui n'ont pas leur place dans un fichier
# committé. Même mécanisme que tous les autres secrets du projet (GEMINI_API_KEY, FIREBASE_*, SMTP).
_proxies_raw = os.getenv("PROXIES", "")
PROXIES = [p.strip() for p in _proxies_raw.split(",") if p.strip()]

# --- KIJIJI ---
# ID de catégorie Kijiji, global et stable pour tout le site (voir backend/scraping/kijiji/).
# Pas de mapping au-delà de "Guitars" pour l'instant.
KIJIJI_GUITARS_CATEGORY_ID = 613

# --- CONFIGURATION DES MODÈLES GEMINI ---
# Note : gemini-3.1-pro-preview est un modèle Preview (préavis de dépréciation
# de 2 semaines par email Google, non interceptable par l'API - voir notify_model_error).
# Migration 2026-07-31 : gemini-2.5-* (flash-lite, pro) est retiré par Google en octobre 2026 —
# remplacés par gemini-3.5-flash-lite (Portier) et gemini-3.6-flash (Analyste, capacité égale à
# 3.5-flash mais moins cher/plus rapide — voir JOURNAL.md pour le détail des benchmarks).
# Migration 2026-09-06 : Analyste gemini-3.6-flash -> gemini-3.7-flash (Intelligence Index 56 vs
# 52, plus rapide, même tarif standard $1.50/$7.50 par 1M tokens). Bénéficie jusqu'au 31/12/2026
# d'un tarif de lancement à $0.75/$3.75 (moitié prix) — repasse au tarif standard le 01/01/2027,
# alerte email programmée pour reconsidérer le choix de modèle avant cette date.
GEMINI_MODELS = {
    "available": [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash",
        "gemini-3.1-pro-preview"
    ],
    "default_gatekeeper": "gemini-3.5-flash-lite",
    "default_analyst": "gemini-3.7-flash",
    "default_expert": "gemini-3.1-pro-preview"
}

# --- CHANTIER H : BASCULE DU PORTIER (TIER 1) VERS QWEN (2026-09-20) ---
# Porté depuis `dev` sur cette branche Postgres le 2026-09-22 (jamais inclus dans le rattrapage
# Chantier G du 2026-09-19 — exclusion délibérée à l'époque, "module d'observation séparé, jamais
# utilisé pour la décision réelle"). Historique : observation Qwen en parallèle depuis le
# 2026-09-13 (jamais décisionnelle), puis analyse complète le 2026-09-20 — comparaison directe sur
# 166 annonces réelles (`backend/scripts/compare_qwen_flashlite_agreement.py`) + lecture des
# verdicts T2/T3 déjà écrits en base pour les 21 désaccords "coûteux" : 10/21 jamais promues en
# Tier 2 (`NOT_PROMOTED`, hors recherche active — aucune perte possible), 3/21 confirmées
# `BAD_DEAL` par le Tier 2 lui-même (Qwen avait raison, pas Flash-Lite), 6/21 confirmées `FAIR`
# (marge insuffisante pour un flip), 1/21 `LUTHIER_PROJ` marginal. Un seul cas réel de perte
# confirmée sur 166 annonces. Décision utilisateur : bascule.
#
# `T1_GATEKEEPER_PROVIDER` : ne pilote plus la décision T1 réelle depuis le Chantier I (voir
# T1_PROVIDER_CHAIN ci-dessous) — rôle réduit au choix du fournisseur comparé en miroir par
# l'observation Chantier H ("qwen" -> miroir Gemini, "gemini" -> miroir Qwen), déjà désactivée
# par défaut (T1_OBSERVATION_ENABLED=false). Conservé pour ne pas casser ce mécanisme existant.
TOKENROUTER_API_KEY = os.getenv("TOKENROUTER_API_KEY")
TOKENROUTER_BASE_URL = "https://api.tokenrouter.com/v1"
T1_OBSERVATION_QWEN_MODEL = os.getenv("T1_OBSERVATION_QWEN_MODEL", "qwen/qwen3.8-flash")
T1_GATEKEEPER_PROVIDER = os.getenv("T1_GATEKEEPER_PROVIDER", "qwen").strip().lower()

# --- CHANTIER I (2026-09-29) : CHAÎNE DE FOURNISSEURS T1 (local Dell primaire, Qwen cloud secours) ---
# Historique complet (validation du local sur 665 annonces, découverte du vrai taux d'échec de
# Qwen cloud 13-25%, décision "local permanent, cloud en secours" actée avec Opus) : voir
# JOURNAL.md/TODO.md § Chantier I. `T1_PROVIDER_CHAIN` remplace `T1_GATEKEEPER_PROVIDER` comme
# source de vérité pour la décision RÉELLE (accept/reject) : liste ordonnée, essayée dans l'ordre
# par `analyzer.py::_run_analysis_cascade`, chaque fournisseur pouvant être mis en pause par le
# coupe-circuit (`backend/t1_circuit_breaker.py`) après des échecs répétés. Un seul mot suffit à
# revenir au comportement pré-Chantier I (ex: "qwen" seul), sans redéploiement de code.
_t1_chain_raw = os.getenv("T1_PROVIDER_CHAIN", "local,qwen")
T1_PROVIDER_CHAIN = [p.strip().lower() for p in _t1_chain_raw.split(",") if p.strip()]

# Portier local (Dell T5810, Ollama via Tailscale) — modèle `qwen3-vl:8b-instruct` validé (pas la
# variante Thinking `qwen3-vl:8b`, voir JOURNAL.md 2026-09-27) avec le prompt simplifié devenu
# l'instruction Portier de prod (décision utilisateur 2026-09-29, voir DEFAULT_GATEKEEPER_INSTRUCTION).
T1_LOCAL_BASE_URL = os.getenv("T1_LOCAL_BASE_URL", "http://100.94.33.54:11434/v1")
T1_LOCAL_MODEL = os.getenv("T1_LOCAL_MODEL", "qwen3-vl:8b-instruct")
# Ollama n'exige aucune authentification, mais le SDK OpenAI refuse une clé vide — valeur factice.
T1_LOCAL_API_KEY = os.getenv("T1_LOCAL_API_KEY", "ollama")
# Concurrence max des appels T1 vers le Dell, tous threads utilisateurs confondus. Diagnostic
# 2026-10-02 (llm_usage) : appel isolé P90 14 s, mais en rafale (ANALYSIS_WORKERS=5 requêtes
# simultanées sur un Ollama à 8 Go de VRAM) P50 23 s / P90 52 s — les requêtes font la queue côté
# Ollama. Le sémaphore fait attendre en amont de l'appel HTTP, donc l'attente ne compte pas dans
# le timeout. À remonter (env) seulement si OLLAMA_NUM_PARALLEL le permet réellement.
T1_LOCAL_MAX_CONCURRENCY = max(1, int(os.getenv("T1_LOCAL_MAX_CONCURRENCY", 1)))
# Timeout d'UN appel local (hors attente du sémaphore). Le SDK OpenAI refaisait 2 retries
# silencieux par défaut : 3 × 60 s = jusqu'à 180 s par appel (pic 181 s observé) — désormais 0
# retry, l'échec remonte au coupe-circuit/chaîne qui bascule sur Qwen cloud.
T1_LOCAL_TIMEOUT_SECONDS = int(os.getenv("T1_LOCAL_TIMEOUT_SECONDS", 60))

# Coupe-circuit T1 : nombre d'échecs CONSÉCUTIFS avant de mettre un fournisseur en pause, et durée
# de cette pause. Volontairement simple (pas de sondes dédiées) — voir t1_circuit_breaker.py.
T1_CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("T1_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 3))
T1_CIRCUIT_BREAKER_COOLDOWN_SECONDS = int(os.getenv("T1_CIRCUIT_BREAKER_COOLDOWN_SECONDS", 600))
# Coupe-circuit explicite : si l'observation miroir cause un problème en production (latence,
# erreurs TokenRouter, etc.), la désactiver ne nécessite qu'une variable d'env, pas un
# redéploiement de code.
# Défaut passé à "false" (2026-09-28, décision utilisateur) : la comparaison Qwen/Gemini qui a
# validé la bascule du 2026-09-20 est terminée (voir JOURNAL.md) — laisser tourner ce miroir
# n'accumulait plus qu'un coût caché (double appel IA sur chaque annonce) sans nouvelle décision
# à informer. Repasser à "true" (variable d'env, sans redéploiement) si une nouvelle comparaison
# Gemini est nécessaire un jour.
T1_OBSERVATION_ENABLED = os.getenv("T1_OBSERVATION_ENABLED", "false").lower() in ("1", "true", "yes")

# --- SEUILS DE DÉCLENCHEMENT EXPERT PRO (TIER 3) ---
DEFAULT_PRO_PRICE_THRESHOLD = 1000
DEFAULT_PRO_DEAL_SCORE_THRESHOLD = 8
DEFAULT_PRO_RESTO_SCORE_THRESHOLD = 7
DEFAULT_PRO_COMBINED_DEAL_SCORE = 6
DEFAULT_PRO_AUTH_SCORE_THRESHOLD = 7
DEFAULT_PRO_CONFIDENCE_THRESHOLD = 0.75

# --- VALIDATION AU DÉMARRAGE ---
if not APP_ID_TARGET:
    print("ERREUR: APP_ID_TARGET doit etre defini dans le fichier .env")
    sys.exit(1)

if not USER_IDS_TARGET:
    print("[WARN] USER_IDS_TARGET est vide. Le bot attendra la découverte dynamique d'utilisateurs.")
else:
    print(f"[OK] Multi-utilisateurs (Seed) : {len(USER_IDS_TARGET)} utilisateur(s) configure(s) : {USER_IDS_TARGET}")


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
DEFAULT_SOLD_BACKFILL_INSTRUCTION = prompts_data.get('sold_backfill_instruction', "")
DEFAULT_TAXONOMY = prompts_data.get('taxonomy_master', {})
DEFAULT_FEW_SHOT_EXAMPLES = prompts_data.get('few_shot_examples', [])
DEFAULT_REJECTION_VERDICTS = prompts_data.get('rejection_verdicts', ["BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE", "INCOMPLETE_DATA"])

# --- MOTS-CLÉS D'EXCLUSION ---
DEFAULT_EXCLUSION_KEYWORDS = [
    "First Act", "Esteban", "Rogue", "Silvertone", "Spectrum", 
    "Denver", "Groove", "Stagg", "Maestro by Gibson", "Beaver Creek", "kmise"
]

