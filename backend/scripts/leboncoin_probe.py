"""
Script de test pour `backend.scraping_leboncoin.LeboncoinScraper`.

Deux modes :
- **Interactif** (défaut) : une seule session/fenêtre reste ouverte du
  lancement du script jusqu'à ce que l'utilisateur choisisse explicitement de
  quitter — jamais de fermeture/réouverture automatique entre deux recherches.
  En cas de blocage détecté, la page reste ouverte pour permettre une
  intervention manuelle (ex : résoudre un slider DataDome).
- **Soak test** (`--soak-cycles N`) : enchaîne N cycles de recherche sans
  interaction manuelle, avec un intervalle aléatoire et large entre chaque
  (défaut 45-90 min, aligné/au-dessus du rythme Facebook — un test qui bannirait
  le compte irait à l'encontre de son propre but), pour obtenir un vrai signal
  chiffré (taux de blocage) sur une campagne de test longue plutôt qu'une
  impression sur quelques essais manuels. Marque aussi une pause automatique la
  nuit (heure de Paris) plutôt que de scanner 24h/24.

Aucune écriture Firestore — script de test uniquement.

Prérequis : avoir généré une session via `backend.scripts.leboncoin_login_once`.

Usage :
    python -m backend.scripts.leboncoin_probe
    python -m backend.scripts.leboncoin_probe --query "guitare parlor" --max-price 200
    python -m backend.scripts.leboncoin_probe --query "guitare acoustique" --min-price 50 --max-price 200 \
        --locations "bordeaux_33000__44.8367_-0.5810_5000" --owner-type private --max-pages 2
    python -m backend.scripts.leboncoin_probe --soak-cycles 20

Après chaque recherche (mode interactif), un prompt propose :
    [Entrée] relancer la même recherche | [n] nouveaux paramètres | [q] quitter
"""
import sys
import os
import argparse
import json
import logging
import random
import time
from datetime import datetime, timezone

sys.path.insert(0, '.')

from backend.scraping_leboncoin import LeboncoinScraper, seconds_until_active

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger("leboncoin_probe")

DEFAULT_STATE = "backend/scripts/leboncoin_storage_state.json"
SOAK_LOG_PATH = "leboncoin_soak_log.jsonl"


def _max_pages_limit(params):
    """0 (ou non fourni) = pas de plafond, on suit le max_pages réel du site."""
    return params["max_pages"] if params["max_pages"] > 0 else None


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
    params["max_pages"] = int(ask("Pages max (0 = illimité, suit le site)", params["max_pages"]) or 0)
    return params


def _print_results(ads):
    print(f"\n📋 {len(ads)} annonce(s) extraite(s) :")
    for ad in ads[:10]:
        print(f"   [{ad['id']}] {ad['title']} — {ad['price']}€ — {ad['location']['city']} ({ad['location']['zipcode']})")
    if len(ads) > 10:
        print(f"   ... et {len(ads) - 10} autre(s).")


def _run_interactive(scraper, params, all_results):
    while True:
        ads, blocked_reason = scraper.search(
            params["query"], locations=params["locations"], category=params["category"],
            min_price=params["min_price"], max_price=params["max_price"],
            owner_type=params["owner_type"], max_pages_limit=_max_pages_limit(params),
        )
        all_results.extend(ads)  # même en cas de blocage/échec, on garde le déjà-collecté

        if blocked_reason:
            print(f"🚨 ARRÊT DE LA RECHERCHE : {blocked_reason}")
            print("   La page reste ouverte : résous un éventuel slider/captcha dans la fenêtre si besoin.")
        else:
            _print_results(ads)

        try:
            choice = input("\n👉 [Entrée] relancer la même recherche | [n] nouveaux paramètres | [q] quitter : ").strip().lower()
        except EOFError:
            choice = "q"

        if choice == "q":
            break
        if choice == "n":
            params = _prompt_new_params(params)
        # Entrée seule : relance à l'identique, même session/même navigateur.


def _run_soak(scraper, params, cycles, min_wait, max_wait, all_results):
    clean_count = 0
    blocked_count = 0
    for i in range(cycles):
        wait_s = seconds_until_active()
        if wait_s > 0:
            logger.info(f"   🌙 Plage nocturne (heure de Paris) — pause avant reprise dans ~{wait_s / 3600:.1f}h...")
            time.sleep(wait_s)

        logger.info(f"=== Cycle soak {i + 1}/{cycles} ===")
        started = time.time()
        ads, blocked_reason = scraper.search(
            params["query"], locations=params["locations"], category=params["category"],
            min_price=params["min_price"], max_price=params["max_price"],
            owner_type=params["owner_type"], max_pages_limit=_max_pages_limit(params),
        )
        all_results.extend(ads)

        entry = {
            "cycle": i + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_s": round(time.time() - started, 1),
            "ads_found": len(ads),
            "blocked": bool(blocked_reason),
            "reason": blocked_reason,
        }
        with open(SOAK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        if blocked_reason:
            blocked_count += 1
            print(f"🚨 Cycle {i + 1}/{cycles} bloqué : {blocked_reason} — arrêt du soak test.")
            print("   La page reste ouverte : résous un éventuel slider/captcha dans la fenêtre si besoin.")
            break

        clean_count += 1
        print(f"✅ Cycle {i + 1}/{cycles} : {len(ads)} annonce(s), aucun blocage.")

        if i < cycles - 1:
            wait_s = random.uniform(min_wait, max_wait)
            logger.info(f"   Prochain cycle dans ~{wait_s / 60:.1f} min...")
            time.sleep(wait_s)

    print(f"\n📊 Bilan soak test : {clean_count} cycle(s) propre(s), {blocked_count} bloqué(s) — journal complet dans {SOAK_LOG_PATH}")


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
    parser.add_argument(
        "--max-pages", type=int, default=0,
        help="Nombre maximum de pages à parcourir. 0 (défaut) = pas de plafond, suit le nombre réel "
             "de pages annoncé par le site (searchData.max_pages)."
    )
    parser.add_argument("--state", default=DEFAULT_STATE, help=f"Chemin du fichier de session (défaut: {DEFAULT_STATE})")
    parser.add_argument(
        "--soak-cycles", type=int, default=None,
        help="Mode test de charge : lance N cycles de recherche automatiques (sans prompt interactif), "
             "avec un intervalle aléatoire entre chaque, et une pause automatique la nuit (heure de Paris). "
             "Journalise chaque cycle dans leboncoin_soak_log.jsonl."
    )
    parser.add_argument("--soak-min-wait", type=int, default=2700, help="Intervalle minimum en secondes entre deux cycles soak (défaut: 2700 = 45min)")
    parser.add_argument("--soak-max-wait", type=int, default=5400, help="Intervalle maximum en secondes entre deux cycles soak (défaut: 5400 = 90min)")
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
        if args.soak_cycles:
            _run_soak(scraper, params, args.soak_cycles, args.soak_min_wait, args.soak_max_wait, all_results)
        else:
            _run_interactive(scraper, params, all_results)
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
