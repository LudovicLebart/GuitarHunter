"""
Script one-shot : télécharge et aplatit l'arbre de lieux Kijiji pour une province, en
lookup ville -> ID de lieu utilisable par KijijiScraper.

Kijiji publie un arbre statique et complet de tous ses lieux (province > région > ville)
via `https://www.kijiji.ca/j-locations.json?q=<province>`. Le paramètre `q` filtre par
nom de PROVINCE, pas par ville (confirmé en test live du 2026-07-26 : `q=Quebec` retourne
tout l'arbre de la province de Québec, `q=Ontario` tout l'Ontario). GuitarHunter ne scanne
actuellement que des villes du Québec (voir `backend/resources/city_coordinates.json`),
d'où le défaut `--province Quebec` — une seule requête suffit à couvrir toutes les villes
pertinentes pour l'app, sans jamais avoir à automatiser un sélecteur de lieu.

Usage :
  python -m backend.scripts.fetch_kijiji_locations
  python -m backend.scripts.fetch_kijiji_locations --province Ontario --output backend/resources/kijiji_locations_ontario.json
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
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def main():
    parser = argparse.ArgumentParser(description="Télécharge et aplatit l'arbre de lieux Kijiji pour une province.")
    parser.add_argument("--province", default="Quebec", help="Nom de la province à récupérer (défaut: Quebec)")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help=f"Chemin du fichier de sortie (défaut: {_DEFAULT_OUTPUT})")
    args = parser.parse_args()

    url = f"https://www.kijiji.ca/j-locations.json?q={args.province}"
    logger.info(f"Téléchargement : {url}")

    response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=30)
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
