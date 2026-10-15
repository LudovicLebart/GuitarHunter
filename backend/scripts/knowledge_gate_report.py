"""Rapport de la PORTE DE QUALITÉ des fiches de la base « univers des guitares » + feuille de relecture.
100 % LECTURE SEULE (connexion `read_only`), aucun appel IA ni réseau, coût 0 $.

  1. RAPPORT : combien de fiches sont servies au Portier, lesquelles la porte écarte d'office (erreurs évidentes) et
     pourquoi, combien restent à relire, quels drapeaux reviennent le plus.
  2. FEUILLE DE RELECTURE (`--sheet`) : les fiches importées les plus souvent TROUVÉES dans tes annonces (ce sont celles
     qui comptent), avec tout ce qu'il faut pour juger en 20 secondes : nom, type, pays, années, parent, description,
     alias, nombre de sources, drapeaux. Tu remplaces `DECISION: ?` par `A` (approuver) ou `R` (rejeter) et tu peux
     ajouter une note ; `knowledge_review_apply.py` enregistre ensuite tes décisions.

Usage (sur le serveur, `export DATABASE_URL=...` ; ces scripts ne lisent pas .env) :
  python -m backend.scripts.knowledge_gate_report                        # rapport seul
  python -m backend.scripts.knowledge_gate_report --sheet ~/kb_a_relire.txt --top 100

La feuille contient des textes de fiches (pas d'annonces, pas d'identifiants d'utilisateurs).
"""
import argparse
import os
import sys
import time
from collections import Counter

from backend import guitar_knowledge as gk

DEFAULT_TOP = 100
# Au-delà, la marque est si répandue (Fender, Yamaha…) que le Portier la connaît déjà : une fiche n'y change rien, et la
# relire ferait perdre du temps sur des fiches « géantes ». Les fiches utiles sont celles des marques OBSCURES.
DEFAULT_MAX_HITS = 100

FICHE_SQL = """
SELECT k.id, k.kind, k.name, k.description, k.countries, k.active_from, k.active_to, k.tier, k.hunt_notes, k.made_by,
       k.curated, k.source, k.confidence, k.parent_id, COALESCE(k.relevance_override, k.relevance) AS relevance,
       EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(k.raw->'origin', '[]'::jsonb)) o
               WHERE o LIKE 'category%%') AS from_maker_category,
       p.name AS parent_name,
       COALESCE((SELECT array_agg(a.alias ORDER BY a.alias) FROM guitar_knowledge_alias a WHERE a.knowledge_id = k.id),
                '{{}}') AS aliases,
       (SELECT count(*) FROM guitar_knowledge_source s WHERE s.knowledge_id = k.id) AS n_sources,
       {review_columns}
FROM guitar_knowledge k LEFT JOIN guitar_knowledge p ON p.id = k.parent_id
"""


def fetch_fiches(conn):
    rows = conn.execute(FICHE_SQL.format(review_columns=gk._review_columns(conn))).fetchall()
    fiches = [dict(r) for r in rows]
    by_id = {f["id"]: f for f in fiches}
    for f in fiches:
        f["parent_matched"] = True          # pas de texte ici : le drapeau « série sans sa marque » ne s'évalue pas
        f["hard"] = gk.hard_failures(f)
        f["flags"] = gk.soft_flags(f)
        f["trusted"] = gk.is_trusted(f)
        f["state"] = gk.review_state(f)
        f["served"] = not f["hard"] and f["trusted"] and f["relevance"] != "accessories"
    return fiches, by_id


def summarize(fiches):
    """Compteurs du rapport (fonction pure)."""
    total = len(fiches)
    hard = [f for f in fiches if f["hard"]]
    reasons = Counter(r.split(" (")[0] for f in hard for r in f["hard"])
    states = Counter(f["state"] or "non relue" for f in fiches)
    flags = Counter(x for f in fiches for x in f["flags"])
    served = [f for f in fiches if f["served"]]
    to_review = [f for f in fiches if not f["hard"] and not f["trusted"] and f["relevance"] != "accessories"]
    return {"total": total, "hard": len(hard), "hard_reasons": reasons, "states": states, "flags": flags,
            "served": len(served), "to_review": len(to_review),
            "trusted": sum(1 for f in fiches if f["trusted"]),
            "by_source": Counter(f["source"] for f in fiches)}


def hit_counts(conn, days=None, examples=None, per=4):
    """Combien d'annonces chaque fiche est trouvée dans (titre + description, recherche du Portier sur toute la base).
    `examples` (dict, optionnel) reçoit pour chaque fiche jusqu'à `per` annonces récentes où elle a été trouvée, avec
    l'alias qui a déclenché la correspondance : de quoi juger la fiche sur pièces (knowledge_review_html.py)."""
    gk.configure_version("latest")
    gk.configure_review_gate(False)
    where, params = "", ()
    if days:
        where, params = "WHERE timestamp >= now() - (%s || ' days')::interval", (str(int(days)),)
    hits = Counter()
    n = 0
    for d in conn.execute(
            "SELECT id, title, description, link, price, storage_image_urls, image_urls FROM guitar_deals "
            f"{where} ORDER BY timestamp DESC", params):
        n += 1
        for kid, (alias, how) in gk.find_ids(conn, d["title"], (d["description"] or "")[:3000]).items():
            hits[kid] += 1
            if examples is not None and len(examples.setdefault(kid, [])) < per:
                examples[kid].append({"deal": d, "alias": alias, "how": how})
    return hits, n


