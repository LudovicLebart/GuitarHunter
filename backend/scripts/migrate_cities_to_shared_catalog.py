"""
Script de migration one-shot : copie les villes de User 0 vers le catalogue partagé.

Ce script doit être exécuté une seule fois lors du passage à l'architecture
de villes partagées.

Flux :
  1. Lire toutes les villes de USER_ID_TARGET (User 0) depuis :
       artifacts/{APP_ID}/users/{USER_0}/cities/
  2. Pour chaque ville, écrire dans le catalogue partagé :
       artifacts/{APP_ID}/cities/{facebook_city_id}
     Le docId = data['id'] (Facebook city ID).
  3. Écrire la préférence isScannable de User 0 dans :
       artifacts/{APP_ID}/users/{USER_0}/cities/{facebook_city_id}
     (docId normalisé = facebook_city_id, isScannable préservé)
  4. Optionnel (--also-migrate-prefs) : créer les prefs pour tous les autres
     users de USER_IDS_TARGET avec isScannable=False par défaut.

Usage :
  python -m backend.scripts.migrate_cities_to_shared_catalog            # Mode réel
  python -m backend.scripts.migrate_cities_to_shared_catalog --dry-run  # Simulation
  python -m backend.scripts.migrate_cities_to_shared_catalog --also-migrate-prefs
"""

import sys
import argparse
import logging

sys.path.insert(0, '.')

from config import FIREBASE_KEY_PATH, APP_ID_TARGET, USER_ID_TARGET, USER_IDS_TARGET
from backend.database import DatabaseService

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("migrate_cities")


def migrate(dry_run: bool, also_migrate_prefs: bool):
    if not USER_ID_TARGET:
        logger.error("USER_ID_TARGET manquant dans la configuration. Abandon.")
        sys.exit(1)

    logger.info(f"Initialisation Firebase (APP_ID={APP_ID_TARGET}, User 0={USER_ID_TARGET[:8]}...)")
    db_service = DatabaseService(FIREBASE_KEY_PATH)
    db = db_service.db

    # Références
    user0_cities_ref = (
        db.collection('artifacts').document(APP_ID_TARGET)
        .collection('users').document(USER_ID_TARGET)
        .collection('cities')
    )
    shared_cities_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('cities')

    # Lecture des villes de User 0
    user0_docs = list(user0_cities_ref.stream())
    logger.info(f"{len(user0_docs)} villes trouvées pour User 0.")

    if not user0_docs:
        logger.warning("Aucune ville à migrer. Abandon.")
        return

    migrated = 0
    skipped = 0

    for old_doc in user0_docs:
        data = old_doc.to_dict()
        facebook_city_id = str(data.get('id', ''))

        if not facebook_city_id:
            logger.warning(f"Document {old_doc.id} sans champ 'id'. Ignoré.")
            skipped += 1
            continue

        city_name = data.get('name', 'Inconnue')
        is_scannable = data.get('isScannable', False)

        # Données du catalogue (sans isScannable)
        catalog_data = {
            k: v for k, v in data.items()
            if k != 'isScannable'
        }

        logger.info(
            f"  {'[DRY-RUN] ' if dry_run else ''}Ville: {city_name} "
            f"(id={facebook_city_id}, isScannable={is_scannable})"
        )

        if not dry_run:
            # 1. Écriture dans le catalogue partagé
            shared_cities_ref.document(facebook_city_id).set(catalog_data, merge=True)

            # 2. Écriture de la pref User 0 (docId normalisé = facebook_city_id)
            user0_cities_ref.document(facebook_city_id).set(
                {'isScannable': is_scannable}, merge=True
            )

            # 3. Suppression de l'ancien document si le docId était auto-généré
            if old_doc.id != facebook_city_id:
                logger.info(
                    f"    Suppression de l'ancien document auto-généré: {old_doc.id}"
                )
                user0_cities_ref.document(old_doc.id).delete()

        migrated += 1

    logger.info(f"\n{'[DRY-RUN] ' if dry_run else ''}✅ {migrated} villes migrées, {skipped} ignorées.")

    # Optionnel : créer les prefs vides pour les autres users
    if also_migrate_prefs and not dry_run:
        other_users = [uid for uid in USER_IDS_TARGET if uid != USER_ID_TARGET]
        if other_users:
            logger.info(f"\nCréation des prefs (isScannable=False) pour {len(other_users)} autre(s) user(s)...")
            catalog_snapshot = {doc.id for doc in shared_cities_ref.stream()}
            for uid in other_users:
                user_prefs_ref = (
                    db.collection('artifacts').document(APP_ID_TARGET)
                    .collection('users').document(uid)
                    .collection('cities')
                )
                existing_prefs = {doc.id for doc in user_prefs_ref.stream()}
                for city_id in catalog_snapshot:
                    if city_id not in existing_prefs:
                        user_prefs_ref.document(city_id).set({'isScannable': False}, merge=True)
                logger.info(f"  User {uid[:8]}... : prefs initialisées.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migre les villes vers le catalogue partagé.')
    parser.add_argument('--dry-run', action='store_true', help='Simulation sans écriture.')
    parser.add_argument('--also-migrate-prefs', action='store_true',
                        help='Initialise les prefs isScannable=False pour tous les autres users.')
    args = parser.parse_args()
    migrate(dry_run=args.dry_run, also_migrate_prefs=args.also_migrate_prefs)
