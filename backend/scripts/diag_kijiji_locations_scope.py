"""
Script de diagnostic one-shot : vérifie si https://www.kijiji.ca/j-locations.json?q=<X>
filtre réellement par province, ou renvoie systématiquement le même arbre (une seule
province fixe, ou pancanadien) quel que soit `q`.

Compare deux requêtes (q=Quebec et q=Ontario par défaut) sur trois signaux :
  1. Nombre total de lieux terminaux (leaf) trouvés dans chaque réponse.
  2. Valeurs distinctes de `regionLabel` (le champ qui étiquette la province de chaque
     région, ex: "Québec" — vu dans la réponse q=Quebec du 2026-07-26) rencontrées dans
     chaque réponse.
  3. Présence de villes caractéristiques de l'autre province (ex: "Toronto" dans la
     réponse "Quebec", "Longueuil"/"Montréal" dans la réponse "Ontario").

Si les deux réponses ont le même nombre de lieux et les mêmes regionLabel, q= ne filtre
pas réellement — mieux vaut le savoir avant de baser fetch_kijiji_locations.py dessus.

Usage :
    python -m backend.scripts.diag_kijiji_locations_scope
    python -m backend.scripts.diag_kijiji_locations_scope --province-a Quebec --province-b "British Columbia"
"""
import sys
import argparse
import logging

import requests

sys.path.insert(0, '.')
from backend.scraping.kijiji.locations import parse_locations_response

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("diag_kijiji_locations_scope")

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Villes emblématiques pour repérer si l'autre province apparaît dans une réponse censée
# être filtrée.
_QUEBEC_MARKERS = ["Montréal", "Longueuil", "Québec", "Laval", "Sherbrooke"]
_ONTARIO_MARKERS = ["Toronto", "Ottawa", "Hamilton", "Mississauga", "London"]


def _collect_stats(tree):
    """Parcourt tout l'arbre (régions ET feuilles, contrairement à
    locations.flatten_locations_tree qui ne garde que les feuilles) pour ce diagnostic —
    on a besoin des regionLabel des régions, pas seulement des villes terminales."""
    leaf_count = 0
    region_labels = set()
    all_names = set()

    def _walk(node):
        nonlocal leaf_count
        if not isinstance(node, dict):
            return
        if node.get("regionLabel"):
            region_labels.add(node["regionLabel"])
        for name_key in ("nameEn", "nameFr"):
            if node.get(name_key):
                all_names.add(node[name_key])
        if node.get("leaf"):
            leaf_count += 1
        for child in node.get("children") or []:
            _walk(child)

    _walk(tree)
    return {"leaf_count": leaf_count, "region_labels": region_labels, "all_names": all_names}


def _fetch(query: str):
    url = f"https://www.kijiji.ca/j-locations.json?q={query}"
    logger.info(f"Téléchargement : {url}")
    response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=30)
    response.raise_for_status()
    return parse_locations_response(response.text)


def main():
    parser = argparse.ArgumentParser(description="Vérifie si j-locations.json filtre réellement par province.")
    parser.add_argument("--province-a", default="Quebec")
    parser.add_argument("--province-b", default="Ontario")
    args = parser.parse_args()

    stats_a = _collect_stats(_fetch(args.province_a))
    stats_b = _collect_stats(_fetch(args.province_b))

    print(f"\n--- q={args.province_a} ---")
    print(f"Lieux terminaux : {stats_a['leaf_count']}")
    print(f"regionLabel rencontrés : {sorted(stats_a['region_labels'])}")
    found_ontario_markers = [m for m in _ONTARIO_MARKERS if m in stats_a["all_names"]]
    print(f"Villes ontariennes trouvées dedans : {found_ontario_markers or 'aucune'}")

    print(f"\n--- q={args.province_b} ---")
    print(f"Lieux terminaux : {stats_b['leaf_count']}")
    print(f"regionLabel rencontrés : {sorted(stats_b['region_labels'])}")
    found_quebec_markers = [m for m in _QUEBEC_MARKERS if m in stats_b["all_names"]]
    print(f"Villes québécoises trouvées dedans : {found_quebec_markers or 'aucune'}")

    print("\n=== Verdict ===")
    same_content = stats_a["leaf_count"] == stats_b["leaf_count"] and stats_a["region_labels"] == stats_b["region_labels"]
    if same_content:
        print("⚠️  Les deux réponses ont le même contenu (même nombre de lieux, mêmes regionLabel).")
        print(f"   -> q= NE FILTRE PAS réellement : l'arbre retourné semble toujours le même,")
        print(f"      quel que soit q= ({args.province_a} et {args.province_b} donnent un résultat identique).")
    elif found_ontario_markers or found_quebec_markers:
        print("⚠️  Contamination croisée détectée (une réponse contient des villes de l'autre province).")
        print("   -> q= filtre partiellement, ou retourne plus que la province demandée.")
    else:
        print(f"✅ q= filtre bien par province : '{args.province_a}' et '{args.province_b}' sont deux ensembles disjoints de lieux.")


if __name__ == "__main__":
    main()
