"""
Script one-shot : télécharge et aplatit l'arbre COMPLET de lieux Kijiji (tout le
Canada) en lookup ville -> ID de lieu utilisable par KijijiScraper.

Kijiji publie un arbre statique via `https://www.kijiji.ca/j-locations.json`. Le
paramètre `q` (ex: `?q=Quebec`) a d'abord semblé filtrer par province, mais un
diagnostic comparatif (`diag_kijiji_locations_scope.py`) puis une vérification directe
(recherche de l'ID de Toronto, 1700273, dans la réponse) ont confirmé le 2026-07-26 que
`q` ne filtre en réalité rien : la réponse est toujours l'arbre complet, pour tout le
Canada, peu importe `q`. Une seule requête suffit donc à couvrir toutes les villes,
sans avoir à automatiser un sélecteur de lieu ni à interroger province par province.

Usage :
  python -m backend.scripts.fetch_kijiji_locations
  python -m backend.scripts.fetch_kijiji_locations --output backend/resources/kijiji_locations_backup.json
"""
import sys
import argparse
import json
import logging

import requests

sys.path.insert(0, '.')
from backend.scraping.kijiji.locations import (
    parse_locations_response,
    flatten_locations_tree,
    build_location_lookup,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("fetch_kijiji_locations")

_DEFAULT_OUTPUT = "backend/resources/kijiji_locations.json"
_URL = "https://www.kijiji.ca/j-locations.json"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def main():
    parser = argparse.ArgumentParser(description="Télécharge et aplatit l'arbre complet de lieux Kijiji (tout le Canada).")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help=f"Chemin du fichier de sortie (défaut: {_DEFAULT_OUTPUT})")
    args = parser.parse_args()

    logger.info(f"Téléchargement : {_URL}")
    response = requests.get(_URL, headers={"User-Agent": _USER_AGENT}, timeout=30)
    response.raise_for_status()

    tree = parse_locations_response(response.text)
    leaves = flatten_locations_tree(tree)
    lookup = build_location_lookup(leaves)

    logger.info(f"{len(leaves)} lieu(x) terminal(aux) trouvé(s), {len(lookup)} clé(s) de recherche générée(s).")
    if not leaves:
        logger.error("❌ Aucun lieu terminal trouvé — la réponse est-elle bien celle attendue ? (voir parse_locations_response)")
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(lookup, f, ensure_ascii=False, indent=2, sort_keys=True)

    logger.info(f"✅ Écrit dans {args.output}")


if __name__ == "__main__":
    main()
