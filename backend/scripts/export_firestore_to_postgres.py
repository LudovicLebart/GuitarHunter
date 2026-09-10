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
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.api.db import _register_json_codecs, SCHEMA_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("export_firestore_to_postgres")


# --------------------------------------------------------------------------------------------
# Fonctions de correspondance (pures — dict Python en entrée, dict de colonnes en sortie, aucune
# dépendance Firestore/Postgres) : testées isolément dans test_export_firestore_to_postgres.py.
# --------------------------------------------------------------------------------------------

# Champs de premier niveau écrits par le scraper/bot (backend/bot.py::listing_data), déjà en
# snake_case côté Firestore (pas de conversion camelCase — ce sont des clés Python passées
# telles quelles à Firestore, contrairement aux mutations faites depuis firestoreService.js).
_DEAL_SCALAR_FIELDS = {
    "title": "title", "price": "price", "original_price": "original_price",
    "price_drop_amount": "price_drop_amount", "link": "link", "location": "location",
    "latitude": "latitude", "longitude": "longitude", "published_at_raw": "published_at_raw",
}

# Champs camelCase écrits par le frontend (firestoreService.js) ou par repository.py::create_new_deal
# (initialVerdict/initialModelUsed), valeurs scalaires directes (pas de conversion de type).
_DEAL_CAMEL_SCALAR_FIELDS = {
    "isFavorite": "is_favorite", "isPurchased": "is_purchased",
    "manualClassification": "manual_classification", "purchasePrice": "purchase_price",
    "initialVerdict": "initial_verdict", "initialModelUsed": "initial_model_used",
}

# Champs camelCase JSONB (objets/tableaux) — passés par `_sanitize_json` (Timestamps imbriqués
# possibles, ex: dans manualAnalysisOverrides si jamais un champ date y était copié).
_DEAL_CAMEL_JSON_FIELDS = {
    "manualAnalysisOverrides": "manual_analysis_overrides", "imageUrls": "image_urls",
    "storageImageUrls": "storage_image_urls", "storageImageGsUris": "storage_image_gs_uris",
}

# Champ camelCate TIMESTAMPTZ (posé via serverTimestamp() côté toggleDealPurchased).
_DEAL_CAMEL_DATETIME_FIELDS = {"purchasedAt": "purchased_at"}

# Champs nichés dans `aiAnalysis` (analyzer.py, snake_case en interne) promus en colonnes propres
# (voir schema.sql) — le dict `aiAnalysis` complet est de toute façon conservé tel quel dans
# `ai_analysis_raw`, cette promotion ne fait que dupliquer certains champs pour l'indexation SQL.
_AI_ANALYSIS_FIELDS = {
    "verdict": "verdict", "classification": "classification",
    "classification_rejected": "classification_rejected", "brand": "brand",
    "model_name": "model_name", "production_year": "production_year",
    "country_of_origin": "country_of_origin", "color": "color",
    "finish_application": "finish_application", "finish_texture": "finish_texture",
    "deal_score": "deal_score", "authenticity_score": "authenticity_score",
    "condition_score": "condition_score", "liquidity_score": "liquidity_score",
    "restoration_interest_score": "restoration_interest_score",
    "model_used": "model_used", "tier3_trigger": "tier3_trigger",
}

_SMALLINT_COLUMNS = {
    "deal_score", "authenticity_score", "condition_score", "liquidity_score",
    "restoration_interest_score",
}

# Ordre EXACT des colonnes de guitar_deals dans schema.sql (hors index/triggers) — source unique
# pour générer l'UPSERT, plutôt que 42 paramètres positionnels écrits à la main.
DEAL_COLUMNS = [
    "id", "user_id", "title", "price", "original_price", "price_drop_amount", "status",
    "verdict", "classification", "classification_rejected", "brand", "model_name",
    "production_year", "country_of_origin", "color", "finish_application", "finish_texture",
    "deal_score", "authenticity_score", "condition_score", "liquidity_score",
    "restoration_interest_score", "model_used", "tier3_trigger", "initial_verdict",
    "initial_model_used", "is_favorite", "is_purchased", "manual_classification",
    "manual_analysis_overrides", "link", "location", "latitude", "longitude",
    "published_at_raw", "image_urls", "storage_image_urls", "storage_image_gs_uris",
    "ai_analysis_raw", "sold_at", "timestamp", "purchase_price", "purchased_at",
]

