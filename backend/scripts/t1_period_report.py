"""Rapport de mesure du Portier (T1) par période, en lecture seule sur la base de production.

Compare des périodes séparées par des instants de changement (contexte Ollama, prompt…) :
  - T1 : fournisseur, volume, échecs, latence (médiane / P90), tokens d'entrée ;
  - décisions par annonce, rattachées à la période de leur PREMIER appel T1 (jamais à `guitar_deals.timestamp`, qui
    est la date de dernière modification) : rejets, non promues, FAIR, BAD_DEAL, opportunités, part passée en T2.

La base est en UTC ; les instants sont donnés en UTC (ISO, ex. 2026-10-02T13:00Z). Le serveur est en heure de
Montréal (EDT, UTC-4) : 17:17 EDT = 21:17Z.

Usage (sur le serveur, `export DATABASE_URL=...` — ces scripts ne lisent pas `.env`) :
  python -m backend.scripts.t1_period_report
  python -m backend.scripts.t1_period_report --since 2026-09-30 \\
      --cut 2026-10-02T13:00Z "contexte 8192" --cut 2026-10-02T21:17Z "nouveau prompt"

Seules des requêtes SELECT sont émises. Les petits effectifs (< 30 annonces par période) sont signalés : les
écarts ne sont alors pas significatifs.
"""
import argparse
import os
import sys
from datetime import datetime, timezone


DEFAULT_SINCE = "2026-09-30T00:00Z"
DEFAULT_CUTS = [
    ("2026-10-02T13:00Z", "ctx 8192, ancien prompt"),        # dernier appel plafonné à 4096 : 12:55Z
    ("2026-10-02T21:17Z", "ctx 8192, nouveau prompt"),       # 17:17 EDT : clé obsolète retirée de la config
]
FIRST_LABEL = "ctx 4096"
OPPORTUNITY = ("PEPITE", "FAST_FLIP", "LUTHIER_PROJ", "CASE_WIN", "COLLECTION")
MIN_DEALS_SIGNIFICANT = 30


def parse_instant(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def period_label(boundaries, labels, instant):
    """Libellé de la période contenant `instant` (boundaries triées, labels[0] = avant la 1re coupure)."""
    index = sum(1 for b in boundaries if instant >= b)
    return labels[index]


def build_periods(cuts):
    cuts = sorted(((parse_instant(t), name) for t, name in cuts), key=lambda c: c[0])
    return [c[0] for c in cuts], [FIRST_LABEL] + [c[1] for c in cuts]


def _case(column, boundaries, labels):
    """Fragment SQL CASE paramétré (valeurs passées en paramètres, jamais interpolées)."""
    parts = ["CASE"]
    params = []
    for i, boundary in enumerate(boundaries):
        parts.append(f"WHEN {column} < %s THEN %s")
        params += [boundary, labels[i]]
    parts.append("ELSE %s END")
    params.append(labels[-1])
    return " ".join(parts), params


def fetch(conn, sql, params):
    from psycopg.rows import dict_row   # import différé : le module reste importable sans libpq (tests locaux)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def t1_by_period(conn, since, boundaries, labels):
    case, p = _case("created_at", boundaries, labels)
    return fetch(conn, f"""
        SELECT {case} AS periode, provider, count(*) AS n, sum((NOT ok)::int) AS ko,
               round((percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms))::numeric) AS med_ms,
               round((percentile_cont(0.9) WITHIN GROUP (ORDER BY latency_ms))::numeric) AS p90_ms,
               round(avg(input_tokens)::numeric) AS tok_in
        FROM llm_usage WHERE action = 't1_gatekeeper' AND created_at >= %s
        GROUP BY 1, 2 ORDER BY 1, 2""", p + [since])


def deals_by_period(conn, since, boundaries, labels):
    """Une ligne par annonce, rattachée à la période de son PREMIER appel T1 réussi (`llm_usage`).

    `guitar_deals.timestamp` n'est PAS la date de scan : c'est la date de dernière modification (annonce passée en
    « vendue », ré-analyse…), donc inutilisable pour dater une décision du Portier. Le T2 est cherché par annonce
    (`deal_id`), pas par date d'appel : un T2 peut tomber dans une autre période que son T1."""
    case, p = _case("f.t", boundaries, labels)
    return fetch(conn, f"""
        WITH f AS (SELECT deal_id, min(created_at) AS t FROM llm_usage
                   WHERE action = 't1_gatekeeper' AND ok AND deal_id IS NOT NULL AND created_at >= %s
                   GROUP BY deal_id)
        SELECT {case} AS periode, count(*) AS n,
               count(*) FILTER (WHERE g.initial_verdict LIKE 'REJECTED%%') AS rejets,
               count(*) FILTER (WHERE g.initial_verdict = 'NOT_PROMOTED') AS non_promues,
               count(*) FILTER (WHERE g.initial_verdict = 'FAIR') AS fair,
               count(*) FILTER (WHERE g.initial_verdict = 'BAD_DEAL') AS bad_deal,
               count(*) FILTER (WHERE g.initial_verdict = ANY(%s)) AS opportunite,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM llm_usage u
                                              WHERE u.deal_id = f.deal_id AND u.action = 't2_analyst')) AS avec_t2
        FROM f JOIN guitar_deals g ON g.id = f.deal_id
        GROUP BY 1 ORDER BY 1""", [since] + p + [list(OPPORTUNITY)])


def pct(part, whole):
    return f"{100 * part / whole:.0f} %" if whole else "—"


def print_table(title, headers, rows):
    print(f"\n{title}")
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]
    print("  " + "  ".join(str(h).ljust(w) for h, w in zip(headers, widths)))
    for r in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(r, widths)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=DEFAULT_SINCE)
    parser.add_argument("--cut", nargs=2, action="append", metavar=("INSTANT_UTC", "LIBELLE"),
                        help="instant de changement et libellé de la période qui commence ; répétable")
    args = parser.parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL absent (export DATABASE_URL=... ; ces scripts ne lisent pas .env)")

    import psycopg

    boundaries, labels = build_periods(args.cut or DEFAULT_CUTS)
    since = parse_instant(args.since)
    with psycopg.connect(url) as conn:
        conn.read_only = True
        t1 = t1_by_period(conn, since, boundaries, labels)
        deals = deals_by_period(conn, since, boundaries, labels)

    print(f"Périodes (UTC) : " + " | ".join(f"{labels[i]} < {boundaries[i]:%m-%d %H:%M}" for i in range(len(boundaries))) + f" | {labels[-1]}")
    print_table("T1 par fournisseur", ["période", "fournisseur", "n", "échecs", "méd. ms", "P90 ms", "tokens entrée"],
                [(r["periode"], r["provider"], r["n"], r["ko"], r["med_ms"], r["p90_ms"], r["tok_in"]) for r in t1])
    print_table("Décisions du Portier, par annonce (période du 1er appel T1)",
                ["période", "annonces", "rejets", "% rejets", "non promues", "FAIR", "BAD_DEAL", "opportunité", "avec T2", "% T2"],
                [(r["periode"], r["n"], r["rejets"], pct(r["rejets"], r["n"]), r["non_promues"], r["fair"], r["bad_deal"],
                  r["opportunite"], r["avec_t2"], pct(r["avec_t2"], r["n"])) for r in deals])
    small = [r["periode"] for r in deals if r["n"] < MIN_DEALS_SIGNIFICANT]
    if small:
        print(f"\nATTENTION : moins de {MIN_DEALS_SIGNIFICANT} annonces dans {small} — écarts non significatifs.")


if __name__ == "__main__":
    main()
