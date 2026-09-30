"""Carte des trous de la base de connaissances « univers des guitares » (STRATEGIE_IA.md §3.7 étape 2).

Compare les annonces DÉJÀ analysées (table `guitar_deals`) à la base `guitar_knowledge*` et répond à :
  1. COUVERTURE (§3.8) : sur quelle part des annonces la base reconnaît-elle au moins une fiche (marque,
     série, usine) — globalement, et parmi les annonces acceptées / les pépites / les rejets ?
  2. TROUS : quelles marques citées dans tes annonces la base ne connaît PAS, classées par fréquence et par
     nombre de pépites — c'est là que se cachent les bonnes affaires sous des noms obscurs (Yamaha Eterna).
  3. TROUS DE MODÈLES : marque reconnue mais aucune fiche « série/modèle » pour le modèle cité.

100 % LECTURE SEULE : la connexion est ouverte en `read_only`, aucune écriture, aucun appel IA, aucun
appel réseau, coût 0 $. Doit tourner SUR le serveur (la base n'est joignable qu'en localhost), avec le même
`DATABASE_URL` que le bot (le script ne lit PAS `.env` tout seul) :

    export DATABASE_URL="$(grep -h '^DATABASE_URL=' .env | tail -1 | cut -d= -f2- | tr -d '\\r')"
    python backend/scripts/knowledge_coverage.py --csv-out ~/kb_gaps.csv
    python backend/scripts/knowledge_coverage.py --days 180 --top 40 --json-out ~/kb_gaps.json

Le CSV liste TOUS les trous (≥ --min-count annonces) avec des exemples de titres et de liens : c'est la
liste de travail pour l'élargissement de la base (sources, curation). Rien n'est ajouté à la base ici.
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend import guitar_knowledge as gk  # noqa: E402

# Valeurs qui ne désignent aucune marque (sorties « je ne sais pas » du Portier ou de l'Analyste).
SKIP_BRANDS = {
    "", "n a", "na", "none", "null", "unknown", "inconnu", "inconnue", "generic", "generique", "aucune",
    "autre", "other", "non specifie", "non identifie", "non identifiee", "sans marque", "no brand",
    "unbranded", "no name", "noname", "guitare", "guitar", "bass", "basse", "acoustic", "electric",
    "unidentified", "indetermine", "indeterminee", "a determiner", "vintage", "custom",
}
ORG_KINDS = {"company", "brand", "factory", "line"}        # ce qui compte comme « la base connaît cette marque »
GEM_VERDICTS = {"PEPITE", "FAST_FLIP", "LUTHIER_PROJ", "CASE_WIN", "COLLECTION"}   # verdicts « bonne affaire »
# Type probable d'un « trou », d'après les titres de ses annonces : la plupart des trous ne sont pas des marques
# de guitares (accordeurs, amplis, pédales, jeux vidéo) et noient les vraies marques à chercher.
TITLE_TYPES = (
    ("jeu video", re.compile(r"guitar hero|rock ?band|xbox|playstation|\bps[2345]\b|\bwii\b|nintendo|manette|controller")),
    ("ampli", re.compile(r"\bamplis?\b|amplificateur|amplifier|\bamp\b|combo")),
    ("pedale/effet", re.compile(r"p[ée]dale|pedal|overdrive|distortion|delay|reverb|chorus|fuzz|wah|multi-?effets?|looper")),
    ("accessoire", re.compile(r"accordeur|tuner|\bcapo\b|\bstand\b|support|sangle|strap|c[âa]ble|cable|m[ée]diator|\bpicks?\b|\bcordes?\b|strings")),
)
NON_GUITAR_SHARE = 0.5      # un trou est « probablement pas une guitare » si ≥ 50 % de ses titres sont d'un même type
SAMPLES_TITLES = 3
SAMPLES_LINKS = 2

QUERY = """
SELECT id, title, COALESCE(NULLIF(brand, ''), NULLIF(gatekeeper_brand, '')) AS brand_any,
       model_name, status, verdict, price, link
FROM guitar_deals
{where}
"""


def clean_brand(raw):
    """Marque normalisée (minuscules, sans accents ni ponctuation) ou None si ce n'est pas une marque."""
    norm = gk.normalize(raw)
    if not norm or norm in SKIP_BRANDS or norm.replace(" ", "").isdigit():
        return None
    return norm


