"""
Étude à coût zéro (lecture Postgres seule, aucun appel IA) : quelle part des verdicts T2 repose
sur des informations VISUELLES absentes du texte de l'annonce ?

Question de fond : un résumé textuel des photos (hybride Qwen → raisonneur texte, Chantier I-2)
peut-il remplacer l'analyse visuelle ? Avant de payer un rejeu, on regarde ce que le T2 actuel
DIT avoir vu (`ai_analysis_raw.visual_inspection`) et on cherche, pour chaque fait visuel, s'il
figurait déjà dans le titre ou la description. Un fait visuel absent du texte = un cas où les
photos ont apporté quelque chose, donc un cas que le descripteur devra savoir capturer.

Méthode (lexicale, volontairement simple et reproductible)
- Faits visuels repérés par catégories de motifs FR/EN (défauts, matériel, finition, tête,
  texte lu sur l'instrument, ...), chacune rattachée à une PARTIE de guitare → correspond aux
  classes du détecteur de parties (tête, chevalet, rosace, manche, corps, ...).
- Marque : `brand` identifiée par le T2 mais absente du titre et de la description = marque
  probablement lue sur les photos (ou déduite des formes).
- Limite assumée : SOUS-estime la dépendance visuelle (paraphrases non couvertes, faits visuels
  qui ont pesé sans être écrits). C'est une borne basse, pas une mesure exacte.

Sorties
- Part des verdicts T2 avec ≥1 fait visuel absent du texte, globale et par verdict.
- Fréquence par catégorie de fait et par partie de guitare (priorise les classes de crops).
- Liste stratifiée de candidats pour le rejeu hybride (~150 annonces, `--export-sample`).

Usage (serveur de prod, même DATABASE_URL que le bot)
    python backend/scripts/study_visual_dependence.py
    python backend/scripts/study_visual_dependence.py --since 2026-06-01 --examples 5
    python backend/scripts/study_visual_dependence.py --export-sample backend/benchmark/hybrid_replay_sample.json --sample-size 150
"""
import argparse
import json
import os
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# Catégories de faits visuels. `part` = classe de crop la plus proche (détecteur de parties).
# Motifs sur texte normalisé (minuscules, sans accents). Ajuster librement : c'est le cœur de
# l'étude, et la relecture des exemples (--examples) sert précisément à les affiner.
# ---------------------------------------------------------------------------
CATEGORIES = {
    "defaut_fissure": {"part": "table/corps", "patterns": [
        r"fissur", r"\bfendu", r"\bfente", r"\bcrack", r"\bcracked", r"lezard"]},
    "defaut_decollement": {"part": "chevalet", "patterns": [
        r"decoll", r"\bleve\b", r"se souleve", r"soulevement", r"bridge lift", r"lifting"]},
    "defaut_manche_angle": {"part": "manche/talon", "patterns": [
        r"angle (du|de) manche", r"neck reset", r"neck angle", r"action (tres |trop )?haute",
        r"high action", r"manche (tordu|voile|creuse)", r"\bbow\b", r"\bwarp"]},
    "defaut_frettes": {"part": "touche/frettes", "patterns": [
        r"frettes? (usee|creusee|abime)", r"fret wear", r"worn frets", r"divots?"]},
    "defaut_casse_manque": {"part": "divers", "patterns": [
        r"\bcasse", r"brise", r"manquant", r"\bmanque\b", r"broken", r"missing", r"arrache"]},
    "defaut_usure_finition": {"part": "corps", "patterns": [
        r"eclat", r"\bchips?\b", r"bosses?", r"\bdings?\b", r"rayur", r"scratch", r"craquel",
        r"checking", r"usure", r"\bwear\b", r"relic"]},
    "defaut_oxydation": {"part": "accastillage", "patterns": [
        r"rouill", r"oxyd", r"corros", r"\brust"]},
    "reparation_visible": {"part": "divers", "patterns": [
        r"repar", r"recoll", r"refin", r"repeint", r"overspray", r"refret", r"\brepair"]},
    "materiel_micros": {"part": "micros", "patterns": [
        r"humbucker", r"single[- ]coil", r"\bp-?90", r"mini[- ]humbucker", r"filtertron", r"\bmicros?\b"]},
    "materiel_chevalet": {"part": "chevalet", "patterns": [
        r"tune-?o-?matic", r"vibrato", r"tremolo", r"bigsby", r"stop ?tail", r"cordier",
        r"chevalet (fixe|flottant)", r"hardtail", r"floyd"]},
    "materiel_mecaniques": {"part": "tete", "patterns": [
        r"mecaniques?", r"kluson", r"grover", r"tuners?", r"machine heads?"]},
    "tete_forme_logo": {"part": "tete", "patterns": [
        r"\btete\b", r"headstock", r"\blogo", r"3\s*\+\s*3", r"6 en ligne", r"six en ligne",
        r"inline", r"volute", r"cache (de )?truss", r"truss rod cover"]},
    "texte_lu_instrument": {"part": "tete/etiquette", "patterns": [
        r"etiquette", r"\blabel\b", r"numero de serie", r"serial", r"inscri", r"estampill",
        r"\bmade in\b", r"decal"]},
    "rosace_ouies": {"part": "rosace", "patterns": [
        r"rosace", r"rosette", r"\bouies?\b", r"f-?holes?", r"soundhole"]},
    "filets_incrustations": {"part": "corps/touche", "patterns": [
        r"\bfilets?\b", r"binding", r"incrust", r"inlays?", r"reperes? (de touche)?", r"blocks?",
        r"nacre", r"abalone", r"purfling"]},
    "finition_couleur": {"part": "corps", "patterns": [
        r"sunburst", r"burst", r"naturel", r"\bnatural\b", r"satin", r"brillant", r"gloss",
        r"nitro", r"vieilli", r"jaunie?", r"ambre", r"flamme", r"figured", r"quilt", r"erable ondé"]},
    "forme_corps": {"part": "corps", "patterns": [
        r"single ?cut", r"double ?cut", r"cutaway", r"pan coupe", r"offset", r"dreadnought",
        r"jumbo", r"parlou?r", r"archtop", r"semi-?hollow", r"hollow ?body", r"table voutee"]},
    "plaque_manche": {"part": "manche/talon", "patterns": [
        r"plaque de manche", r"neck ?plate", r"4 vis", r"3 vis", r"micro-?tilt", r"talon", r"\bheel\b"]},
}

