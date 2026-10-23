"""
Compare l'ID Facebook d'une ville en base (`cities.id`) à celui que `CityFinder` (celui du flux
d'ajout de ville, avec `region_hint`) retrouve aujourd'hui. Anonyme, lecture seule : aucune
écriture en base, rien n'est modifié.

Usage (DATABASE_URL exporté pour comparer à la base ; sinon seul l'ID retrouvé est affiché) :
    xvfb-run -a python -m backend.scripts.list_fb_city_candidates --names "Bromont,Beloeil"
    xvfb-run -a python -m backend.scripts.list_fb_city_candidates --user-id <UID> --all

--region : indice de région passé à CityFinder (défaut « Québec »).
--all    : toutes les villes actives de l'utilisateur.
Statut : OK (même ID), DIFF (ID différent), SANS-INDICE (aucune suggestion ne correspond à la
région : CityFinder est retombé sur la première, résultat à ne pas croire).
"""
import re
import sys
import time
import argparse
import logging

sys.path.insert(0, '.')

from backend.scraping.core import FacebookScraper
from backend.scraping.config import ScraperConfig
from backend.scraping.city_finder import CityFinder
from backend.scraping.parser import ListingParser


def explore(scraper, name, pick=None):
    """Ouvre le sélecteur de lieu (mêmes sélecteurs que CityFinder) et tape `name`.
    pick=None : retourne le texte de TOUTES les suggestions.
    pick=i    : clique la suggestion i, applique, et retourne (id ou alias lu dans l'URL, libellé)."""
    scraper._ensure_session()
    page = scraper.context.new_page()
    try:
        page.goto("https://www.facebook.com/marketplace/", timeout=30000)
        scraper._close_login_popup(page)
        btn = page.locator("div[role='button']").filter(has_text=re.compile(r"\d+\s*(km|mi)", re.IGNORECASE)).first
        if not btn.is_visible(timeout=5000):  # même repli que CityFinder
            btn = page.locator("div[aria-label*='Lieu'], div[aria-label*='Location'], div[aria-label*='Lugar']").first
        btn.click(force=True, timeout=10000)
        page.wait_for_selector("div[role='dialog']", timeout=8000)
        field = page.locator("input[aria-label='Lieu'], input[aria-label='Location'], input[placeholder*='Lieu'], input[placeholder*='Location']").first
        field.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        field.fill(name)
        time.sleep(3)
        options = page.locator("div[role='option']").all()
        labels = [" | ".join(o.inner_text().split("\n")) for o in options]
        if pick is None:
            return labels
        options[pick].click()
        time.sleep(0.5)
        page.locator("div[aria-label='Appliquer'], div[aria-label='Apply']").first.click()
        page.wait_for_url(re.compile(r"/marketplace/.*?/"), timeout=10000)
        seg = page.url.split("/marketplace/")[1].split("/")[0]
        return seg, labels[pick]
    except Exception as e:
        return [f"(erreur: {str(e)[:80]})"] if pick is None else ("?", f"(erreur: {str(e)[:80]})")
    finally:
        page.close()


def main():
    parser = argparse.ArgumentParser(description="ID Facebook en base vs CityFinder (lecture seule)")
    parser.add_argument("--names", help="Noms séparés par des virgules")
    parser.add_argument("--all", action="store_true", help="Toutes les villes actives de l'utilisateur")
    parser.add_argument("--user-id")
    parser.add_argument("--region", default="Québec")
    parser.add_argument("--try-all", action="store_true",
                        help="Clique chaque suggestion et affiche son ID (puis tester chaque ID avec compare_fb_anon_vs_auth --anon-only --city-id)")
    args = parser.parse_args()
    if not args.names and not args.all:
        parser.error("--names ou --all est requis")

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger = logging.getLogger("fb_city_candidates")

    db_ids = {}
    names = [n.strip() for n in (args.names or "").split(",") if n.strip()]
    if args.all or args.user_id:
        from backend.scripts.compare_fb_anon_vs_auth import load_user_setup
        setup = load_user_setup(args.user_id)
        if setup is None:
            sys.exit(1)
        for c in setup[2]:
            db_ids[ListingParser.normalize_city_name(c["name"])] = str(c["id"])
        if args.all:
            names = sorted(c["name"] for c in setup[2])

    scraper = FacebookScraper({}, {}, config=ScraperConfig(), logger=logger)
    if args.try_all:
        try:
            for name in names:
                found = explore(scraper, name)
                if not found or found[0].startswith("(erreur"):
                    print(f"\n=== {name} : échec du sélecteur de lieu {found[:1]} ===")
                    continue
                n = len(found)
                print(f"\n=== {name} : {n} suggestion(s) ===")
                for i, lab in enumerate(found, 1):
                    print(f"  libellé {i}: {lab}")
                for i in range(n):
                    cid, label = explore(scraper, name, pick=i)
                    print(f"  suggestion {i + 1}: ID={cid:<18} {label}")
        finally:
            scraper.close_session()
        return

    print(f"{'statut':<12}{'ville':<28}{'ID base':<22}{'ID CityFinder':<22}suggestion retenue")
    try:
        for name in names:
            try:
                found_id, _, label, confident = CityFinder.find_city_id_and_coords(scraper, name, region_hint=args.region)
            except Exception as e:
                found_id, label, confident = None, f"(erreur: {str(e)[:60]})", False
            for i, opt in enumerate(explore(scraper, name), 1):
                print(f"   suggestion {i}: {opt}")
            db_id = db_ids.get(ListingParser.normalize_city_name(name), "-")
            if not found_id:
                status = "ÉCHEC"
            elif not confident:
                status = "SANS-INDICE"
            elif db_id == "-":
                status = "?"
            else:
                status = "OK" if db_id == str(found_id) else "DIFF"
            print(f"{status:<12}{name:<28}{db_id:<22}{str(found_id):<22}{' '.join((label or '').split())}")
    finally:
        scraper.close_session()


if __name__ == "__main__":
    main()
