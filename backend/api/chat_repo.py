"""Accès SQL à `deal_chat` — tranche 3 du Chantier A.

`parts` reste un blob JSON opaque (payload Gemini complet, y compris les pièces image gs://
invisibles à l'utilisateur) — ni lu ni interprété ici, exactement comme côté Firestore
actuel (`firestoreService.js::addDealChatMessage`).

Les colonnes JSONB prennent des objets Python bruts (dict/list/None), jamais du JSON déjà
sérialisé à la main : le codec asyncpg (voir db.py::_register_json_codecs) encode/décode
automatiquement — un `json.dumps()` manuel en plus double-encoderait la valeur.
"""
import asyncpg


async def get_deal_owner(pool: asyncpg.Pool, deal_id: str) -> str | None:
    """Utilisé pour vérifier la propriété d'une annonce avant d'exposer son chat (REST et WS) —
    `deal_chat` n'a pas de `user_id` propre, seulement une FK vers `guitar_deals`."""
    row = await pool.fetchrow("SELECT user_id FROM guitar_deals WHERE id = $1", deal_id)
    return row["user_id"] if row else None


async def list_messages(pool: asyncpg.Pool, deal_id: str):
    return await pool.fetch(
        "SELECT * FROM deal_chat WHERE deal_id = $1 ORDER BY created_at ASC", deal_id
    )


async def add_message(
    pool: asyncpg.Pool, deal_id: str, role: str, parts, display_text: str | None,
    attached_image_part_indices=None, restoration_proposals=None, photo_recall=None,
    is_error: bool = False, requalification_proposal=None,
):
    row = await pool.fetchrow(
        """
        INSERT INTO deal_chat (deal_id, role, parts, display_text, attached_image_part_indices,
                                restoration_proposals, photo_recall, is_error, requalification_proposal)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """,
        deal_id, role, parts, display_text, attached_image_part_indices,
        restoration_proposals, photo_recall, is_error, requalification_proposal,
    )
    return row["id"]


async def replace_message(
    pool: asyncpg.Pool, message_id: int, parts, display_text: str | None,
    restoration_proposals=None, photo_recall=None, is_error: bool = False,
    requalification_proposal=None,
):
    """Remplace en place (bouton "Réessayer") — mêmes champs remis à NULL quand absents que
    `firestoreService.js::replaceDealChatMessage` (pas juste omis)."""
    await pool.execute(
        """
        UPDATE deal_chat
        SET parts = $2, display_text = $3, restoration_proposals = $4,
            photo_recall = $5, is_error = $6, requalification_proposal = $7
        WHERE id = $1
        """,
        message_id, parts, display_text, restoration_proposals,
        photo_recall, is_error, requalification_proposal,
    )


async def mark_added_to_gallery(pool: asyncpg.Pool, message_id: int, part_index: int, url: str):
    await pool.execute(
        """
        UPDATE deal_chat
        SET added_to_gallery_urls = COALESCE(added_to_gallery_urls, '{}'::jsonb)
            || jsonb_build_object($2::text, $3::text)
        WHERE id = $1
        """,
        message_id, str(part_index), url,
    )


async def mark_restoration_proposal_status(pool: asyncpg.Pool, message_id: int, proposal_index: int, new_status: str, item_id: str | None = None):
    """`restoration_proposals` est un tableau JSON ; on met à jour l'élément `proposal_index`
    par fusion (jsonb_set), sans réécrire tout le tableau depuis l'application."""
    patch = {"status": new_status}
    if item_id is not None:
        patch["itemId"] = item_id
    await pool.execute(
        """
        UPDATE deal_chat
        SET restoration_proposals = jsonb_set(
            restoration_proposals, ARRAY[$2::text], (restoration_proposals -> $2::int) || $3::jsonb
        )
        WHERE id = $1
        """,
        message_id, str(proposal_index), patch,
    )


async def mark_requalification_proposal_status(pool: asyncpg.Pool, message_id: int, new_status: str):
    await pool.execute(
        """
        UPDATE deal_chat
        SET requalification_proposal = requalification_proposal || jsonb_build_object('status', $2::text)
        WHERE id = $1
        """,
        message_id, new_status,
    )
