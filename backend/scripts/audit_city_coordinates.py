"""
Diagnostic (2026-08-25, suite à la découverte de coordonnées françaises pour "Saint-Lambert"
dans un scan Kijiji en production) : vérifie les coordonnées de TOUTES les villes configurées
(catalogue partagé + fallback legacy, voir `repository.py::get_cities()`) pour repérer d'autres
cas de géocodage erroné vers un homonyme hors Amérique du Nord (même piège que "Beloeil"
Québec/Wallonie déjà documenté, mais ici sur "Saint-Lambert" Québec/France).

AUCUNE requête réseau — lecture seule sur Firestore (le catalogue de villes déjà stocké).

Usage local (nécessite les credentials Firebase) :
    python3 backend/scripts/audit_city_coordinates.py

Depuis cet environnement de dev (aucun accès Firestore) : armer via `backend/scripts/run_once.py`.
"""
import sys
import os
import logging

sys.path.insert(0, os.getcwd())

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("audit_city_coordinates")

# Boîte englobante généreuse pour l'est de l'Amérique du Nord (Québec + voisinage direct :
# Ontario, provinces maritimes, nord des États-Unis) — pas une frontière précise, juste large
# assez pour ne jamais flaguer une vraie ville configurée par erreur, tout en attrapant un
# homonyme géocodé en Europe (comme "Saint-Lambert" -> France, longitude proche de 0).
LAT_RANGE = (40.0, 55.0)
LON_RANGE = (-85.0, -55.0)


def run():
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"{len(users)} utilisateur(s).")

    for user_doc in users:
        user_id = user_doc.id
        repo = FirestoreRepository(db_client, APP_ID_TARGET, user_id)
        cities = repo.get_cities()
        if not cities:
            continue

        logger.info(f"--- user={user_id} : {len(cities)} ville(s) scannable(s) ---")
        suspicious = []
        for city in cities:
            lat = city.get('latitude')
            lon = city.get('longitude')
            name = city.get('name', '?')
            if lat is None or lon is None:
                logger.warning(f"  ⚠️ '{name}' sans coordonnées (latitude/longitude absentes).")
                continue
            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
                suspicious.append((name, lat, lon))

        if suspicious:
            logger.warning(f"  🚨 {len(suspicious)} ville(s) avec des coordonnées hors zone attendue :")
            for name, lat, lon in suspicious:
                logger.warning(f"     '{name}' -> lat={lat}, lon={lon} (hors [{LAT_RANGE}]/[{LON_RANGE}])")
        else:
            logger.info("  Aucune coordonnée suspecte détectée.")


if __name__ == "__main__":
    run()
