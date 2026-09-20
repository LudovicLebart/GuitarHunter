"""Accès SQL à `guitar_deals` — tranche 2 du Chantier A.

Réécrit le 2026-09-20 pour le catalogue PARTAGÉ (voir schema.sql, JOURNAL.md 2026-09-19/20) :
`guitar_deals` n'a plus de `user_id` — une même annonce réelle est analysée UNE SEULE fois, quel
que soit le nombre d'utilisateurs dont la recherche la recoupe. Ce que `user_id` faisait avant se
répartit désormais sur deux tables :
- `user_deal_matches` : VISIBILITÉ — "le scan de cet utilisateur a retrouvé cette annonce". Toute
  lecture scopée par utilisateur (liste, fiche, mutation) passe par une jointure/EXISTS dessus.
- `user_deal_state` : préférences PERSONNELLES (favori, rejet manuel) — plus de colonnes
  `is_favorite`/rejet sur `guitar_deals` elle-même.

L'achat (`is_purchased`/`purchased_by_user_id`) reste sur `guitar_deals` : décision explicite de
l'utilisateur, une guitare achetée dans la vraie vie est indisponible pour tout le monde, pas
seulement pour l'acheteur.
"""
import asyncpg

from backend.deal_mapping import AI_ANALYSIS_COLUMNS

# Colonnes préférence (`user_deal_state`) exposées sous leur ancien nom de colonne
# `guitar_deals` pour ne rien changer côté frontend (`apiService.js` mappe déjà ces clés).
_PREFERENCE_SELECT = (
    "COALESCE(uds.is_favorite, false) AS is_favorite, "
    "COALESCE(uds.is_rejected, false) AS is_rejected"
)


async def _is_visible(pool: asyncpg.Pool, user_id: str, deal_id: str) -> bool:
    """Un utilisateur peut agir sur une annonce si son propre scan l'a matchée (visibilité,
    voir `user_deal_matches`) — pas seulement si l'annonce existe globalement."""
    row = await pool.fetchrow(
        "SELECT 1 FROM user_deal_matches WHERE user_id = $1 AND deal_id = $2", user_id, deal_id
    )
    return row is not None


async def list_deals(pool: asyncpg.Pool, user_id: str, status: str | None = None, favorite_only: bool = False):
    query = f"""
        SELECT gd.*, {_PREFERENCE_SELECT}
        FROM guitar_deals gd
        JOIN user_deal_matches udm ON udm.deal_id = gd.id AND udm.user_id = $1
        LEFT JOIN user_deal_state uds ON uds.deal_id = gd.id AND uds.user_id = $1
    """
    params = [user_id]
    conditions = []
    if status is not None:
        params.append(status)
        conditions.append(f"gd.status = ${len(params)}")
    if favorite_only:
        conditions.append("COALESCE(uds.is_favorite, false) = true")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += ' ORDER BY gd."timestamp" DESC'
    return await pool.fetch(query, *params)


async def get_deal(pool: asyncpg.Pool, user_id: str, deal_id: str):
    return await pool.fetchrow(
        f"""
        SELECT gd.*, {_PREFERENCE_SELECT}
        FROM guitar_deals gd
        JOIN user_deal_matches udm ON udm.deal_id = gd.id AND udm.user_id = $2
        LEFT JOIN user_deal_state uds ON uds.deal_id = gd.id AND uds.user_id = $2
        WHERE gd.id = $1
        """,
        deal_id, user_id,
    )


async def get_deals_by_ids(pool: asyncpg.Pool, user_id: str, ids: list[str]):
    return await pool.fetch(
        f"""
        SELECT gd.*, {_PREFERENCE_SELECT}
        FROM guitar_deals gd
        JOIN user_deal_matches udm ON udm.deal_id = gd.id AND udm.user_id = $1
        LEFT JOIN user_deal_state uds ON uds.deal_id = gd.id AND uds.user_id = $1
        WHERE gd.id = ANY($2::text[])
        """,
        user_id, ids,
    )


