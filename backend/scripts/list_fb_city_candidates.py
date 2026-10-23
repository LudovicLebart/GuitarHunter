"""
Liste, pour un ou plusieurs noms de villes, TOUTES les suggestions du sélecteur de lieu Facebook
Marketplace avec l'ID associé à chacune (anonyme, lecture seule, rien n'est écrit).

Sert à repérer le bon ID quand `FacebookScraper.get_city_id_and_coords()` — qui clique sur la
PREMIÈRE suggestion sans vérifier la région — a retenu la mauvaise ville (ex. Bromont en France).

Usage :
    xvfb-run -a python -m backend.scripts.list_fb_city_candidates --names "Bromont,Beloeil"
    xvfb-run -a python -m backend.scripts.list_fb_city_candidates --names "Bromont" --suffix ", Québec"

--suffix est ajouté au nom tapé dans le champ de lieu (défaut : aucun, pour voir ce que voit le bot).
Les suggestions contenant « Québec », « Quebec » ou « QC » sont marquées d'une flèche.
"""
import re
import sys
import time
import argparse

sys.path.insert(0, '.')

from playwright.sync_api import sync_playwright

from backend.scraping.config import ScraperConfig
from backend.scripts.compare_fb_anon_vs_auth import _new_context

INPUT_SEL = "input[aria-label='Lieu'], input[aria-label='Location'], input[placeholder='Rechercher un lieu']"
OPTION_SEL = "ul[role='listbox'] li, div[role='option']"
QC_MARKERS = ("québec", "quebec", ", qc")


START_URL = "https://www.facebook.com/marketplace/110035235685771/"  # page à ID : le bouton de lieu y existe (audit)


def diagnose(page):
    """Texte seulement (pas d'image) : de quoi adapter les sélecteurs si Facebook a changé."""
    print(f"  [diag] url={page.url}")
    try:
        print(f"  [diag] titre={page.title()!r}")
    except Exception:
        pass
    try:
        buttons = page.locator("div[role='button']").all()[:30]
        for b in buttons:
            t = " ".join((b.inner_text(timeout=1000) or "").split())[:70]
            if t:
                print(f"  [diag] bouton: {t}")
    except Exception as e:
        print(f"  [diag] boutons illisibles: {e}")
    try:
        body = page.inner_text("body", timeout=3000).lower()
        for marker in ("se connecter", "log in", "connexion", "captcha"):
            if marker in body:
                print(f"  [diag] la page contient « {marker} »")
    except Exception:
        pass


def open_picker(page, text):
    page.goto(START_URL, timeout=60000)
    time.sleep(2)
    try:
        page.locator("div[aria-label='Fermer'], div[aria-label='Close']").first.click(timeout=2000)
    except Exception:
        pass
    btn = page.locator("div[role='button']").filter(has_text="·").first
    if btn.count() == 0:
        btn = page.locator("div[role='main']").locator("div[role='button']").first
    try:
        btn.click(timeout=8000)
    except Exception:
        diagnose(page)
        raise
    time.sleep(2)
    page.locator(INPUT_SEL).first.fill(text)
    time.sleep(2.5)


def candidates(page, text, max_n):
    open_picker(page, text)
    options = page.locator(OPTION_SEL)
    n = min(options.count(), max_n)
    labels = [" ".join(options.nth(i).inner_text().split()) for i in range(n)]
    results = []
    for i in range(n):
        open_picker(page, text)
        page.locator(OPTION_SEL).nth(i).click()
        time.sleep(1)
        for name in ("Appliquer", "Apply"):
            apply_btn = page.locator("div[role='button']").filter(has_text=name).first
            if apply_btn.count() > 0:
                apply_btn.click()
                break
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(2)
        m = re.search(r'/marketplace/([^/?]+)/', page.url)
        results.append((labels[i], m.group(1) if m else "?"))
    return results


def main():
    parser = argparse.ArgumentParser(description="Candidats d'ID de ville Facebook (lecture seule)")
    parser.add_argument("--names", required=True, help="Noms séparés par des virgules")
    parser.add_argument("--suffix", default="", help="Texte ajouté au nom tapé (ex. ', Québec')")
    parser.add_argument("--max", type=int, default=6, help="Nombre max de suggestions par ville")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser, context = _new_context(p, ScraperConfig())
        try:
            for name in [n.strip() for n in args.names.split(",") if n.strip()]:
                print(f"\n=== {name}{args.suffix} ===")
                page = context.new_page()
                try:
                    res = candidates(page, name + args.suffix, args.max)
                except Exception as e:
                    print(f"  (erreur: {str(e)[:100]})")
                    res = []
                finally:
                    page.close()
                for label, cid in res:
                    mark = "←" if any(m in label.lower() for m in QC_MARKERS) else " "
                    print(f"  {mark} {cid:<18}{label}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
