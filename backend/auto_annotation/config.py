import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(name)s | %(message)s')

# Poids du modèle d'amorçage
YOLO_V1_OBB_WEIGHTS = 'yolov8n-obb.pt'

# Configuration Oracle VLM Local
OLLAMA_API_URL = 'http://localhost:11434/api/generate'
VLM_MODEL = 'qwen2.5-vl'

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
