"""
Compare le scraper Facebook Marketplace en mode anonyme (production) et connecté (storage_state).

Lecture seule : réutilise FacebookScraper.scan_marketplace() tel quel, sans écriture en base ni
analyse IA. Les deux modes tournent avec la même requête, ville, budget et ordre de tri.

Prérequis : python -m backend.scripts.facebook_login_once  (génère la session connectée)

Usage :
    python -m backend.scripts.compare_fb_anon_vs_auth \
        --query guitare --city-id 123456789 --city-name "Saint-Bruno" \
        --allowed "saint-bruno,longueuil,boucherville" --min-price 0 --max-price 1500 --max-ads 40

--city-id : ID numérique Facebook de la ville (visible dans l'URL /marketplace/<ID>/).
--allowed : villes autorisées (liste blanche), séparées par des virgules ; sert à mesurer le
            remplissage hors zone. Vide = tout est accepté.
--runs    : nombre d'alternances anonyme/connecté (défaut 1) pour lisser la variabilité de Facebook.

Le rapport détaillé (IDs d'annonces seulement, aucun titre ni URL) est écrit dans
fb_compare_<horodatage>.json, ignoré par git (dépôt public).
"""
import sys
import json
import time
import argparse
import logging

sys.path.insert(0, '.')

from backend.scraping.core import FacebookScraper
from backend.scraping.config import ScraperConfig
from backend.scraping.parser import ListingParser

DEFAULT_STATE = "backend/scripts/facebook_storage_state.json"


def run_mode(label, storage_state, args, allowed, logger):
    cfg = ScraperConfig(storage_state_path=storage_state)
    scraper = FacebookScraper({}, {}, allowed_cities=allowed, config=cfg, logger=logger)
    scan_config = {
        "search_query": args.query, "location": args.city_id,
        "min_price": args.min_price, "max_price": args.max_price, "max_ads": args.max_ads,
    }
    t0 = time.time()
    try:
        res = scraper.scan_marketplace(scan_config)
    finally:
        scraper.close_session()
    deals = res["deals"]
    n = len(deals)
    return {
        "mode": label,
        "duration_s": round(time.time() - t0, 1),
        "anti_bot_blocked": res["anti_bot_blocked"],
        "total_cards_seen": res["total_cards_seen"],
        "rejected_out_of_list": res["rejected_out_of_list"],
        "dropped_no_location": res["dropped_no_location"],
        "dropped_no_price": res["dropped_no_price"],
        "kept": n,
        "kept_with_photos": sum(1 for d in deals if d.get("imageUrls")),
        "kept_with_description": sum(1 for d in deals if len(d.get("description") or "") > 80),
        "kept_with_gps": sum(1 for d in deals if d.get("latitude")),
        "kept_with_publish_date": sum(1 for d in deals if d.get("published_at_raw")),
        "avg_photos": round(sum(len(d.get("imageUrls") or []) for d in deals) / n, 2) if n else 0,
        "ids": [d["id"] for d in deals],
    }


def pct(part, whole):
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def print_table(rows):
    print(f"\n{'mode':<12}{'cartes':>8}{'hors zone':>11}{'sans prix':>11}{'gardées':>9}{'photos':>8}{'desc.':>8}{'GPS':>7}{'date':>7}{'bloqué':>8}{'durée':>8}")
    for r in rows:
        k = r["kept"]
        print(f"{r['mode']:<12}{r['total_cards_seen']:>8}"
              f"{r['rejected_out_of_list']:>5} ({pct(r['rejected_out_of_list'], r['total_cards_seen']):>4})"
              f"{r['dropped_no_price']:>11}{k:>9}"
              f"{pct(r['kept_with_photos'], k):>8}{pct(r['kept_with_description'], k):>8}"
              f"{pct(r['kept_with_gps'], k):>7}{pct(r['kept_with_publish_date'], k):>7}"
              f"{str(r['anti_bot_blocked']):>8}{r['duration_s']:>7}s")


def main():
    parser = argparse.ArgumentParser(description="Compare Facebook Marketplace anonyme vs connecté (lecture seule)")
    parser.add_argument("--query", required=True)
    parser.add_argument("--city-id", required=True, help="ID numérique Facebook de la ville")
    parser.add_argument("--allowed", default="", help="Villes autorisées, séparées par des virgules")
    parser.add_argument("--min-price", type=int, default=0)
    parser.add_argument("--max-price", type=int, default=1500)
    parser.add_argument("--max-ads", type=int, default=40)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--storage-state", default=DEFAULT_STATE)
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger = logging.getLogger("fb_compare")
    allowed = {ListingParser.normalize_city_name(c) for c in args.allowed.split(",") if c.strip()}

    rows = []
    for i in range(args.runs):
        print(f"\n=== Passage {i + 1}/{args.runs} ===")
        rows.append(run_mode("anonyme", None, args, allowed, logger))
        rows.append(run_mode("connecté", args.storage_state, args, allowed, logger))
        print_table(rows[-2:])

    if args.runs > 1:
        print("\n=== Tous les passages ===")
        print_table(rows)

    anon = {x for r in rows if r["mode"] == "anonyme" for x in r["ids"]}
    auth = {x for r in rows if r["mode"] == "connecté" for x in r["ids"]}
    print(f"\nAnnonces gardées : anonyme={len(anon)}  connecté={len(auth)}  "
          f"communes={len(anon & auth)}  seulement connecté={len(auth - anon)}  seulement anonyme={len(anon - auth)}")

    out = f"fb_compare_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"args": vars(args), "runs": rows}, f, ensure_ascii=False, indent=2)
    print(f"Rapport détaillé (IDs uniquement) : {out}")


if __name__ == "__main__":
    main()
