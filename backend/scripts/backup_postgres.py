"""Sauvegarde `pg_dump` d'une base Postgres, uploadée vers le bucket Firebase Storage déjà utilisé
par le projet (mêmes credentials que le reste du backend, aucun nouvel outil/compte à provisionner).

Contexte (Phase B.5, voir docs/management/plans/CUTOVER_RUNBOOK.md) : Firestore est managé/répliqué
automatiquement par Google ; Postgres sur un serveur unique ne l'est pas — ce script comble ce trou
resté ouvert depuis le début du plan de migration (§6, FIRESTORE_MIGRATION_PLAN.md).

Usage :
    python backend/scripts/backup_postgres.py --database-url postgresql://... --label prod

Pense à planifier via cron une fois validé manuellement (ex: `0 4 * * * cd ~/GuitareHunter && \
venv/bin/python backend/scripts/backup_postgres.py --database-url "$DATABASE_URL" --label prod \
>> /var/log/guitarhunter-backup.log 2>&1`), avec DATABASE_URL sourcé depuis le bon fichier
d'environnement (guitarhunter_prod_db.env) — pas fait automatiquement par ce script, décision
opérationnelle à valider séparément (fréquence, rétention, fenêtre horaire).

`--label` est obligatoire : chaque base cible (prod, staging, ...) a son propre préfixe de blob
et donc sa propre fenêtre de rétention (voir RETENTION_COUNT) — sans ça, un run manuel contre
staging (pour tester un changement de schéma, par ex.) partagerait la même fenêtre de 14 que le
cron de prod et pourrait faire expulser une vraie sauvegarde de prod (trouvé en revue de code,
2026-09-21 : le script avait déjà tourné deux fois contre staging et une fois contre prod dans le
même préfixe avant que ce ne soit corrigé).
"""
import argparse
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger(__name__)

# Rétention : nombre de sauvegardes les plus récentes à garder sur le bucket — les plus anciennes
# sont supprimées après un upload réussi, pour ne pas laisser grossir le bucket indéfiniment.
RETENTION_COUNT = 14


def dump_database(database_url: str, out_path: Path) -> None:
    """`pg_dump -Fc` (format custom, compressé, restaurable sélectivement via `pg_restore`) —
    préféré à un simple `.sql` texte pour une base de cette taille (~7000 annonces + images en
    JSONB)."""
    result = subprocess.run(
        ["pg_dump", "-Fc", "-f", str(out_path), database_url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump a échoué (code {result.returncode}) : {result.stderr}")
    logger.info(f"Dump créé : {out_path} ({out_path.stat().st_size / 1_048_576:.1f} Mo)")


def upload_and_prune(db_service: DatabaseService, local_path: Path, prefix: str) -> None:
    blob_name = f"{prefix}{local_path.name}"
    blob = db_service.bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))
    logger.info(f"Uploadé : gs://{db_service.bucket.name}/{blob_name}")

    existing = sorted(db_service.bucket.list_blobs(prefix=prefix), key=lambda b: b.name)
    stale = existing[:-RETENTION_COUNT] if len(existing) > RETENTION_COUNT else []
    for blob in stale:
        blob.delete()
        logger.info(f"Supprimé (rétention {RETENTION_COUNT}) : {blob.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database-url", required=True, help="DSN Postgres à sauvegarder.")
    parser.add_argument(
        "--label", required=True,
        help="Identifie la base cible (ex: 'prod', 'staging') — isole sa fenêtre de rétention des autres.",
    )
    parser.add_argument("--keep-local", action="store_true", help="Ne pas supprimer le fichier local après upload/échec.")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(f"/tmp/guitarhunter_pg_backup_{args.label}_{timestamp}.dump")

    try:
        dump_database(args.database_url, out_path)

        db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
        if db_service.bucket is None:
            raise RuntimeError("Bucket Firebase Storage non configuré (FIREBASE_STORAGE_BUCKET manquant).")
        upload_and_prune(db_service, out_path, prefix=f"backups/postgres/{args.label}/")

        logger.info("Sauvegarde terminée avec succès.")
    finally:
        # Nettoie le fichier local que le dump ait réussi, échoué en cours de route (fichier
        # partiel) ou que l'upload ait échoué après coup (fichier complet mais jamais uploadé) —
        # sans ça, des échecs répétés du cron quotidien accumulent des dumps de ~17 Mo dans /tmp
        # jusqu'à remplir le disque du serveur (trouvé en revue de code, 2026-09-21).
        if not args.keep_local and out_path.exists():
            out_path.unlink()
            logger.info("Fichier local supprimé.")


if __name__ == "__main__":
    main()
