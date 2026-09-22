"""Accès SQL à la table `commands` — utilisé par l'endpoint HTTP (frontend) et, à terme,
directement par le bot (accès Postgres direct, pas via l'API — voir
FIRESTORE_MIGRATION_PLAN.md §3). Isolé pour être réutilisable des deux côtés sans dépendre
de FastAPI.

Les colonnes JSONB (payload) prennent des objets Python bruts, jamais du JSON déjà
sérialisé à la main : le codec asyncpg (voir db.py::_register_json_codecs) s'en charge —
lui repasser une chaîne déjà encodée la ré-encoderait une seconde fois (double guillemets).
"""
import asyncpg


async def create_command(pool: asyncpg.Pool, user_id: str, type_: str, payload) -> int:
    row = await pool.fetchrow(
        """
        INSERT INTO commands (user_id, type, payload, status)
        VALUES ($1, $2, $3, 'pending')
        RETURNING id, created_at
        """,
        user_id, type_, payload,
    )
    return row["id"]


async def get_command(pool: asyncpg.Pool, user_id: str, command_id: int):
    return await pool.fetchrow(
        "SELECT id, type, payload, status, error_message, created_at, completed_at "
        "FROM commands WHERE id = $1 AND user_id = $2",
        command_id, user_id,
    )


async def list_pending_commands(pool: asyncpg.Pool, user_id: str | None = None):
    """Lues côté bot (accès direct, pas d'auth HTTP nécessaire ici — même process serveur).

    `user_id=None` renvoie les commandes en attente de tous les utilisateurs, pour le
    watchdog multi-tenant (voir main.py::main_loop dans le monde Firestore actuel).
    """
    if user_id is not None:
        return await pool.fetch(
            "SELECT id, user_id, type, payload, status, created_at FROM commands "
            "WHERE user_id = $1 AND status = 'pending' ORDER BY created_at",
            user_id,
        )
    return await pool.fetch(
        "SELECT id, user_id, type, payload, status, created_at FROM commands "
        "WHERE status = 'pending' ORDER BY created_at"
    )


async def mark_command_completed(pool: asyncpg.Pool, command_id: int) -> None:
    await pool.execute(
        "UPDATE commands SET status = 'completed', completed_at = now() WHERE id = $1",
        command_id,
    )


async def mark_command_failed(pool: asyncpg.Pool, command_id: int, error_message: str) -> None:
    await pool.execute(
        "UPDATE commands SET status = 'failed', error_message = $2, completed_at = now() WHERE id = $1",
        command_id, error_message,
    )
