"""Dashboard Administrateur sur Postgres (2026-10-11) — remplace `AdminDashboard.jsx` lisant Firestore
(`collectionGroup('users')`, `admin_stats/latest`) et le job quotidien `backend/admin_stats.py`.

Les statistiques (volume/jour, annonces arrivées en T2/T3, coût estimé) sont calculées À LA LECTURE sur
les 24 dernières heures glissantes, à partir de `user_deal_matches` (annonces retrouvées par le scan de
l'utilisateur) et `guitar_deals.model_used` : plus de snapshot quotidien à tenir à jour. L'e-mail et la
dernière connexion viennent de Firebase Auth (la table `users` ne les porte pas).
"""
import asyncio
from datetime import datetime, timezone

import asyncpg
from firebase_admin import auth as firebase_auth

from backend.api import commands_repo, users_repo
from backend.api.auth import _ensure_firebase_app
from backend.funnel_cost import estimate_profitability

_STATS_SQL = """
SELECT u.uid, u.bot_status, u.config, u.created_at,
       (SELECT count(*) FROM user_city_prefs p WHERE p.user_id = u.uid AND p.active) AS cities_count,
       COALESCE(s.volume, 0) AS daily_volume, COALESCE(s.t2, 0) AS reached_t2, COALESCE(s.t3, 0) AS reached_t3
FROM users u
LEFT JOIN LATERAL (
    SELECT count(*) AS volume,
           count(*) FILTER (WHERE g.model_used NOT ILIKE 'backfill_leger%'
                              AND array_length(string_to_array(g.model_used, '->'), 1) >= 2) AS t2,
           count(*) FILTER (WHERE g.model_used NOT ILIKE 'backfill_leger%'
                              AND g.model_used ILIKE ANY($1::text[])) AS t3
    FROM user_deal_matches m JOIN guitar_deals g ON g.id = m.deal_id
    WHERE m.user_id = u.uid AND m.matched_at >= now() - interval '1 day'
) s ON true
ORDER BY u.created_at
"""


# Un modèle « Expert » (T3) se reconnaît à son nom dans `model_used` : « pro » pour Gemini Pro, « claude » pour le T3 Claude
# (`T3_PROVIDER == "claude"` : `T3_CLAUDE_MODEL`, ex. claude-sonnet-5-5, ne contient pas « pro »). Les analyses légères de
# rattrapage (« backfill_leger -> modèle », 2 maillons) ne sont pas passées par le portier : exclues des comptes T2 et T3.
# Motifs en dur et non lus dans `config` : ce module tourne dans l'API de production, qui ne recopie pas config.py.
_T3_MODEL_PATTERNS = ["%pro%", "%claude%"]


def _estimated_daily_cost(volume: int, t2: int, t3: int) -> float:
    if volume <= 0:
        return 0.0
    t2_rate = t2 / volume
    t3_rate = (t3 / t2) if t2 > 0 else 0.0
    return round(estimate_profitability(volume, t2_rate, t3_rate)["cost_no_cache_per_day"], 4)


def _firebase_users_by_uid(uids) -> dict:
    """E-mail et dernière connexion depuis Firebase Auth, pour ces seuls `uids` (lots de 100, maximum de l'API) ;
    appel bloquant : à lancer dans un thread. Pas de listage de tous les comptes de Firebase."""
    _ensure_firebase_app()
    uids = list(uids)
    result = {}
    for start in range(0, len(uids), 100):
        batch = [firebase_auth.UidIdentifier(uid) for uid in uids[start:start + 100]]
        for user in firebase_auth.get_users(batch).users:
            last = getattr(user.user_metadata, "last_sign_in_timestamp", None)
            result[user.uid] = {
                "email": user.email,
                "lastLogin": datetime.fromtimestamp(last / 1000, tz=timezone.utc).isoformat() if last else None,
            }
    return result


async def list_admin_users(pool: asyncpg.Pool) -> list[dict]:
    rows = await pool.fetch(_STATS_SQL, _T3_MODEL_PATTERNS)
    auth_users = await asyncio.to_thread(_firebase_users_by_uid, [r["uid"] for r in rows])
    users = []
    for r in rows:
        scan = (r["config"] or {}).get("scanConfig") or {}
        info = auth_users.get(r["uid"], {})
        users.append({
            "uid": r["uid"],
            "email": info.get("email"),
            "createdAt": r["created_at"].isoformat(),
            "lastLogin": info.get("lastLogin"),
            "botStatus": r["bot_status"],
            "scanFrequency": scan.get("frequency"),
            "maxListings": scan.get("max_listings") or 0,
            "citiesCount": r["cities_count"],
            "dailyVolume": r["daily_volume"],
            "reachedT2": r["reached_t2"],
            "reachedT3": r["reached_t3"],
            "estimatedDailyCost": _estimated_daily_cost(r["daily_volume"], r["reached_t2"], r["reached_t3"]),
        })
    return users


async def pause_user(pool: asyncpg.Pool, target_uid: str) -> bool:
    """Pause = commande `STOP_BOT` consommée par le bot de l'utilisateur (comme le bouton du front) ;
    écrire `bot_status` directement serait écrasé par le prochain `set_status` du bot."""
    if await pool.fetchval("SELECT 1 FROM users WHERE uid = $1", target_uid) is None:
        return False
    await commands_repo.create_command(pool, target_uid, "STOP_BOT", {})
    return True


async def set_scan_frequency(pool: asyncpg.Pool, target_uid: str, minutes: int) -> bool:
    try:
        await users_repo.update_user_config(pool, target_uid, {"scanConfig": {"frequency": minutes}})
    except LookupError:
        return False
    return True


async def delete_user_data(pool: asyncpg.Pool, target_uid: str) -> str:
    """Supprime la ligne `users` (cascade : villes, favoris, matches, commandes, plan de restauration
    via leurs FK `ON DELETE CASCADE`) — pas le compte Firebase Auth. Refusé tant que son bot scanne.
    Le contrôle de l'état et la suppression sont UNE seule requête : le bot ne peut pas passer en scan entre les deux."""
    deleted = await pool.fetchval(
        "DELETE FROM users WHERE uid = $1 AND bot_status NOT IN ('scanning', 'scanning_url') RETURNING uid", target_uid)
    if deleted is not None:
        return "deleted"
    exists = await pool.fetchval("SELECT 1 FROM users WHERE uid = $1", target_uid)
    return "bot_active" if exists is not None else "not_found"
