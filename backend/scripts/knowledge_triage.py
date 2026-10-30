"""Tri AUTOMATIQUE des fiches de la base « univers des guitares », par RÈGLES (aucun appel IA, aucun coût).

Les fiches importées de Wikipédia/Wikidata sont fiables dans leur grande majorité : ce qui compte, c'est d'écarter les
cas où l'import a pu se tromper de personne ou de sujet. Chaque fiche tombe dans UNE catégorie :

  saine       importée de la catégorie des fabricants de guitares, pertinence « guitares », pays renseigné (ou série avec
              sa marque mère), aucun alias partagé avec une fiche sans lien de parenté, aucune erreur évidente.
              → approuvée automatiquement par `apply` (note « règles, sans IA », empreinte du contenu : si un réimport
              change la fiche, l'approbation tombe).
  à vérifier  au moins une raison de doute (affichée) : hors catégorie de fabricants, pertinence incertaine, pays absent,
              alias partagé, série sans marque mère, luthier non curé.
  fausse      erreur évidente (années incohérentes, description sans rapport) : déjà écartée par la porte de qualité.
  déjà traitée / hors sujet (accessoires) : ignorées.
En plus, `creuse` (description trop pauvre) est un drapeau à part : une fiche saine peut être creuse (elle est exacte mais
dit peu) ; `export` liste les creuses utiles pour qu'on les remplisse avec des sources.

  python -m backend.scripts.knowledge_triage report                      # les chiffres, lecture seule
  python -m backend.scripts.knowledge_triage apply --dry-run             # ce qui serait approuvé
  python -m backend.scripts.knowledge_triage apply                       # écrit (jamais sur une fiche déjà décidée)
  python -m backend.scripts.knowledge_triage export --out ~/kb_export.json    # les « à vérifier » + les creuses, sans annonces

Serveur : `export DATABASE_URL=...` (ces scripts ne lisent pas .env). L'export ne contient que des faits de fiches
(aucun titre d'annonce, aucun identifiant d'utilisateur).
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

from backend import guitar_knowledge as gk
from backend.scripts import knowledge_gate_report as rep
from backend.scripts import knowledge_review_apply as apply_

SAFE, CHECK, FALSE, DONE, OFFTOPIC = "saine", "à vérifier", "fausse", "déjà traitée", "hors sujet"
SOURCES_OK = {"wikidata", "wikipedia"}
UPDATE_AUTO_SQL = apply_.UPDATE_SQL.rstrip() + " AND review_status IS NULL"
AUTO_NOTE = "auto (règles, sans IA) : importée de la catégorie des fabricants de guitares, fiche cohérente"


def alias_owners(fiches):
    """{alias normalisé: {ids de fiches}} sur toute la base."""
    owners = defaultdict(set)
    for f in fiches:
        for a in f.get("aliases") or []:
            owners[gk.normalize(a)].add(f["id"])
        owners[gk.normalize(f["name"])].add(f["id"])
    return owners


def shared_with_strangers(f, by_id, owners):
    """Alias de `f` portés aussi par une fiche SANS lien de parenté (ni parent, ni enfant) : risque d'homonyme."""
    shared = []
    for a in set([gk.normalize(x) for x in (f.get("aliases") or [])] + [gk.normalize(f["name"])]):
        for other_id in owners.get(a, ()):
            if other_id == f["id"]:
                continue
            other = by_id[other_id]
            if f.get("parent_id") == other_id or other.get("parent_id") == f["id"]:
                continue
            if f.get("parent_id") and f.get("parent_id") == other.get("parent_id"):
                continue                                     # même maison mère : même famille
            shared.append(f"« {a} » aussi sur « {other['name']} »")
    return sorted(set(shared))


def triage(f, by_id, owners):
    """(catégorie, raisons). Fonction pure sur une fiche telle que renvoyée par `knowledge_gate_report.fetch_fiches`
    (+ `parent_id` et `from_maker_category`)."""
    if f["state"] is not None or f["trusted"]:
        return DONE, []
    if f["relevance"] == "accessories":
        return OFFTOPIC, []
    if f["hard"]:
        return FALSE, list(f["hard"])
    reasons = []
    is_line = f["kind"] == "line"
    if f.get("source") not in SOURCES_OK:
        reasons.append("fiche non importée de Wikipédia/Wikidata")
    if not is_line and not f.get("from_maker_category"):
        reasons.append("hors catégorie des fabricants de guitares")
    if f["relevance"] != "guitars":
        reasons.append(f"pertinence {f['relevance']}")
    if is_line and not f.get("parent_id"):
        reasons.append("série sans marque mère")
    if not is_line and not f.get("countries"):
        reasons.append("pays absent")
    if f["kind"] == "luthier":
        reasons.append("luthier non curé")
    reasons += [f"alias partagé : {s}" for s in shared_with_strangers(f, by_id, owners)[:3]]
    return (CHECK, reasons) if reasons else (SAFE, [])