# Deux familles, traitées différemment :
# - ÉTAT (défauts, réparations) : jamais déductible du nom du modèle → un fait d'état absent du
#   texte compte TOUJOURS comme dépendance visuelle. C'est là que se jouent les pépites à réparer.
# - IDENTIFICATION (matériel, formes, tête, finition, texte lu) : REDONDANT si la marque figure
#   déjà dans le texte (une Stratocaster a un vibrato : l'avoir vu n'apporte rien). Ne compte
#   comme dépendance que si le texte ne nomme pas la marque.
STATE_CATEGORIES = {
    "defaut_fissure", "defaut_decollement", "defaut_manche_angle", "defaut_frettes",
    "defaut_casse_manque", "defaut_usure_finition", "defaut_oxydation", "reparation_visible",
}

# Formulations génériques : un `visual_inspection` qui ne dit rien de concret.
GENERIC_PATTERNS = [r"^\s*$", r"photos? (de )?(bonne|mauvaise) qualite\.?\s*$", r"rien a signaler",
                    r"aucune? (anomalie|defaut) visible\.?\s*$", r"n/?a"]

UNKNOWN_BRANDS = {"", "inconnu", "inconnue", "unknown", "n/a", "na", "none", "aucune", "generique",
                  "generic", "sans marque", "no name", "noname"}


def norm(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.lower())


COMPILED = {k: [re.compile(p) for p in v["patterns"]] for k, v in CATEGORIES.items()}
GENERIC = [re.compile(p) for p in GENERIC_PATTERNS]


def categories_in(text):
    return {k for k, pats in COMPILED.items() if any(p.search(text) for p in pats)}


