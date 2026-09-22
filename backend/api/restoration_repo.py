"""Accès SQL à `restoration_plan_items` — tranche 4 du Chantier A.

`deal_id` est la seule FK (pas de `user_id` propre, comme `deal_chat` — la propriété se
vérifie via `chat_repo.get_deal_owner`, réutilisé tel quel ici, aucune raison de dupliquer
cette requête pour une deuxième table qui pointe vers `guitar_deals` de la même façon).

Toute mutation par `item_id` filtre AUSSI sur `deal_id` (`WHERE id = ... AND deal_id = ...`),
même raison que `chat_repo.py` : `id` est un BIGSERIAL global (partagé entre toutes les
annonces/utilisateurs, trivialement énumérable) — un filtrage sur la seule clé primaire
permettrait à un propriétaire d'UNE annonce (vérifié côté main.py sur le `deal_id` de l'URL)
de modifier l'étape de restauration d'une AUTRE annonce en devinant son id (IDOR réel, trouvé
en revue de code). Les fonctions à cible unique renvoient `True`/`False` pour que l'appelant
réponde 404 plutôt que de laisser croire à un succès silencieux ; `reorder_items` filtre de
la même façon mais reste best-effort (un id étranger glissé dans la liste est simplement
ignoré, sans erreur — l'essentiel est qu'il ne puisse écrire nulle part hors de `deal_id`).
"""
import asyncpg

# Correspondance champ API (camelCase, contrat calqué sur firestoreService.js) -> colonne SQL.
# Volontairement restreint à ces 6 champs : une mise à jour ne doit jamais pouvoir toucher
# deal_id/source/proposed_by_message_id/item_order/photo_urls par ce chemin (routes dédiées).
_PATCHABLE_FIELDS = {
    "label": "label",
    "category": "category",
    "status": "status",
    "estimatedCost": "estimated_cost",
    "actualCost": "actual_cost",
    "notes": "notes",
}


async def list_items(pool: asyncpg.Pool, deal_id: str):
    return await pool.fetch(
        "SELECT * FROM restoration_plan_items WHERE deal_id = $1 ORDER BY item_order NULLS LAST, created_at ASC",
        deal_id,
    )


async def add_item(
    pool: asyncpg.Pool, deal_id: str, label: str, category: str | None = None,
    estimated_cost: float | None = None, notes: str | None = None, source: str = "user",
    proposed_by_message_id: int | None = None, order: int | None = None,
) -> int:
    row = await pool.fetchrow(
        """
        INSERT INTO restoration_plan_items
            (deal_id, label, category, estimated_cost, notes, source, proposed_by_message_id, item_order)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        deal_id, label, category, estimated_cost, notes, source, proposed_by_message_id, order,
    )
    return row["id"]


async def update_item(pool: asyncpg.Pool, deal_id: str, item_id: int, patch: dict) -> bool:
    """Mise à jour champ par champ (jamais l'objet entier) — même principe que
    `updateRestorationItem` côté Firestore : une valeur `None` explicitement présente dans
    `patch` efface le champ (colonne nullable), une clé absente ne le touche pas.
    `completed_at` posé/effacé automatiquement selon `status`, comme côté Firestore
    (`payload.completedAt` / `deleteField()`). Renvoie False si `item_id` n'existe pas ou
    n'appartient pas à `deal_id` (patch vide compris — vérifié par une lecture dans ce cas)."""
    if not patch:
        row = await pool.fetchrow(
            "SELECT 1 FROM restoration_plan_items WHERE id = $1 AND deal_id = $2", item_id, deal_id,
        )
        return row is not None
    values = [item_id, deal_id]
    set_parts = []
    for key, value in patch.items():
        column = _PATCHABLE_FIELDS[key]
        values.append(value)
        set_parts.append(f"{column} = ${len(values)}")
    if "status" in patch:
        set_parts.append("completed_at = now()" if patch["status"] == "done" else "completed_at = NULL")
    set_parts.append("updated_at = now()")
    result = await pool.execute(
        f"UPDATE restoration_plan_items SET {', '.join(set_parts)} WHERE id = $1 AND deal_id = $2",
        *values,
    )
    return result.endswith("1")  # "UPDATE 0" ou "UPDATE 1" — id est la clé primaire


async def delete_item(pool: asyncpg.Pool, deal_id: str, item_id: int) -> bool:
    result = await pool.execute(
        "DELETE FROM restoration_plan_items WHERE id = $1 AND deal_id = $2", item_id, deal_id,
    )
    return result.endswith("1")


async def reorder_items(pool: asyncpg.Pool, deal_id: str, ordered_item_ids: list[int]) -> None:
    """Réordonnancement complet en un seul aller-retour SQL (glisser-déposer manuel, proposition
    IA appliquée, ou rattrapage silencieux `backfillRestorationOrder`) — même fonction pour les
    3 cas côté Firestore actuel, réutilisée ici à l'identique plutôt que dupliquée. Un id qui
    n'appartient pas à `deal_id` (glissé dans la liste par un appelant malveillant) est
    simplement filtré par le `AND r.deal_id = $1` ci-dessous — pas d'écriture hors de ce deal."""
    if not ordered_item_ids:
        return
    await pool.execute(
        """
        UPDATE restoration_plan_items AS r
        SET item_order = v.ord, updated_at = now()
        FROM (SELECT * FROM unnest($2::bigint[], $3::int[]) AS t(id, ord)) AS v
        WHERE r.id = v.id AND r.deal_id = $1
        """,
        deal_id, ordered_item_ids, list(range(len(ordered_item_ids))),
    )


async def add_photo(pool: asyncpg.Pool, deal_id: str, item_id: int, url: str) -> bool:
    """Équivalent `arrayUnion` (pas de doublon) sur un tableau JSONB de chaînes."""
    result = await pool.execute(
        """
        UPDATE restoration_plan_items
        SET photo_urls = CASE
                WHEN COALESCE(photo_urls, '[]'::jsonb) @> jsonb_build_array($3::text) THEN photo_urls
                ELSE COALESCE(photo_urls, '[]'::jsonb) || jsonb_build_array($3::text)
            END,
            updated_at = now()
        WHERE id = $1 AND deal_id = $2
        """,
        item_id, deal_id, url,
    )
    return result.endswith("1")


async def remove_photo(pool: asyncpg.Pool, deal_id: str, item_id: int, url: str) -> bool:
    """Équivalent `arrayRemove` — l'opérateur `jsonb - text` retire les éléments de tableau
    correspondants (pas seulement les clés d'objet, malgré le nom)."""
    result = await pool.execute(
        "UPDATE restoration_plan_items SET photo_urls = COALESCE(photo_urls, '[]'::jsonb) - $3::text, updated_at = now() WHERE id = $1 AND deal_id = $2",
        item_id, deal_id, url,
    )
    return result.endswith("1")