def group_of(row):
    """gem = bonne affaire ; rejected = écartée ; accepted = analysée sans être une pépite."""
    if (row.get("verdict") or "") in GEM_VERDICTS:
        return "gem"
    return "rejected" if row.get("status") == "rejected" else "accepted"


def title_type(title):
    t = (title or "").lower()
    for label, pattern in TITLE_TYPES:
        if pattern.search(t):
            return label
    return "guitare/autre"


def _kinds_seen(found, kinds):
    return {kinds.get(k) for k in found}


def _new_stats():
    return {"n": 0, "gem": 0, "pepite": 0, "accepted": 0, "rejected": 0, "prices": [], "variants": Counter(),
            "forms": Counter(), "types": Counter(), "titles": [], "links": []}


def _add(stats, row, group, raw_variant, form):
    stats["n"] += 1
    stats[group] += 1
    stats["pepite"] += 1 if (row.get("verdict") or "") == "PEPITE" else 0
    stats["forms"][form] += 1
    stats["types"][title_type(row.get("title"))] += 1
    if row.get("price") is not None:
        try:
            stats["prices"].append(float(row["price"]))
        except (TypeError, ValueError):
            pass
    stats["variants"][raw_variant] += 1
    title = (row.get("title") or "").strip()
    if title and title not in stats["titles"] and len(stats["titles"]) < SAMPLES_TITLES:
        stats["titles"].append(title)
    link = row.get("link")
    if link and link not in stats["links"] and len(stats["links"]) < SAMPLES_LINKS:
        stats["links"].append(link)


def _probable_type(stats):
    label, count = next(((t, c) for t, c in stats["types"].most_common() if t != "guitare/autre"), (None, 0))
    return label if label and count / stats["n"] >= NON_GUITAR_SHARE else "guitare/autre"


def _finalize(key, stats):
    prices = stats["prices"]
    brand = stats["forms"].most_common(1)[0][0]      # forme la plus fréquente (« carmelo catania » et « catania carmelo » fusionnés)
    return {
        "brand": brand,
        **({"model": key[1]} if not isinstance(key, str) else {}),
        "probable_type": _probable_type(stats),
        "n_listings": stats["n"], "n_gems": stats["gem"], "n_pepites": stats["pepite"], "n_accepted": stats["accepted"],
        "n_rejected": stats["rejected"],
        "median_price": round(statistics.median(prices)) if prices else None,
        "variants": [v for v, _ in stats["variants"].most_common(5)],
        "sample_titles": stats["titles"], "sample_links": stats["links"],
    }


def _sorted_key(norm):
    return " ".join(sorted(norm.split()))


def analyze(rows, kinds, find, min_count=2, accessory_brands=frozenset()):
    """`kinds` : {id de fiche: kind} ; `find(*textes)` : {id de fiche: (alias, 'exact'|'fuzzy')} (voir
    `guitar_knowledge.find_ids`). `accessory_brands` : alias normalisés des fiches classées « accessories »
    (D'Addario, Line 6...) : connues de la base, donc PAS des trous (mais jamais injectées au Portier).
    Séparé de la base pour être testable sans Postgres."""
    listing_cov = defaultdict(lambda: Counter())     # groupe -> {total, recognized}
    brand_cov = Counter()                            # total / exact / fuzzy / missing
    gaps, model_gaps = defaultdict(_new_stats), defaultdict(_new_stats)

    for row in rows:
        group = group_of(row)
        title, brand_raw, model = row.get("title") or "", row.get("brand_any") or "", row.get("model_name") or ""

        found = find(title, brand_raw, model)
        listing_cov[group]["total"] += 1
        listing_cov["all"]["total"] += 1
        if ORG_KINDS & _kinds_seen(found, kinds):
            listing_cov[group]["recognized"] += 1
            listing_cov["all"]["recognized"] += 1

        brand = clean_brand(brand_raw)
        if not brand:
            brand_cov["no_brand"] += 1
            continue
        brand_cov["total"] += 1
        if brand in accessory_brands:
            brand_cov["known_accessory"] += 1
            continue
        brand_found = find(brand_raw)
        org_matches = {k: v for k, v in brand_found.items() if kinds.get(k) in ORG_KINDS}
        if not org_matches:
            brand_cov["missing"] += 1
            _add(gaps[_sorted_key(brand)], row, group, brand_raw.strip(), brand)
            continue
        brand_cov["fuzzy_only" if all(t == "fuzzy" for _, t in org_matches.values()) else "exact"] += 1

        model_norm = gk.normalize(model)
        if model_norm and model_norm not in SKIP_BRANDS and not model_norm.replace(" ", "").isdigit():
            line_found = find(f"{brand_raw} {model}", title)
            if "line" not in _kinds_seen(line_found, kinds):
                _add(model_gaps[(_sorted_key(brand), model_norm)], row, group,
                     f"{brand_raw.strip()} {model.strip()}", brand)

    def rank(d):
        out = [_finalize(k, s) for k, s in d.items() if s["n"] >= min_count]
        return sorted(out, key=lambda g: (-g["n_gems"], -g["n_listings"], g["brand"]))

    return {
        "total_listings": listing_cov["all"]["total"],
        "listing_coverage": {g: {"total": c["total"], "recognized": c["recognized"]} for g, c in listing_cov.items()},
        "brands": dict(brand_cov),
        "gaps": rank(gaps),
        "gaps_by_frequency": sorted(rank(gaps), key=lambda g: (-g["n_listings"], -g["n_gems"], g["brand"])),
        "model_gaps": sorted(rank(model_gaps), key=lambda g: (-g["n_listings"], -g["n_gems"], g["brand"])),
    }


