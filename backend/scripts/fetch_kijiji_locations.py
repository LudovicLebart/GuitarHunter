"""
Script one-shot : télécharge et aplatit l'arbre de lieux Kijiji pour une ou plusieurs
provinces, en lookup ville -> ID de lieu utilisable par KijijiScraper.

Kijiji publie un arbre statique et complet de tous ses lieux (province > région > ville)
via `https://www.kijiji.ca/j-locations.json?q=<province>`. Le paramètre `q` filtre par
nom de PROVINCE, pas par ville (confirmé en test live du 2026-07-26 : `q=Quebec` retourne
tout l'arbre de la province de Québec, `q=Ontario` tout l'Ontario). GuitarHunter ne scanne
actuellement que des villes du Québec (voir `backend/resources/city_coordinates.json`),
d'où le défaut `--province Quebec` — une seule requête suffit à couvrir toutes les villes
pertinentes pour l'app aujourd'hui. Pour élargir plus tard à d'autres provinces, il suffit
de relancer ce script avec plusieurs `--province` : aucun changement requis côté
`KijijiScraper`, qui lit le même fichier ressource quel que soit son contenu.

Usage :
  python -m backend.scripts.fetch_kijiji_locations
  python -m backend.scripts.fetch_kijiji_locations --province Quebec Ontario
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
    parser = argparse.ArgumentParser(description="Télécharge et aplatit l'arbre de lieux Kijiji pour une ou plusieurs provinces.")
    parser.add_argument("--province", nargs="+", default=["Quebec"], help="Nom(s) de province(s) à récupérer, séparés par des espaces (défaut: Quebec)")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help=f"Chemin du fichier de sortie (défaut: {_DEFAULT_OUTPUT})")
    args = parser.parse_args()

    combined_lookup = {}
    total_leaves = 0

    for province in args.province:
        url = f"https://www.kijiji.ca/j-locations.json?q={province}"
        logger.info(f"Téléchargement : {url}")

        response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=30)
        response.raise_for_status()

        tree = parse_locations_response(response.text)
        leaves = flatten_locations_tree(tree)
        if not leaves:
            logger.warning(f"⚠️ Aucun lieu terminal trouvé pour '{province}' — nom de province mal orthographié ?")
            continue

        total_leaves += len(leaves)
        province_lookup = build_location_lookup(leaves)
        for key, value in province_lookup.items():
            combined_lookup.setdefault(key, value)
        logger.info(f"   {province}: {len(leaves)} lieu(x) terminal(aux).")

    logger.info(f"{total_leaves} lieu(x) au total, {len(combined_lookup)} clé(s) de recherche générée(s).")
    if not combined_lookup:
        logger.error("❌ Aucun lieu trouvé pour aucune des provinces demandées — la réponse est-elle bien celle attendue ? (voir parse_locations_response)")
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(combined_lookup, f, ensure_ascii=False, indent=2, sort_keys=True)

    logger.info(f"✅ Écrit dans {args.output}")


if __name__ == "__main__":
    main()