def load_rows(since, limit):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise SystemExit("psycopg absent : pip install 'psycopg[binary]' (déjà requis par le bot).")
    dsn = os.getenv("DATABASE_URL", "postgresql://guitarhunter@localhost/guitarhunter").replace("\r", "").strip()
    # `description` : colonne ajoutée tardivement ; les annonces migrées l'ont parfois encore dans
    # `_unmapped` (voir schema.sql) — on lit les deux.
    query = """
        SELECT id, title, verdict, classification, brand, model_name, deal_score, model_used,
               is_purchased, "timestamp",
               COALESCE(description,
                        ai_analysis_raw -> '_unmapped' ->> 'description',
                        ai_analysis_raw ->> 'description', '') AS description,
               ai_analysis_raw ->> 'visual_inspection' AS visual_inspection,
               jsonb_array_length(COALESCE(image_urls, '[]'::jsonb)) AS n_images
        FROM guitar_deals
        WHERE ai_analysis_raw ? 'visual_inspection'
          AND COALESCE(ai_analysis_raw ->> 'visual_inspection', '') <> ''
    """
    params = []
    if since:
        query += ' AND "timestamp" >= %s'
        params.append(since)
    query += ' ORDER BY "timestamp" DESC'
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        return conn.execute(query, params).fetchall()


def analyze(row):
    listing = norm(f"{row['title']} {row['description']}")
    visual = norm(row["visual_inspection"])
    generic = any(p.search(visual) for p in GENERIC) or len(visual) < 25
    in_visual = categories_in(visual)
    in_listing = categories_in(listing)
    visual_only = sorted(in_visual - in_listing)

    brand = norm(row["brand"]).strip()
    brand_known = bool(brand) and brand not in UNKNOWN_BRANDS
    brand_in_text = brand_known and brand in listing
    brand_from_photos = brand_known and not brand_in_text
    state_only = [c for c in visual_only if c in STATE_CATEGORIES]
    ident_only = [c for c in visual_only if c not in STATE_CATEGORIES]
    # Identification redondante quand le texte nomme déjà la marque (voir STATE_CATEGORIES).
    informative = state_only + ([] if brand_in_text else ident_only)
    return {
        "generic": generic,
        "visual_only": visual_only,
        "informative": sorted(informative),
        "state_only": state_only,
        "brand_from_photos": brand_from_photos,
        "depends_on_vision": bool(informative) or brand_from_photos,
        "depends_on_state": bool(state_only),
    }


