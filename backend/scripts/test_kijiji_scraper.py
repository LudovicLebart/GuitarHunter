"""
Script de test manuel du scraper Kijiji (backend/scraping/kijiji/).

Ne touche ni Firestore ni le pipeline IA — sert uniquement à valider les
sélecteurs Playwright contre le vrai DOM de kijiji.ca, chose impossible à
faire depuis un environnement de développement sans accès réseau au site
(voir la note de validation en tête de `KijijiScraper`).

Modes disponibles :

  1. --url : scrape une seule annonce connue (le plus rapide à valider —
     isole la fiche détail : JSON-LD, images, prix, sans dépendre des
     sélecteurs de recherche/scroll).
  2. --query (+ --location / --max-ads) : recherche complète via le champ de
     recherche de la page d'accueil (fragile : le filtre de lieu dépend d'une
     modale non encore identifiée, voir --diag-search).
  3. --search-url (+ --max-ads) : scrape directement une URL de résultats de
     recherche déjà construite (ex: copiée depuis une recherche manuelle dans
     un navigateur : `.../b-guitar/longueuil-rive-sud/c613l1700279?...`) —
     évite complètement le champ de recherche/la modale de lieu.
  4. --diag-search : dump de tous les <input> de la page d'accueil kijiji.ca
     (id/name/placeholder/aria-label) — à utiliser si le mode 2 échoue avec
     "Champ de recherche Kijiji introuvable" pour identifier le vrai sélecteur.
  5. --diag-images URL : dump de la structure DOM de la galerie photo d'une
     fiche détail (chaîne de classes/data-testid, dimensions, compteurs style
     "3/9") — à utiliser si le nombre d'images extraites semble incomplet.
  6. --diag-search-data URL : dump des __typename présents dans l'état Apollo
     (__NEXT_DATA__) d'une page de résultats de recherche, + un exemple complet
     d'entrée contenant un prix — pour savoir si les cartes de résultats (prix/
     lieu par annonce) sont, comme la fiche détail, lisibles directement en JSON
     plutôt que via des sélecteurs DOM fragiles sur chaque carte.

Par défaut le navigateur est visible (non headless) pour repérer d'un coup
d'œil où un sélecteur ne matche plus rien.

Usage :
    python -m backend.scripts.test_kijiji_scraper --url "https://www.kijiji.ca/v-guitars-amps/.../1234567890"
    python -m backend.scripts.test_kijiji_scraper --query "guitare électrique" --location "Montreal" --max-ads 5
    python -m backend.scripts.test_kijiji_scraper --search-url "https://www.kijiji.ca/b-guitar/longueuil-rive-sud/c613l1700279?..." --max-ads 5
    python -m backend.scripts.test_kijiji_scraper --diag-search
    python -m backend.scripts.test_kijiji_scraper --diag-images "https://www.kijiji.ca/v-guitars-amps/.../1234567890"
    python -m backend.scripts.test_kijiji_scraper --diag-search-data "https://www.kijiji.ca/b-guitar/longueuil-rive-sud/c613l1700279?..."
"""
import sys
import argparse
import logging
import json

sys.path.insert(0, '.')
from backend.scraping.kijiji import KijijiScraper, KijijiScraperConfig


