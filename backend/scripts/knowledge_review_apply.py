"""Enregistre tes décisions de relecture (feuille produite par `knowledge_gate_report.py --sheet`).

  python -m backend.scripts.knowledge_review_apply ~/kb_a_relire.txt --dry-run     # montre ce qui serait écrit
  python -m backend.scripts.knowledge_review_apply ~/kb_a_relire.txt               # écrit

Seules les lignes `DECISION: A` (approuvée) et `DECISION: R` (rejetée) sont enregistrées ; `?` ne fait rien. Chaque
décision mémorise l'empreinte du contenu de la fiche : si un réimport change la fiche, l'approbation ne vaut plus
(`guitar_knowledge.review_state`). Les colonnes de relecture sont créées si besoin (idempotent). Une décision se corrige
en la ré-appliquant avec l'autre lettre. Écrit dans la base de production : à lancer avec `DATABASE_URL`.
"""
import argparse
import os
import re
import sys

DECISION_RE = re.compile(r"^DECISION:\s*([ARar?])\s*(.*)$", re.I)
HEADER_RE = re.compile(r"^#\d+\s+(\S+)\s+\|")

DDL = """
ALTER TABLE guitar_knowledge ADD COLUMN IF NOT EXISTS review_status TEXT;
ALTER TABLE guitar_knowledge ADD COLUMN IF NOT EXISTS review_note TEXT;
ALTER TABLE guitar_knowledge ADD COLUMN IF NOT EXISTS reviewed_digest TEXT;
ALTER TABLE guitar_knowledge ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
"""
UPDATE_SQL = """
UPDATE guitar_knowledge SET review_status = %s, review_note = %s, reviewed_at = now(),
       reviewed_digest = md5(concat_ws('|', name, description, active_from::text, active_to::text, parent_id, kind))
WHERE id = %s
"""


def parse_sheet(text):
    """Décisions de la feuille : liste de (id, 'approved'|'rejected', note). Une fiche sans en-tête ou sans décision
    lisible est ignorée ; une ligne DECISION sans fiche au-dessus lève une erreur (feuille abîmée)."""
    out, current = [], None
    for lineno, line in enumerate(text.splitlines(), 1):
        header = HEADER_RE.match(line)
        if header:
            current = header.group(1)
            continue
        m = DECISION_RE.match(line.strip())
        if not m:
            continue
        if current is None:
            raise ValueError(f"ligne {lineno} : DECISION sans fiche au-dessus")
        letter = m.group(1).upper()
        if letter in ("A", "R"):
            out.append((current, "approved" if letter == "A" else "rejected", m.group(2).strip() or None))
        current = None
    ids = [i for i, _, _ in out]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"fiche décidée plusieurs fois : {', '.join(sorted(dup))}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheet")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    with open(os.path.expanduser(args.sheet), encoding="utf-8") as fh:
        decisions = parse_sheet(fh.read())
    if not decisions:
        sys.exit("Aucune décision A ou R dans la feuille : rien à faire.")
    approved = sum(1 for _, s, _ in decisions if s == "approved")
    print(f"{len(decisions)} décision(s) : {approved} approuvée(s), {len(decisions) - approved} rejetée(s).")

    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        known = {r["id"] for r in conn.execute("SELECT id FROM guitar_knowledge WHERE id = ANY(%s)",
                                               ([i for i, _, _ in decisions],))}
        missing = [i for i, _, _ in decisions if i not in known]
        if missing:
            sys.exit(f"Fiches introuvables dans la base : {', '.join(missing)} — feuille d'une autre base ? Rien n'est écrit.")
        if args.dry_run:
            for kid, status, note in decisions:
                print(f"  {status:<9} {kid}  {note or ''}")
            print("--dry-run : rien n'est écrit.")
            return
        conn.execute(DDL)
        for kid, status, note in decisions:
            conn.execute(UPDATE_SQL, (status, note, kid))
        conn.commit()
    print("Décisions enregistrées. Les fiches rejetées ne sont plus servies nulle part ; les approuvées le sont tant que leur contenu ne change pas.")


if __name__ == "__main__":
    main()
