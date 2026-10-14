"""Relit le fichier de `replay_t3` (sans aucun appel payant) et montre, annonce par annonce, ce que chaque modèle a
répondu à chaque passage et ce que les juges leur reprochent — pour VÉRIFIER À LA MAIN les annonces litigieuses
sans avoir à annoter les autres.

Usage :
  python -m backend.scripts.replay_t3_digest --contested        # seulement les annonces où les juges se contredisent
  python -m backend.scripts.replay_t3_digest                    # toutes
  python -m backend.scripts.replay_t3_digest --ids a,b --file ~/t3_essai.jsonl

Affiche des titres d'annonces : local, ne pas versionner ni copier dans le dépôt public.
"""
import argparse
import json
import os

from backend.scripts.replay_t3 import AXES, DEFAULT_OUT, MODELS, is_contested

FIELDS = ("brand", "model_name", "production_year", "verdict", "deal_score", "estimated_value")
MAX_ERR = 4
ERR_CHARS = 220
EXPL_CHARS = 320


def short(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def run_line(result):
    if not result:
        return "(échec)"
    return " | ".join(f"{k}={result.get(k)}" for k in FIELDS)


def digest_row(row):
    """Texte lisible pour UNE annonce du fichier de rejeu."""
    out = [f"== {row['id']}  {row.get('title')}" + ("   [LITIGIEUSE]" if is_contested(row) else "")]
    for m in MODELS:
        runs = row["runs"].get(m, [])
        tag = " (réponse déjà stockée en production)" if row.get("gemini_stored") and m == "gemini" else ""
        for i, run in enumerate(runs, 1):
            out.append(f"  {m:<6} #{i}{tag}: {run_line(run.get('result'))}")
    for jname, js in row.get("judgments", {}).items():
        for j in js:
            axes = " ".join(f"{a[:5]}={j.get(a, '?')}" for a in AXES)
            out.append(f"  juge {jname:<6} → global: {j.get('overall', '?'):<6} ({axes})")
            if j.get("explanation"):
                out.append(f"      « {short(j['explanation'], EXPL_CHARS)} »")
    # erreurs relevées, tous jugements confondus, sans doublon
    for m in MODELS:
        seen, errs = set(), []
        for js in row.get("judgments", {}).values():
            for j in js:
                for e in (j.get("errors") or {}).get(m, []):
                    key = short(e, 80).lower()
                    if key not in seen:
                        seen.add(key)
                        errs.append(e)
        if errs:
            out.append(f"  erreurs reprochées à {m} :")
            out.extend(f"    - {short(e, ERR_CHARS)}" for e in errs[:MAX_ERR])
            if len(errs) > MAX_ERR:
                out.append(f"    (+{len(errs) - MAX_ERR} autres dans le fichier)")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=DEFAULT_OUT)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--contested", action="store_true", help="seulement les annonces où les juges se contredisent")
    args = ap.parse_args(argv)
    with open(os.path.expanduser(args.file), encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    if args.ids:
        wanted = set(args.ids.split(","))
        rows = [r for r in rows if r["id"] in wanted]
    if args.contested:
        rows = [r for r in rows if is_contested(r)]
    for r in rows:
        print(digest_row(r), end="\n\n")
    print(f"{len(rows)} annonce(s).")


if __name__ == "__main__":
    main()
