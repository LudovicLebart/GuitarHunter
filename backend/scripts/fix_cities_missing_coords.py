"""
Correction (2026-10-05) des villes du catalogue partagé `cities` (Postgres) sans coordonnées.

Symptôme : le scan Facebook ignore la ville (« Données incomplètes pour la ville Chambly »,
`bot.py`) et le scan Kijiji échoue à l'ancrage (« Impossible d'ancrer la recherche Kijiji pour
'McMasterville' … lat/lng fourni(s) : False », `scraping/kijiji/core.py`).

Pour chaque ville avec `latitude` ou `longitude` NULL :
  1. coordonnées connues dans `backend/resources/city_coordinates.json` (clé normalisée par
     `normalize_city_key`, donc insensible aux accents/tirets/Saint-St) ;
  2. sinon Nominatim (Québec puis Canada), et la ville est alors marquée `needs_review` (une
     devinette géocodée en aveugle doit être vérifiée, voir `bot.py::add_city_auto`).
Ne touche QUE les villes sans coordonnées et uniquement `latitude`/`longitude`/`needs_review` ;
idempotent (une ville corrigée ne ressort plus de la requête). Une ville introuvable est laissée
telle quelle et listée en fin de rapport.

Usage :
  python -m backend.scripts.fix_cities_missing_coords --dry-run   # rapport seul, aucune écriture
  python -m backend.scripts.fix_cities_missing_coords             # applique
En production : via `backend/scripts/run_once.py` (aucun accès Postgres prod depuis le dev).
Connexion directe `psycopg.connect(connect_timeout=10)`, comme `audit_city_catalog_duplicates.py`.
"""
import sys
import os
import json
import time
import argparse
import logging

sys.path.insert(0, os.getcwd())

import requests

from backend.cities import normalize_city_key

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("fix_cities_missing_coords")

COORDS_FILE = os.path.join(os.path.dirname(__file__), "..", "resources", "city_coordinates.json")
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "GuitarHunter/1.0"}


def load_known_coords(path=COORDS_FILE):
    """{clé normalisée: (lat, lon)} depuis `city_coordinates.json` (clés `lat`/`lng`)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {normalize_city_key(k): (v["lat"], v["lng"]) for k, v in raw.items()}


def geocode_nominatim(city_name):
    """(lat, lon) du 1er résultat Nominatim au Canada (Québec d'abord), ou None."""
    for suffix in (", Quebec, Canada", ", Canada"):
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": city_name.split(',')[0].strip() + suffix, "format": "json",
                        "limit": 1, "countrycodes": "ca"},
                headers=NOMINATIM_HEADERS, timeout=10,
            )
            resp.raise_for_status()
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception as e:
            logger.warning(f"  Nominatim erreur pour {city_name!r}{suffix}: {e}")
        time.sleep(1)  # politique d'usage Nominatim : 1 requête/s
    return None


def resolve_coords(name, known):
    """Retourne (lat, lon, source) avec source in {'fichier', 'nominatim'}, ou None."""
    coords = known.get(normalize_city_key(name))
    if coords:
        return coords[0], coords[1], "fichier"
    coords = geocode_nominatim(name)
    if coords:
        return coords[0], coords[1], "nominatim"
    return None


def run(dry_run=False):
    import psycopg
    from psycopg.rows import dict_row
    from backend.pg_db import DATABASE_URL

    known = load_known_coords()
    fixed, unresolved = [], []
    with psycopg.connect(DATABASE_URL, connect_timeout=10, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT id, name FROM cities WHERE latitude IS NULL OR longitude IS NULL ORDER BY name"
        ).fetchall()
        logger.info(f"{len(rows)} ville(s) sans coordonnées complètes dans le catalogue.")
        for row in rows:
            res = resolve_coords(row["name"], known)
            if res is None:
                unresolved.append(row)
                logger.warning(f"  ✗ {row['name']} (id={row['id']}) : coordonnées introuvables.")
                continue
            lat, lon, source = res
            logger.info(f"  ✓ {row['name']} (id={row['id']}) <- {source}: {lat:.4f}, {lon:.4f}"
                        f"{' [dry-run]' if dry_run else ''}")
            fixed.append((row, source))
            if not dry_run:
                conn.execute(
                    "UPDATE cities SET latitude = %s, longitude = %s, "
                    "needs_review = needs_review OR %s WHERE id = %s",
                    (lat, lon, source == "nominatim", row["id"]),
                )
        if not dry_run:
            conn.commit()
    logger.info(f"Bilan : {len(fixed)} corrigée(s), {len(unresolved)} introuvable(s)"
                f"{' (dry-run : rien écrit)' if dry_run else ''}.")
    return fixed, unresolved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="rapport seul, aucune écriture")
    run(dry_run=parser.parse_args().dry_run)