async def toggle_favorite(pool: asyncpg.Pool, user_id: str, deal_id: str):
    """Préférence PERSONNELLE (`user_deal_state`, pas `guitar_deals`) — un favori posé par un
    utilisateur n'affecte pas les autres. Bascule atomique via `ON CONFLICT DO UPDATE` (même
    principe que l'ancien `toggle_purchased` : `NOT COALESCE(...)` lu contre la ligne EXISTANTE,
    pas contre `EXCLUDED`, pour éviter la course lire-puis-écrire en deux allers-retours)."""
    if not await _is_visible(pool, user_id, deal_id):
        return None
    row = await pool.fetchrow(
        """
        INSERT INTO user_deal_state (user_id, deal_id, is_favorite) VALUES ($1, $2, true)
        ON CONFLICT (user_id, deal_id) DO UPDATE
            SET is_favorite = NOT COALESCE(user_deal_state.is_favorite, false), updated_at = now()
        RETURNING is_favorite
        """,
        user_id, deal_id,
    )
    return row["is_favorite"] if row else None


async def toggle_purchased(pool: asyncpg.Pool, user_id: str, deal_id: str, purchase_price: float | None = None):
    """Achat GLOBAL (décision explicite de l'utilisateur, 2026-09-19) : une guitare achetée dans
    la vraie vie est indisponible pour tout le monde, pas seulement pour l'acheteur — donc,
    contrairement à `toggle_favorite`, cette écriture touche `guitar_deals` (partagée), pas
    `user_deal_state`. `WHERE (NOT is_purchased OR purchased_by_user_id = $2)` empêche un
    utilisateur de "désacheter" l'annonce d'un AUTRE — 0 ligne affectée dans ce cas, distingué
    d'un id inexistant/invisible par l'appel à `_is_visible` en amont (voir `main.py`, qui lève
    409 plutôt que 404 sur ce cas précis)."""
    if not await _is_visible(pool, user_id, deal_id):
        return None
    row = await pool.fetchrow(
        """
        UPDATE guitar_deals
        SET is_purchased = NOT is_purchased,
            purchased_by_user_id = CASE WHEN NOT is_purchased THEN $2 ELSE NULL END,
            purchase_price = CASE WHEN NOT is_purchased THEN $3::numeric ELSE NULL END,
            purchased_at = CASE WHEN NOT is_purchased THEN now() ELSE NULL END
        WHERE id = $1 AND (NOT is_purchased OR purchased_by_user_id = $2)
        RETURNING is_purchased
        """,
        deal_id, user_id, purchase_price,
    )
    if row is not None:
        return row["is_purchased"]
    # Visible mais l'UPDATE n'a rien affecté : forcément "déjà achetée par un AUTRE utilisateur"
    # (le cas "id inexistant" a déjà été écarté par _is_visible ci-dessus).
    return "locked_by_other_user"


async def set_classification(pool: asyncpg.Pool, user_id: str, deal_id: str, classification_path: str | None) -> bool:
    """`classification_path=None` annule la correction manuelle (retombe sur `classification`,
    la valeur IA). Correction GLOBALE (2026-09-19) : elle profite à tous les utilisateurs qui
    voient cette annonce partagée, pas seulement à celui qui l'a posée."""
    if not await _is_visible(pool, user_id, deal_id):
        return False
    await pool.execute(
        "UPDATE guitar_deals SET manual_classification = $2 WHERE id = $1",
        deal_id, classification_path,
    )
    return True


async def add_gallery_image(pool: asyncpg.Pool, user_id: str, deal_id: str, url: str) -> bool:
    """Remplace `addImageToDealGallery` (firestoreService.js) — même sémantique `arrayUnion`
    (dédoublonne, jamais deux fois la même URL). Renvoie False si l'annonce n'existe pas ou
    n'est pas visible pour cet utilisateur (catalogue partagé : la galerie ajoutée est globale,
    mais seul un utilisateur qui voit l'annonce peut y contribuer)."""
    if not await _is_visible(pool, user_id, deal_id):
        return False
    await pool.execute(
        """
        UPDATE guitar_deals
        SET storage_image_urls = CASE
            WHEN storage_image_urls IS NULL THEN jsonb_build_array($2::text)
            WHEN storage_image_urls @> jsonb_build_array($2::text) THEN storage_image_urls
            ELSE storage_image_urls || jsonb_build_array($2::text)
        END
        WHERE id = $1
        """,
        deal_id, url,
    )
    return True


