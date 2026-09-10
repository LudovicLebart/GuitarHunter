import logging
from pathlib import Path

# Racines absolues — indépendant du répertoire de lancement
MODULE_ROOT = Path(__file__).parent          # backend/auto_annotation/
PROJECT_ROOT = MODULE_ROOT.parent.parent     # racine GuitarHunter/

# --- Modèle YOLO d'amorçage ---
# À remplacer par le checkpoint fine-tuné après Phase 0 (critère mAP50-OBB >= 0.50)
YOLO_V1_OBB_WEIGHTS = str(PROJECT_ROOT / 'yolov8n-obb.pt')

# --- Oracle VLM Local (Ollama) ---
OLLAMA_API_URL = 'http://localhost:11434/api/generate'
OLLAMA_TIMEOUT_S = 30  # Timeout total par requête Ollama (secondes)
# Moondream (2B) choisi sur LLaVA (7B+) : 3x plus rapide, suffisant pour TRUE/FALSE binaire
VLM_MODEL = 'moondream'
# Prompt de validation binaire — {class_name} est substitué dynamiquement
VLM_PROMPT = (
    "L'image montre-t-elle exclusivement un(e) {class_name} de guitare ? "
    "Réponds uniquement par TRUE ou FALSE."
)

# --- Chemins d'exportation (absolus, indépendants du CWD) ---
OUTPUT_DIR = PROJECT_ROOT / 'dataset_v2'
IMAGES_DIR = OUTPUT_DIR / 'images'
LABELS_DIR = OUTPUT_DIR / 'labels'

# --- Classes du modèle ---
# CRITIQUE : cet ordre doit correspondre EXACTEMENT à l'ordre du data.yaml utilisé
# pour le fine-tuning Phase 0. Validé au démarrage contre model.names (voir main.py).
CLASS_NAMES = ['headstock', 'neck', 'body', 'bridge', 'pickups', 'soundhole']

# --- Heuristiques spatiales (seuils configurables) ---
# Ratio min max(w/h, h/w) pour valider un manche (long et fin par nature)
NECK_RATIO_MIN = 2.0
# Part de surface d'un pickup/soundhole devant être incluse dans le body
INCLUSION_RATIO_MIN = 0.8

# --- Qualité des données ---
# Dimension minimale (px) d'un crop OBB pour être envoyé au VLM
MIN_CROP_DIM = 10
# Dimension minimale (px) du côté court d'une image pour être traitée
MIN_IMAGE_DIM = 300

# --- Concurrence du pipeline ---
# Nombre d'images traitées en parallèle (I/O réseau image + VLM simultanés)
PIPELINE_CONCURRENCY = 4


def setup_directories():
    """Crée les répertoires nécessaires pour l'export YOLO-OBB."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)

