"""Repère, dans la base de production, les annonces où l'utilisateur a laissé une trace humaine — des candidates à une
VÉRITÉ TERRAIN pour comparer les modèles (rejeu Expert Gemini contre Claude, voir `COST_OPTIMIZATION_CHANTIERS.md`
Chantier F : la vérité terrain ne doit PAS être la sortie de Gemini lui-même).

Signaux, du plus fort au plus faible (le score est la somme des poids) :
  override    la fiche a été corrigée À LA MAIN (`manual_analysis_overrides` ou `manual_classification`)        5
  requal      une requalification proposée par le chat a été ACCEPTÉE (`requalification_proposal.status`)      4
  purchased   guitare achetée                                                                                  3
  rescued     rejetée par le Portier puis analyse FORCÉE (`gatekeeperVerdict` = MANUAL_RETRY) : le Portier avait tort  2
  chat        au moins 3 messages de l'utilisateur dans le chat de l'annonce (1 ou 2 : poids 1)               2
  favorite    mise en favori                                                                                   1
Un signal ne dit PAS que l'IA avait tort : il dit que l'utilisateur sait quelque chose sur cette annonce. C'est à lui
d'écrire la vérité terrain, en s'aidant de ses propres messages de chat (affichés ci-dessous).

Usage (sur le serveur, `export DATABASE_URL=...` — ces scripts ne lisent pas `.env`) :
  python -m backend.scripts.truth_candidates
  python -m backend.scripts.truth_candidates --limit 12 --t3-only

Lecture seule : la connexion est ouverte en `read_only`, seules des requêtes SELECT sont émises. Le fichier produit
(`backend/scripts/data/truth_candidates.jsonl`) contient titres, liens et extraits de chat : il est dans `.gitignore`
et ne doit JAMAIS être versionné (dépôt GitHub public).
"""
import argparse
import json
import os
import sys

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "data", "truth_candidates.jsonl")
EXCERPT_CHARS = 400
EXCERPTS_PER_DEAL = 3

# Poids des signaux ; l'ordre est celui de l'affichage.
WEIGHTS = {"override": 5, "requal": 4, "purchased": 3, "rescued": 2, "chat": 2, "favorite": 1}
T1_REJECTED = ("REJECTED_ITEM", "REJECTED_SERVICE")
FORCED_ANALYSIS = "MANUAL_RETRY"  # écrase `ai_analysis_raw.gatekeeperVerdict` quand l'utilisateur force l'analyse
# Hors sujet pour juger un expert en guitares : étuis et amplis (racines de la taxonomie), sauf `--with-accessories`.
ACCESSORY_ROOTS = ("etui_housse", "amplificateur")

_CANDIDATES_SQL = """
WITH chat AS (
    SELECT deal_id,
           count(*) FILTER (WHERE role = 'user' AND NOT is_error)                AS user_msgs,
           count(*)                                                              AS msgs,
           COALESCE(bool_or(requalification_proposal->>'status' = 'applied'), false) AS requal_applied
    FROM deal_chat GROUP BY deal_id
), fav AS (
    SELECT deal_id, bool_or(is_favorite) AS favorite FROM user_deal_state GROUP BY deal_id
)
SELECT d.id, d.title, d.link, d.status, d.verdict, d.initial_verdict, d.model_used, d.tier3_trigger,
       d.classification, d.manual_classification, d.ai_analysis_raw->>'gatekeeperVerdict' AS gatekeeper_final, d.manual_analysis_overrides, d.is_purchased,
       COALESCE(c.user_msgs, 0) AS user_msgs, COALESCE(c.msgs, 0) AS msgs,
       COALESCE(c.requal_applied, false) AS requal_applied, COALESCE(f.favorite, false) AS favorite,
       CASE WHEN jsonb_typeof(d.image_urls) = 'array' THEN jsonb_array_length(d.image_urls) ELSE 0 END AS image_count,
       d."timestamp"
FROM guitar_deals d
LEFT JOIN chat c ON c.deal_id = d.id
LEFT JOIN fav f ON f.deal_id = d.id
WHERE (%(since)s::timestamptz IS NULL OR d."timestamp" >= %(since)s::timestamptz)
"""

_EXCERPTS_SQL = """
SELECT deal_id, display_text, created_at FROM (
    SELECT deal_id, display_text, created_at,
           row_number() OVER (PARTITION BY deal_id ORDER BY created_at DESC) AS rn
    FROM deal_chat
    WHERE deal_id = ANY(%(ids)s) AND role = 'user' AND NOT is_error AND COALESCE(display_text, '') <> ''
) t WHERE rn <= %(n)s ORDER BY deal_id, created_at
"""


