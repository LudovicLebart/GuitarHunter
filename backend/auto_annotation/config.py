import logging
from pathlib import Path

# Poids du modèle d'amorçage
YOLO_V1_OBB_WEIGHTS = 'yolov8n-obb.pt'

# Configuration Oracle VLM Local
OLLAMA_API_URL = 'http://localhost:11434/api/generate'
# Moondream (2B) choisi sur LLaVA (7B+) : 3x plus rapide, suffisant pour TRUE/FALSE binaire
VLM_MODEL = 'moondream'

# Chemins d'exportation du dataset
OUTPUT_DIR = Path('dataset_v2')
IMAGES_DIR = OUTPUT_DIR / 'images'
LABELS_DIR = OUTPUT_DIR / 'labels'

# Liste des classes du modèle d'amorçage
CLASS_NAMES = ['headstock', 'neck', 'body', 'bridge', 'pickups', 'soundhole']

def setup_directories():
    """Crée les répertoires nécessaires pour l'export YOLO-OBB"""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
