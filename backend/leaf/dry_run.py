"""Passage à blanc Leaf : lit Kijiji + AutoHebdo, applique filtres/règles/scores et AFFICHE le résultat.
N'écrit rien (ni base, ni fichier, ni notification).

    python -m backend.leaf.dry_run                        # budget par défaut
    python -m backend.leaf.dry_run --max-price 6000 --max-km 130000 --pages 2

Courtoisie : ≥ 2 s entre requêtes, arrêt immédiat sur 403/429.
"""
import argparse
import sys
from typing import Any, Dict, List

from backend.leaf import filters, pipeline
from backend.leaf.sources import BlockedError, fetch_html, autohebdo, kijiji_autos
from backend.leaf.sources.detail import DetailFetcher


def collect(years, min_price: int, max_price: int, pages: int, fetch=fetch_html) -> List[Dict[str, Any]]:
    raws: List[Dict[str, Any]] = []
    for p in range(1, pages + 1):
        try:
            found = kijiji_autos.parse_search_page(fetch(kijiji_autos.build_search_url(p, min_price, max_price)))
        except BlockedError as e:
            print(f"[kijiji] bloqué, arrêt : {e}", file=sys.stderr)
            break
        except Exception as e:  # réseau, HTML inattendu... : on continue avec les autres sources
            print(f"[kijiji] page {p} : {e}", file=sys.stderr)
            break
        raws += found
        if not found:
            break
    for year in years:
        try:
            raws += autohebdo.parse_results_page(fetch(autohebdo.build_search_url(year)), year)
        except BlockedError as e:
            print(f"[autohebdo] bloqué, arrêt : {e}", file=sys.stderr)
            break
        except Exception as e:
            print(f"[autohebdo] {year} : {e}", file=sys.stderr)
    return raws


def main(argv=None) -> int:
    d = filters.DEFAULT_CRITERIA
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--min-price", type=int, default=d["min_price"])
    ap.add_argument("--max-price", type=int, default=d["max_price"])
    ap.add_argument("--max-km", type=int, default=d["max_km"])
    ap.add_argument("--pages", type=int, default=2, help="pages de résultats Kijiji")
    ap.add_argument("--no-detail", action="store_true", help="ne lit pas les fiches (liste seulement)")
    args = ap.parse_args(argv)

    criteria = {"min_price": args.min_price, "max_price": args.max_price, "max_km": args.max_km}
    raws = collect(d["years"], args.min_price, args.max_price, args.pages)
    fetcher = None if args.no_detail else DetailFetcher()
    result = pipeline.evaluate_listings(raws, criteria, detail_fetcher=fetcher)
    print(f"{len(raws)} annonces lues : {len(result['kept'])} retenues, {len(result['rejected'])} rejetées "
          f"par les règles, {len(result['ignored'])} hors périmètre.")
    if fetcher:
        print(f"Fiches lues : {fetcher.fetched}, illisibles : {fetcher.failed}"
              + (" — site bloqué, arrêt des lectures." if fetcher.blocked else "") + ".")
    for a in result["kept"]:
        wf = a["winter_fit"]
        winter = f"{wf['low_km']}-{wf['high_km']} km" if wf["low_km"] else "?"
        km = f"{a['km']:,} km".replace(",", " ") if a.get("km") is not None else "km ?"
        soh = f"SOH {a['soh_announced']:.0f} %" if a.get("soh_announced") is not None else "SOH ?"
        print(f"\n{a['year']} Leaf {a['trim'] or '?'} — {a['price']} $ — {km} — {soh} — hiver {winter} "
              f"({wf['verdict']}) — {a['source']}")
        if a["risk_flags"] or a["duplicate_of"]:
            print("   " + " · ".join(a["risk_flags"] + (["doublon probable"] if a["duplicate_of"] else [])))
    for a in result["rejected"]:
        print(f"\n[rejetée] {a['year']} {a['price']} $ : {', '.join(a['reject_reasons'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
