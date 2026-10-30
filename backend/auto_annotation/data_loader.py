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


def get_deal_images(limit: int = None):
    """
    Générateur itératif des URLs d'images (`guitar_deals.storage_image_urls`) depuis Postgres.
    Curseur côté serveur (nommé) : les lignes sont lues par paquets, jamais chargées toutes en RAM.
    `DATABASE_URL` : même variable que le reste du projet (voir CLAUDE.md : les scripts ne lisent pas `.env`).
    """
    import os
    import psycopg

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL absent : `export DATABASE_URL=postgresql://...` avant de lancer.")

    yielded_count = 0
    with psycopg.connect(dsn) as conn, conn.cursor(name="auto_annotation_deal_images") as cur:
        cur.itersize = 200
        cur.execute(
            "SELECT id, storage_image_urls FROM guitar_deals "
            "WHERE jsonb_typeof(storage_image_urls) = 'array' ORDER BY id"
        )
        for deal_id, urls in cur:
            for idx, url in enumerate(urls or []):
                if limit and yielded_count >= limit:
                    return
                yield f"{deal_id}_{idx}", url
                yielded_count += 1
