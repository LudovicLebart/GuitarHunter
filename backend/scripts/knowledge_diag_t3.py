"""Diagnostic EN LECTURE SEULE de la base de marques sur des annonces : que verrait le Portier (recherche par le titre
et la description) et que renverrait l'outil `lookup_brand` de l'Expert Claude (recherche par ce que le modèle lit) ?
Aucun appel payant, aucune écriture.

Usage (sur le serveur, `export DATABASE_URL=...` ; ces scripts ne lisent pas .env) :
  python -m backend.scripts.knowledge_diag_t3                         # annonces du fichier de rejeu
  python -m backend.scripts.knowledge_diag_t3 --ids a,b,c             # annonces choisies
  python -m backend.scripts.knowledge_diag_t3 --query "carmelo catania" --query "guerilla"   # texte libre, sans annonce
  python -m backend.scripts.knowledge_diag_t3 --read ID="texte lu sur la tête de manche"     # simule ce que le modèle lirait

Affiche des titres d'annonces : sortie locale, ne pas versionner (dépôt GitHub public).
"""
import argparse
import json
import os
import sys

from backend import guitar_knowledge as gk
from backend.scripts.replay_t3 import DEFAULT_OUT

MAX_DESC = 3000


def portier_view(conn, title, description):
    """Fiches que le Portier recevrait (version validée, puis toute la base) : {mode: [(nom, alias, type)]}."""
    out = {}
    for mode in ("validated", "latest"):
        gk.configure_version(mode)
        found = gk.lookup(conn, title, (description or "")[:MAX_DESC], limit=3)
        out[mode] = [(f["name"], f["matched_on"], f["match_type"]) for f in found]
    gk.configure_version("validated")
    return out


def tool_view(conn, text):
    return [(r["name"], r["match_type"], r["score"], r["unverified_reasons"]) for r in gk.search_brand(conn, text)]


def report_listing(conn, deal, reads):
    lines = [f"== {deal['id']}  {deal['title']}"]
    pv = portier_view(conn, deal["title"], deal.get("description"))
    for mode, label in (("validated", "Portier, version validée"), ("latest", "Portier, toute la base")):
        shown = ", ".join(f"{n} [{a}, {t}]" for n, a, t in pv[mode]) or "aucune fiche"
        lines.append(f"  {label:<26}: {shown}")
    queries = {"titre": deal["title"] or ""}
    queries.update({f"lu: {r}": r for r in reads})
    for label, text in queries.items():
        res = tool_view(conn, text)
        shown = "; ".join(f"{n} [{t} {s:.2f}{' NON VÉRIFIÉE: ' + ' / '.join(rs) if rs else ''}]"
                          for n, t, s, rs in res) or "aucune fiche"
        lines.append(f"  lookup_brand({label[:40]!r}): {shown}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=DEFAULT_OUT, help="fichier produit par replay_t3 (si --ids absent)")
    ap.add_argument("--ids", default=None)
    ap.add_argument("--query", action="append", default=[], help="texte libre à soumettre à lookup_brand")
    ap.add_argument("--read", action="append", default=[], metavar="ID=TEXTE",
                    help="texte supposé lu sur les photos de l'annonce ID (répétable)")
    args = ap.parse_args(argv)

    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")

    reads = {}
    for item in args.read:
        key, sep, text = item.partition("=")
        if not sep or not text.strip():
            sys.exit(f"--read attend ID=TEXTE, reçu : {item!r}")
        reads.setdefault(key.strip(), []).append(text.strip())

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.read_only = True
        for q in args.query:
            res = tool_view(conn, q)
            print(f"lookup_brand({q!r}) -> " + ("; ".join(f"{n} [{t} {s:.2f}"
                  f"{' NON VÉRIFIÉE' if rs else ''}]" for n, t, s, rs in res) or "aucune fiche"))
        ids = args.ids.split(",") if args.ids else None
        if ids is None and not args.query:
            with open(os.path.expanduser(args.file), encoding="utf-8") as fh:
                ids = [json.loads(line)["id"] for line in fh if line.strip()]
        if ids:
            deals = {d["id"]: d for d in conn.execute(
                "SELECT id, title, description FROM guitar_deals WHERE id = ANY(%s)", (ids,)).fetchall()}
            for i in ids:
                if i in deals:
                    print(report_listing(conn, deals[i], reads.get(i, [])), end="\n\n")
                else:
                    print(f"== {i}  (introuvable dans la base)\n")


if __name__ == "__main__":
    main()
