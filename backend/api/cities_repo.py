"""Accès SQL à `cities` (catalogue partagé) + `user_city_prefs` — tranche 5 du Chantier A.

Périmètre volontairement limité à ce que le frontend consomme aujourd'hui
(`firestoreService.js` : `onCitiesUpdate`, `deleteCity`, `toggleCityScannable`,
`setCityKijijiRadius`) : l'écriture du catalogue partagé lui-même reste faite par
`bot.py::add_city_auto()` côté Firestore jusqu'à la bascule (voir FIRESTORE_MIGRATION_PLAN.md
§5.1) — l'ajout d'une ville passe déjà par la commande `ADD_CITY` (tranche 1, table
`commands`), rien de plus à construire ici pour ce chemin.
"""
import asyncpg


async def city_exists(pool: asyncpg.Pool, city_id: str) -> bool:
    row = await pool.fetchrow("SELECT 1 FROM cities WHERE id = $1", city_id)
    return row is not None


async def list_cities_for_user(pool: asyncpg.Pool, user_id: str):
    """Reproduit la fusion catalogue + prefs de `onCitiesUpdate` : `isScannable`/
    `kijiji_radius_km` retombent sur leur valeur par défaut (false/NULL) pour toute ville sans
    ligne de préférence pour cet utilisateur (LEFT JOIN, pas de ligne obligatoire)."""
    return await pool.fetch(
        """
        SELECT c.id, c.name, c.latitude, c.longitude, c.needs_review,
               COALESCE(p.active, false) AS is_scannable,
               p.kijiji_radius_km
        FROM cities c
        LEFT JOIN user_city_prefs p ON p.city_id = c.id AND p.user_id = $1
        ORDER BY c.name ASC
        """,
        user_id,
    )


async def delete_city_pref(pool: asyncpg.Pool, user_id: str, city_id: str) -> None:
    """Retire la ville de la liste active de l'utilisateur — la ville reste dans le catalogue
    partagé (`deleteCity` ne touche jamais `cities`, seulement `user_city_prefs`)."""
    await pool.execute("DELETE FROM user_city_prefs WHERE user_id = $1 AND city_id = $2", user_id, city_id)


async def toggle_scannable(pool: asyncpg.Pool, user_id: str, city_id: str) -> bool:
    """Absence de ligne == non scannable (voir schema.sql) : le premier bascule crée la ligne à
    `true` (INSERT), un bascule suivant inverse la valeur existante (ON CONFLICT)."""
    row = await pool.fetchrow(
        """
        INSERT INTO user_city_prefs (user_id, city_id, active)
        VALUES ($1, $2, true)
        ON CONFLICT (user_id, city_id) DO UPDATE SET active = NOT user_city_prefs.active
        RETURNING active
        """,
        user_id, city_id,
    )
    return row["active"]


async def set_kijiji_radius(pool: asyncpg.Pool, user_id: str, city_id: str, radius_km: float | None) -> None:
    """`radius_km=None` efface le réglage (repli sur le défaut backend) — jamais `active`, qui
    doit rester intact si la ligne existe déjà, et à sa valeur par défaut (false) si elle est
    créée ici pour la première fois (voir commentaire schema.sql)."""
    await pool.execute(
        """
        INSERT INTO user_city_prefs (user_id, city_id, kijiji_radius_km)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, city_id) DO UPDATE SET kijiji_radius_km = EXCLUDED.kijiji_radius_km
        """,
        user_id, city_id, radius_km,
    )