def load_rows(conn, days=None):
    where, params = "", ()
    if days:
        where, params = 'WHERE "timestamp" >= now() - make_interval(days => %s)', (days,)
    return conn.execute(QUERY.format(where=where), params).fetchall()


def load_kinds(conn):
    return {r["id"]: r["kind"] for r in conn.execute("SELECT id, kind FROM guitar_knowledge").fetchall()}


def load_accessory_aliases(conn):
    return {r["alias_norm"] for r in conn.execute(
        """SELECT a.alias_norm FROM guitar_knowledge_alias a JOIN guitar_knowledge k ON k.id = a.knowledge_id
           WHERE COALESCE(k.relevance_override, k.relevance) = 'accessories'""").fetchall()}


def run_analysis(conn, days=None, min_count=2):
    rows = load_rows(conn, days)
    kinds = load_kinds(conn)
    report = analyze(rows, kinds, lambda *texts: gk.find_ids(conn, *texts), min_count=min_count,
                     accessory_brands=load_accessory_aliases(conn))
    report["kb_fiches"] = len(kinds)
    return report


def _pct(part, whole):
    return f"{100 * part / whole:5.1f} %" if whole else "   n/a"


def print_report(report, top=30, all_types=False):
    total = report["total_listings"]
    print(f"Annonces analysées : {total}   |   fiches dans la base : {report['kb_fiches']}")
    print("\n== 1. COUVERTURE : annonces où la base reconnaît au moins une marque/série ==")
    labels = {"all": "toutes", "gem": "pépites", "accepted": "acceptées (hors pépites)", "rejected": "rejetées"}
    for g in ("all", "gem", "accepted", "rejected"):
        c = report["listing_coverage"].get(g)
        if c:
            print(f"  {labels[g]:26s} {c['recognized']:5d} / {c['total']:5d}   {_pct(c['recognized'], c['total'])}")
    b = report["brands"]
    if b.get("total"):
        print(f"\n  Marques citées par les annonces : {b['total']} (hors « inconnu », {b.get('no_brand', 0)} sans marque)")
        print(f"    reconnues : {b.get('exact', 0)} ({_pct(b.get('exact', 0), b['total']).strip()})"
              f", seulement approximatives : {b.get('fuzzy_only', 0)}"
              f", connues comme accessoires/amplis (jamais injectées) : {b.get('known_accessory', 0)}"
              f", ABSENTES de la base : {b.get('missing', 0)} ({_pct(b.get('missing', 0), b['total']).strip()})")

    def table(title, items, with_model=False, all_types=False):
        shown = items if all_types else [g for g in items if g["probable_type"] == "guitare/autre"]
        hidden = len(items) - len(shown)
        print(f"\n{title}")
        if not shown:
            print("  (rien à signaler)")
        else:
            head = (f"  {'marque':24s}" + (f"{'modèle':22s}" if with_model else "") +
                    f"{'annonces':>9s}{'PEPITE':>7s}{'aff.':>6s}{'acc.':>6s}{'rej.':>6s}{'prix méd.':>10s}  exemple")
            print(head)
            for g in shown[:top]:
                price = f"{g['median_price']} $" if g["median_price"] is not None else "-"
                print(f"  {g['brand'][:23]:24s}" + (f"{g['model'][:21]:22s}" if with_model else "") +
                      f"{g['n_listings']:9d}{g['n_pepites']:7d}{g['n_gems']:6d}{g['n_accepted']:6d}{g['n_rejected']:6d}{price:>10s}  "
                      f"{(g['sample_titles'] or [''])[0].splitlines()[0][:60]}")
        if hidden:
            kinds_hidden = Counter(g["probable_type"] for g in items if g["probable_type"] != "guitare/autre")
            print(f"  ({hidden} masqués car probablement pas des guitares : "
                  + ", ".join(f"{k} {v}" for k, v in kinds_hidden.most_common()) + " — voir --all-types / le CSV)")

    print("\n  Colonnes : PEPITE = verdict PEPITE ; aff. = « bonnes affaires » (PEPITE, FAST_FLIP, LUTHIER_PROJ, CASE_WIN, COLLECTION)")
    with_gems = [g for g in report["gaps"] if g["n_gems"]]
    table("== 2a. TROUS À PRIORITÉ HAUTE : marques absentes de la base où tu as trouvé des bonnes affaires ==", with_gems, all_types=all_types)
    table("== 2b. TROUS LES PLUS FRÉQUENTS : marques absentes de la base (toutes annonces) ==",
          report["gaps_by_frequency"], all_types=all_types)
    table("== 3. TROUS DE MODÈLES : marque connue, mais aucune fiche de série/modèle pour le modèle cité ==",
          report["model_gaps"], with_model=True, all_types=all_types)