def _years(f):
    if f.get("active_from") or f.get("active_to"):
        return f"{f.get('active_from') or '?'}–{f.get('active_to') or ''}"
    return "non renseignées"


def sheet_block(i, f, n_hits):
    flags = f["hard"] + f["flags"]
    alias = ", ".join((f.get("aliases") or [])[:12]) or "(aucun)"
    desc = " ".join((f.get("description") or "(aucune description)").split())
    return "\n".join([
        f"#{i}  {f['id']}  |  {f['name']}  ({f['kind']})",
        f"   trouvée dans {n_hits} annonce(s) ; sources : {f['n_sources']} ; pertinence : {f['relevance']}",
        f"   pays : {', '.join(f.get('countries') or []) or 'non renseigné'} ; années : {_years(f)} ; "
        f"parent : {f.get('parent_name') or '—'}",
        f"   description : {desc[:600]}",
        f"   alias : {alias}",
        f"   drapeaux : {' ; '.join(flags) or 'aucun'}",
        "DECISION: ?",
        "",
    ])


SHEET_HEAD = """FEUILLE DE RELECTURE DES FICHES — {n} fiches, les plus souvent trouvées dans tes annonces.

Pour chaque fiche, remplace le « ? » de la ligne « DECISION: ? » par :
  A  = approuver (la fiche est juste, elle peut être servie)
  R  = rejeter (erreur : mauvaise entité, homonyme, années fausses, hors sujet…) — la fiche n'est plus servie nulle part
  ?  = ne pas se prononcer (rien n'est enregistré)
Tu peux écrire une note après la lettre : « DECISION: R années fausses, c'est 1957 ».
Critères : bonne entité (pas un homonyme), bon type (marque / série / usine), maison mère, pays, années, alias sans mot
courant, description utile pour reconnaître une guitare. En cas de doute : « ? ».

"""


def review_pool(fiches, hits, max_hits=DEFAULT_MAX_HITS):
    """Fiches à relire : importées, non relues, sans erreur évidente, trouvées dans au moins une annonce mais pas dans
    plus de `max_hits` (les marques géantes, déjà connues du Portier, sont écartées), les plus trouvées d'abord."""
    pool = [f for f in fiches if not f["trusted"] and f["state"] is None and f["relevance"] != "accessories"
            and hits.get(f["id"]) and (not max_hits or hits[f["id"]] <= max_hits)]
    pool.sort(key=lambda f: (-hits[f["id"]], f["name"].lower(), f["id"]))
    return pool


def build_sheet(fiches, hits, top=DEFAULT_TOP, max_hits=DEFAULT_MAX_HITS):
    """Texte de la feuille : voir `review_pool`."""
    pool = review_pool(fiches, hits, max_hits)
    chosen = pool[:top]
    body = "".join(sheet_block(i, f, hits[f["id"]]) for i, f in enumerate(chosen, 1))
    return SHEET_HEAD.format(n=len(chosen)) + body, len(pool)


def print_report(s, n_deals, hits):
    print(f"Fiches : {s['total']} ({', '.join(f'{k} {v}' for k, v in s['by_source'].items())})")
    print(f"  de confiance (relues et approuvées, curées ou écrites à la main) : {s['trusted']}")
    print(f"  SERVIES AU PORTIER avec la porte active                         : {s['served']}")
    print(f"  écartées d'office (erreur évidente ou rejet)                     : {s['hard']}")
    for reason, n in s["hard_reasons"].most_common():
        print(f"      - {reason} : {n}")
    print(f"  à relire (importées, non relues, sans erreur évidente)            : {s['to_review']}")
    print("État de relecture : " + ", ".join(f"{k} {v}" for k, v in s["states"].most_common()))
    if s["flags"]:
        print("Drapeaux : " + " ; ".join(f"{k} {v}" for k, v in s["flags"].most_common()))
    if hits is not None:
        print(f"Annonces examinées : {n_deals} ; fiches trouvées au moins une fois : {len(hits)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", default=None, help="écrit la feuille de relecture dans ce fichier")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP, help="nombre de fiches de la feuille")
    ap.add_argument("--days", type=int, default=None, help="annonces des N derniers jours seulement")
    ap.add_argument("--max-hits", type=int, default=DEFAULT_MAX_HITS,
                    help="écarte les fiches trouvées dans plus de N annonces (marques géantes) ; 0 = aucune limite")
    args = ap.parse_args(argv)

    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.read_only = True
        fiches, _ = fetch_fiches(conn)
        hits, n_deals = hit_counts(conn, args.days) if args.sheet else (None, 0)
        print_report(summarize(fiches), n_deals, hits)
        if args.sheet:
            text, pool = build_sheet(fiches, hits, args.top, args.max_hits)
            path = os.path.expanduser(args.sheet)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"\nFeuille écrite : {path} ({min(args.top, pool)} fiches sur {pool} à relire et trouvées dans tes annonces)")


if __name__ == "__main__":
    main()