def pct(n, d):
    return f"{100 * n / d:5.1f}%" if d else "   n/d"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default=None, help="date ISO (AAAA-MM-JJ)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--examples", type=int, default=3, help="exemples affichés par catégorie (relecture)")
    ap.add_argument("--export-sample", default=None, help="chemin JSON des candidats au rejeu hybride")
    ap.add_argument("--sample-size", type=int, default=150)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = load_rows(args.since, args.limit)
    if not rows:
        print("Aucune annonce avec `visual_inspection` non vide. Vérifier DATABASE_URL / --since.")
        return

    results = [(r, analyze(r)) for r in rows]
    n = len(results)
    no_desc = sum(1 for r, _ in results if not (r["description"] or "").strip())
    generic = sum(1 for _, a in results if a["generic"])
    dep = [x for x in results if x[1]["depends_on_vision"]]
    brand_ph = sum(1 for _, a in results if a["brand_from_photos"])

    print("=" * 92)
    print(f"DÉPENDANCE VISUELLE DES VERDICTS T2 — {n} annonces avec `visual_inspection`")
    print("=" * 92)
    print(f"Sans description texte              : {no_desc:5d}  {pct(no_desc, n)}  (titre seul → vision surreprésentée)")
    print(f"`visual_inspection` générique/vide  : {generic:5d}  {pct(generic, n)}")
    print(f"Marque absente du texte (lue/déduite des photos) : {brand_ph:5d}  {pct(brand_ph, n)}")
    state = sum(1 for _, a in results if a["depends_on_state"])
    print(f"État (défaut/réparation) vu mais absent du texte : {state:5d}  {pct(state, n)}   ← le cœur du sujet")
    print(f"Dépendance visuelle totale (état + identif. non redondante + marque photo) : "
          f"{len(dep):5d}  {pct(len(dep), n)}   ← borne basse")

    # Par verdict
    by_verdict = defaultdict(lambda: [0, 0, 0])
    for r, a in results:
        v = r["verdict"] or "?"
        by_verdict[v][0] += 1
        by_verdict[v][1] += a["depends_on_vision"]
        by_verdict[v][2] += a["depends_on_state"]
    print("\nPAR VERDICT (là où ça compte : PEPITE / FAST_FLIP)")
    for v, (tot, d, st) in sorted(by_verdict.items(), key=lambda kv: -kv[1][0]):
        print(f"  {v[:28]:28s}{tot:6d} annonces   dépendance visuelle {pct(d, tot)}   dont état {pct(st, tot)}")

    # Achats confirmés : l'étalon indépendant
    bought = [(r, a) for r, a in results if r["is_purchased"]]
    if bought:
        d = sum(a["depends_on_vision"] for _, a in bought)
        print(f"\n  Achats confirmés (étalon indépendant) : {len(bought)} annonces, dépendance visuelle {pct(d, len(bought))}")

    # Par catégorie et par partie
    cat_count = Counter(c for _, a in results for c in a["informative"])
    redundant = Counter(c for _, a in results for c in a["visual_only"] if c not in a["informative"])
    part_count = Counter(CATEGORIES[c]["part"] for _, a in results for c in a["informative"])
    print("\nFAITS VISUELS INFORMATIFS (absents du texte, non redondants), PAR CATÉGORIE")
    for c, k in cat_count.most_common():
        print(f"  {c:28s}{k:6d}  ({pct(k, n)} des annonces)   partie : {CATEGORIES[c]['part']}")
    if redundant:
        print("  (écartés comme redondants avec la marque nommée : "
              + ", ".join(f"{c} {k}" for c, k in redundant.most_common(5)) + ")")
    print("\nPAR PARTIE DE GUITARE (→ classes de crops prioritaires)")
    for p, k in part_count.most_common():
        print(f"  {p:20s}{k:6d}")

    # Exemples à relire pour affiner les motifs
    if args.examples:
        print("\nEXEMPLES À RELIRE (affiner les motifs si faux positifs)")
        for c, _ in cat_count.most_common(6):
            shown = 0
            for r, a in results:
                if c in a["informative"]:
                    vi = re.sub(r"\s+", " ", r["visual_inspection"])[:180]
                    print(f"  [{c}] {r['id']} « {(r['title'] or '')[:50]} » → {vi}")
                    shown += 1
                    if shown >= args.examples:
                        break

    # Échantillon stratifié pour le rejeu hybride
    if args.export_sample:
        rng = random.Random(args.seed)
        target = args.sample_size
        strata = {
            "vision_pepite": [r for r, a in results if a["depends_on_vision"] and (r["verdict"] or "") in ("PEPITE", "FAST_FLIP")],
            "achat_confirme": [r for r, a in results if r["is_purchased"]],
            "vision_autres": [r for r, a in results if a["depends_on_vision"] and (r["verdict"] or "") not in ("PEPITE", "FAST_FLIP")],
            "texte_suffit": [r for r, a in results if not a["depends_on_vision"] and not a["generic"]],
        }
        quotas = {"vision_pepite": 0.35, "achat_confirme": 0.15, "vision_autres": 0.30, "texte_suffit": 0.20}
        chosen, seen = [], set()
        for name, share in quotas.items():
            pool = [r for r in strata[name] if r["id"] not in seen]
            rng.shuffle(pool)
            for r in pool[: int(round(target * share))]:
                seen.add(r["id"])
                chosen.append({"id": r["id"], "stratum": name, "verdict": r["verdict"],
                               "deal_score": r["deal_score"], "title": r["title"]})
        # Compléter si une strate était trop petite
        rest = [r for r, _ in results if r["id"] not in seen]
        rng.shuffle(rest)
        for r in rest[: max(0, target - len(chosen))]:
            chosen.append({"id": r["id"], "stratum": "complement", "verdict": r["verdict"],
                           "deal_score": r["deal_score"], "title": r["title"]})
        os.makedirs(os.path.dirname(os.path.abspath(args.export_sample)), exist_ok=True)
        with open(args.export_sample, "w", encoding="utf-8") as fh:
            json.dump(chosen, fh, ensure_ascii=False, indent=2, default=str)
        print(f"\nÉchantillon de rejeu écrit : {args.export_sample} ({len(chosen)} annonces) — "
              + ", ".join(f"{k} {sum(1 for c in chosen if c['stratum'] == k)}" for k in list(quotas) + ["complement"]))


if __name__ == "__main__":
    main()
