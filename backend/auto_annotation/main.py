import os
import sys
import logging
import asyncio
from pathlib import Path
from ultralytics import YOLO

# Ajouter la racine du projet pour importer les modules partagés
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService

# Importation des modules spécifiques à l'auto-annotation
from .config import setup_directories, YOLO_V1_OBB_WEIGHTS
from .data_loader import get_deal_images, fetch_image
from .geometry import parse_obb
from .heuristics import apply_heuristics
from .vlm_client import validate_with_vlm
from .exporter import save_yolo_obb_format
from . import geometry

logger = logging.getLogger(__name__)

async def process_image_pipeline(image_id, image_url, model):
    """Orchestre le pipeline complet pour une image individuelle."""
    image = fetch_image(image_url)
    if image is None: return

    # 1. Inférence YOLO OBB (stream=True évite de charger tous les résultats en RAM)
    results = model.predict(source=image, stream=True, verbose=False)
    results = list(results)  # Matérialiser une seule image
    if not results or not hasattr(results[0], 'obb') or results[0].obb is None:
        return
        
    obb_boxes = results[0].obb
    if obb_boxes is None: return
    classes = obb_boxes.cls
    
    # Transformation des boîtes en RotatedRect OpenCV
    rects = [parse_obb(obb_boxes, i) for i in range(len(obb_boxes))]

    # 2. Filtre Heuristique OBB (Géométrique et déterministe)
    heuristic_valid = apply_heuristics(rects, classes)
    if not heuristic_valid: return
        
    # 3. Filtre VLM avec Redressement OpenCV (Asynchrone)
    final_valid = await validate_with_vlm(image, rects, classes, heuristic_valid, geometry)
    
    # 4. Export OBB
    save_yolo_obb_format(image_id, image, obb_boxes, classes, final_valid)

async def run_pipeline(limit=None):
    """Boucle principale du pipeline."""
    setup_directories()
    
    if not os.path.exists(YOLO_V1_OBB_WEIGHTS):
        logger.error(f"Modèle introuvable: {YOLO_V1_OBB_WEIGHTS}")
        return

    logger.info("Chargement du modèle YOLO OBB...")
    try:
        model = YOLO(YOLO_V1_OBB_WEIGHTS)
    except Exception as e:
        logger.error(f"Erreur au chargement du modèle: {e}")
        return
    
    logger.info("Connexion Firebase...")
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if not db_service.db:
        logger.error("Erreur de connexion Firestore.")
        return

    logger.info("Démarrage de l'inférence de masse...")
    image_count = 0
    
    for image_id, image_url in get_deal_images(db_service.db, APP_ID_TARGET, limit=limit):
        # Déduplication : sauter les images déjà traitées (résumabilité après crash)
        from .config import LABELS_DIR
        if (LABELS_DIR / f"{image_id}.txt").exists():
            logger.debug(f"Déjà traité, skip: {image_id}")
            continue
        logger.info(f"Traitement de {image_id}")
        await process_image_pipeline(image_id, image_url, model)
        image_count += 1
        
    logger.info(f"Pipeline terminé avec succès. {image_count} images traitées.")

if __name__ == '__main__':
    # Remplacer None par un entier (ex: limit=50) pour des tests restreints
    asyncio.run(run_pipeline(limit=None))