CHAT_COLUMNS = [
    "deal_id", "role", "parts", "display_text", "attached_image_part_indices",
    "restoration_proposals", "added_to_gallery_urls", "photo_recall", "is_error",
    "requalification_proposal", "created_at",
]

RESTO_COLUMNS = [
    "deal_id", "label", "category", "status", "estimated_cost", "actual_cost", "notes",
    "source", "proposed_by_message_id", "item_order", "photo_urls", "created_at",
    "updated_at", "completed_at",
]


def _sanitize_json(value):
    """Rend une valeur Firestore sérialisable en JSON : les Timestamps (`DatetimeWithNanoseconds`,
    sous-classe de `datetime.datetime`) deviennent des chaînes ISO 8601 ; tout le reste passe tel
    quel. Récursif sur dict/list. Les colonnes TIMESTAMPTZ (hors JSONB) n'ont PAS besoin de ça :
    asyncpg accepte un `datetime.datetime` (et donc `DatetimeWithNanoseconds`) directement."""
    if isinstance(value, dict):
        return {k: _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_json(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _to_datetime(value):
    return value if isinstance(value, datetime) else None


def _smallint(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def map_deal(deal_id: str, data: dict) -> dict:
    """Document Firestore `guitar_deals/{id}` -> dict de colonnes `guitar_deals` (sans `user_id`,
    rempli par l'appelant qui connaît l'utilisateur du contexte d'itération, pas du document)."""
    row = {"id": deal_id}

    for fs_key, col in _DEAL_SCALAR_FIELDS.items():
        row[col] = data.get(fs_key)
    for fs_key, col in _DEAL_CAMEL_SCALAR_FIELDS.items():
        row[col] = data.get(fs_key)
    for fs_key, col in _DEAL_CAMEL_JSON_FIELDS.items():
        row[col] = _sanitize_json(data.get(fs_key))
    for fs_key, col in _DEAL_CAMEL_DATETIME_FIELDS.items():
        row[col] = _to_datetime(data.get(fs_key))

    row["status"] = data.get("status") or "analyzed"
    row["timestamp"] = _to_datetime(data.get("timestamp")) or datetime.now()
    row["sold_at"] = _to_datetime(data.get("soldAt"))
    # is_favorite/is_purchased sont NOT NULL DEFAULT false côté Postgres (colonnes indexées
    # nativement, voir schema.sql) — un document Firestore sans ces clés (jamais touché depuis
    # leur introduction, cas réel pour d'anciennes annonces) doit retomber sur False, pas NULL
    # (même repli que repository.py::create_new_deal : `deal_data.get('isFavorite', False)`).
    # Bug trouvé par le test d'intégration (NotNullViolationError), pas par les tests purs
    # (qui ne touchent jamais un vrai Postgres) — voir test_export_firestore_to_postgres_integration.py.
    row["is_favorite"] = bool(row["is_favorite"])
    row["is_purchased"] = bool(row["is_purchased"])

    ai = data.get("aiAnalysis") or {}
    if isinstance(ai, list):  # garde-fou déjà présent côté lecture, repository.py::_update_deal_index
        ai = ai[0] if ai else {}
    if not isinstance(ai, dict):
        ai = {}
    for ai_key, col in _AI_ANALYSIS_FIELDS.items():
        value = ai.get(ai_key)
        row[col] = _smallint(value) if col in _SMALLINT_COLUMNS else value
    row["ai_analysis_raw"] = _sanitize_json(ai)

    consumed = ({"status", "aiAnalysis", "timestamp", "soldAt", "chunkId"}
                | set(_DEAL_SCALAR_FIELDS) | set(_DEAL_CAMEL_SCALAR_FIELDS)
                | set(_DEAL_CAMEL_JSON_FIELDS) | set(_DEAL_CAMEL_DATETIME_FIELDS))
    unmapped = {k: v for k, v in data.items() if k not in consumed}
    if data.get("soldNotes") is not None:
        unmapped["soldNotes"] = data.get("soldNotes")
    if unmapped:
        row["ai_analysis_raw"] = {**(row["ai_analysis_raw"] or {}), "_unmapped": _sanitize_json(unmapped)}

    return row, sorted(unmapped.keys())


def map_chat_message(deal_id: str, data: dict) -> dict:
    """Document `guitar_deals/{id}/chat/{msgId}` -> dict de colonnes `deal_chat` (sans `id` : la
    clé Postgres est un BIGSERIAL réassigné à l'insertion, l'id Firestore d'origine n'est pas
    conservé comme clé — voir la limitation documentée en tête de fichier)."""
    row = {
        "deal_id": deal_id,
        "role": data.get("role"),
        "parts": _sanitize_json(data.get("parts")),
        "display_text": data.get("displayText"),
        "attached_image_part_indices": data.get("attachedImagePartIndices"),
        "added_to_gallery_urls": data.get("addedToGalleryUrls"),
        "photo_recall": _sanitize_json(data.get("photoRecall")),
        "is_error": bool(data.get("isError", False)),
        "created_at": _to_datetime(data.get("createdAt")) or datetime.now(),
    }

    # `restorationProposalStates` (map Firestore séparée, {index: {status, itemId?}}) n'a pas de
    # colonne propre côté Postgres : chat_repo.py::mark_restoration_proposal_status fusionne
    # directement l'état DANS l'élément du tableau `restoration_proposals` — on reproduit ici le
    # même résultat final pour qu'une relecture de l'historique migré se comporte identiquement.
    proposals = data.get("restorationProposals")
    if proposals:
        proposals = [dict(p) if isinstance(p, dict) else p for p in proposals]
        states = data.get("restorationProposalStates") or {}
        for idx_str, state in states.items():
            try:
                idx = int(idx_str)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(proposals) and isinstance(proposals[idx], dict):
                proposals[idx] = {**proposals[idx], **state}
    row["restoration_proposals"] = _sanitize_json(proposals)

    # Même principe pour `requalificationProposalState` (champ singulier séparé) ->
    # chat_repo.py::mark_requalification_proposal_status fusionne son `status` DANS
    # `requalification_proposal` lui-même.
    requal = data.get("requalificationProposal")
    requal_state = data.get("requalificationProposalState")
    if requal and requal_state:
        requal = {**requal, **requal_state}
    row["requalification_proposal"] = _sanitize_json(requal)

    return row


def map_restoration_item(deal_id: str, data: dict, proposed_by_message_id: int | None) -> dict:
    """Document `guitar_deals/{id}/restorationPlan/{itemId}` -> dict de colonnes
    `restoration_plan_items`. `proposed_by_message_id` doit déjà être résolu par l'appelant (voir
    `_migrate_deal` : nécessite la table de correspondance id Firestore -> id Postgres construite
    en migrant `chat` d'abord pour le même deal)."""
    created_at = _to_datetime(data.get("createdAt")) or datetime.now()
    return {
        "deal_id": deal_id,
        "label": data.get("label"),
        "category": data.get("category"),
        "status": data.get("status") or "pending",
        "estimated_cost": data.get("estimatedCost"),
        "actual_cost": data.get("actualCost"),
        "notes": data.get("notes"),
        "source": data.get("source") or "user",
        "proposed_by_message_id": proposed_by_message_id,
        "item_order": data.get("order"),
        "photo_urls": _sanitize_json(data.get("photoUrls")),
        "created_at": created_at,
        "updated_at": _to_datetime(data.get("updatedAt")) or created_at,
        "completed_at": _to_datetime(data.get("completedAt")),
    }


def map_city(city_id: str, data: dict) -> dict:
    return {
        "id": city_id, "name": data.get("name"),
        "latitude": data.get("latitude"), "longitude": data.get("longitude"),
        "needs_review": bool(data.get("needsReview", False)),
        "created_by": data.get("createdBy"),
    }


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
