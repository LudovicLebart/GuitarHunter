"""
Script de migration one-shot : rétro-remplit storageImageGsUris sur les annonces qui ont déjà
storageImageUrls (uploadées avant l'ajout du champ gs://, 2026-07-31 — voir chat Gemini,
docs/reference/ARCHITECTURE.md § Chat Gemini intégré).

Contrairement à migrate_images.py (pensé pour les URLs Facebook expirées, qui re-scrape et
re-uploade), ce script ne télécharge rien : les images sont déjà dans Firebase Storage, il suffit
de lister les blobs déjà présents sous deals/{deal_id}/ pour en déduire les URIs gs://.

Usage :
  python -m backend.scripts.backfill_gs_uris           # Mode réel
  python -m backend.scripts.backfill_gs_uris --dry-run  # Simulation
"""

import sys
import argparse
import logging

sys.path.insert(0, '.')

from config import FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET, APP_ID_TARGET, USER_ID_TARGET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("backfill_gs_uris")


def backfill(dry_run=False):
    logger.info("=== Démarrage du backfill storageImageGsUris ===")
    logger.info(f"Mode : {'DRY-RUN (simulation)' if dry_run else 'RÉEL'}")

    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if db_service.offline_mode:
        logger.error("❌ Impossible de se connecter à Firebase. Abandon.")
        sys.exit(1)

    repo = FirestoreRepository(db_service.db, APP_ID_TARGET, USER_ID_TARGET, bucket=db_service.bucket)

    try:
        all_docs = list(repo.collection_ref.stream())
    except Exception as e:
        logger.error(f"❌ Erreur lecture Firestore : {e}")
        sys.exit(1)

    total = len(all_docs)
    logger.info(f"📦 {total} annonces trouvées.")

    updated = skipped = no_blob = 0

    for i, doc in enumerate(all_docs, 1):
        data = doc.to_dict()
        deal_id = doc.id
        title = data.get('title', deal_id)[:50]

        if data.get('storageImageGsUris'):
            skipped += 1
            continue
        if not data.get('storageImageUrls'):
            # Jamais uploadée du tout — hors périmètre de ce script, voir migrate_images.py.
            skipped += 1
            continue

        gs_uris = repo.list_deal_image_gs_uris(deal_id)
        if not gs_uris:
            logger.warning(f"[{i}/{total}] {title} — storageImageUrls présent mais aucun blob trouvé sous deals/{deal_id}/. Skip.")
            no_blob += 1
            continue

        logger.info(f"[{i}/{total}] {title} — {len(gs_uris)} image(s).")
        if not dry_run:
            doc.reference.update({'storageImageGsUris': gs_uris})
        updated += 1

    logger.info("\n=== Backfill terminé ===")
    logger.info(f"  ✅ Mises à jour : {updated}{' (dry-run, rien écrit)' if dry_run else ''}")
    logger.info(f"  ⏭️  Ignorées     : {skipped} (déjà à jour ou jamais uploadées)")
    logger.info(f"  ⚠️  Sans blob    : {no_blob}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rétro-remplit storageImageGsUris depuis les blobs Storage déjà uploadés.")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans écriture.")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
