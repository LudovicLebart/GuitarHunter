"""
Script de migration one-shot : copie les villes de User 0 vers le catalogue partagé.

Ce script doit être exécuté une seule fois lors du passage à l'architecture
de villes partagées.

Flux :
  1. Lire toutes les villes de SOURCE_USER_ID depuis :
       artifacts/{APP_ID}/users/{SOURCE_USER_ID}/cities/
  2. Pour chaque ville, écrire dans le catalogue partagé :
       artifacts/{APP_ID}/cities/{facebook_city_id}
     Le docId = data['id'] (Facebook city ID).
  3. Écrire la préférence isScannable de SOURCE_USER_ID dans :
       artifacts/{APP_ID}/users/{SOURCE_USER_ID}/cities/{facebook_city_id}
     (docId normalisé = facebook_city_id, isScannable préservé)
  4. Optionnel (--target-user-id) : copier les prefs isScannable vers un autre user.
  5. Optionnel (--also-migrate-prefs) : initialiser les prefs isScannable=False
     pour tous les autres users de USER_IDS_TARGET qui ne sont ni source ni target.

Usage :
  # Lecture depuis USER_ID_TARGET (.env), écriture catalogue partagé uniquement
  python -m backend.scripts.migrate_cities_to_shared_catalog

  # Simulation sans écriture
  python -m backend.scripts.migrate_cities_to_shared_catalog --dry-run

  # Migrer depuis un ancien UID vers le catalogue + copier prefs vers le nouvel UID
  python -m backend.scripts.migrate_cities_to_shared_catalog \\
      --source-user-id 00737242777130596039 \\
      --target-user-id wbPlgZgkW2VcAl0a2l44UMSDTaG2

  # Aussi initialiser les prefs pour tous les autres users
  python -m backend.scripts.migrate_cities_to_shared_catalog \\
      --source-user-id 00737242777130596039 \\
      --target-user-id wbPlgZgkW2VcAl0a2l44UMSDTaG2 \\
      --also-migrate-prefs
"""

import sys
import argparse
import logging

sys.path.insert(0, '.')

from config import FIREBASE_KEY_PATH, APP_ID_TARGET, USER_ID_TARGET, USER_IDS_TARGET
from backend.database import DatabaseService

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("migrate_cities")