def main():
    parser = argparse.ArgumentParser(description="Teste le scraper Kijiji contre le site réel.")
    parser.add_argument("--url", default=None, help="URL d'une annonce Kijiji précise (scan_specific_url)")
    parser.add_argument("--query", default=None, help="Mots-clés de recherche (scan_marketplace)")
    parser.add_argument("--location", default=None, help="Lieu (texte libre tapé dans le champ de recherche)")
    parser.add_argument("--search-url", default=None, metavar="URL", help="URL de résultats de recherche déjà construite (scan_search_url)")
    parser.add_argument("--max-ads", type=int, default=5, help="Nombre max d'annonces à scraper (défaut: 5)")
    parser.add_argument("--headless", action="store_true", help="Navigateur invisible (défaut: visible pour debug)")
    parser.add_argument("--diag-search", action="store_true", help="Dump des <input> de la page d'accueil kijiji.ca")
    parser.add_argument("--diag-images", default=None, metavar="URL", help="Dump de la structure DOM de la galerie photo d'une fiche détail")
    parser.add_argument("--diag-search-data", default=None, metavar="URL", help="Dump de l'état Apollo (__NEXT_DATA__) d'une page de résultats de recherche")
    args = parser.parse_args()

    if not any([args.url, args.query, args.search_url, args.diag_search, args.diag_images, args.diag_search_data]):
        print("❌ Fournis --url, --query, --search-url, --diag-search, --diag-images ou --diag-search-data.")
        sys.exit(1)

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    log = logging.getLogger("test_kijiji_scraper")

    config = KijijiScraperConfig(headless=args.headless)
    scraper = KijijiScraper(config=config, logger=log)

    try:
        if args.diag_search:
            _diag_search(scraper)

        if args.diag_images:
            _diag_images(scraper, args.diag_images)

        if args.diag_search_data:
            _diag_search_data(scraper, args.diag_search_data)

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

        if args.search_url:
            print(f"\n🌍 Test scan_search_url : {args.search_url} (max {args.max_ads})\n")
            deals = scraper.scan_search_url(args.search_url, max_ads=args.max_ads)
            print(f"\n✅ {len(deals)} annonce(s) trouvée(s).\n")
            for deal in deals:
                _print_deal(deal)
    finally:
        scraper.close_session()


def _diag_search(scraper: KijijiScraper):
    """Dump de tous les <input> de la page d'accueil kijiji.ca — pour retrouver le vrai
    sélecteur du champ de recherche quand celui codé en dur ne matche plus rien."""
    print("\n🔬 Diagnostic recherche (page d'accueil kijiji.ca)\n")
    scraper._ensure_session()
    page = scraper.context.new_page()
    try:
        page.goto("https://www.kijiji.ca/", timeout=scraper.config.timeout_navigation)
        scraper._accept_cookies(page)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            print(f"(timeout networkidle, on continue quand même : {e})")
        inputs = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(el => ({
                id: el.id || null,
                name: el.name || null,
                type: el.type || null,
                placeholder: el.placeholder || null,
                ariaLabel: el.getAttribute('aria-label'),
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
            }));
        }""")
        print(f"{len(inputs)} <input> trouvé(s) :")
        for i in inputs:
            print(f"  - {json.dumps(i, ensure_ascii=False)}")
    except Exception as e:
        print(f"❌ Erreur diagnostic recherche : {e}")
    finally:
        page.close()


def _diag_images(scraper: KijijiScraper, url: str):
    """Dump de la structure DOM des grandes images (>200px) d'une fiche détail, avec leur
    chaîne parent (classes/data-testid) et tout compteur texte style "3/9" — pour identifier
    la vraie galerie/le bon mécanisme de navigation (clic vs clavier) quand le nombre
    d'images extraites est incomplet."""
    print(f"\n🔬 Diagnostic images : {url}\n")
    scraper._ensure_session()
    page = scraper.context.new_page()
    try:
        page.goto(url, timeout=scraper.config.timeout_navigation)
        scraper._accept_cookies(page)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            print(f"(timeout networkidle, on continue quand même : {e})")

        info = page.evaluate(r"""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            const bigImgs = imgs.filter(img => (img.naturalWidth > 150 || img.width > 150));
            const summary = bigImgs.slice(0, 20).map(img => {
                let el = img;
                let chain = [];
                for (let i = 0; i < 4 && el; i++) {
                    const cls = el.className ? '.' + String(el.className).trim().split(/\s+/).join('.') : '';
                    const testid = el.getAttribute && el.getAttribute('data-testid');
                    chain.push((el.tagName || '') + cls + (testid ? `[data-testid=${testid}]` : ''));
                    el = el.parentElement;
                }
                return { src: img.src.slice(0, 90), w: img.width, h: img.height, chain: chain.join(' < ') };
            });
            const counterRegex = /\d+\s*\/\s*\d+|\d+\s*(photos?|images?)/i;
            const counters = Array.from(document.querySelectorAll('body *'))
                .filter(el => el.children.length === 0 && el.tagName !== 'SCRIPT' && el.tagName !== 'STYLE' && counterRegex.test(el.innerText || ''))
                .map(el => el.innerText.trim().slice(0, 100))
                .slice(0, 8);
            const buttons = Array.from(document.querySelectorAll('button, [role="button"]'))
                .filter(el => /photo|image|suivant|next|voir tout/i.test((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')))
                .map(el => (el.getAttribute('aria-label') || el.innerText || '').trim())
                .slice(0, 8);
            return { totalImgTags: imgs.length, bigCount: bigImgs.length, images: summary, counters, buttons };
        }""")
        print(f"Total <img> sur la page : {info['totalImgTags']} — dont >150px : {info['bigCount']}")
        print("\nImages (chaîne parent, 4 niveaux) :")
        for im in info["images"]:
            print(f"  - {im['w']}x{im['h']} src={im['src']}")
            print(f"    chain: {im['chain']}")
        print(f"\nCompteurs texte trouvés (ex: '3/9', '9 photos') : {info['counters']}")
        print(f"Boutons liés aux photos trouvés : {info['buttons']}")
    except Exception as e:
        print(f"❌ Erreur diagnostic images : {e}")
    finally:
        page.close()


