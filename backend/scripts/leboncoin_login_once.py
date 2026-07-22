"""
Calibration LeBonCoin (étape 1/2) : connexion manuelle unique pour générer une
session authentifiée réutilisable par la sonde (leboncoin_probe.py).

Ne fait AUCUN scraping — ouvre une fenêtre Chromium visible sur leboncoin.fr et
attend que tu te connectes toi-même à la main (compte "réchauffé" par une
navigation manuelle préalable), puis sauvegarde les cookies de session dans un
fichier local (jamais commité — voir .gitignore).

Usage :
    python -m backend.scripts.leboncoin_login_once
    python -m backend.scripts.leboncoin_login_once --output chemin/personnalise.json
"""
import sys
import argparse
import random

sys.path.insert(0, '.')

from playwright.sync_api import sync_playwright

DEFAULT_OUTPUT = "backend/scripts/leboncoin_storage_state.json"

# Mêmes flags/UA/viewports que leboncoin_probe.py — la fenêtre de login doit
# avoir la même posture de furtivité que la sonde, sinon elle risque d'être
# bloquée avant même que la connexion manuelle ait pu avoir lieu.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
]


def main():
    parser = argparse.ArgumentParser(description="Connexion manuelle unique pour générer une session LeBonCoin réutilisable")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Chemin du fichier de session à générer (défaut: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-sandbox"],
        )
        ua = random.choice(USER_AGENTS)
        vp = random.choice(VIEWPORTS)
        context = browser.new_context(locale="fr-FR", user_agent=ua, viewport=vp)
        page = context.new_page()
        page.goto("https://www.leboncoin.fr/", timeout=60000)

        print("\n👉 Connecte-toi manuellement à ton compte LeBonCoin dans la fenêtre ouverte.")
        print("   Navigue un peu (consulte quelques annonces) pour garder la session 'réchauffée'.")
        input("   Une fois connecté et prêt, appuie sur Entrée ici pour sauvegarder la session...\n")

        context.storage_state(path=args.output)
        print(f"✅ Session sauvegardée dans : {args.output}")

        browser.close()


if __name__ == "__main__":
    main()
