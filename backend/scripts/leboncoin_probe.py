"""
Calibration LeBonCoin (étape 2/2) : vérifie uniquement si une session
Playwright "douce" (mêmes mesures stealth que le scraper Facebook — rotation
UA/viewport, flags anti-détection — mais SANS contournement actif de
DataDome type SSL Pinning/TLS spoofing) parvient à charger une page de
recherche sans être bloquée.

Ne fait AUCUNE extraction fiable de contenu à ce stade : la structure DOM
réelle de LeBonCoin n'a pas pu être vérifiée depuis l'environnement de
développement (aucun accès réseau LeBonCoin possible ici). La priorité est
d'observer si ça passe le premier obstacle (challenge JS/captcha DataDome)
avant d'écrire des sélecteurs d'extraction précis. Si la page charge, le HTML
complet est sauvegardé localement pour permettre d'écrire ces sélecteurs dans
une étape suivante. Aucune écriture Firestore — script de test uniquement.

Prérequis : avoir généré une session via `backend.scripts.leboncoin_login_once`.

Usage :
    python -m backend.scripts.leboncoin_probe
    python -m backend.scripts.leboncoin_probe --query "guitare parlor" --max-price 200
    python -m backend.scripts.leboncoin_probe --headless
"""
import sys
import os
import argparse
import random
import time
import urllib.parse

sys.path.insert(0, '.')

from playwright.sync_api import sync_playwright

DEFAULT_STATE = "backend/scripts/leboncoin_storage_state.json"

# Mêmes familles de User-Agent/viewports que FacebookScraper (backend/scraping/core.py)
# pour une posture de furtivité cohérente entre les deux scrapers.
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

# Domaine connu du challenge DataDome — une redirection dessus signale un
# blocage actif, pas un simple ralentissement.
DATADOME_CHALLENGE_MARKERS = ["captcha-delivery.com"]
SUSPICIOUS_TITLE_KEYWORDS = ["just a moment", "vérification", "attention requise", "access denied", "pardon our interruption"]


def looks_blocked(page, responses):
    """Détection best-effort — à affiner une fois qu'on aura observé un vrai blocage."""
    if any(marker in page.url for marker in DATADOME_CHALLENGE_MARKERS):
        return True, f"Redirection vers un domaine de challenge DataDome : {page.url}"

    for resp in responses:
        if resp.status in (403, 429):
            return True, f"Réponse HTTP {resp.status} sur {resp.url}"

    title = (page.title() or "").lower()
    if any(kw in title for kw in SUSPICIOUS_TITLE_KEYWORDS):
        return True, f"Titre de page suspect : '{page.title()}'"

    return False, None


def main():
    parser = argparse.ArgumentParser(description="Sonde de calibration LeBonCoin — teste si la session passe sans être bloquée")
    parser.add_argument("--query", default="guitare", help="Terme de recherche (défaut: guitare)")
    parser.add_argument("--max-price", type=int, default=0, help="Prix maximum (0 = pas de filtre)")
    parser.add_argument("--state", default=DEFAULT_STATE, help=f"Chemin du fichier de session (défaut: {DEFAULT_STATE})")
    parser.add_argument("--headless", action="store_true", help="Lancer en mode headless (défaut: fenêtre visible pour observer)")
    args = parser.parse_args()

    if not os.path.exists(args.state):
        print(f"❌ Fichier de session introuvable : {args.state}")
        print("   Lance d'abord : python -m backend.scripts.leboncoin_login_once")
        sys.exit(1)

    responses = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-sandbox"],
        )
        ua = random.choice(USER_AGENTS)
        vp = random.choice(VIEWPORTS)
        context = browser.new_context(storage_state=args.state, user_agent=ua, viewport=vp, locale="fr-FR")
        page = context.new_page()
        page.on("response", lambda r: responses.append(r))

        query_encoded = urllib.parse.quote(args.query)
        url = f"https://www.leboncoin.fr/recherche?text={query_encoded}"
        if args.max_price > 0:
            url += f"&price=min-{args.max_price}"

        print(f"➡️  Navigation : {url}")
        page.goto(url, timeout=30000)
        time.sleep(3)  # laisse le temps à un éventuel challenge JS de s'exécuter

        blocked, reason = looks_blocked(page, responses)
        if blocked:
            print(f"🚨 BLOCAGE DÉTECTÉ : {reason}")
            screenshot_path = "leboncoin_probe_blocked.png"
            page.screenshot(path=screenshot_path)
            print(f"   Capture d'écran sauvegardée : {screenshot_path}")
        else:
            print("✅ Page chargée sans signe de blocage détecté.")
            print(f"   URL finale : {page.url}")
            print(f"   Titre : {page.title()}")
            html_path = "leboncoin_probe_page.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            print(f"   HTML complet sauvegardé dans : {html_path}")
            print("\n⚠️  Extraction de contenu non tentée : la structure DOM réelle de LeBonCoin")
            print("   n'a pas pu être vérifiée depuis l'environnement de développement. Partage")
            print("   ce fichier HTML (ou ce que tu observes dans la fenêtre) pour qu'on écrive")
            print("   des sélecteurs d'extraction fiables à l'étape suivante.")

        browser.close()


if __name__ == "__main__":
    main()
