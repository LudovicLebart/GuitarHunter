"""Correspondance document Firestore <-> colonnes Postgres pour `guitar_deals`/`deal_chat`/
`restoration_plan_items`/`cities` — extrait de `backend/scripts/export_firestore_to_postgres.py`
(2026-09-10) pour être partagé avec `backend/pg_repository.py` (accès Postgres du bot, Phase A.1
de la bascule, voir `docs/management/plans/FIRESTORE_MIGRATION_PLAN.md` §5.3) : les deux ont
besoin exactement du même mapping, dupliquer aurait signifié corriger deux fois chaque futur
champ Firestore découvert.

Fonctions pures — dict Python en entrée, dict de colonnes en sortie, aucune dépendance
Firestore/Postgres réelle. Testées isolément dans `backend/scripts/test_export_firestore_to_postgres.py`.
"""
from datetime import datetime

# Champs de premier niveau écrits par le scraper/bot (backend/bot.py::listing_data), déjà en
# snake_case côté Firestore (pas de conversion camelCase — ce sont des clés Python passées
# telles quelles à Firestore, contrairement aux mutations faites depuis firestoreService.js).
_DEAL_SCALAR_FIELDS = {
    "title": "title", "price": "price", "original_price": "original_price",
    "price_drop_amount": "price_drop_amount", "link": "link", "location": "location",
    "latitude": "latitude", "longitude": "longitude", "published_at_raw": "published_at_raw",
    "description": "description", "published_at_ts": "published_at_ts",
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
    "soldNotes": "sold_notes",
}

# Champ camelCase TIMESTAMPTZ (posé via serverTimestamp() côté toggleDealPurchased).
_DEAL_CAMEL_DATETIME_FIELDS = {"purchasedAt": "purchased_at"}

# Table de correspondance combinée (clé Firestore, snake_case ou camelCase -> colonne Postgres),
# utilisée par `backend/pg_repository.py::update_deal_data_and_analysis` pour ne mettre à jour QUE
# les colonnes correspondant aux clés réellement présentes dans un `.update()` partiel — l'export
# (qui reçoit toujours un document complet) n'en a pas besoin, mais un accès direct type
# repository doit reproduire la sémantique "champ absent = jamais touché" de Firestore.
DEAL_FIELD_TO_COLUMN = {
    **_DEAL_SCALAR_FIELDS, **_DEAL_CAMEL_SCALAR_FIELDS,
    **_DEAL_CAMEL_JSON_FIELDS, **_DEAL_CAMEL_DATETIME_FIELDS,
}

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
# pour générer les UPSERT/INSERT, plutôt que des paramètres positionnels écrits à la main.
DEAL_COLUMNS = [
    "id", "user_id", "title", "price", "original_price", "price_drop_amount", "status",
    "verdict", "classification", "classification_rejected", "brand", "model_name",
    "production_year", "country_of_origin", "color", "finish_application", "finish_texture",
    "deal_score", "authenticity_score", "condition_score", "liquidity_score",
    "restoration_interest_score", "model_used", "tier3_trigger", "initial_verdict",
    "initial_model_used", "is_favorite", "is_purchased", "manual_classification",
    "manual_analysis_overrides", "link", "location", "latitude", "longitude",
    "published_at_raw", "image_urls", "storage_image_urls", "storage_image_gs_uris",
    "ai_analysis_raw", "sold_at", "timestamp", "purchase_price", "purchased_at", "description",
    "sold_notes", "published_at_ts",
]

# Colonnes promues depuis `aiAnalysis` (voir _AI_ANALYSIS_FIELDS) — exposées pour
# `backend/pg_repository.py::update_deal_analysis`, qui ne doit toucher QUE ces colonnes +
# `ai_analysis_raw` (jamais les champs `deal_data`, absents d'une simple ré-analyse).
AI_ANALYSIS_COLUMNS = list(_AI_ANALYSIS_FIELDS.values())

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
    les deux drivers (asyncpg comme psycopg) acceptent un `datetime.datetime` directement."""
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


def map_deal(deal_id: str, data: dict) -> tuple[dict, list[str]]:
    """Document Firestore `guitar_deals/{id}` -> dict de colonnes `guitar_deals` (sans `user_id`,
    rempli par l'appelant qui connaît l'utilisateur du contexte d'itération, pas du document).
    Retourne aussi la liste des clés de premier niveau non reconnues (voir `ai_analysis_raw`)."""
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
    if unmapped:
        row["ai_analysis_raw"] = {**(row["ai_analysis_raw"] or {}), "_unmapped": _sanitize_json(unmapped)}

    return row, sorted(unmapped.keys())


def map_chat_message(deal_id: str, data: dict) -> dict:
    """Document `guitar_deals/{id}/chat/{msgId}` -> dict de colonnes `deal_chat` (sans `id` : la
    clé Postgres est un BIGSERIAL réassigné à l'insertion, l'id Firestore d'origine n'est pas
    conservé comme clé)."""
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
    `restoration_plan_items`. `proposed_by_message_id` doit déjà être résolu par l'appelant."""
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


CITY_FIELD_TO_COLUMN = {
    "name": "name", "latitude": "latitude", "longitude": "longitude",
    "needsReview": "needs_review", "createdBy": "created_by",
}


def map_city(city_id: str, data: dict) -> dict:
    return {
        "id": city_id,
        **{col: data.get(field) for field, col in CITY_FIELD_TO_COLUMN.items()},
        "needs_review": bool(data.get("needsReview", False)),
    }