def score_signals(row):
    """`(score, [signaux])` d'une ligne de `_CANDIDATES_SQL` (dict). Pure : aucune base requise."""
    signals = []
    if row.get("manual_analysis_overrides") or row.get("manual_classification"):
        signals.append("override")
    if row.get("requal_applied"):
        signals.append("requal")
    if row.get("is_purchased"):
        signals.append("purchased")
    if row.get("initial_verdict") in T1_REJECTED and row.get("gatekeeper_final") == FORCED_ANALYSIS:
        signals.append("rescued")
    user_msgs = row.get("user_msgs") or 0
    if user_msgs >= 1:
        signals.append("chat")
    if row.get("favorite"):
        signals.append("favorite")
    score = sum(WEIGHTS[s] for s in signals)
    if "chat" in signals and user_msgs < 3:
        score -= 1  # 1-2 messages : indice faible (poids 1 au lieu de 2)
    return score, sorted(signals, key=list(WEIGHTS).index)


def is_accessory(row):
    """Étui ou ampli (classification manuelle prioritaire sur celle de l'IA)."""
    cls = row.get("manual_classification") or row.get("classification") or ""
    return cls.split(".")[0] in ACCESSORY_ROOTS


def rank(rows, limit, t3_only=False, with_accessories=False):
    """Candidates triées (score décroissant, puis passage par l'Expert, puis récence), sans les annonces sans signal
    ni (par défaut) les étuis/amplis."""
    scored = []
    for row in rows:
        score, signals = score_signals(row)
        if score <= 0 or (t3_only and not row.get("tier3_trigger")):
            continue
        if not with_accessories and is_accessory(row):
            continue
        scored.append({**row, "score": score, "signals": signals, "has_t3": bool(row.get("tier3_trigger"))})
    scored.sort(key=lambda r: (-r["score"], not r["has_t3"], -(r["timestamp"].timestamp() if r.get("timestamp") else 0)))
    return scored[:limit]


def fetch_candidates(conn, since=None):
    with conn.cursor() as cur:
        cur.execute(_CANDIDATES_SQL, {"since": since})
        return cur.fetchall()


def fetch_excerpts(conn, deal_ids):
    """Derniers messages de l'UTILISATEUR par annonce (ses propres mots : la matière de la vérité terrain)."""
    if not deal_ids:
        return {}
    out = {}
    with conn.cursor() as cur:
        cur.execute(_EXCERPTS_SQL, {"ids": list(deal_ids), "n": EXCERPTS_PER_DEAL})
        for r in cur.fetchall():
            text = " ".join(str(r["display_text"]).split())
            out.setdefault(r["deal_id"], []).append(text[:EXCERPT_CHARS] + ("…" if len(text) > EXCERPT_CHARS else ""))
    return out


def summarize(rows):
    """Effectifs par signal sur TOUTE la base (avant `--limit`) : dit si l'objectif de 10-15 annonces est atteignable."""
    counts = {s: 0 for s in WEIGHTS}
    with_t3 = {s: 0 for s in WEIGHTS}
    for row in rows:
        _, signals = score_signals(row)
        for s in signals:
            counts[s] += 1
            with_t3[s] += 1 if row.get("tier3_trigger") else 0
    return counts, with_t3


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=15, help="nombre d'annonces candidates à garder (défaut 15)")
    ap.add_argument("--since", default=None, help="ne regarder que les annonces modifiées depuis cette date (ISO)")
    ap.add_argument("--t3-only", action="store_true", help="seulement les annonces déjà passées par l'Expert (T3)")
    ap.add_argument("--with-accessories", action="store_true", help="garder aussi les étuis et amplis (exclus par défaut)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="fichier JSONL de sortie (local, non versionné)")
    args = ap.parse_args(argv)

    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.read_only = True
        rows = fetch_candidates(conn, args.since)
        counts, with_t3 = summarize(rows)
        picked = rank(rows, args.limit, args.t3_only, args.with_accessories)
        excerpts = fetch_excerpts(conn, [r["id"] for r in picked])

    print(f"{len(rows)} annonces en base. Signaux humains trouvés (dont déjà passées par l'Expert T3) :")
    for s in WEIGHTS:
        print(f"  {s:<10} {counts[s]:>4}   (T3 : {with_t3[s]})")
    print(f"\n{len(picked)} candidates retenues (score décroissant, T3 en premier à score égal) :\n")
    for r in picked:
        flags = ",".join(r["signals"])
        print(f"[{r['score']:>2}] {r['id']}  {r['verdict'] or '-':<13} T1={r['initial_verdict'] or '-':<16} "
              f"T3={'oui' if r['has_t3'] else 'non'}  photos={r['image_count']}  chat={r['user_msgs']}/{r['msgs']}  {flags}")
        print(f"     {r['title']}")
        for text in excerpts.get(r["id"], []):
            print(f"       > {text}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in picked:
            record = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}
            record["user_chat_excerpts"] = excerpts.get(r["id"], [])
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    print(f"\nÉcrit : {args.out}  (local, dans .gitignore — ne jamais versionner)")


if __name__ == "__main__":
    main()
