"""
Audit (2026-09-27, suite à un signalement UI : la liste de villes du ConfigPanel affiche des
doublons/triplons, ex: "Boucherville" ou "Bromont" apparaissant deux fois) du catalogue partagé
`cities` (Postgres, table lue par `GET /cities` -> `useCities.js` -> `ConfigPanel.jsx`).

AUCUNE écriture — lecture seule sur `cities` + `user_city_prefs`. Regroupe les lignes par clé
canonique (`backend/cities.py::normalize_city_key`, la même fonction que côté stats — insensible
aux accents/casse/tirets/abréviations Saint-St) et affiche, pour chaque groupe en double, de quoi
décider quelle ligne garder : id, coordonnées, date de création, et combien d'utilisateurs l'ont
active dans `user_city_prefs`.

Cause probable (à confirmer par ce script) : `bot.py::add_city_auto()` ne dédoublonne que sur un
`name.lower()` exact — les entrées migrées historiquement depuis les anciennes collections
per-user (`backend/scripts/migrate_cities_to_shared_catalog.py`, architecture catalogue partagé)
ont pu préserver plusieurs `city_id` Facebook distincts pour un même nom de ville. Ne fusionne
RIEN automatiquement : une fusion réassigne des `user_city_prefs` et supprime des lignes
`cities`, irréversible — décision à prendre à la main une fois ce rapport lu.

Depuis cet environnement de dev (aucun accès Postgres prod) : armer via `backend/scripts/run_once.py`.
"""
import sys
import os
import logging
from collections import defaultdict

sys.path.insert(0, os.getcwd())

import config  # noqa: F401 -- charge .env (DATABASE_URL) via load_dotenv() à l'import
from backend.pg_db import init_pool
from backend.cities import normalize_city_key

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("audit_city_catalog_duplicates")


def run():
    pool = init_pool()

    with pool.connection() as conn:
        cities = conn.execute(
            "SELECT id, name, latitude, longitude, created_at, created_by FROM cities ORDER BY name ASC"
        ).fetchall()
        prefs = conn.execute(
            "SELECT city_id, user_id FROM user_city_prefs WHERE active = true"
        ).fetchall()

    active_users_by_city = defaultdict(list)
    for pref in prefs:
        active_users_by_city[pref["city_id"]].append(pref["user_id"])

    groups = defaultdict(list)
    for city in cities:
        groups[normalize_city_key(city["name"])].append(city)

    duplicates = {key: rows for key, rows in groups.items() if len(rows) > 1}

    logger.info(f"{len(cities)} ville(s) au catalogue | {len(groups)} clé(s) canonique(s) | "
                f"{len(duplicates)} clé(s) en double/triple.")
    logger.info("=" * 78)

    for key, rows in sorted(duplicates.items()):
        logger.warning(f"⚠️ '{key}' -> {len(rows)} entrées :")
        for row in sorted(rows, key=lambda r: r["created_at"]):
            active_users = active_users_by_city.get(row["id"], [])
            logger.warning(
                f"    id={row['id']!r} name={row['name']!r} "
                f"lat/lon=({row['latitude']}, {row['longitude']}) "
                f"created_at={row['created_at']} created_by={row['created_by']!r} "
                f"-- {len(active_users)} user(s) actif(s): {[u[:8] for u in active_users]}"
            )

    logger.info("=" * 78)
    logger.info(f"TOTAL : {len(duplicates)} ville(s) à dédoublonner manuellement.")


if __name__ == "__main__":
    run()