def _diag_search_data(scraper: KijijiScraper, url: str):
    """Dump des __typename présents dans l'état Apollo (__NEXT_DATA__) d'une page de
    résultats de recherche, + un exemple complet d'entrée contenant un prix — pour savoir
    si les cartes de résultats (prix/lieu par annonce) sont, comme la fiche détail,
    lisibles directement en JSON plutôt que via des sélecteurs DOM fragiles par carte."""
    print(f"\n🔬 Diagnostic __NEXT_DATA__ (page de résultats) : {url}\n")
    scraper._ensure_session()
    page = scraper.context.new_page()
    try:
        page.goto(url, timeout=scraper.config.timeout_navigation)
        scraper._accept_cookies(page)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            print(f"(timeout networkidle, on continue quand même : {e})")

        raw = page.evaluate("document.querySelector('script#__NEXT_DATA__')?.textContent || null")
        if not raw:
            print("❌ __NEXT_DATA__ introuvable sur cette page.")
            return

        data = json.loads(raw)
        apollo_state = data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {})
        if not isinstance(apollo_state, dict):
            print("❌ __APOLLO_STATE__ introuvable ou de forme inattendue.")
            return

        print(f"{len(apollo_state)} clé(s) dans __APOLLO_STATE__. __typename rencontrés :")
        typenames: dict = {}
        for key, value in apollo_state.items():
            if isinstance(value, dict):
                t = value.get("__typename", "?")
                typenames.setdefault(t, []).append(key)
        for t, keys in sorted(typenames.items(), key=lambda kv: -len(kv[1])):
            print(f"  - {t}: {len(keys)} — ex: {keys[:3]}")

        # Complétude : les StandardListing de la page de résultats sont-ils aussi
        # complets que sur la fiche détail individuelle (mêmes images/description), ou
        # tronqués (aperçu seulement) ? Décisif pour savoir si on peut se passer
        # entièrement de visiter chaque fiche détail.
        standard_listings = {k: v for k, v in apollo_state.items() if k.startswith("StandardListing:")}
        if standard_listings:
            print(f"\n{len(standard_listings)} StandardListing trouvé(s) sur la page de résultats. Exemple complet (le premier) :")
            first_key, first_value = next(iter(standard_listings.items()))
            print(f"--- {first_key} ---")
            print(json.dumps(first_value, ensure_ascii=False, indent=2)[:3000])

        # Un exemple complet de la première entrée qui ressemble à une annonce de résultats
        # (contient à la fois un prix et un id, mais n'est pas la fiche StandardListing complète).
        for key, value in apollo_state.items():
            if isinstance(value, dict) and "price" in value and value.get("__typename") != "StandardListing":
                print(f"\nExemple ({key}) :")
                print(json.dumps(value, ensure_ascii=False, indent=2)[:2500])
                break
        else:
            print("\n(Aucune entrée avec un champ 'price' trouvée en dehors de StandardListing.)")
    except Exception as e:
        print(f"❌ Erreur diagnostic search data : {e}")
    finally:
        page.close()


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
