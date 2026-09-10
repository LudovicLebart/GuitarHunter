"""Export ponctuel Firestore -> Postgres (Chantier A, dry-run de migration).

Contexte : `docs/management/plans/FIRESTORE_MIGRATION_PLAN.md` §8 "reste à faire" point 2. Les 6
tranches de l'API Postgres sont codées et testées (voir le plan), mais AUCUNE donnée réelle n'a
encore été copiée — ce script fait cette copie, en LECTURE SEULE sur Firestore (aucun `.set()`/
`.update()`/`.delete()` ici, uniquement `DatabaseService`/`stream()`), écriture idempotente côté
Postgres (rejouable sans risque, voir `_migrate_*` ci-dessous).

**Ne PAS lancer depuis un environnement sans les vrais credentials Firebase** (`backend/config/
serviceAccountKey.json`, voir `config.py::FIREBASE_KEY_PATH`) — sans ce fichier, `DatabaseService`
bascule en mode hors-ligne et ce script s'arrête immédiatement (voir `main()`). Il doit tourner
depuis le serveur (ou un poste ayant une copie de la clé de service), jamais depuis un
environnement de dev sans accès Firestore — même famille de contrainte que
`backend/scripts/run_once.py` (voir CLAUDE.md).

Cible recommandée : un Postgres de **staging**, PAS la base utilisée par les tests d'intégration
(`backend/api/test_*.py`, qui nettoient leurs propres lignes) ni une base de dev déjà en usage —
passer `--database-url` explicitement plutôt que de compter sur le défaut de `backend/api/db.py`.

Portée : `users` (juste `uid`/`bot_status`/`config`, voir note dans `_migrate_user`),
`guitar_deals` + sous-collections `chat`/`restorationPlan`, `cities` (catalogue partagé) +
`user_city_prefs` (`users/{uid}/cities`), `shared_deals` (collection top-level séparée). Exclut
`commands`/`logs` (files/données transitoires, voir FIRESTORE_MIGRATION_PLAN.md §8 — décision
prise avant d'écrire ce script, pas une omission).

Chaque champ Firestore de premier niveau non reconnu (ainsi que `soldNotes`, jamais promu en
colonne côté guitar_deals) est conservé sans perte dans `ai_analysis_raw['_unmapped']` plutôt que
silencieusement abandonné : ce mapping n'a jamais pu être vérifié contre de vraies données de
production (pas d'accès Firestore réel depuis l'environnement où il a été écrit) — mieux vaut
sur-conserver et le signaler dans le rapport de fin d'exécution que perdre une donnée réelle.

Limitation connue, acceptée sciemment (pas un oubli) : `restorationProposals[i]` d'un message de
chat peut référencer `itemId` (id Firestore de l'étape de restauration appliquée). Comme les ids
`deal_chat`/`restoration_plan_items` sont des BIGSERIAL Postgres réassignés à l'export (les ids
Firestore d'origine sont des chaînes), cet `itemId` n'est PAS retraduit — il resterait un id
Firestore orphelin dans ce JSONB après migration. Pur affichage (lien "voir l'étape" dans une
bulle de chat déjà traitée), aucune contrainte FK dessus : dégradation cosmétique mineure, pas une
perte de donnée. Corriger proprement demanderait un id stable partagé entre les deux migrations
(chat et restorationPlan) avant même leur création Postgres — hors de proportion pour ce gain.
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.api.db import _register_json_codecs, SCHEMA_PATH
from backend.deal_mapping import (
    CHAT_COLUMNS, DEAL_COLUMNS, RESTO_COLUMNS, _sanitize_json,
    map_chat_message, map_city, map_deal, map_restoration_item,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("export_firestore_to_postgres")


# --------------------------------------------------------------------------------------------
# Orchestration (lecture Firestore, écriture Postgres idempotente).
# --------------------------------------------------------------------------------------------

class MigrationReport:
    def __init__(self):
        self.counts = {"users": 0, "deals": 0, "chat_messages": 0, "restoration_items": 0,
                       "cities": 0, "user_city_prefs": 0, "shared_deals": 0,
                       "legacy_cities_created": 0}
        self.unmapped_deal_fields: dict[str, list[str]] = {}
        self.dangling_proposed_by: list[tuple[str, str]] = []  # (deal_id, firestore_message_id)

    def log_summary(self, logger):
        logger.info("=" * 70)
        logger.info("Résumé de l'export :")
        for key, value in self.counts.items():
            logger.info(f"  {key:24s} : {value}")
        if self.unmapped_deal_fields:
            logger.warning(f"{len(self.unmapped_deal_fields)} annonce(s) avec des champs non "
                            f"reconnus (conservés dans ai_analysis_raw['_unmapped']) :")
            for deal_id, keys in self.unmapped_deal_fields.items():
                logger.warning(f"    {deal_id} : {keys}")
        if self.dangling_proposed_by:
            logger.warning(f"{len(self.dangling_proposed_by)} proposedByMessageId orphelin(s) "
                            f"(message introuvable, laissé NULL) : {self.dangling_proposed_by}")
        logger.info("=" * 70)


async def _upsert(conn, table: str, columns: list[str], row: dict, conflict_col: str):
    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != conflict_col)
    query = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_col}) DO UPDATE SET {set_clause}"
    )
    await conn.execute(query, *[row[c] for c in columns])


async def _migrate_cities_catalog(app_ref, pool, report: MigrationReport):
    docs = list(app_ref.collection("cities").stream())
    async with pool.acquire() as conn:
        for doc in docs:
            row = map_city(doc.id, doc.to_dict() or {})
            await _upsert(conn, "cities", list(row.keys()), row, "id")
            report.counts["cities"] += 1
    logger.info(f"Catalogue de villes : {len(docs)} ville(s) migrée(s).")


async def _migrate_shared_deals(fs, pool, report: MigrationReport):
    docs = list(fs.collection("shared_deals").stream())
    async with pool.acquire() as conn:
        for doc in docs:
            data = doc.to_dict() or {}
            await conn.execute(
                "INSERT INTO shared_deals (id, snapshot) VALUES ($1, $2) "
                "ON CONFLICT (id) DO UPDATE SET snapshot = EXCLUDED.snapshot",
                doc.id, _sanitize_json(data),
            )
            report.counts["shared_deals"] += 1
    logger.info(f"shared_deals : {len(docs)} annonce(s) partagée(s) migrée(s).")


async def _ensure_city_exists(conn, city_id: str, legacy_pref_data: dict, report: MigrationReport):
    """FK `user_city_prefs.city_id -> cities.id` : une ville présente UNIQUEMENT dans
    `users/{uid}/cities` (jamais migrée vers le catalogue partagé — architecture pré-2026-09,
    voir `repository.py::get_cities()` "Fallback ancienne architecture") ferait échouer l'insert
    sans ça. Crée une entrée minimale à partir du doc de préférence lui-même plutôt que de perdre
    la préférence utilisateur ou de planter l'export."""
    exists = await conn.fetchrow("SELECT 1 FROM cities WHERE id = $1", city_id)
    if exists:
        return
    await conn.execute(
        "INSERT INTO cities (id, name, latitude, longitude) VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (id) DO NOTHING",
        city_id, legacy_pref_data.get("name") or city_id,
        legacy_pref_data.get("latitude"), legacy_pref_data.get("longitude"),
    )
    report.counts["legacy_cities_created"] += 1
    logger.warning(f"Ville '{city_id}' absente du catalogue partagé — créée depuis "
                    f"users/*/cities (architecture legacy).")


