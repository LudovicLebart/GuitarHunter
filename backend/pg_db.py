"""Pool de connexions Postgres SYNCHRONE (psycopg) pour le bot — Phase A.1 de la bascule (voir
docs/management/plans/FIRESTORE_MIGRATION_PLAN.md §5.3).

Miroir sync de `backend/api/db.py` (qui utilise `asyncpg`, pilote async, pour le service FastAPI
async-natif). Le bot tourne en thread-par-utilisateur, entièrement synchrone (voir CLAUDE.md) —
un pool sync est le choix naturel ici, plutôt que de ponter chaque appel vers une boucle asyncio
depuis du code déjà threadé. Les deux pilotes touchent le même schéma (`backend/api/schema.sql`,
partagé, pas dupliqué) : rien n'empêche deux drivers différents de lire/écrire les mêmes tables.

Isolé de `backend/database.py` (Firestore) : ce module ne touche à rien de l'existant, conforme
à FIRESTORE_MIGRATION_PLAN.md §5.1 ("construire sur une branche séparée, sans toucher au chemin
Firestore existant") — n'est importé par aucun code de production tant que la bascule (Phase B)
n'a pas eu lieu.
"""
import os
from pathlib import Path

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

SCHEMA_PATH = Path(__file__).parent / "api" / "schema.sql"

# Même défaut que backend/api/db.py (Postgres local, auth locale sans mot de passe réseau).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://guitarhunter@localhost/guitarhunter")

_pool: ConnectionPool | None = None


def init_pool() -> ConnectionPool:
    """Crée le pool (idempotent) et joue le schéma (idempotent aussi, voir schema.sql) — à
    appeler une fois au démarrage du bot, comme `backend/api/db.py::init_pool()` pour l'API."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True,
        )
        with _pool.connection() as conn:
            conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Pool Postgres non initialisé — appeler init_pool() au démarrage.")
    return _pool
