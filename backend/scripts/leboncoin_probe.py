"""
Calibration LeBonCoin (étape 2/2) : vérifie si une session Playwright "douce"
(mêmes mesures stealth que le scraper Facebook — rotation UA/viewport, flags
anti-détection — mais SANS contournement actif de DataDome type SSL
Pinning/TLS spoofing) parvient à charger une page de recherche sans être
bloquée, et si oui, extrait les résultats.

Extraction : LeBonCoin (Next.js) embarque les résultats de recherche en JSON
structuré dans <script id="__NEXT_DATA__">, bien plus fiable que des
sélecteurs CSS. Liste blanche stricte de champs extraits (titre, prix,
localisation approximative, lien, date, photos) — le bloc "owner" (pseudo,
user_id, store_id du vendeur) est délibérément exclu, conformément à la
règle "pas de données personnelles" fixée pour ce chantier. La description
complète (vide sur la page de résultats) n'est pas encore récupérée — nécessite
de visiter chaque fiche détail, à faire dans une étape suivante.

Aucune écriture Firestore — script de test uniquement.

Prérequis : avoir généré une session via `backend.scripts.leboncoin_login_once`.

Usage :
    python -m backend.scripts.leboncoin_probe
    python -m backend.scripts.leboncoin_probe --query "guitare parlor" --max-price 200
    python -m backend.scripts.leboncoin_probe --headless
"""
import sys
import os
import re
import json
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


def extract_ads(html):
    """Parse le JSON __NEXT_DATA__ de la page de résultats et retourne une liste
    d'annonces minimisées (liste blanche de champs). Retourne None si le bloc
    est absent ou d'une forme inattendue (structure LeBonCoin non confirmée
    stable dans le temps)."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        ads = data["props"]["pageProps"]["searchData"]["ads"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None

    results = []
    for ad in ads:
        location = ad.get("location") or {}
        images = ad.get("images") or {}
        price_list = ad.get("price") or []
        results.append({
            "id": ad.get("list_id"),
            "title": ad.get("subject"),
            "price": price_list[0] if price_list else None,
            "description": ad.get("body") or None,  # vide sur la page de résultats
            "url": ad.get("url"),
            "published_at": ad.get("first_publication_date"),
            "location": {
                "city": location.get("city"),
                "zipcode": location.get("zipcode"),
                "lat": location.get("lat"),
                "lng": location.get("lng"),
            },
            "image_urls": images.get("urls") or [],
            # NOTE : le bloc "owner" (pseudo, user_id, store_id du vendeur) est
            # intentionnellement exclu — aucune donnée personnelle vendeur stockée.
        })
    return results


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

            html = page.content()
            ads = extract_ads(html)

            if ads is None:
                html_path = "leboncoin_probe_page.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"   ⚠️  Bloc __NEXT_DATA__ introuvable ou de forme inattendue.")
                print(f"   HTML complet sauvegardé dans : {html_path} pour investigation.")
            else:
                print(f"\n📋 {len(ads)} annonce(s) extraite(s) :")
                for ad in ads[:10]:
                    print(f"   [{ad['id']}] {ad['title']} — {ad['price']}€ — {ad['location']['city']} ({ad['location']['zipcode']})")
                if len(ads) > 10:
                    print(f"   ... et {len(ads) - 10} autre(s).")

                results_path = "leboncoin_probe_results.json"
                with open(results_path, "w", encoding="utf-8") as f:
                    json.dump(ads, f, ensure_ascii=False, indent=2)
                print(f"\n   Résultats complets (minimisés, sans données vendeur) sauvegardés dans : {results_path}")

        browser.close()


if __name__ == "__main__":
    main()
