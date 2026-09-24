import numpy as np
import cv2
import requests
import logging
from .config import MIN_IMAGE_DIM

logger = logging.getLogger(__name__)


def fetch_image(url: str):
    """
    Télécharge et décode une image depuis Firebase Storage.

    Filtre les images trop petites (vignettes, erreurs d'upload).
    Fonction SYNCHRONE — appeler via asyncio.to_thread() depuis un contexte async
    pour ne pas bloquer l'event loop.
    """
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"HTTP {resp.status_code} pour: {url}")
            return None

        nparr = np.frombuffer(resp.content, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            logger.warning(f"Impossible de décoder (contenu corrompu ?): {url}")
            return None

        # Filtrer les images trop petites : vignettes, erreurs d'upload Firebase
        h, w = image.shape[:2]
        if min(h, w) < MIN_IMAGE_DIM:
            logger.debug(f"Image ignorée (trop petite: {w}×{h} px): {url}")
            return None

        return image

    except Exception as e:
        logger.error(f"Erreur de téléchargement: {e}")
        return None


def get_deal_images(db_client, app_id: str, limit: int = None):
    """
    Générateur itératif des URLs d'images depuis Firestore.
    Itère directement sur les streams (sans list()) pour ne pas charger
    des milliers de documents en RAM simultanément.
    """
    users_ref = db_client.collection('artifacts').document(app_id).collection('users')

    yielded_count = 0

    # Itération directe — Firestore stream pagine internement
    for user_doc in users_ref.stream():
        deals_ref = user_doc.reference.collection('guitar_deals')

        for deal in deals_ref.stream():
            data = deal.to_dict()
            urls = data.get('storageImageUrls', [])

            for idx, url in enumerate(urls):
                if limit and yielded_count >= limit:
                    return

                yield f"{deal.id}_{idx}", url
                yielded_count += 1

