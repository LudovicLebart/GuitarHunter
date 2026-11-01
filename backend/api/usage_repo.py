"""Accès SQL à `llm_usage` côté API — Chantier C-0. Le bot écrit via `backend/llm_usage.py`
(psycopg, sync) ; le chat, qui appelle Gemini depuis le navigateur (Firebase AI Logic), n'a pas
d'autre moyen que de poster son `usageMetadata` ici."""
import asyncpg


def provider_of(model: str) -> str:
    """Fournisseur déduit du nom du modèle (le chat peut tourner sur Claude ou Gemini)."""
    return "anthropic" if str(model).startswith("claude") else "gemini"


async def add_usage(pool: asyncpg.Pool, uid: str, row: dict, provider: str = None) -> None:
    """`provider` : fourni par le serveur quand c'est lui qui appelle le modèle (Claude) ; sinon déduit du modèle."""
    await pool.execute(
        """
        INSERT INTO llm_usage (source, provider, model, action, deal_id, user_ref, images,
                               input_tokens, cached_tokens, output_tokens, thoughts_tokens, latency_ms, ok,
                               error_type, cache_write_tokens)
        VALUES ('chat', $13, $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $14)
        """,
        row["model"], row["action"], row.get("deal_id"), uid, row.get("images", 0),
        row.get("input_tokens", 0), row.get("cached_tokens", 0), row.get("output_tokens", 0),
        row.get("thoughts_tokens", 0), row.get("latency_ms"), row.get("ok", True),
        row.get("error_type"), provider or provider_of(row["model"]), row.get("cache_write_tokens", 0),
    )
