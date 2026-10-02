"""Accès SQL à `logs` côté API — lecture pour le LogViewer. Le bot écrit via
`backend/logging_config.py::PostgresHandler` (psycopg, sync, flush toutes les 3s)."""
import asyncpg


async def list_logs(pool: asyncpg.Pool, uid: str, limit: int) -> list[dict]:
    """Les `limit` derniers logs de l'utilisateur, du plus ancien au plus récent (ordre
    d'affichage du LogViewer). Tri sur `id` (BIGSERIAL, monotone) plutôt que `created_at` : les
    lignes d'un même flush partagent des horodatages quasi identiques."""
    rows = await pool.fetch(
        "SELECT id, message, level, created_at FROM logs WHERE user_id = $1 ORDER BY id DESC LIMIT $2",
        uid, limit,
    )
    return [dict(r) for r in reversed(rows)]
