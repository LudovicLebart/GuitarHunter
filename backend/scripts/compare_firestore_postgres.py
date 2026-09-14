"""Vérification ponctuelle Firestore <-> Postgres après un export (Chantier A, dry-run de
migration — voir `export_firestore_to_postgres.py` pour le contexte complet et les mêmes
contraintes : lecture seule des DEUX côtés, nécessite les vrais credentials Firebase, à lancer
depuis le serveur, pas depuis un environnement de dev sans accès Firestore).

Deux niveaux de vérification :
1. Comptages exhaustifs par table/utilisateur (rapide, couvre 100% des données).
2. Comparaison champ par champ d'un échantillon de `--sample` annonces par utilisateur (déjà
   passées par `export_firestore_to_postgres.map_deal` pour dériver la valeur ATTENDUE côté
   Postgres à partir du document Firestore, puis comparées à la valeur RÉELLEMENT lue en base) —
   réutilise le même mapping que l'export : un bug de mapping serait donc invisible à CE script
   s'il est déjà dans `map_deal` (les deux partagent le même code). Ce que ce script attrape
   réellement : une exécution de l'export qui a échoué à mi-chemin, une valeur tronquée/convertie
   différemment par Postgres (précision NUMERIC, timestamp), ou une donnée modifiée entre-temps.
"""
import argparse
import asyncio
import logging
import random
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.api.db import _register_json_codecs
from backend.scripts.export_firestore_to_postgres import map_deal, DEAL_COLUMNS

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("compare_firestore_postgres")

# Colonnes exclues de la comparaison champ par champ :
# - ai_analysis_raw : dict potentiellement enrichi de `_unmapped` par l'export, comparaison
#   directe trop fragile (faux positifs) pour la valeur qu'elle apporterait ici.
# - user_id : connu par construction (vient de l'itération, pas du document).
_SKIP_COLUMNS = {"ai_analysis_raw", "user_id"}
_TIMESTAMP_TOLERANCE = timedelta(seconds=1)  # précision nanoseconde Firestore vs microseconde Postgres


def _normalize(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _values_match(column: str, expected, actual) -> bool:
    expected, actual = _normalize(expected), _normalize(actual)
    if hasattr(expected, "isoformat") and hasattr(actual, "isoformat"):
        return abs(expected - actual) <= _TIMESTAMP_TOLERANCE
    return expected == actual


async def _compare_user_deals(fs, app_id, uid, conn, sample_size, report):
    user_ref = fs.collection("artifacts").document(app_id).collection("users").document(uid)
    deal_docs = list(user_ref.collection("guitar_deals").stream())
    fs_count = len(deal_docs)
    pg_count = await conn.fetchval("SELECT count(*) FROM guitar_deals WHERE user_id = $1", uid)
    report.add_count("guitar_deals", uid, fs_count, pg_count)

    sample = random.sample(deal_docs, min(sample_size, len(deal_docs)))
    for deal_doc in sample:
        expected, _ = map_deal(deal_doc.id, deal_doc.to_dict() or {})
        pg_row = await conn.fetchrow("SELECT * FROM guitar_deals WHERE id = $1", deal_doc.id)
        if pg_row is None:
            report.mismatches.append((deal_doc.id, "id", "<présent Firestore>", "<absent Postgres>"))
            continue
        for column in DEAL_COLUMNS:
            if column in _SKIP_COLUMNS or column == "id":
                continue
            if not _values_match(column, expected.get(column), pg_row[column]):
                report.mismatches.append((deal_doc.id, column, expected.get(column), pg_row[column]))

        chat_fs = len(list(deal_doc.reference.collection("chat").stream()))
        chat_pg = await conn.fetchval("SELECT count(*) FROM deal_chat WHERE deal_id = $1", deal_doc.id)
        if chat_fs != chat_pg:
            report.mismatches.append((deal_doc.id, "chat_count", chat_fs, chat_pg))

        resto_fs = len(list(deal_doc.reference.collection("restorationPlan").stream()))
        resto_pg = await conn.fetchval("SELECT count(*) FROM restoration_plan_items WHERE deal_id = $1", deal_doc.id)
        if resto_fs != resto_pg:
            report.mismatches.append((deal_doc.id, "restoration_count", resto_fs, resto_pg))


class ComparisonReport:
    def __init__(self):
        self.counts: list[tuple[str, str, int, int]] = []  # (table, scope, firestore, postgres)
        self.mismatches: list[tuple[str, str, object, object]] = []  # (deal_id, column, expected, actual)

    def add_count(self, table, scope, fs_count, pg_count):
        self.counts.append((table, scope, fs_count, pg_count))

    def log_summary(self, logger):
        logger.info("=" * 70)
        logger.info("Comptages (Firestore vs Postgres) :")
        any_count_mismatch = False
        for table, scope, fs_count, pg_count in self.counts:
            status = "OK" if fs_count == pg_count else "ÉCART"
            if fs_count != pg_count:
                any_count_mismatch = True
            logger.info(f"  [{status:5s}] {table:20s} {scope:24s} Firestore={fs_count:5d}  Postgres={pg_count:5d}")

        logger.info(f"Échantillon champ par champ : {len(self.mismatches)} écart(s) trouvé(s).")
        for deal_id, column, expected, actual in self.mismatches:
            logger.warning(f"  {deal_id} . {column} : Firestore={expected!r}  Postgres={actual!r}")

        logger.info("=" * 70)
        if not any_count_mismatch and not self.mismatches:
            logger.info("Aucun écart détecté sur ce qui a été vérifié.")
        return any_count_mismatch or bool(self.mismatches)


async def compare_all(database_url: str, sample_size: int, only_uid: str | None = None):
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if db_service.offline_mode or not db_service.db:
        logger.error(
            f"Firebase en mode hors-ligne (clé de service introuvable à '{FIREBASE_KEY_PATH}') — "
            "ce script doit tourner depuis un environnement avec les vrais credentials. Abandon."
        )
        return
    fs = db_service.db

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4, init=_register_json_codecs)
    report = ComparisonReport()
    try:
        app_ref = fs.collection("artifacts").document(APP_ID_TARGET)

        fs_cities = len(list(app_ref.collection("cities").stream()))
        async with pool.acquire() as conn:
            pg_cities = await conn.fetchval("SELECT count(*) FROM cities")
        report.add_count("cities", "(catalogue)", fs_cities, pg_cities)

        fs_shared = len(list(fs.collection("shared_deals").stream()))
        async with pool.acquire() as conn:
            pg_shared = await conn.fetchval("SELECT count(*) FROM shared_deals")
        report.add_count("shared_deals", "(global)", fs_shared, pg_shared)

        if only_uid:
            user_docs = [d for d in [app_ref.collection("users").document(only_uid).get()] if d.exists]
        else:
            user_docs = list(app_ref.collection("users").stream())

        async with pool.acquire() as conn:
            for user_doc in user_docs:
                await _compare_user_deals(fs, APP_ID_TARGET, user_doc.id, conn, sample_size, report)

        has_issues = report.log_summary(logger)
        return has_issues
    finally:
        await pool.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database-url", required=True, help="DSN Postgres à vérifier (le même que celui passé à l'export).")
    parser.add_argument("--sample", type=int, default=20, help="Nombre d'annonces comparées champ par champ, par utilisateur (défaut 20).")
    parser.add_argument("--user", default=None, help="Limiter la vérification à un seul uid.")
    args = parser.parse_args()
    has_issues = asyncio.run(compare_all(args.database_url, args.sample, only_uid=args.user))
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
