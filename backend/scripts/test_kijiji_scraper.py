"""
Script de test manuel du scraper Kijiji (backend/scraping/kijiji/).

Ne touche ni Firestore ni le pipeline IA — sert uniquement à valider les
sélecteurs Playwright contre le vrai DOM de kijiji.ca, chose impossible à
faire depuis un environnement de développement sans accès réseau au site
(voir la note de validation en tête de `KijijiScraper`).

Deux modes, à utiliser dans cet ordre :

  1. --url : scrape une seule annonce connue (le plus rapide à valider —
     isole la fiche détail : JSON-LD, images, prix, sans dépendre des
     sélecteurs de recherche/scroll).
  2. --query (+ --location / --max-ads) : recherche complète, teste le champ
     de recherche, le filtre de lieu et le scroll dynamique.

Par défaut le navigateur est visible (non headless) pour repérer d'un coup
d'œil où un sélecteur ne matche plus rien.

Usage :
    python -m backend.scripts.test_kijiji_scraper --url "https://www.kijiji.ca/v-guitars-amps/.../1234567890"
    python -m backend.scripts.test_kijiji_scraper --query "guitare électrique" --location "Montreal" --max-ads 5
    python -m backend.scripts.test_kijiji_scraper --query "guitare électrique" --headless
"""
import sys
import argparse
import logging

sys.path.insert(0, '.')
from backend.scraping.kijiji import KijijiScraper, KijijiScraperConfig


def main():
    parser = argparse.ArgumentParser(description="Teste le scraper Kijiji contre le site réel.")
    parser.add_argument("--url", default=None, help="URL d'une annonce Kijiji précise (scan_specific_url)")
    parser.add_argument("--query", default=None, help="Mots-clés de recherche (scan_marketplace)")
    parser.add_argument("--location", default=None, help="Lieu (texte libre tapé dans le champ de recherche)")
    parser.add_argument("--max-ads", type=int, default=5, help="Nombre max d'annonces à scraper (défaut: 5)")
    parser.add_argument("--headless", action="store_true", help="Navigateur invisible (défaut: visible pour debug)")
    args = parser.parse_args()

    if not args.url and not args.query:
        print("❌ Fournis --url (test d'une annonce) ou --query (test de recherche).")
        sys.exit(1)

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    log = logging.getLogger("test_kijiji_scraper")

    config = KijijiScraperConfig(headless=args.headless)
    scraper = KijijiScraper(config=config, logger=log)

    try:
        if args.url:
            print(f"\n🔗 Test scan_specific_url : {args.url}\n")
            results = []
            scraper.scan_specific_url(args.url, results.append)
            for deal in results:
                _print_deal(deal)
            if not results:
                print("⚠️ Aucune annonce retournée — vérifier les logs ci-dessus (page invalide, ID introuvable...).")

        if args.query:
            print(f"\n🌍 Test scan_marketplace : '{args.query}' @ {args.location or 'Canada'} (max {args.max_ads})\n")
            deals = scraper.scan_marketplace({
                "search_query": args.query,
                "location": args.location,
                "max_ads": args.max_ads,
            })
            print(f"\n✅ {len(deals)} annonce(s) trouvée(s).\n")
            for deal in deals:
                _print_deal(deal)
    finally:
        scraper.close_session()


def _print_deal(deal: dict):
    print("-" * 60)
    print(f"Titre       : {deal.get('title')}")
    print(f"Prix        : {deal.get('price')}$")
    print(f"Lieu        : {deal.get('location')}")
    print(f"ID          : {deal.get('id')}")
    print(f"Lien        : {deal.get('link')}")
    print(f"Images      : {len(deal.get('imageUrls') or [])}")
    description = deal.get('description') or ''
    print(f"Description : {description[:200]}{'...' if len(description) > 200 else ''}")


if __name__ == "__main__":
    main()