async def _migrate_user(fs, app_id: str, uid: str, user_data: dict, pool, report: MigrationReport):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (uid, bot_status, config) VALUES ($1, $2, $3) "
            "ON CONFLICT (uid) DO UPDATE SET bot_status = EXCLUDED.bot_status, config = EXCLUDED.config",
            uid, user_data.get("botStatus") or "idle", _sanitize_json(user_data),
        )
        report.counts["users"] += 1

    user_ref = fs.collection("artifacts").document(app_id).collection("users").document(uid)

    deal_docs = list(user_ref.collection("guitar_deals").stream())
    logger.info(f"[{uid[:8]}] {len(deal_docs)} annonce(s) à migrer...")
    for deal_doc in deal_docs:
        await _migrate_deal(user_ref, uid, deal_doc.id, deal_doc.to_dict() or {}, pool, report)

    pref_docs = list(user_ref.collection("cities").stream())
    async with pool.acquire() as conn:
        for pref_doc in pref_docs:
            pref_data = pref_doc.to_dict() or {}
            await _ensure_city_exists(conn, pref_doc.id, pref_data, report)
            await conn.execute(
                """
                INSERT INTO user_city_prefs (user_id, city_id, active, kijiji_radius_km)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, city_id) DO UPDATE
                    SET active = EXCLUDED.active, kijiji_radius_km = EXCLUDED.kijiji_radius_km
                """,
                uid, pref_doc.id, bool(pref_data.get("isScannable", False)), pref_data.get("kijijiRadiusKm"),
            )
            report.counts["user_city_prefs"] += 1


