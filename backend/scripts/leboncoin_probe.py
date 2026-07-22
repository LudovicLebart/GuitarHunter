"""
Script de test pour `backend.scraping_leboncoin.LeboncoinScraper` : lance une
ou plusieurs recherches dans la même session (pas de fermeture systématique
entre chaque appel — voir docstring du module pour le raisonnement), avec
pagination automatique, et affiche/sauvegarde les résultats.

Aucune écriture Firestore — script de test uniquement.

Prérequis : avoir généré une session via `backend.scripts.leboncoin_login_once`.

Usage :
    python -m backend.scripts.leboncoin_probe
    python -m backend.scripts.leboncoin_probe --query "guitare parlor" --max-price 200
    python -m backend.scripts.leboncoin_probe --query "guitare acoustique" --min-price 50 --max-price 200 \
        --locations "bordeaux_33000__44.8367_-0.5810_5000" --owner-type private --max-pages 2
    python -m backend.scripts.leboncoin_probe --repeat 3
"""
import sys
import os
import argparse
import json
import logging

sys.path.insert(0, '.')

from backend.scraping_leboncoin import LeboncoinScraper

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("leboncoin_probe")

DEFAULT_STATE = "backend/scripts/leboncoin_storage_state.json"


def main():
    parser = argparse.ArgumentParser(description="Test du module LeboncoinScraper")
    parser.add_argument("--query", default="guitare", help="Terme de recherche (défaut: guitare)")
    parser.add_argument("--min-price", type=int, default=0, help="Prix minimum (défaut: 0)")
    parser.add_argument("--max-price", type=int, default=0, help="Prix maximum (0 = pas de filtre)")
    parser.add_argument("--category", default="30", help="ID de catégorie LeBonCoin (défaut: 30, Instruments de musique)")
    parser.add_argument(
        "--locations", default=None,
        help="Valeur brute du paramètre 'locations' copiée depuis une recherche manuelle sur leboncoin.fr "
             "(gère nativement le multi-villes via des virgules) — non deviné, à fournir tel quel."
    )
    parser.add_argument("--owner-type", default=None, choices=["private", "pro"], help="Filtrer par type de vendeur (défaut: aucun filtre)")
    parser.add_argument("--max-pages", type=int, default=1, help="Nombre maximum de pages à parcourir (défaut: 1)")
    parser.add_argument("--repeat", type=int, default=1, help="Nombre de recherches à lancer dans la même session (défaut: 1)")
    parser.add_argument("--state", default=DEFAULT_STATE, help=f"Chemin du fichier de session (défaut: {DEFAULT_STATE})")
    args = parser.parse_args()

    if not os.path.exists(args.state):
        print(f"❌ Fichier de session introuvable : {args.state}")
        print("   Lance d'abord : python -m backend.scripts.leboncoin_login_once")
        sys.exit(1)

    scraper = LeboncoinScraper(args.state, logger=logger)
    all_results = []

    try:
        for i in range(args.repeat):
            if i > 0:
                logger.info(f"--- Recherche {i + 1}/{args.repeat} (même session) ---")
            ads, blocked_reason = scraper.search(
                args.query, locations=args.locations, category=args.category,
                min_price=args.min_price, max_price=args.max_price,
                owner_type=args.owner_type, max_pages_limit=args.max_pages,
            )

            all_results.extend(ads)  # même en cas d'arrêt (blocage/échec extraction), on garde le déjà-collecté

            if blocked_reason:
                print(f"🚨 ARRÊT DE LA RECHERCHE : {blocked_reason}")
                break

            print(f"\n📋 {len(ads)} annonce(s) extraite(s) (recherche {i + 1}/{args.repeat}) :")
            for ad in ads[:10]:
                print(f"   [{ad['id']}] {ad['title']} — {ad['price']}€ — {ad['location']['city']} ({ad['location']['zipcode']})")
            if len(ads) > 10:
                print(f"   ... et {len(ads) - 10} autre(s).")
    finally:
        # La fenêtre reste ouverte tant que l'utilisateur n'a pas validé lui-même —
        # utile pour observer visuellement la page (scroll, blocage éventuel...)
        # avant fermeture, plutôt qu'une fermeture automatique imposée.
        try:
            input("\n👉 Appuie sur Entrée pour fermer la fenêtre du navigateur...\n")
        except EOFError:
            pass
        scraper.close_session()
        # Dans le finally pour toujours sauvegarder le déjà-collecté, même si une
        # exception (ex: timeout Playwright) interrompt la boucle --repeat en cours de route.
        if all_results:
            results_path = "leboncoin_probe_results.json"
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
            print(f"\n   Résultats complets (minimisés, sans données vendeur) sauvegardés dans : {results_path}")


if __name__ == "__main__":
    main()