def is_sparse(f):
    return "fiche creuse" in f["flags"]


def run_triage(conn):
    fiches, by_id = rep.fetch_fiches(conn)
    owners = alias_owners(fiches)
    out = []
    for f in fiches:
        cat, reasons = triage(f, by_id, owners)
        out.append((f, cat, reasons))
    return out


def summarize(rows, hits=None):
    cats = Counter(c for _, c, _ in rows)
    reasons = Counter(r.split(" : ")[0] for _, c, rs in rows if c == CHECK for r in rs)
    sparse = [f for f, c, _ in rows if c in (SAFE, CHECK) and is_sparse(f)]
    out = {"total": len(rows), "categories": cats, "reasons": reasons, "sparse": len(sparse)}
    if hits is not None:
        out["found"] = {c: sum(1 for f, cc, _ in rows if cc == c and hits.get(f["id"])) for c in (SAFE, CHECK)}
        out["sparse_found"] = sum(1 for f in sparse if hits.get(f["id"]))
    return out


def print_summary(s):
    print(f"Fiches : {s['total']}")
    for cat in (SAFE, CHECK, FALSE, DONE, OFFTOPIC):
        extra = f" (dont {s['found'][cat]} trouvées dans tes annonces)" if "found" in s and cat in s["found"] else ""
        print(f"  {cat:<13}: {s['categories'].get(cat, 0)}{extra}")
    if s["reasons"]:
        print("Raisons des « à vérifier » (une fiche peut en cumuler) :")
        for reason, n in s["reasons"].most_common():
            print(f"      - {reason} : {n}")
    sf = f" (dont {s['sparse_found']} trouvées dans tes annonces)" if "sparse_found" in s else ""
    print(f"Fiches creuses (saines ou à vérifier) : {s['sparse']}{sf}")


def apply_safe(conn, rows, dry_run=False, log=print):
    ids = [f["id"] for f, c, _ in rows if c == SAFE]
    if not dry_run:
        conn.execute(apply_.DDL)
        for kid in ids:
            conn.execute(UPDATE_AUTO_SQL, ("approved", AUTO_NOTE, kid))
        conn.commit()
    log(f"{len(ids)} fiche(s) saine(s) {'qui seraient approuvées' if dry_run else 'approuvée(s)'} "
        f"(celles déjà décidées ne sont jamais touchées).")
    return ids


def export_rows(conn, rows, hits, min_hits=1):
    """Fiches « à vérifier » et creuses utiles, faits seulement, les plus trouvées d'abord."""
    sources = {}
    for r in conn.execute("SELECT knowledge_id, url, title, publisher FROM guitar_knowledge_source ORDER BY id"):
        sources.setdefault(r["knowledge_id"], []).append({k: r[k] for k in ("url", "title", "publisher")})
    out = []
    for f, cat, reasons in rows:
        if hits.get(f["id"], 0) < min_hits:
            continue
        if cat == DONE and f["state"] in ("approved", "stale") and is_sparse(f):
            cat = "approuvée"                    # saine, déjà approuvée, mais creuse : à remplir
        if cat not in (SAFE, CHECK, "approuvée"):
            continue
        if cat in (SAFE, "approuvée") and not is_sparse(f):
            continue
        out.append({"id": f["id"], "category": cat, "reasons": reasons, "creuse": is_sparse(f), "n_hits": hits[f["id"]],
                    "name": f["name"], "kind": f["kind"], "description": f.get("description"),
                    "countries": f.get("countries") or [], "active_from": f.get("active_from"),
                    "active_to": f.get("active_to"), "parent": f.get("parent_name"),
                    "aliases": (f.get("aliases") or [])[:20], "source": f.get("source"),
                    "sources": sources.get(f["id"], [])})
    out.sort(key=lambda x: (-x["n_hits"], x["name"].lower()))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    a = sub.add_parser("apply")
    a.add_argument("--dry-run", action="store_true")
    e = sub.add_parser("export")
    e.add_argument("--out", default="~/kb_export.json")
    e.add_argument("--min-hits", type=int, default=1)
    args = ap.parse_args(argv)

    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        if args.cmd != "apply":
            conn.read_only = True
        rows = run_triage(conn)
        if args.cmd == "apply":
            apply_safe(conn, rows, args.dry_run)
            return
        hits, _n = rep.hit_counts(conn)
        print_summary(summarize(rows, hits))
        if args.cmd == "export":
            data = export_rows(conn, rows, hits, args.min_hits)
            path = os.path.expanduser(args.out)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            print(f"\nExport écrit : {path} ({len(data)} fiches : "
                  f"{sum(1 for x in data if x['category'] == CHECK)} à vérifier, "
                  f"{sum(1 for x in data if x['creuse'])} creuses). Aucune annonce dedans.")


if __name__ == "__main__":
    main()
