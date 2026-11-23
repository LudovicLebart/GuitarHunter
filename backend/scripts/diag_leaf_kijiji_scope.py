"""Mesure (lecture seule) : combien de Nissan Leaf proches du point de référence la recherche Kijiji ACTUELLE de Leaf voit-elle, comparée à
une recherche ANCRÉE par ville avec rayon (mécanique des guitares, `backend/scraping/kijiji/locations.py`) ?

    python -m backend.scripts.diag_leaf_kijiji_scope [--radius 150] [--pages 3]

N'écrit rien (ni base, ni fichier) et n'affiche que des NOMBRES : aucun titre, aucune URL, aucun identifiant d'annonce. Courtoisie : pause de
2 s entre requêtes, arrêt au premier 403/429. Sert à décider si la recherche ancrée vaut d'être adoptée (voir LEAF_HUNTER_PLAN.md)."""
import argparse
import sys

from backend.leaf import config as leaf_config
from backend.leaf.geo import calculate_distance
from backend.leaf.sources import BlockedError, extract_next_data, fetch_html, kijiji_autos
from backend.scraping.kijiji import locations as loc

CATEGORY_AUTOS = kijiji_autos.AUTOS_CATEGORY_ID


def collect(urls, label):
    """Annonces distinctes (par id) lues sur les pages `urls` ; arrêt propre sur blocage ou page vide."""
    found, info = {}, None
    for url in urls:
        try:
            html = fetch_html(url)
        except BlockedError as e:
            print(f"[{label}] bloqué, arrêt : {e}", file=sys.stderr)
            break
        except Exception as e:
            print(f"[{label}] erreur : {e}", file=sys.stderr)
            break
        page = kijiji_autos.parse_search_page(html)
        if info is None:
            data = extract_next_data(html) or {}
            info = (((data.get("props") or {}).get("pageProps") or {}).get("searchQuery") or {}).get("area")
        if not page:
            break
        for item in page:
            found[item["id"]] = item
    return found, info


def within(items, lat, lng, radius):
    out = {}
    for i, it in items.items():
        if it.get("latitude") is not None and it.get("longitude") is not None \
                and calculate_distance(lat, lng, it["latitude"], it["longitude"]) <= radius:
            out[i] = it
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--radius", type=int, default=leaf_config.DEFAULT_RADIUS_KM)
    ap.add_argument("--pages", type=int, default=3)
    args = ap.parse_args(argv)
    home = leaf_config.DEFAULT_HOME
    lat, lng = home["latitude"], home["longitude"]
    d = leaf_config.DEFAULT_SCAN if hasattr(leaf_config, "DEFAULT_SCAN") else {}
    min_price, max_price = 1500, 7500

    current_urls = [kijiji_autos.build_search_url(p, min_price, max_price) for p in range(1, args.pages + 1)]
    hubs = loc.build_resolvable_hubs(loc.load_location_lookup(), loc.load_city_coordinates())
    hub = loc.nearest_resolvable_hub(lat, lng, hubs)
    if not hub:
        print("Aucun point d'ancrage Kijiji résolu pour la ville de référence.")
        return 1
    anchored_urls = []
    for p in range(1, args.pages + 1):
        url = loc.build_search_url(CATEGORY_AUTOS, hub["id"], "nissan leaf", "autos-camions", hub["slug"], min_price, max_price,
                                   address=f"{home['name']}, QC", lat=lat, lng=lng, radius_km=args.radius)
        url = url.replace("/k0c", f"/page-{p}/k0c", 1) if p > 1 else url
        anchored_urls.append(url + ("&" if "?" in url else "?") + "sort=dateDesc")

    cur, cur_area = collect(current_urls, "actuelle")
    anc, anc_area = collect(anchored_urls, "ancrée")
    cur_near, anc_near = within(cur, lat, lng, args.radius), within(anc, lat, lng, args.radius)
    only_anchored = set(anc_near) - set(cur_near)
    only_current = set(cur_near) - set(anc_near)
    print(f"Point d'ancrage : lieu Kijiji id={hub['id']} ; rayon demandé {args.radius} km ; pages lues : {args.pages}")
    print(f"Recherche ACTUELLE (province, {len(current_urls)} pages max) : {len(cur)} annonces distinctes, dont {len(cur_near)} à {args.radius} km ou moins.")
    print(f"Recherche ANCRÉE (ville + rayon, {len(anchored_urls)} pages max) : {len(anc)} annonces distinctes, dont {len(anc_near)} à {args.radius} km ou moins.")
    print(f"Vues par l'ancrée et RATÉES par l'actuelle (dans le rayon) : {len(only_anchored)} ; l'inverse : {len(only_current)}.")
    print(f"Zone appliquée par Kijiji (searchQuery.area) — actuelle : {cur_area} ; ancrée : {anc_area}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
