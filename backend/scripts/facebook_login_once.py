"""
Connexion Facebook manuelle unique : génère un `storage_state` Playwright réutilisable par
compare_fb_anon_vs_auth.py (comparaison anonyme vs compte connecté).

Ne fait AUCUN scraping. Ouvre Chromium (fenêtre visible, donc à lancer sur un poste avec écran),
attend que tu te connectes à la main (compte dédié recommandé), puis sauvegarde les cookies dans
un fichier local — jamais commité (voir .gitignore).

Usage :
    python -m backend.scripts.facebook_login_once
    python -m backend.scripts.facebook_login_once --output chemin/personnalise.json
"""
import sys
import argparse
import random

sys.path.insert(0, '.')

from playwright.sync_api import sync_playwright
from backend.scraping.config import ScraperConfig

DEFAULT_OUTPUT = "backend/scripts/facebook_storage_state.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"


def main():
    parser = argparse.ArgumentParser(description="Connexion manuelle unique pour générer une session Facebook réutilisable")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Fichier de session à générer (défaut: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    cfg = ScraperConfig()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-sandbox"],
        )
        context = browser.new_context(
            locale=cfg.locale, timezone_id=cfg.timezone, user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        page.goto("https://www.facebook.com/marketplace/", timeout=60000)

        print("\n👉 Connecte-toi manuellement à Facebook dans la fenêtre ouverte, puis ouvre Marketplace.")
        input("   Une fois connecté et sur Marketplace, appuie sur Entrée ici pour sauvegarder la session...\n")

        context.storage_state(path=args.output)
        print(f"✅ Session sauvegardée dans : {args.output}")
        browser.close()


if __name__ == "__main__":
    main()
