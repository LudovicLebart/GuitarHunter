"""Accès SQL à `restoration_plan_items` — tranche 4 du Chantier A.

`deal_id` est la seule FK (pas de `user_id` propre, comme `deal_chat` — la propriété se
vérifie via `chat_repo.get_deal_owner`, réutilisé tel quel ici, aucune raison de dupliquer
cette requête pour une deuxième table qui pointe vers `guitar_deals` de la même façon).
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


async def update_item(pool: asyncpg.Pool, item_id: int, patch: dict) -> None:
    """Mise à jour champ par champ (jamais l'objet entier) — même principe que
    `updateRestorationItem` côté Firestore : une valeur `None` explicitement présente dans
    `patch` efface le champ (colonne nullable), une clé absente ne le touche pas.
    `completed_at` posé/effacé automatiquement selon `status`, comme côté Firestore
    (`payload.completedAt` / `deleteField()`)."""
    if not patch:
        return
    set_parts = []
    values = []
    for key, value in patch.items():
        column = _PATCHABLE_FIELDS[key]
        values.append(value)
        set_parts.append(f"{column} = ${len(values)}")
    if "status" in patch:
        set_parts.append("completed_at = now()" if patch["status"] == "done" else "completed_at = NULL")
    set_parts.append("updated_at = now()")
    values.append(item_id)
    await pool.execute(
        f"UPDATE restoration_plan_items SET {', '.join(set_parts)} WHERE id = ${len(values)}",
        *values,
    )


async def delete_item(pool: asyncpg.Pool, item_id: int) -> None:
    await pool.execute("DELETE FROM restoration_plan_items WHERE id = $1", item_id)


async def reorder_items(pool: asyncpg.Pool, ordered_item_ids: list[int]) -> None:
    """Réordonnancement complet en un seul aller-retour SQL (glisser-déposer manuel, proposition
    IA appliquée, ou rattrapage silencieux `backfillRestorationOrder`) — même fonction pour les
    3 cas côté Firestore actuel, réutilisée ici à l'identique plutôt que dupliquée."""
    if not ordered_item_ids:
        return
    await pool.execute(
        """
        UPDATE restoration_plan_items AS r
        SET item_order = v.ord, updated_at = now()
        FROM (SELECT * FROM unnest($1::bigint[], $2::int[]) AS t(id, ord)) AS v
        WHERE r.id = v.id
        """,
        ordered_item_ids, list(range(len(ordered_item_ids))),
    )


async def add_photo(pool: asyncpg.Pool, item_id: int, url: str) -> None:
    """Équivalent `arrayUnion` (pas de doublon) sur un tableau JSONB de chaînes."""
    await pool.execute(
        """
        UPDATE restoration_plan_items
        SET photo_urls = CASE
                WHEN COALESCE(photo_urls, '[]'::jsonb) @> jsonb_build_array($2::text) THEN photo_urls
                ELSE COALESCE(photo_urls, '[]'::jsonb) || jsonb_build_array($2::text)
            END,
            updated_at = now()
        WHERE id = $1
        """,
        item_id, url,
    )


async def remove_photo(pool: asyncpg.Pool, item_id: int, url: str) -> None:
    """Équivalent `arrayRemove` — l'opérateur `jsonb - text` retire les éléments de tableau
    correspondants (pas seulement les clés d'objet, malgré le nom)."""
    await pool.execute(
        "UPDATE restoration_plan_items SET photo_urls = COALESCE(photo_urls, '[]'::jsonb) - $2::text, updated_at = now() WHERE id = $1",
        item_id, url,
    )
