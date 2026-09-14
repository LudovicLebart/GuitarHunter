"""
Validation empirique (2026-08-24, suite à la discussion Fable sur le rayon/géométrie) : la
boucle actuelle sur les 22 villes configurées (une recherche Facebook complète par ville, voir
`bot.py::_run_facebook_scan()`) pourrait-elle être remplacée par 1-3 points d'ancrage, en
s'appuyant sur le rayon implicite (~40-65km, non documenté officiellement) que Facebook applique
déjà autour de la ville recherchée ?

AUCUNE requête Facebook ici — lecture seule sur `deals_index` (latitude/longitude déjà indexées,
`la`/`lo`, voir `repository.py::_update_deal_index`). Principe : sur les annonces DÉJÀ trouvées
par la boucle actuelle, quelle proportion tombe dans un rayon donné autour d'un ou plusieurs
points d'ancrage candidats ? Une couverture déjà très haute est un signal fort — mais pas une
preuve absolue : ce n'est qu'un point de départ, symétrique à un biais de la boucle actuelle
elle-même (une zone qu'elle n'a jamais bien couverte resterait un angle mort ici aussi).

Usage local (nécessite les credentials Firebase) :
    python3 backend/scripts/audit_anchor_coverage.py
"""
import sys
import os
import logging

sys.path.insert(0, os.getcwd())

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository
from backend.scraping.utils import calculate_distance

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("audit_anchor_coverage")

# Coordonnées reprises de backend/resources/city_coordinates.json — candidats d'ancrage à tester,
# pas une recommandation figée (à ajuster selon les résultats).
ANCHOR_CANDIDATES = {
    "Longueuil": (45.5369, -73.5105),
    "Saint-Bruno-de-Montarville": (45.5333, -73.3500),
}
# Balayage (2026-08-25, au lieu de 3 valeurs fixes devinées) — permet de repérer le
# PLATEAU de saturation (rayon au-delà duquel ajouter du rayon ne trouve plus aucune
# annonce supplémentaire), un signal plus fiable qu'un test de quelques valeurs isolées.
# Complémentaire (pas un remplacement) du signal direct "📏 Rayon observé" ajouté dans
# `bot.py::_run_facebook_scan()` — celui-ci vient de Facebook lui-même à chaque cycle,
# celui-ci est une lecture unique sur l'historique déjà indexé.
RADII_KM = list(range(20, 151, 5))


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
        snapshot = repo.get_deals_index_snapshot()

        # Kijiji exclu : ce n'est pas la boucle Facebook qu'on cherche à remplacer, et son
        # filtrage géographique fonctionne déjà différemment (voir locations.py).
        deals_with_coords = [
            (deal_id, d.get('la'), d.get('lo'), d.get('l'))
            for deal_id, d in snapshot.items()
            if d.get('la') is not None and d.get('lo') is not None and not deal_id.startswith('kijiji_')
        ]
        if not deals_with_coords:
            continue

        logger.info(f"--- user={user_id} : {len(deals_with_coords)} annonces Facebook avec coordonnées sur {len(snapshot)} au total ---")

        for anchor_name, (a_lat, a_lon) in ANCHOR_CANDIDATES.items():
            for radius in RADII_KM:
                covered = sum(
                    1 for _, la, lo, _ in deals_with_coords
                    if calculate_distance(a_lat, a_lon, la, lo) <= radius
                )
                pct = 100 * covered / len(deals_with_coords)
                logger.info(f"  Ancrage={anchor_name:<28} rayon={radius:>3}km -> {covered}/{len(deals_with_coords)} ({pct:.1f}%)")

        # Couverture COMBINÉE (union de tous les ancrages, ce qui compte réellement pour
        # décider s'ils remplacent la boucle 22 villes) + détection du PLATEAU de
        # saturation (2026-08-25) : le premier rayon à partir duquel élargir encore ne
        # trouve plus aucune annonce supplémentaire dans cet historique — un signal plus
        # fiable qu'un test de 3 valeurs fixes devinées pour choisir/recalibrer
        # `FACEBOOK_ANCHOR_RADIUS_KM` (`bot.py`).
        logger.info("  --- Couverture combinée (union de tous les ancrages) ---")
        combined_counts = []
        for radius in RADII_KM:
            covered = sum(
                1 for _, la, lo, _ in deals_with_coords
                if any(calculate_distance(a_lat, a_lon, la, lo) <= radius for a_lat, a_lon in ANCHOR_CANDIDATES.values())
            )
            combined_counts.append((radius, covered))
            pct = 100 * covered / len(deals_with_coords)
            logger.info(f"  Combiné rayon={radius:>3}km -> {covered}/{len(deals_with_coords)} ({pct:.1f}%)")

        plateau_radius = combined_counts[-1][0]
        for i in range(len(combined_counts) - 1, 0, -1):
            radius, covered = combined_counts[i]
            prev_radius, prev_covered = combined_counts[i - 1]
            if covered != prev_covered:
                break
            plateau_radius = prev_radius
        logger.info(f"  📈 Plateau de saturation : à partir de {plateau_radius}km, aucune annonce supplémentaire jusqu'à {RADII_KM[-1]}km testé.")

        max_radius = max(RADII_KM)
        missed_all = [
            (deal_id, loc) for deal_id, la, lo, loc in deals_with_coords
            if all(
                calculate_distance(a_lat, a_lon, la, lo) > max_radius
                for a_lat, a_lon in ANCHOR_CANDIDATES.values()
            )
        ]
        if missed_all:
            logger.info(f"  Hors de TOUS les ancrages même à {max_radius}km : {len(missed_all)} — ex: {missed_all[:8]}")
        else:
            logger.info(f"  Aucune annonce hors des ancrages, même au rayon max testé ({max_radius}km).")


if __name__ == "__main__":
    run()