async def _migrate_deal(user_ref, uid: str, deal_id: str, deal_data: dict, pool, report: MigrationReport):
    row, unmapped_keys = map_deal(deal_id, deal_data)
    row["user_id"] = uid
    if unmapped_keys:
        report.unmapped_deal_fields[deal_id] = unmapped_keys

    deal_ref = user_ref.collection("guitar_deals").document(deal_id)
    chat_docs = list(deal_ref.collection("chat").order_by("createdAt").stream())
    resto_docs = list(deal_ref.collection("restorationPlan").stream())

    async with pool.acquire() as conn:
        async with conn.transaction():
            await _upsert(conn, "guitar_deals", DEAL_COLUMNS, row, "id")
            report.counts["deals"] += 1

            # Repartir de zéro pour chat/restorationPlan à chaque exécution : ces deux tables
            # n'ont pas de colonne portant l'id Firestore d'origine (clé Postgres = BIGSERIAL
            # réassigné), donc pas de UPSERT possible par id — un DELETE+INSERT par deal_id est
            # idempotent au niveau du deal entier, ce qui suffit pour ce script (copie complète,
            # pas une synchronisation incrémentale).
            await conn.execute("DELETE FROM deal_chat WHERE deal_id = $1", deal_id)
            await conn.execute("DELETE FROM restoration_plan_items WHERE deal_id = $1", deal_id)

            chat_id_map: dict[str, int] = {}
            for chat_doc in chat_docs:
                chat_row = map_chat_message(deal_id, chat_doc.to_dict() or {})
                placeholders = ", ".join(f"${i + 1}" for i in range(len(CHAT_COLUMNS)))
                new_id = await conn.fetchval(
                    f"INSERT INTO deal_chat ({', '.join(CHAT_COLUMNS)}) VALUES ({placeholders}) RETURNING id",
                    *[chat_row[c] for c in CHAT_COLUMNS],
                )
                chat_id_map[chat_doc.id] = new_id
                report.counts["chat_messages"] += 1

            for resto_doc in resto_docs:
                resto_data = resto_doc.to_dict() or {}
                firestore_message_id = resto_data.get("proposedByMessageId")
                pg_message_id = chat_id_map.get(firestore_message_id) if firestore_message_id else None
                if firestore_message_id and pg_message_id is None:
                    report.dangling_proposed_by.append((deal_id, firestore_message_id))
                resto_row = map_restoration_item(deal_id, resto_data, pg_message_id)
                placeholders = ", ".join(f"${i + 1}" for i in range(len(RESTO_COLUMNS)))
                await conn.execute(
                    f"INSERT INTO restoration_plan_items ({', '.join(RESTO_COLUMNS)}) VALUES ({placeholders})",
                    *[resto_row[c] for c in RESTO_COLUMNS],
                )
                report.counts["restoration_items"] += 1


async def export_all(database_url: str, only_uid: str | None = None):
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    if db_service.offline_mode or not db_service.db:
        logger.error(
            "Firebase en mode hors-ligne (clé de service introuvable ou invalide à "
            f"'{FIREBASE_KEY_PATH}') — ce script doit tourner depuis un environnement avec les "
            "vrais credentials (le serveur, pas cet environnement de dev). Abandon."
        )
        return
    fs = db_service.db

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4, init=_register_json_codecs)
    report = MigrationReport()
    try:
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

        app_ref = fs.collection("artifacts").document(APP_ID_TARGET)
        await _migrate_cities_catalog(app_ref, pool, report)
        await _migrate_shared_deals(fs, pool, report)

        if only_uid:
            user_docs = [app_ref.collection("users").document(only_uid).get()]
            user_docs = [d for d in user_docs if d.exists]
        else:
            user_docs = list(app_ref.collection("users").stream())
        logger.info(f"{len(user_docs)} utilisateur(s) à migrer.")

        for user_doc in user_docs:
            await _migrate_user(fs, APP_ID_TARGET, user_doc.id, user_doc.to_dict() or {}, pool, report)

        report.log_summary(logger)
    finally:
        await pool.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--database-url", required=True,
        help="DSN Postgres CIBLE (staging recommandé) — ex: postgresql://guitarhunter@localhost/guitarhunter_staging",
    )
    parser.add_argument("--user", default=None, help="Limiter la migration à un seul uid (validation rapide).")
    args = parser.parse_args()
    asyncio.run(export_all(args.database_url, only_uid=args.user))


if __name__ == "__main__":
    main()