def migrate(dry_run: bool, source_user_id: str, target_user_id: str | None, also_migrate_prefs: bool):
    if not source_user_id:
        logger.error("source_user_id manquant. Abandon.")
        sys.exit(1)

    logger.info(f"Initialisation Firebase (APP_ID={APP_ID_TARGET})")
    logger.info(f"Source: {source_user_id[:12]}...")
    if target_user_id:
        logger.info(f"Target: {target_user_id[:12]}...")

    db_service = DatabaseService(FIREBASE_KEY_PATH)
    db = db_service.db

    # Références
    source_cities_ref = (
        db.collection('artifacts').document(APP_ID_TARGET)
        .collection('users').document(source_user_id)
        .collection('cities')
    )
    shared_cities_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('cities')

    # Lecture des villes de la source
    source_docs = list(source_cities_ref.stream())
    logger.info(f"{len(source_docs)} villes trouvées pour la source.")

    if not source_docs:
        logger.warning("Aucune ville à migrer. Abandon.")
        return

    migrated = 0
    skipped = 0
    scannable_city_ids = []

    for old_doc in source_docs:
        data = old_doc.to_dict()
        # Priorité : champ 'id' dans les données, sinon le docId lui-même
        # (ancienne architecture : docId = Facebook city ID)
        facebook_city_id = str(data.get('id', '') or old_doc.id)

        if not facebook_city_id:
            logger.warning(f"Document {old_doc.id} sans facebook city ID. Ignore.")
            skipped += 1
            continue

        city_name = data.get('name', 'Inconnue')
        is_scannable = data.get('isScannable', False)

        # Données du catalogue (sans isScannable, avec id explicite)
        catalog_data = {
            k: v for k, v in data.items()
            if k != 'isScannable'
        }
        # Garantir que le champ 'id' est présent dans le catalogue
        if 'id' not in catalog_data:
            catalog_data['id'] = facebook_city_id

        logger.info(
            f"  {'[DRY-RUN] ' if dry_run else ''}Ville: {city_name} "
            f"(id={facebook_city_id}, isScannable={is_scannable})"
        )

        if not dry_run:
            # 1. Écriture dans le catalogue partagé
            shared_cities_ref.document(facebook_city_id).set(catalog_data, merge=True)

            # 2. Écriture de la pref source (docId normalisé = facebook_city_id)
            source_cities_ref.document(facebook_city_id).set(
                {'isScannable': is_scannable}, merge=True
            )

            # 3. Suppression de l'ancien document si le docId était auto-généré
            if old_doc.id != facebook_city_id:
                logger.info(
                    f"    Suppression de l'ancien document auto-généré: {old_doc.id}"
                )
                source_cities_ref.document(old_doc.id).delete()

        if is_scannable:
            scannable_city_ids.append(facebook_city_id)

        migrated += 1

    logger.info(f"\n{'[DRY-RUN] ' if dry_run else ''}✅ {migrated} villes migrées vers le catalogue, {skipped} ignorées.")
    logger.info(f"   Dont {len(scannable_city_ids)} ville(s) isScannable=True.")

    # Optionnel : copier les prefs isScannable vers le target user
    if target_user_id and not dry_run:
        logger.info(f"\nCopie des prefs isScannable vers le target user {target_user_id[:12]}...")
        target_prefs_ref = (
            db.collection('artifacts').document(APP_ID_TARGET)
            .collection('users').document(target_user_id)
            .collection('cities')
        )
        catalog_snapshot = list(shared_cities_ref.stream())
        for city_doc in catalog_snapshot:
            city_id = city_doc.id
            # Lire la pref source pour ce city_id
            source_pref_doc = source_cities_ref.document(city_id).get()
            is_scannable = source_pref_doc.to_dict().get('isScannable', False) if source_pref_doc.exists else False
            target_prefs_ref.document(city_id).set({'isScannable': is_scannable}, merge=True)
        logger.info(f"  Target {target_user_id[:12]}... : prefs copiées depuis la source ({len(catalog_snapshot)} villes).")

    elif target_user_id and dry_run:
        logger.info(f"\n[DRY-RUN] Copierait les prefs isScannable vers {target_user_id[:12]}...")

    # Optionnel : créer les prefs vides pour les autres users
    if also_migrate_prefs and not dry_run:
        already_handled = {source_user_id, target_user_id} if target_user_id else {source_user_id}
        other_users = [uid for uid in USER_IDS_TARGET if uid not in already_handled]
        if other_users:
            logger.info(f"\nInitialisation des prefs (isScannable=False) pour {len(other_users)} autre(s) user(s)...")
            catalog_snapshot_ids = {doc.id for doc in shared_cities_ref.stream()}
            for uid in other_users:
                user_prefs_ref = (
                    db.collection('artifacts').document(APP_ID_TARGET)
                    .collection('users').document(uid)
                    .collection('cities')
                )
                existing_prefs = {doc.id for doc in user_prefs_ref.stream()}
                for city_id in catalog_snapshot_ids:
                    if city_id not in existing_prefs:
                        user_prefs_ref.document(city_id).set({'isScannable': False}, merge=True)
                logger.info(f"  User {uid[:12]}... : prefs initialisées (isScannable=False).")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migre les villes vers le catalogue partagé.')
    parser.add_argument('--dry-run', action='store_true', help='Simulation sans écriture.')
    parser.add_argument('--source-user-id', default=None,
                        help='UID source des villes (défaut : USER_ID_TARGET du .env).')
    parser.add_argument('--target-user-id', default=None,
                        help='UID cible pour copier les prefs isScannable (avec même valeur que source).')
    parser.add_argument('--also-migrate-prefs', action='store_true',
                        help='Initialise les prefs isScannable=False pour tous les autres users.')
    args = parser.parse_args()

    source = args.source_user_id or USER_ID_TARGET
    migrate(
        dry_run=args.dry_run,
        source_user_id=source,
        target_user_id=args.target_user_id,
        also_migrate_prefs=args.also_migrate_prefs,
    )
