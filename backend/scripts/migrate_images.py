"""
Script de migration one-shot : télécharge et stocke dans Firebase Storage
les images de toutes les annonces existantes dans Firestore.

Flux pour chaque annonce :
  1. Skip si storageImageUrls est déjà renseigné.
  2. Tester la validité de chaque URL (HTTP HEAD).
  3. Si valide → télécharger et uploader dans Firebase Storage.
  4. Si expirée → re-scraper la page Facebook pour récupérer de nouvelles URLs,
     puis uploader.
  5. Mettre à jour le document Firestore avec storageImageUrls.

Usage :
  python -m backend.scripts.migrate_images           # Mode réel
  python -m backend.scripts.migrate_images --dry-run  # Simulation
"""

import sys
import time
import argparse
import requests
import logging

# Chemin vers la racine du projet
sys.path.insert(0, '.')

from config import FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET, APP_ID_TARGET, USER_ID_TARGET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository
from backend.scraping import FacebookScraper

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("migrate_images")


def is_url_valid(url, timeout=8):
    """Teste si une URL est encore accessible (non expirée)."""
    if not url:
        return False
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


def rescrape_image_urls(scraper, listing_url):
    """
    Re-scrape la page Facebook pour extraire les nouvelles URLs d'images.
    Utilise scan_specific_url avec un callback qui capture les données.
    Retourne une liste d'URLs (peut être vide si la page est inaccessible).
    """
    if not listing_url:
        return []
    
    captured = []
    
    def capture_listing(data):
        captured.append(data)
    
    try:
        logger.info(f"   🔄 Re-scraping de la page FB : {listing_url[:60]}...")
        scraper.scan_specific_url(listing_url, capture_listing)
        if captured:
            data = captured[0]
            return data.get('imageUrls') or ([data.get('imageUrl')] if data.get('imageUrl') else [])
    except Exception as e:
        logger.warning(f"   ⚠️ Re-scraping échoué : {e}")
    return []


def migrate(dry_run=False):
    logger.info("=== Démarrage de la migration des images ===")
    logger.info(f"Mode : {'DRY-RUN (simulation)' if dry_run else 'RÉEL'}")

    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if db_service.offline_mode:
        logger.error("❌ Impossible de se connecter à Firebase. Abandon.")
        sys.exit(1)

    repo = FirestoreRepository(db_service.db, APP_ID_TARGET, USER_ID_TARGET, bucket=db_service.bucket)
    scraper = FacebookScraper({}, {})

    # Récupération de toutes les annonces (actives + rejetées + vendues)
    try:
        all_docs = list(repo.collection_ref.stream())
    except Exception as e:
        logger.error(f"❌ Erreur lecture Firestore : {e}")
        sys.exit(1)

    total = len(all_docs)
    logger.info(f"📦 {total} annonces trouvées.")

    skipped = uploaded = failed = rescraped = 0

    for i, doc in enumerate(all_docs, 1):
        data = doc.to_dict()
        deal_id = doc.id
        title = data.get('title', deal_id)[:50]

        logger.info(f"\n[{i}/{total}] {title}")

        # 1. Déjà migré ?
        if data.get('storageImageUrls'):
            logger.info("   ✅ Déjà migré. Skip.")
            skipped += 1
            continue

        # 2. Collect des URLs sources
        image_urls = data.get('imageUrls') or ([data.get('imageUrl')] if data.get('imageUrl') else [])
        if not image_urls:
            logger.info("   ⚠️ Aucune URL d'image dans ce document. Skip.")
            skipped += 1
            continue

        # 3. Test de validité du premier lien
        first_url = image_urls[0]
        if not is_url_valid(first_url):
            logger.info("   ❌ URL expirée. Tentative de re-scraping...")
            fresh_urls = rescrape_image_urls(scraper, data.get('link'))
            if fresh_urls:
                image_urls = fresh_urls
                rescraped += 1
            else:
                logger.warning("   ❌ Re-scraping sans résultat. Skip.")
                failed += 1
                continue

        # 4. Upload dans Firebase Storage
        if dry_run:
            logger.info(f"   [DRY-RUN] Uploaderait {len(image_urls)} image(s) pour {deal_id}.")
            uploaded += 1
        else:
            stable_urls = repo.upload_images_to_storage(image_urls, deal_id)
            if stable_urls:
                doc.reference.update({'storageImageUrls': stable_urls})
                logger.info(f"   ✅ {len(stable_urls)} image(s) uploadée(s) et sauvegardées.")
                uploaded += 1
            else:
                logger.warning("   ⚠️ Upload échoué pour toutes les images.")
                failed += 1

        time.sleep(0.3)  # Respect du rate limit Firebase Storage

    # Fermeture propre du scraper
    try:
        scraper.close_session()
    except Exception:
        pass

    logger.info("\n=== Migration terminée ===")
    logger.info(f"  ✅ Upladées  : {uploaded}")
    logger.info(f"  ⏭️  Ignorées  : {skipped}")
    logger.info(f"  🔄 Re-scrapées : {rescraped}")
    logger.info(f"  ❌ Échouées  : {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migration des images vers Firebase Storage.")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans écriture.")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
