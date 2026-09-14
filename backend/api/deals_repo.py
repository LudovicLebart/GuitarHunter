"""Accès SQL à `guitar_deals` — tranche 2 du Chantier A.

Les mutations frontend (favori, achat, classification manuelle) n'ont plus besoin de mettre
à jour un index séparé : les colonnes sont indexées nativement (voir schema.sql), ce qui
remplace le bricolage `deals_index` (20 chunks Firestore, `_update_deal_index` côté bot) —
une seule écriture, jamais deux comme dans `firestoreService.js` actuel.
"""
import asyncpg

from backend.deal_mapping import AI_ANALYSIS_COLUMNS


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


async def add_gallery_image(pool: asyncpg.Pool, user_id: str, deal_id: str, url: str) -> bool:
    """Remplace `addImageToDealGallery` (firestoreService.js) — même sémantique `arrayUnion`
    (dédoublonne, jamais deux fois la même URL), pas un simple `||` qui dupliquerait à chaque
    appel répété. Renvoie False si l'annonce n'existe pas ou n'appartient pas à cet utilisateur."""
    result = await pool.execute(
        """
        UPDATE guitar_deals
        SET storage_image_urls = CASE
            WHEN storage_image_urls IS NULL THEN jsonb_build_array($3::text)
            WHEN storage_image_urls @> jsonb_build_array($3::text) THEN storage_image_urls
            ELSE storage_image_urls || jsonb_build_array($3::text)
        END
        WHERE id = $1 AND user_id = $2
        """,
        deal_id, user_id, url,
    )
    return result.endswith("1")


async def apply_manual_analysis_overrides(pool: asyncpg.Pool, user_id: str, deal_id: str, fields: dict) -> bool:
    """Corrige directement une ou plusieurs colonnes `aiAnalysis` promues (voir
    `AI_ANALYSIS_COLUMNS`, `deal_mapping.py`) SANS repasser par une ré-analyse Gemini — remplace
    `applyManualAnalysisOverrides` (`firestoreService.js`). Whitelist stricte : toute clé absente
    de `AI_ANALYSIS_COLUMNS` est ignorée plutôt que d'écrire dans une colonne arbitraire
    (`title`/`price`/...) sur un payload malformé — ce endpoint n'a pas d'autre vocation.

    Reflète AUSSI la correction dans `manual_analysis_overrides` (JSONB) — relu par le bot à
    chaque future (ré-)analyse (voir `pg_repository.py::_get_manual_analysis_overrides`), sans
    quoi elle serait perdue au prochain scan ou "Ré-analyser" (qui réécrit `aiAnalysis` en
    entier). Pas d'équivalent de l'index léger (`deals_index`) à mettre à jour en plus : les
    colonnes sont déjà indexées nativement, voir l'en-tête de ce fichier."""
    allowed = {k: v for k, v in fields.items() if k in AI_ANALYSIS_COLUMNS}
    if not allowed:
        # Patch vide (ou entièrement hors whitelist) : toujours vérifier que l'annonce existe et
        # appartient à cet utilisateur, sinon un payload vide sur un id étranger répondrait 200 à
        # tort (même piège qu'un `restoration_repo.py::update_item` sans cette vérification).
        row = await pool.fetchrow("SELECT 1 FROM guitar_deals WHERE id = $1 AND user_id = $2", deal_id, user_id)
        return row is not None
    values = list(allowed.values())
    set_clause = ", ".join(f"{col} = ${i + 3}" for i, col in enumerate(allowed))
    jsonb_index = len(values) + 3
    result = await pool.execute(
        f"""
        UPDATE guitar_deals
        SET {set_clause},
            manual_analysis_overrides = COALESCE(manual_analysis_overrides, '{{}}'::jsonb) || ${jsonb_index}::jsonb
        WHERE id = $1 AND user_id = $2
        """,
        deal_id, user_id, *values, dict(allowed),
    )
    return result.endswith("1")


async def reject_deal(pool: asyncpg.Pool, user_id: str, deal_id: str):
    await pool.execute(
        "UPDATE guitar_deals SET status = 'rejected' WHERE id = $1 AND user_id = $2",
        deal_id, user_id,
    )


async def delete_deal(pool: asyncpg.Pool, user_id: str, deal_id: str) -> bool:
    result = await pool.execute("DELETE FROM guitar_deals WHERE id = $1 AND user_id = $2", deal_id, user_id)
    return result.endswith("1")  # asyncpg renvoie "DELETE <n>"
