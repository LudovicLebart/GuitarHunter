"""Pool de connexions Postgres (asyncpg) + initialisation du schéma.

Isolé de backend/database.py (Firestore) : ce module ne touche à rien de l'existant, conforme
à FIRESTORE_MIGRATION_PLAN.md §5.1 ("construire sur une branche séparée, sans toucher au
chemin Firestore existant").
"""
import json
import os
from pathlib import Path

import asyncpg

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# DSN par défaut adapté au serveur de dev/prod (Postgres local, pas de mot de passe réseau
# nécessaire via peer/trust auth sur socket Unix) ; surchargé en prod via la variable d'env.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://guitarhunter@localhost/guitarhunter")

_pool: asyncpg.Pool | None = None


async def _register_json_codecs(conn: asyncpg.Connection) -> None:
    """Sans ça, asyncpg renvoie les colonnes JSON/JSONB comme des chaînes brutes (pas des
    dict/list Python) — piège réel rencontré en écrivant la tranche 3 (chat), où une lecture
    de `restoration_proposals` renvoyait une string plutôt qu'une liste. Appliqué à CHAQUE
    connexion du pool via le paramètre `init` de `create_pool()`."""
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text")


async def init_pool() -> asyncpg.Pool:
    """Crée le pool de connexions et joue le schéma (idempotent). Appelé au démarrage de l'API."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10, init=_register_json_codecs)
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        async with _pool.acquire() as conn:
            await conn.execute(schema_sql)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool Postgres non initialisé — appeler init_pool() au démarrage.")
    return _pool
