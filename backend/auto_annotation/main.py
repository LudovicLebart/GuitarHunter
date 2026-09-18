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
from .config import (
    setup_directories, YOLO_V1_OBB_WEIGHTS,
    LABELS_DIR, CLASS_NAMES, PIPELINE_CONCURRENCY,
)
from .data_loader import get_deal_images, fetch_image
from .geometry import parse_obb
from .heuristics import apply_heuristics
from .vlm_client import validate_with_vlm
from .exporter import save_yolo_obb_format

logger = logging.getLogger(__name__)


async def process_image_pipeline(image_id: str, image_url: str, model, counters: dict):
    """
    Orchestre le pipeline complet pour une image individuelle.
    Met à jour `counters` à chaque étape pour le reporting final.

    fetch_image est appelé via asyncio.to_thread pour ne pas bloquer l'event loop
    pendant le téléchargement HTTP synchrone.
    """
    # Download en thread — requests.get est synchrone, ne doit pas bloquer l'event loop
    image = await asyncio.to_thread(fetch_image, image_url)
    if image is None:
        logger.debug(f"[{image_id}] skip: téléchargement échoué ou image trop petite")
        return

    # 1. Inférence YOLO OBB
    # Note: stream=True est utile pour des sources multiples (liste/dossier).
    # Pour une image numpy unique, on l'utilise pour homogénéité de l'API Ultralytics.
    try:
        results = list(model.predict(source=image, stream=True, verbose=False))
    except Exception as e:
        logger.error(f"[{image_id}] Erreur YOLO: {e}")
        return

    if not results or not hasattr(results[0], 'obb') or results[0].obb is None:
        logger.debug(f"[{image_id}] skip: YOLO — aucune boîte OBB détectée")
        return

    obb_boxes = results[0].obb
    if len(obb_boxes) == 0:
        logger.debug(f"[{image_id}] skip: YOLO — 0 boîtes")
        return

    counters['yolo_kept'] += 1
    classes = obb_boxes.cls

    # Transformation des boîtes en RotatedRect OpenCV
    rects = [parse_obb(obb_boxes, i) for i in range(len(obb_boxes))]

    # 2. Filtre Heuristique OBB (Géométrique et déterministe)
    heuristic_valid = apply_heuristics(rects, classes)
    if not heuristic_valid:
        logger.debug(f"[{image_id}] skip: heuristiques — 0 boîtes valides sur {len(obb_boxes)}")
        return

    counters['heuristic_kept'] += 1

    # 3. Filtre VLM avec Redressement OpenCV (Asynchrone)
    # geometry est importé directement dans vlm_client — plus de passage de module
    final_valid = await validate_with_vlm(image, rects, classes, heuristic_valid)

    if not final_valid:
        logger.debug(f"[{image_id}] skip: VLM — toutes boîtes rejetées")
        return

    counters['vlm_kept'] += 1

    # 4. Export OBB
    try:
        save_yolo_obb_format(image_id, image, obb_boxes, classes, final_valid)
        counters['exported'] += 1
        logger.debug(f"[{image_id}] exporté ({len(final_valid)} boîte(s))")
    except IOError as e:
        logger.error(f"[{image_id}] Erreur export: {e}")


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

    # Validation que les noms de classes du modèle correspondent à CLASS_NAMES
    # Un mismatch silencieux corromprait l'intégralité du dataset d'annotation.
    if hasattr(model, 'names') and model.names:
        model_class_list = [model.names[i] for i in sorted(model.names.keys())]
        if model_class_list != CLASS_NAMES:
            logger.warning(
                f"ATTENTION: model.names {model_class_list} ≠ CLASS_NAMES {CLASS_NAMES}. "
                "Les prédictions pourraient être mal étiquetées — vérifier data.yaml du fine-tuning."
            )

    logger.info("Connexion Firebase...")
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if not db_service.db:
        logger.error("Erreur de connexion Firestore.")
        return

    counters = {
        'attempted': 0, 'skipped': 0,
        'yolo_kept': 0, 'heuristic_kept': 0,
        'vlm_kept': 0, 'exported': 0,
    }

    # Semaphore : limite le nombre d'images traitées simultanément
    sem = asyncio.Semaphore(PIPELINE_CONCURRENCY)

    async def bounded_process(img_id, img_url):
        async with sem:
            await process_image_pipeline(img_id, img_url, model, counters)

    logger.info(f"Démarrage de l'inférence de masse (concurrence: {PIPELINE_CONCURRENCY})...")
    tasks = []

    for image_id, image_url in get_deal_images(db_service.db, APP_ID_TARGET, limit=limit):
        # Déduplication : sauter les images déjà traitées (résumabilité après crash)
        if (LABELS_DIR / f"{image_id}.txt").exists():
            logger.debug(f"[{image_id}] skip: déjà exporté")
            counters['skipped'] += 1
            continue
        counters['attempted'] += 1
        tasks.append(bounded_process(image_id, image_url))

    await asyncio.gather(*tasks)

    logger.info(
        "Pipeline terminé.\n"
        f"  Tentées          : {counters['attempted']}\n"
        f"  Skippées (déjà)  : {counters['skipped']}\n"
        f"  YOLO kept        : {counters['yolo_kept']} "
        f"({counters['yolo_kept']/max(counters['attempted'], 1)*100:.0f}%)\n"
        f"  Heuristiques kept: {counters['heuristic_kept']}\n"
        f"  VLM kept         : {counters['vlm_kept']}\n"
        f"  Exportées        : {counters['exported']}"
    )


if __name__ == '__main__':
    # Remplacer None par un entier (ex: limit=50) pour des tests restreints
    asyncio.run(run_pipeline(limit=None))

