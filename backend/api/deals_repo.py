"""Accès SQL à `guitar_deals` — tranche 2 du Chantier A.

Les mutations frontend (favori, achat, classification manuelle) n'ont plus besoin de mettre
à jour un index séparé : les colonnes sont indexées nativement (voir schema.sql), ce qui
remplace le bricolage `deals_index` (20 chunks Firestore, `_update_deal_index` côté bot) —
une seule écriture, jamais deux comme dans `firestoreService.js` actuel.
"""
import asyncpg


async def list_deals(pool: asyncpg.Pool, user_id: str, status: str | None = None, favorite_only: bool = False):
    query = "SELECT * FROM guitar_deals WHERE user_id = $1"
    params = [user_id]
    if status is not None:
        params.append(status)
        query += f" AND status = ${len(params)}"
    if favorite_only:
        query += " AND is_favorite = true"
    query += ' ORDER BY "timestamp" DESC'
    return await pool.fetch(query, *params)


async def get_deal(pool: asyncpg.Pool, user_id: str, deal_id: str):
    return await pool.fetchrow("SELECT * FROM guitar_deals WHERE id = $1 AND user_id = $2", deal_id, user_id)


async def get_deals_by_ids(pool: asyncpg.Pool, user_id: str, ids: list[str]):
    return await pool.fetch("SELECT * FROM guitar_deals WHERE user_id = $1 AND id = ANY($2::text[])", user_id, ids)


async def toggle_favorite(pool: asyncpg.Pool, user_id: str, deal_id: str):
    row = await pool.fetchrow(
        "UPDATE guitar_deals SET is_favorite = NOT is_favorite WHERE id = $1 AND user_id = $2 RETURNING is_favorite",
        deal_id, user_id,
    )
    return row["is_favorite"] if row else None


async def toggle_purchased(pool: asyncpg.Pool, user_id: str, deal_id: str, purchase_price: float | None = None):
    """Bascule atomique en une seule requête (comme `toggle_favorite` ci-dessus) — un
    lire-puis-écrire séparé en deux allers-retours (version précédente) laissait une fenêtre où
    deux requêtes concurrentes (double-clic, deux onglets) lisent la même valeur avant que l'une
    ou l'autre n'écrive, perdant une des deux bascules (race trouvée en revue de code). `NOT
    is_purchased` dans le SET est évalué contre la valeur AVANT la mise à jour (sémantique SQL
    standard d'un UPDATE), donc `CASE WHEN NOT is_purchased` ci-dessous lit bien l'état déjà
    inversé, cohérent avec `RETURNING is_purchased`. `purchased_at` suit `toggleDealPurchased`
    (firestoreService.js) : posé à l'instant de l'achat, effacé au retour à `false` — comme
    `purchase_price` (posées/effacées ensemble, jamais l'une sans l'autre)."""
    row = await pool.fetchrow(
        """
        UPDATE guitar_deals
        SET is_purchased = NOT is_purchased,
            purchase_price = CASE WHEN NOT is_purchased THEN $3::numeric ELSE NULL END,
            purchased_at = CASE WHEN NOT is_purchased THEN now() ELSE NULL END
        WHERE id = $1 AND user_id = $2
        RETURNING is_purchased
        """,
        deal_id, user_id, purchase_price,
    )
    return row["is_purchased"] if row else None


async def set_classification(pool: asyncpg.Pool, user_id: str, deal_id: str, classification_path: str | None):
    """`classification_path=None` annule la correction manuelle (retombe sur `classification`,
    la valeur IA — pas de champ à effacer séparément comme l'index Firestore actuel)."""
    await pool.execute(
        "UPDATE guitar_deals SET manual_classification = $3 WHERE id = $1 AND user_id = $2",
        deal_id, user_id, classification_path,
    )


async def reject_deal(pool: asyncpg.Pool, user_id: str, deal_id: str):
    await pool.execute(
        "UPDATE guitar_deals SET status = 'rejected' WHERE id = $1 AND user_id = $2",
        deal_id, user_id,
    )


async def delete_deal(pool: asyncpg.Pool, user_id: str, deal_id: str) -> bool:
    result = await pool.execute("DELETE FROM guitar_deals WHERE id = $1 AND user_id = $2", deal_id, user_id)
    return result.endswith("1")  # asyncpg renvoie "DELETE <n>"
