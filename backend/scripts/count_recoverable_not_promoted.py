"""Décompte, en LECTURE SEULE, des annonces `NOT_PROMOTED` que « Ré-évaluer les annonces mises de côté »
promouvrait vers l'Analyste (T2), par utilisateur — mêmes règles que `bot.py::reevaluate_not_promoted` :
la classification stockée est ramenée à son chemin canonique avant la comparaison à `activeSearchFamilies`.

Pour chaque utilisateur : annonces mises de côté, à promouvoir (déjà conformes / après normalisation), et les
classifications brutes les plus fréquentes parmi celles que la normalisation rattrape ou ne résout pas. Chaque
annonce à promouvoir coûte au moins un appel T2 (et peut déclencher le T3). Aucun titre ni URL n'est affiché.

Usage (sur le serveur, `export DATABASE_URL=...` — ces scripts ne lisent pas `.env`) :
  python -m backend.scripts.count_recoverable_not_promoted
  python -m backend.scripts.count_recoverable_not_promoted --user-id UID

Seules des requêtes SELECT sont émises (connexion en lecture seule).
"""
import argparse
import os
import sys
from collections import Counter

os.environ.setdefault("APP_ID_TARGET", "count_recoverable")  # config.py l'exige ; sans effet ici

from backend.taxonomy import build_index, canonicalize, matches_active_search_family  # noqa: E402
from config import DEFAULT_TAXONOMY  # noqa: E402

TOP_N = 10


def analyse_user(config, classifications):
    """`classifications` : liste des classifications brutes des annonces NOT_PROMOTED de l'utilisateur."""
    analysis_config = (config or {}).get("analysisConfig") or {}
    families = analysis_config.get("activeSearchFamilies") or []
    taxonomy = analysis_config.get("taxonomy", DEFAULT_TAXONOMY)
    index = build_index(taxonomy)

    already, rescued, unresolved = 0, Counter(), Counter()
    for raw in classifications:
        canonical, _ = canonicalize(raw, taxonomy, index) if raw else (None, "empty")
        value = canonical or raw
        if not (not families or matches_active_search_family(value, families)):
            if not canonical:
                unresolved[raw or "(vide)"] += 1
            continue
        if value == raw:
            already += 1
        else:
            rescued[f"{raw} -> {value}"] += 1
    return families, already, rescued, unresolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user-id", help="se limiter à cet utilisateur (uid complet)")
    args = parser.parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL absent (export DATABASE_URL=... ; ces scripts ne lisent pas .env)")

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url) as conn:
        conn.read_only = True
        with conn.cursor(row_factory=dict_row) as cur:
            if args.user_id:
                cur.execute("SELECT uid, config FROM users WHERE uid = %s", (args.user_id,))
            else:
                cur.execute("SELECT uid, config FROM users ORDER BY uid")
            users = cur.fetchall()
            per_user = {}
            for user in users:
                cur.execute(
                    """SELECT gd.gatekeeper_classification AS c FROM guitar_deals gd
                       JOIN user_deal_matches udm ON udm.deal_id = gd.id
                       WHERE udm.user_id = %s AND gd.verdict = 'NOT_PROMOTED'""",
                    (user["uid"],),
                )
                per_user[user["uid"]] = [row["c"] for row in cur.fetchall()]

    total_to_promote = 0
    for user in users:
        classifications = per_user[user["uid"]]
        families, already, rescued, unresolved = analyse_user(user["config"], classifications)
        to_promote = already + sum(rescued.values())
        total_to_promote += to_promote
        print(f"\nUtilisateur {user['uid'][:8]}… — filtre : {families or '(vide : tout serait promu)'}")
        print(f"  mises de côté : {len(classifications)} | à promouvoir : {to_promote} "
              f"({already} déjà conformes, {sum(rescued.values())} après normalisation)")
        for label, counter in (("rattrapées par la normalisation", rescued), ("non résolues (restent écartées)", unresolved)):
            if counter:
                print(f"  {label} :")
                for value, n in counter.most_common(TOP_N):
                    print(f"    {n:>5}  {value}")
    print(f"\nTotal à promouvoir (tous utilisateurs) : {total_to_promote} appel(s) T2 au minimum.")


if __name__ == "__main__":
    main()
