"""
Script de maintenance : nettoie et re-télécharge les images pour toutes les
annonces actives.

Flux pour chaque annonce active (non 'rejected', non 'sold'):
  1. Supprime les images existantes dans Firebase Storage.
  2. Efface le champ 'storageImageUrls' dans Firestore.
  3. Re-scrape la page de l'annonce pour obtenir les URLs d'images fraîches.
  4. Télécharge et uploade les nouvelles images dans Firebase Storage.
  5. Met à jour le document Firestore avec les nouvelles 'storageImageUrls'.

Usage :
  python -m backend.scripts.refresh_images           # Mode réel
  python -m backend.scripts.refresh_images --dry-run  # Simulation
"""

import sys
import time
import argparse
import logging
import random
from datetime import datetime, timezone

# Chemin vers la racine du projet
sys.path.insert(0, '.')

from config import FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET, APP_ID_TARGET, USER_ID_TARGET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository
from backend.scraping import FacebookScraper

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("refresh_images")

def rescrape_listing_data(scraper, listing_url):
    """
    Re-scrape la page Facebook pour extraire les données complètes.
    Retourne le dictionnaire de données de l'annonce ou None.
    """
    if not listing_url:
        return None
    
    captured = []
    
    def capture_listing(data):
        captured.append(data)
    
    try:
        time.sleep(random.uniform(2.0, 5.0))
        logger.info(f"   🔄 Re-scraping de la page FB : {listing_url[:60]}...")
        scraper.scan_specific_url(listing_url, capture_listing)
        if captured:
            return captured[0]
    except Exception as e:
        logger.warning(f"   ⚠️ Re-scraping échoué : {e}")
    return None


def refresh(dry_run=False, since_date_str=None):
    logger.info("=== Démarrage du rafraîchissement des images ===")
    logger.info(f"Mode : {'DRY-RUN (simulation)' if dry_run else 'RÉEL'}")

    since_date = None
    if since_date_str:
        since_date = datetime.strptime(since_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        logger.info(f"Filtre activé : Traitement des annonces depuis le {since_date_str}")

    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if db_service.offline_mode:
        logger.error("❌ Impossible de se connecter à Firebase. Abandon.")
        sys.exit(1)

    repo = FirestoreRepository(db_service.db, APP_ID_TARGET, USER_ID_TARGET, bucket=db_service.bucket)
    
    try:
        active_docs = list(repo.get_active_listings())
    except Exception as e:
        logger.error(f"❌ Erreur lecture Firestore : {e}")
        sys.exit(1)

    if since_date:
        original_count = len(active_docs)
        docs_to_process = [
            doc for doc in active_docs 
            if (ts := doc.to_dict().get('timestamp')) and ts.replace(tzinfo=timezone.utc) > since_date
        ]
        logger.info(f"Filtrage par date : {len(docs_to_process)} annonces sur {original_count} seront traitées.")
    else:
        docs_to_process = active_docs

    total = len(docs_to_process)
    logger.info(f"📦 {total} annonces à traiter.")

    refreshed_count = failed_count = 0

    # --- NOUVEAU : Une seule instance de scraper pour toute la session ---
    scraper = FacebookScraper({}, {})

    try:
        for i, doc in enumerate(docs_to_process, 1):
            data = doc.to_dict()
            deal_id = doc.id
            title = data.get('title', deal_id)[:50]
            listing_url = data.get('link')

            logger.info(f"\n[{i}/{total}] Traitement de : {title}")
            if not listing_url:
                logger.warning("   ⚠️ Pas de lien pour cette annonce. Skip.")
                failed_count += 1
                continue

            if dry_run:
                logger.info(f"   [DRY-RUN] Supprimerait les images pour {deal_id}, re-scraperait et uploaderait les nouvelles.")
                refreshed_count += 1
                continue

            repo.delete_deal_images(deal_id)
            fresh_data = rescrape_listing_data(scraper, listing_url)
            
            if not fresh_data or not (image_urls := fresh_data.get('imageUrls') or ([fresh_data.get('imageUrl')] if fresh_data.get('imageUrl') else [])):
                logger.warning("   ❌ Re-scraping sans résultat ou sans images. L'annonce est peut-être vendue.")
                failed_count += 1
                continue
            
            stable_urls = repo.upload_images_to_storage(image_urls, deal_id)
            if stable_urls:
                doc.reference.update({'storageImageUrls': stable_urls})
                logger.info(f"   ✅ {len(stable_urls)} nouvelle(s) image(s) sauvegardée(s).")
                refreshed_count += 1
            else:
                logger.warning("   ⚠️ Upload échoué pour les nouvelles images.")
                failed_count += 1
            time.sleep(0.5)
    finally:
        try: scraper.close_session()
        except: pass

    logger.info("\n=== Rafraîchissement terminé ===")
    logger.info(f"  ✅ Rafraîchies : {refreshed_count}")
    logger.info(f"  ❌ Échouées   : {failed_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rafraîchissement des images des annonces actives.")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans écriture.")
    parser.add_argument("--since-date", type=str, help="Seulement rafraîchir les annonces créées après cette date (YYYY-MM-DD).")
    args = parser.parse_args()
    refresh(dry_run=args.dry_run, since_date_str=args.since_date)