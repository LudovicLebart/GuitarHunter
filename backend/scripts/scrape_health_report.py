"""
Rapport de santé des scrapers (Facebook / Kijiji) à partir de la table `scrape_runs` : combien de
scans, combien d'échecs, de quel type, pour quelle ville — et depuis quand la dernière réussite.
Lecture seule. Aucun titre ni URL d'annonce n'est stocké ni affiché.

Usage (DATABASE_URL exporté — ces scripts ne lisent pas .env) :
    python -m backend.scripts.scrape_health_report                  # 7 derniers jours, tous les utilisateurs
    python -m backend.scripts.scrape_health_report --days 30 --user-id <UID>
    python -m backend.scripts.scrape_health_report --only-failing   # masque les villes sans échec

Codes : ok | no_cards | geo_mismatch | blocked | detail_degraded | error (voir backend/scrape_health.py).
"""
import sys
import argparse
from collections import defaultdict

sys.path.insert(0, '.')

import psycopg
from psycopg.rows import dict_row

from backend.pg_db import DATABASE_URL
from backend.scrape_health import FAILURE_OUTCOMES, OK

CODES = (OK,) + FAILURE_OUTCOMES


def fetch(conn, days, user_id):
    return conn.execute(
        """
        SELECT source, COALESCE(city_name, '?') AS city_name, city_id, outcome,
               count(*) AS n, max(created_at) AS last_at,
               sum(cards_seen) AS cards, sum(out_of_list) AS out_of_list, sum(kept) AS kept
        FROM scrape_runs
        WHERE created_at > now() - make_interval(days => %(days)s)
          AND (%(uid)s::text IS NULL OR user_id = %(uid)s)
        GROUP BY source, city_name, city_id, outcome
        """,
        {"days": days, "uid": user_id},
    ).fetchall()


def last_ok(conn, user_id):
    rows = conn.execute(
        """
        SELECT source, city_id, max(created_at) AS last_ok FROM scrape_runs
        WHERE outcome = 'ok' AND (%(uid)s::text IS NULL OR user_id = %(uid)s)
        GROUP BY source, city_id
        """,
        {"uid": user_id},
    ).fetchall()
    return {(r["source"], r["city_id"]): r["last_ok"] for r in rows}


def main():
    parser = argparse.ArgumentParser(description="Rapport de santé des scrapers (lecture seule)")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--user-id")
    parser.add_argument("--only-failing", action="store_true")
    args = parser.parse_args()

    with psycopg.connect(DATABASE_URL, connect_timeout=10, row_factory=dict_row) as conn:
        rows = fetch(conn, args.days, args.user_id)
        ok_dates = last_ok(conn, args.user_id)

    if not rows:
        print(f"Aucun scan enregistré sur les {args.days} derniers jours (table scrape_runs vide ou bot pas encore redémarré).")
        return

    cities = defaultdict(lambda: {"codes": defaultdict(int), "cards": 0, "out": 0, "kept": 0})
    for r in rows:
        key = (r["source"], r["city_name"], r["city_id"])
        c = cities[key]
        c["codes"][r["outcome"]] += r["n"]
        c["cards"] += r["cards"] or 0
        c["out"] += r["out_of_list"] or 0
        c["kept"] += r["kept"] or 0

    print(f"Santé des scrapers — {args.days} derniers jours\n")
    header = f"{'source':<10}{'ville':<26}{'scans':>6}" + "".join(f"{c:>16}" for c in CODES[1:]) + f"{'échecs':>9}{'cartes':>8}{'hors liste':>11}{'gardées':>9}  dernier succès"
    print(header)
    tot = defaultdict(int)
    shown = 0
    for (source, city, city_id), c in sorted(cities.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        scans = sum(c["codes"].values())
        fails = sum(c["codes"].get(code, 0) for code in FAILURE_OUTCOMES)
        for code, n in c["codes"].items():
            tot[code] += n
        if args.only_failing and fails == 0:
            continue
        shown += 1
        last = ok_dates.get((source, city_id))
        flag = "  ⚠️" if scans and fails / scans >= 0.5 else ""
        print(f"{source:<10}{city[:25]:<26}{scans:>6}" + "".join(f"{c['codes'].get(code, 0):>16}" for code in CODES[1:])
              + f"{fails:>9}{c['cards']:>8}{c['out']:>11}{c['kept']:>9}  {last.strftime('%Y-%m-%d %H:%M') if last else 'jamais'}{flag}")

    total = sum(tot.values())
    total_fail = sum(tot.get(code, 0) for code in FAILURE_OUTCOMES)
    print(f"\nTotal : {total} scan(s), {total_fail} échec(s) ({100 * total_fail / total:.0f} %)" if total else "")
    if args.only_failing and not shown:
        print("Aucune ville en échec sur la période.")
    print("Détail par code : " + ", ".join(f"{code}={tot.get(code, 0)}" for code in CODES))


if __name__ == "__main__":
    main()