async def apply_manual_analysis_overrides(pool: asyncpg.Pool, user_id: str, deal_id: str, fields: dict) -> bool:
    """Corrige directement une ou plusieurs colonnes `aiAnalysis` promues (voir
    `AI_ANALYSIS_COLUMNS`, `deal_mapping.py`) SANS repasser par une ré-analyse Gemini — remplace
    `applyManualAnalysisOverrides` (`firestoreService.js`). Whitelist stricte : toute clé absente
    de `AI_ANALYSIS_COLUMNS` est ignorée plutôt que d'écrire dans une colonne arbitraire.
    Correction GLOBALE (2026-09-19), comme `set_classification` ci-dessus.

    Reflète AUSSI la correction dans `manual_analysis_overrides` (JSONB) — relu par le bot à
    chaque future (ré-)analyse (voir `pg_repository.py::_get_manual_analysis_overrides`)."""
    if not await _is_visible(pool, user_id, deal_id):
        return False
    allowed = {k: v for k, v in fields.items() if k in AI_ANALYSIS_COLUMNS}
    if not allowed:
        # Patch vide (ou entièrement hors whitelist) : la visibilité a déjà été vérifiée
        # ci-dessus, rien de plus à faire — répondre "trouvé" (200) sans écrire.
        return True
    values = list(allowed.values())
    set_clause = ", ".join(f"{col} = ${i + 2}" for i, col in enumerate(allowed))
    jsonb_index = len(values) + 2
    await pool.execute(
        f"""
        UPDATE guitar_deals
        SET {set_clause},
            manual_analysis_overrides = COALESCE(manual_analysis_overrides, '{{}}'::jsonb) || ${jsonb_index}::jsonb
        WHERE id = $1
        """,
        deal_id, *values, dict(allowed),
    )
    return True


async def reject_deal(pool: asyncpg.Pool, user_id: str, deal_id: str) -> bool:
    """Rejet MANUEL ("pas intéressé", bouton frontend) — préférence PERSONNELLE depuis le
    2026-09-19 (décision explicite de l'utilisateur) : n'affecte ni la visibilité de l'annonce
    pour les autres utilisateurs, ni `guitar_deals.status` (réservé au rejet AUTOMATIQUE par
    verdict IA, un fait sur l'annonce elle-même — voir CLAUDE.md, `BAD_DEAL` != `REJECTED`)."""
    if not await _is_visible(pool, user_id, deal_id):
        return False
    await pool.execute(
        "INSERT INTO user_deal_state (user_id, deal_id, is_rejected) VALUES ($1, $2, true) "
        "ON CONFLICT (user_id, deal_id) DO UPDATE SET is_rejected = true, updated_at = now()",
        user_id, deal_id,
    )
    return True


async def delete_deal(pool: asyncpg.Pool, user_id: str, deal_id: str) -> bool:
    """2026-09-19 : ne supprime PLUS l'annonce globale (catalogue partagé, d'autres utilisateurs
    peuvent la voir) — retire seulement la visibilité/les préférences de CET utilisateur,
    équivalent d'un "retirer de mon fil" (voir `pg_repository.py::delete_listing`, même
    sémantique côté bot)."""
    if not await _is_visible(pool, user_id, deal_id):
        return False
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM user_deal_matches WHERE user_id = $1 AND deal_id = $2", user_id, deal_id)
            await conn.execute("DELETE FROM user_deal_state WHERE user_id = $1 AND deal_id = $2", user_id, deal_id)
    return True