def write_csv(report, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["type", "probable_type", "brand", "model", "n_listings", "n_pepites", "n_gems", "n_accepted",
                    "n_rejected", "median_price", "variants", "sample_titles", "sample_links", "decision"])
        for typ, items in (("marque_absente", report["gaps_by_frequency"]), ("modele_absent", report["model_gaps"])):
            for g in items:
                w.writerow([typ, g["probable_type"], g["brand"], g.get("model", ""), g["n_listings"], g["n_pepites"],
                            g["n_gems"], g["n_accepted"], g["n_rejected"], g["median_price"] if g["median_price"] is not None else "",
                            " | ".join(g["variants"]), " | ".join(t.replace("\n", " ") for t in g["sample_titles"]),
                            " | ".join(g["sample_links"]),
                            ""])   # colonne « decision » à remplir à la main (ajouter / ignorer / déjà connu sous un autre nom)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=None, help="limiter aux annonces des N derniers jours")
    ap.add_argument("--min-count", type=int, default=2, help="n'afficher que les trous vus dans au moins N annonces")
    ap.add_argument("--top", type=int, default=30, help="lignes affichées par tableau (le CSV contient tout)")
    ap.add_argument("--all-types", action="store_true",
                    help="afficher aussi les trous probablement pas des guitares (accordeurs, amplis, pédales, jeux vidéo)")
    ap.add_argument("--csv-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL non défini : ce script ne lit pas .env. Voir l'en-tête du fichier pour la commande.")
    import psycopg
    from psycopg.rows import dict_row
    conn = psycopg.connect(url, row_factory=dict_row)
    conn.read_only = True        # garantie : aucune écriture possible dans cette session
    try:
        report = run_analysis(conn, days=args.days, min_count=args.min_count)
    finally:
        conn.close()
    print_report(report, args.top, args.all_types)
    if args.csv_out:
        write_csv(report, os.path.expanduser(args.csv_out))
        print(f"\nCSV écrit : {args.csv_out} ({len(report['gaps_by_frequency'])} marques absentes, "
              f"{len(report['model_gaps'])} modèles absents)")
    if args.json_out:
        with open(os.path.expanduser(args.json_out), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"JSON écrit : {args.json_out}")


if __name__ == "__main__":
    main()
