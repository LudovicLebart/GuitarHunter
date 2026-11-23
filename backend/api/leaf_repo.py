"""Accès SQL (asyncpg) à Leaf Hunter : `vehicle_deals` + `user_vehicle_matches` / `user_vehicle_state` / `vehicle_price_history`.

AUTONOME volontairement : n'importe rien d'autre de `backend/` (l'API de production ne reçoit qu'une liste de modules,
voir `test_prod_sync.py`). Isolation multi-tenant : toute lecture passe par `user_vehicle_matches` (annonce visible pour
cet utilisateur seulement)."""
from typing import Any, Dict, List, Optional

import asyncpg

_STATE_FIELDS = {"is_favorite": "bool", "is_rejected": "bool", "notes": "text", "checklist": "jsonb"}

_SELECT = """
    SELECT d.*, COALESCE(s.is_favorite, false) AS is_favorite, COALESCE(s.is_rejected, false) AS is_rejected,
           s.notes, s.checklist, m.matched_at, m.withdrawn
    FROM vehicle_deals d
    JOIN user_vehicle_matches m ON m.deal_id = d.id AND m.user_id = $1
    LEFT JOIN user_vehicle_state s ON s.deal_id = d.id AND s.user_id = $1
"""


async def list_deals(pool: asyncpg.Pool, user_id: str, include_sold: bool = False,
                     include_rejected: bool = False) -> List[asyncpg.Record]:
    """`include_sold` : annonces marquées vendues (fait global). `include_rejected` : annonces que l'utilisateur a rejetées à la
    main OU que ses filtres ont écartées (`withdrawn`) ; deux notions distinctes de « vendue », jamais mélangées."""
    where = []
    if not include_sold:
        where.append("d.status = 'active'")
    if not include_rejected:
        where.append("COALESCE(s.is_rejected, false) = false AND NOT m.withdrawn")
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    return await pool.fetch(f"{_SELECT}{clause} ORDER BY d.price ASC NULLS LAST, d.km ASC NULLS LAST", user_id)


async def get_deal(pool: asyncpg.Pool, user_id: str, deal_id: str) -> Optional[asyncpg.Record]:
    return await pool.fetchrow(f"{_SELECT} WHERE d.id = $2", user_id, deal_id)


async def price_history(pool: asyncpg.Pool, user_id: str, deal_id: str) -> Optional[List[Dict[str, Any]]]:
    """None si l'annonce n'est pas visible pour l'utilisateur (≠ liste vide)."""
    if await pool.fetchval("SELECT 1 FROM user_vehicle_matches WHERE user_id = $1 AND deal_id = $2", user_id, deal_id) is None:
        return None
    rows = await pool.fetch("SELECT price, seen_at FROM vehicle_price_history WHERE deal_id = $1 ORDER BY seen_at, id", deal_id)
    return [dict(r) for r in rows]


async def set_state(pool: asyncpg.Pool, user_id: str, deal_id: str, **fields: Any) -> Optional[asyncpg.Record]:
    """Met à jour SEULEMENT les champs fournis (favori, rejet, notes, checklist). None si l'annonce est invisible."""
    unknown = set(fields) - set(_STATE_FIELDS)
    if unknown:
        raise ValueError(f"champs inconnus : {sorted(unknown)}")
    if await pool.fetchval("SELECT 1 FROM user_vehicle_matches WHERE user_id = $1 AND deal_id = $2", user_id, deal_id) is None:
        return None
    cols = list(fields)
    values = [fields[c] for c in cols]      # le pool de l'API encode déjà les dict/list en JSONB (db._register_json_codecs)
    insert_cols = ", ".join(["user_id", "deal_id", *cols])
    placeholders = ", ".join(["$1", "$2", *(f"${i + 3}::{_STATE_FIELDS[c]}" for i, c in enumerate(cols))])
    updates = ", ".join([*(f"{c} = EXCLUDED.{c}" for c in cols), "updated_at = now()"])
    await pool.execute(
        f"INSERT INTO user_vehicle_state ({insert_cols}) VALUES ({placeholders}) "
        f"ON CONFLICT (user_id, deal_id) DO UPDATE SET {updates}", user_id, deal_id, *values)
    return await get_deal(pool, user_id, deal_id)


async def list_runs(pool: asyncpg.Pool, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Derniers passages des sources Leaf (`scrape_runs`, sources `leaf_*`) de l'utilisateur : santé des scrapers."""
    rows = await pool.fetch(
        "SELECT source, outcome, detail, cards_seen, duration_ms, created_at FROM scrape_runs "
        "WHERE user_id = $1 AND source LIKE 'leaf\\_%' ORDER BY created_at DESC, id DESC LIMIT $2", user_id, limit)
    return [dict(r) for r in rows]


async def get_config(pool: asyncpg.Pool, user_id: str) -> Dict[str, Any]:
    """`users.config.leafConfig` brut ({} si absent)."""
    cfg = await pool.fetchval("SELECT config FROM users WHERE uid = $1", user_id)
    return ((cfg or {}).get("leafConfig")) or {}


async def set_config(pool: asyncpg.Pool, user_id: str, new_config: Dict[str, Any]) -> None:
    """Fusionne dans `leafConfig` (les clés absentes de `new_config`, comme une future `analysisConfig`, sont conservées)."""
    await pool.execute(
        "UPDATE users SET config = jsonb_set(COALESCE(config, '{}'::jsonb), '{leafConfig}', "
        "COALESCE(config->'leafConfig', '{}'::jsonb) || $2::jsonb, true) WHERE uid = $1", user_id, new_config)
