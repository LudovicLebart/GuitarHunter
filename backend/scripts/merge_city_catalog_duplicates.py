"""
Fusion (2026-09-28) des doublons du catalogue `cities` (Postgres) diagnostiqués par
`backend/scripts/audit_city_catalog_duplicates.py` — 20 villes en double sur 50 entrées, un seul
schéma pour les 20 : une entrée à ID Facebook **numérique** (avec coordonnées réelles) et une
entrée à ID de type Firestore (alphanumérique, coordonnées `NULL`) — artefact de la migration
historique vers le catalogue partagé (`migrate_cities_to_shared_catalog.py`).

Règle de fusion, déterministe, sans aucun cas à trancher à la main : pour chaque paire partageant
la même clé canonique (`normalize_city_key`), on garde l'entrée dont l'`id` est purement
numérique (le vrai identifiant Facebook — invariant documenté dans `repository.py`/
`cities_repo.py`, `DocId = Facebook city ID`) et on supprime l'autre. Une paire qui ne suit PAS
ce schéma exact (pas exactement 2 entrées, ou aucune/les deux à ID numérique) est laissée de
côté avec un avertissement plutôt que fusionnée à l'aveugle — même principe de prudence que
`audit_cities.py::regions_conflict()`.

Par ville fusionnée, dans une seule transaction :
  1. Les préférences (`user_city_prefs`) de l'entrée supprimée sont réassignées vers l'entrée
     conservée (`ON CONFLICT` : `active` = OR des deux, `kijiji_radius_km` = celui déjà présent
     sur l'entrée conservée, sinon celui de l'entrée supprimée).
  2. L'entrée supprimée est supprimée de `cities` — `ON DELETE CASCADE` sur `user_city_prefs`
     retire alors automatiquement ses lignes de préférences désormais orphelines (déjà
     réassignées à l'étape 1, donc rien n'est perdu).

Idempotent : une fois fusionnée, une paire ne réapparaît plus dans le regroupement au run
suivant (plus qu'une seule entrée pour cette clé canonique) — sûr pour la double exécution
`dev` puis `master` de `run_once.py`. Support `--dry-run`.
"""
import sys
import os
import argparse
import logging
from collections import defaultdict

sys.path.insert(0, os.getcwd())

import config  # noqa: F401 -- charge .env (DATABASE_URL) via load_dotenv() à l'import
import psycopg
from psycopg.rows import dict_row
from backend.pg_db import DATABASE_URL
from backend.cities import normalize_city_key

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("merge_city_catalog_duplicates")


def run(dry_run=False):
    with psycopg.connect(DATABASE_URL, connect_timeout=10, row_factory=dict_row) as conn:
        cities = conn.execute("SELECT id, name FROM cities ORDER BY name ASC").fetchall()

        groups = defaultdict(list)
        for city in cities:
            groups[normalize_city_key(city["name"])].append(city)

        merged = 0
        skipped = 0
        for key, rows in sorted(groups.items()):
            if len(rows) < 2:
                continue
            numeric = [r for r in rows if r["id"].isdigit()]
            non_numeric = [r for r in rows if not r["id"].isdigit()]
            if len(rows) != 2 or len(numeric) != 1 or len(non_numeric) != 1:
                logger.warning(
                    f"⚠️ '{key}' -> {len(rows)} entrées ne suivant pas le schéma attendu "
                    f"(1 ID numérique + 1 non-numérique), laissée telle quelle : "
                    f"{[(r['id'], r['name']) for r in rows]}"
                )
                skipped += 1
                continue

            keep_id, drop_id = numeric[0]["id"], non_numeric[0]["id"]
            keep_name, drop_name = numeric[0]["name"], non_numeric[0]["name"]

            if dry_run:
                logger.info(f"[DRY-RUN] '{key}' : garder id={keep_id!r} ({keep_name!r}), "
                            f"fusionner puis supprimer id={drop_id!r} ({drop_name!r})")
                merged += 1
                continue

            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO user_city_prefs (user_id, city_id, active, kijiji_radius_km)
                    SELECT user_id, %(keep_id)s, active, kijiji_radius_km
                    FROM user_city_prefs WHERE city_id = %(drop_id)s
                    ON CONFLICT (user_id, city_id) DO UPDATE SET
                        active = user_city_prefs.active OR EXCLUDED.active,
                        kijiji_radius_km = COALESCE(user_city_prefs.kijiji_radius_km, EXCLUDED.kijiji_radius_km)
                    """,
                    {"keep_id": keep_id, "drop_id": drop_id},
                )
                conn.execute("DELETE FROM cities WHERE id = %(drop_id)s", {"drop_id": drop_id})

            logger.info(f"✅ '{key}' : conservé id={keep_id!r} ({keep_name!r}), "
                        f"fusionné et supprimé id={drop_id!r} ({drop_name!r})")
            merged += 1

    logger.info("=" * 78)
    logger.info(f"TOTAL : {merged} ville(s) {'à fusionner' if dry_run else 'fusionnées'}, "
                f"{skipped} groupe(s) laissé(s) de côté (schéma inattendu).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fusionne les doublons du catalogue de villes.")
    parser.add_argument('--dry-run', action='store_true', help="Compte et affiche sans rien écrire.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
