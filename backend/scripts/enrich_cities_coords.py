"""
Script one-shot : enrichit les villes du catalogue partagé qui n'ont pas de coordonnées.

Utilise l'API Nominatim (OpenStreetMap) — gratuite, sans clé API.
Pour chaque ville sans latitude/longitude dans artifacts/{APP_ID}/cities/,
interroge Nominatim et écrit les coordonnées dans le catalogue (merge=True).

Usage :
  python -m backend.scripts.enrich_cities_coords            # Mode réel
  python -m backend.scripts.enrich_cities_coords --dry-run  # Simulation
  python -m backend.scripts.enrich_cities_coords --city-id 102183646490762  # Une seule ville
"""

import sys
import time
import argparse
import logging
import requests

sys.path.insert(0, '.')

from config import FIREBASE_KEY_PATH, APP_ID_TARGET
from backend.database import DatabaseService
from backend.scraping.utils import city_name_variants

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("enrich_cities_coords")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "GuitarHunter/1.0"}


def geocode(city_name: str) -> tuple[float, float] | None:
    """Retourne (lat, lon) via Nominatim, ou None.
    Essaie plusieurs variantes du nom (Mc X, Saint→St, accents, tirets...)."""
    for variant in city_name_variants(city_name):
        for suffix in [", Quebec, Canada", ", Canada"]:
            query = variant + suffix
            try:
                resp = requests.get(
                    NOMINATIM_URL,
                    params={"q": query, "format": "json", "limit": 1, "countrycodes": "ca"},
                    headers=NOMINATIM_HEADERS,
                    timeout=10,
                )
                resp.raise_for_status()
                results = resp.json()
                if results:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    logger.info(f"  Nominatim ({query!r}): lat={lat:.4f}, lon={lon:.4f}")
                    return lat, lon
            except Exception as e:
                logger.warning(f"  Nominatim erreur pour {query!r}: {e}")
            time.sleep(1)
    return None


def enrich(dry_run: bool, only_city_id: str | None):
    logger.info(f"Initialisation Firebase (APP_ID={APP_ID_TARGET})")
    db_service = DatabaseService(FIREBASE_KEY_PATH)
    db = db_service.db

    shared_cities_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('cities')
    all_docs = list(shared_cities_ref.stream())
    logger.info(f"{len(all_docs)} villes dans le catalogue partage.")

    to_enrich = []
    for doc in all_docs:
        data = doc.to_dict()
        if only_city_id and doc.id != only_city_id:
            continue
        if data.get('latitude') is None or data.get('longitude') is None:
            to_enrich.append((doc.id, data))

    if not to_enrich:
        logger.info("Toutes les villes ont deja des coordonnees. Rien a faire.")
        return

    logger.info(f"{len(to_enrich)} ville(s) sans coordonnees a enrichir.\n")

    enriched = 0
    failed = 0

    for city_doc_id, city_data in to_enrich:
        city_name = city_data.get('name', city_doc_id)
        logger.info(f"--- {'[DRY-RUN] ' if dry_run else ''}Ville: {city_name} (id={city_doc_id}) ---")

        if dry_run:
            logger.info(f"  Interrogerait Nominatim pour '{city_name}'.")
            enriched += 1
            continue

        coords = geocode(city_name)
        if coords:
            lat, lon = coords
            shared_cities_ref.document(city_doc_id).set(
                {'latitude': lat, 'longitude': lon},
                merge=True
            )
            logger.info(f"  Ecrit dans Firestore.")
            enriched += 1
        else:
            logger.warning(f"  Aucune coordonnee trouvee pour '{city_name}'.")
            failed += 1

        time.sleep(1)  # Rate-limit Nominatim

    logger.info(f"\n{'[DRY-RUN] ' if dry_run else ''}Termine : {enriched} enrichies, {failed} echecs.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enrichit les coordonnees des villes via Nominatim.')
    parser.add_argument('--dry-run', action='store_true', help='Simulation sans ecriture.')
    parser.add_argument('--city-id', default=None, help='Traiter uniquement ce docId Firestore.')
    args = parser.parse_args()
    enrich(dry_run=args.dry_run, only_city_id=args.city_id)
