"""Écrit, dans un fichier À PART, les liens des annonces du fichier de `replay_t3` (pour ouvrir les photos et vérifier
à la main ce que les modèles ont vu ou manqué). Lecture seule de la base.

Usage (sur le serveur, `export DATABASE_URL=...`) :
  python -m backend.scripts.replay_t3_links                    # toutes les annonces rejouées -> ~/t3_liens.txt
  python -m backend.scripts.replay_t3_links --contested        # seulement les litigieuses
  python -m backend.scripts.replay_t3_links --out ~/autre.txt

Le fichier contient des liens d'annonces : local, JAMAIS versionné (dépôt GitHub public).
"""
import argparse
import json
import os
import sys

from backend.scripts.replay_t3 import DEFAULT_OUT, is_contested


def format_links(rows, links):
    """Texte du fichier : un bloc par annonce (titre, identifiant, lien), dans l'ordre du fichier de rejeu."""
    blocs = []
    for r in rows:
        title, link = links.get(r["id"], (r.get("title"), None))
        blocs.append(f"{title}\n  id : {r['id']}\n  lien : {link or '(introuvable dans la base)'}")
    return "\n\n".join(blocs) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=DEFAULT_OUT, help="fichier produit par replay_t3")
    ap.add_argument("--contested", action="store_true", help="seulement les annonces où les juges se contredisent")
    ap.add_argument("--out", default="~/t3_liens.txt")
    args = ap.parse_args(argv)

    with open(os.path.expanduser(args.file), encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    if args.contested:
        rows = [r for r in rows if is_contested(r)]
    if not rows:
        sys.exit("Aucune annonce à lister.")

    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.read_only = True
        found = conn.execute("SELECT id, title, link FROM guitar_deals WHERE id = ANY(%s)",
                             ([r["id"] for r in rows],)).fetchall()
    text = format_links(rows, {d["id"]: (d["title"], d["link"]) for d in found})
    out = os.path.expanduser(args.out)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"{len(rows)} annonce(s) écrite(s) dans {out}  (local, ne pas versionner)")


if __name__ == "__main__":
    main()
