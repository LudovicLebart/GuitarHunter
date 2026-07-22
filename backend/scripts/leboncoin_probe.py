"""
Script de test interactif pour `backend.scraping_leboncoin.LeboncoinScraper` :
une seule session/fenêtre reste ouverte du lancement du script jusqu'à ce que
l'utilisateur choisisse explicitement de quitter — jamais de fermeture/
réouverture automatique entre deux recherches (voir docstring du module pour
le raisonnement anti-prévisibilité). En cas de blocage détecté, la page reste
ouverte pour permettre une intervention manuelle (ex : résoudre un slider
DataDome) avant de continuer ou de quitter.

Aucune écriture Firestore — script de test uniquement.

Prérequis : avoir généré une session via `backend.scripts.leboncoin_login_once`.

Usage :
    python -m backend.scripts.leboncoin_probe
    python -m backend.scripts.leboncoin_probe --query "guitare parlor" --max-price 200
    python -m backend.scripts.leboncoin_probe --query "guitare acoustique" --min-price 50 --max-price 200 \
        --locations "bordeaux_33000__44.8367_-0.5810_5000" --owner-type private --max-pages 2

Après chaque recherche, un prompt propose :
    [Entrée] relancer la même recherche | [n] nouveaux paramètres | [q] quitter
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


def _prompt_new_params(params):
    """Reprend chaque paramètre actuel comme défaut affiché — Entrée seule = inchangé."""
    def ask(label, current):
        raw = input(f"   {label} [{current}] : ").strip()
        return raw if raw else current

    params["query"] = ask("Recherche", params["query"])
    params["min_price"] = int(ask("Prix min", params["min_price"]) or 0)
    params["max_price"] = int(ask("Prix max", params["max_price"]) or 0)
    params["category"] = ask("Catégorie", params["category"])
    params["locations"] = ask("Locations (brut, vide = aucun)", params["locations"] or "") or None
    owner = ask("Type vendeur (private/pro, vide = aucun)", params["owner_type"] or "")
    params["owner_type"] = owner if owner in ("private", "pro") else None
    params["max_pages"] = int(ask("Pages max", params["max_pages"]) or 1)
    return params


def main():
    parser = argparse.ArgumentParser(description="Test interactif du module LeboncoinScraper")
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
    parser.add_argument("--state", default=DEFAULT_STATE, help=f"Chemin du fichier de session (défaut: {DEFAULT_STATE})")
    args = parser.parse_args()

    if not os.path.exists(args.state):
        print(f"❌ Fichier de session introuvable : {args.state}")
        print("   Lance d'abord : python -m backend.scripts.leboncoin_login_once")
        sys.exit(1)

    scraper = LeboncoinScraper(args.state, logger=logger)
    all_results = []
    params = {
        "query": args.query, "min_price": args.min_price, "max_price": args.max_price,
        "category": args.category, "locations": args.locations,
        "owner_type": args.owner_type, "max_pages": args.max_pages,
    }

    try:
        while True:
            ads, blocked_reason = scraper.search(
                params["query"], locations=params["locations"], category=params["category"],
                min_price=params["min_price"], max_price=params["max_price"],
                owner_type=params["owner_type"], max_pages_limit=params["max_pages"],
            )
            all_results.extend(ads)  # même en cas de blocage/échec, on garde le déjà-collecté

            if blocked_reason:
                print(f"🚨 ARRÊT DE LA RECHERCHE : {blocked_reason}")
                print("   La page reste ouverte : résous un éventuel slider/captcha dans la fenêtre si besoin.")
            else:
                print(f"\n📋 {len(ads)} annonce(s) extraite(s) :")
                for ad in ads[:10]:
                    print(f"   [{ad['id']}] {ad['title']} — {ad['price']}€ — {ad['location']['city']} ({ad['location']['zipcode']})")
                if len(ads) > 10:
                    print(f"   ... et {len(ads) - 10} autre(s).")

            try:
                choice = input("\n👉 [Entrée] relancer la même recherche | [n] nouveaux paramètres | [q] quitter : ").strip().lower()
            except EOFError:
                choice = "q"

            if choice == "q":
                break
            if choice == "n":
                params = _prompt_new_params(params)
            # Entrée seule : relance à l'identique, même session/même navigateur.
    except Exception:
        print("\n⚠️ Erreur inattendue pendant la recherche — la fenêtre reste ouverte pour inspection.")
        try:
            input("👉 Appuie sur Entrée pour fermer quand même...\n")
        except EOFError:
            pass
        raise
    finally:
        scraper.close_session()
        if all_results:
            results_path = "leboncoin_probe_results.json"
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
            print(f"\n   Résultats complets (minimisés, sans données vendeur) sauvegardés dans : {results_path}")


if __name__ == "__main__":
    main()
