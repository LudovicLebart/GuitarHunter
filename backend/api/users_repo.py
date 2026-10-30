"""Accès SQL à `users` (config bot + botStatus) — Phase A.2 du Chantier A, remplace
`updateUserConfig`/`onBotConfigUpdate` (`firestoreService.js`).

`config` est un blob JSONB libre (mêmes clés que le document Firestore actuel :
`scanConfig`, `exclusionKeywords`, `analysisConfig`, ...) — pas de colonnes dédiées, la forme
exacte est décidée côté frontend/bot, pas ici (comme côté Firestore).

`update_user_config` reproduit la sémantique `setDoc(doc, data, { merge: true })` de Firestore
(fusion récursive : un objet imbriqué est fusionné champ par champ, une valeur scalaire ou un
tableau remplace entièrement l'ancienne valeur) — PAS un simple `config || $patch` en SQL, qui
serait un remplacement de premier niveau seulement (une mise à jour de `scanConfig.frequency`
seul effacerait le reste de `scanConfig`). Verrouillage explicite (`FOR UPDATE`) le temps de la
fusion : deux requêtes concurrentes (deux onglets) sur des clés différentes ne doivent pas se
perdre l'une l'autre comme un `UPDATE ... SET config = $1` sans lecture préalable le ferait.
"""
import asyncpg


def _deep_merge(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


async def ensure_user_exists(pool: asyncpg.Pool, user_id: str, initial_config: dict) -> bool:
    """Crée la ligne `users` au premier contact authentifié (ne touche rien si elle existe déjà).
    Renvoie `True` si elle vient d'être créée. Le bot découvre les utilisateurs en LISANT cette table
    (`main.py::discover_users`) : sans cette création, un nouvel inscrit n'aurait jamais de bot. Avec
    `initial_config` vide, `pg_repository.ensure_initial_structure` complète les valeurs par défaut
    au premier démarrage de son bot."""
    row = await pool.fetchrow(
        "INSERT INTO users (uid, bot_status, config) VALUES ($1, 'idle', $2) ON CONFLICT (uid) DO NOTHING RETURNING uid",
        user_id, initial_config,
    )
    return row is not None


async def get_user_config(pool: asyncpg.Pool, user_id: str):
    row = await pool.fetchrow("SELECT bot_status, config FROM users WHERE uid = $1", user_id)
    if row is None:
        return None
    return {**(row["config"] or {}), "botStatus": row["bot_status"]}


async def update_user_config(pool: asyncpg.Pool, user_id: str, patch: dict) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT config FROM users WHERE uid = $1 FOR UPDATE", user_id)
            if row is None:
                raise LookupError(f"Utilisateur '{user_id}' introuvable.")
            merged = _deep_merge(row["config"] or {}, patch)
            await conn.execute(
                "UPDATE users SET config = $2, updated_at = now() WHERE uid = $1", user_id, merged
            )
    return merged
