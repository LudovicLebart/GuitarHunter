"""
Audit des IDs de villes Facebook (table `cities`) : ouvre chaque /marketplace/<ID>/ en anonyme et
affiche le lieu que Facebook y associe, pour repérer un mauvais ID (ex. Bromont en France au lieu
de Bromont QC). Lecture seule, aucun compte requis.

Usage (DATABASE_URL exporté) :
    xvfb-run -a python -m backend.scripts.audit_fb_city_ids --user-id <UID>

Les libellés sont affichés pour relecture humaine ; la colonne `?` signale ceux qui ne contiennent
ni « QC » ni « Québec » ni « Quebec ». Aucune écriture, rien n'est sauvegardé.
"""
import sys
import time
import argparse
import logging

sys.path.insert(0, '.')

from playwright.sync_api import sync_playwright

from backend.scraping.config import ScraperConfig
from backend.scripts.compare_fb_anon_vs_auth import load_user_setup, _new_context

OK_MARKERS = ("qc", "québec", "quebec")


def location_label(page):
    """Texte du bouton de lieu (même sélecteur que FacebookScraper.get_city_id_and_coords)."""
    try:
        btn = page.locator("div[role='button']").filter(has_text="·").first
        if btn.count() > 0:
            return " ".join(btn.inner_text(timeout=5000).split())
    except Exception:
        pass
    try:
        return page.title()
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(description="Audit des IDs de villes Facebook (lecture seule)")
    parser.add_argument("--user-id")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    setup = load_user_setup(args.user_id)
    if setup is None:
        sys.exit(1)
    _, _, cities = setup

    cfg = ScraperConfig()
    print(f"{len(cities)} villes à vérifier\n")
    print(f"{'?':<2} {'nom en base':<28}{'ID Facebook':<18}libellé affiché par Facebook")
    with sync_playwright() as p:
        browser, context = _new_context(p, cfg)
        try:
            for c in sorted(cities, key=lambda x: x.get("name") or ""):
                page = context.new_page()
                try:
                    page.goto(f"https://www.facebook.com/marketplace/{c['id']}/", timeout=60000)
                    time.sleep(3)
                    label = location_label(page)
                except Exception as e:
                    label = f"(erreur: {str(e)[:60]})"
                finally:
                    page.close()
                flag = " " if any(m in label.lower() for m in OK_MARKERS) else "?"
                print(f"{flag:<2} {c.get('name', '?'):<28}{c['id']:<18}{label}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
