"""Accès SQL à `shared_deals` — tranche 6 (dernière) du Chantier A.

Table publique en lecture, sans lien de propriété (voir schema.sql pour le détail des règles
Firestore actuelles) — pas de vérification d'appartenance ici, contrairement à `deal_chat`/
`restoration_plan_items`.
"""
import asyncpg


async def upsert_shared_deal(pool: asyncpg.Pool, deal_id: str, snapshot: dict) -> None:
    """`createSharedDeal` fait un `setDoc` complet (jamais un merge) — remplace tout le
    snapshot existant plutôt que de fusionner champ par champ."""
    await pool.execute(
        """
        INSERT INTO shared_deals (id, snapshot)
        VALUES ($1, $2)
        ON CONFLICT (id) DO UPDATE SET snapshot = EXCLUDED.snapshot
        """,
        deal_id, snapshot,
    )


async def get_shared_deal(pool: asyncpg.Pool, deal_id: str):
    return await pool.fetchrow("SELECT snapshot FROM shared_deals WHERE id = $1", deal_id)
