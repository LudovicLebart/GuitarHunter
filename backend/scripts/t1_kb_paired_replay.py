"""Rejeu APPARIÉ et FIDÈLE À LA PROD du Portier T1, sans / avec la base « univers des guitares » (2026-10-14).

Pourquoi ce script existe : les premiers rejeux (compare_qwen_local_vs_prod + compare_knowledge_effect) concluaient
« aucun gain », mais le protocole ne pouvait pas conclure (revue Opus 2026-10-14) : peu d'annonces utiles, vérité
terrain circulaire, critère asymétrique, rejeu non fidèle à la prod. Ici :

  * UNITÉ = l'annonce, pas l'appel : chaque annonce passe dans chaque bras avec N répétitions, on compare des TAUX DE
    REJET par annonce (le Portier local n'est pas déterministe : un seul appel ne dit rien) ;
  * DEUX STRATES : A = faux rejets présumés (rejetées par le Portier à l'origine, reclassées depuis par une analyse ou
    une correction) où la base trouve une fiche et où le Portier d'aujourd'hui rejette encore (sélection faite sur des
    répétitions SÉPARÉES de celles qui mesurent l'effet : pas de régression vers la moyenne) ; B = annonces acceptées
    où la base trouve une fiche (test de non-régression) ;
  * QUATRE BRAS : « sans » (prompt de prod), « avec » (fiches trouvées dans titre + description, comme le Portier de
    prod AVANT la lecture des photos), « photo » (en plus, le texte que l'EXPERT a lu sur les photos,
    `visual_inspection` : borne haute de ce que donnerait un Portier qui lit la marque sur la tête de manche),
    « portier » (en plus, le texte que le PORTIER lui-même lit sur les photos, passe `backend/t1_photo_text.py` : le
    vrai cas qu'on déploierait, interrupteur `T1_KNOWLEDGE_PHOTO_TEXT`). Le texte du Portier est lu UNE fois par
    annonce (étape `ocr`) puis réutilisé à chaque répétition : le bras mesure l'effet des fiches trouvées grâce à
    cette lecture, pas sa variabilité (la qualité de la lecture se mesure à part avec `ocr-check`) ;
  * FIDÉLITÉ : 8 photos, budget de contexte 8192 (réduction des photos), température par défaut du modèle, même
    prompt que la prod (`backend/t1_prompt.py`). Le script REFUSE de tourner sinon (`--allow-nonprod` pour passer outre,
    consigné dans le fichier de méta) ;
  * CRITÈRES FIXÉS D'AVANCE (constantes ci-dessous) : on ne les ajuste pas après avoir vu les résultats.

Sous-commandes (sur le serveur, `export DATABASE_URL=...`, Dell allumé ; ces scripts ne lisent pas .env) :

  python -m backend.scripts.t1_kb_paired_replay plan   --out kb_plan.json
  QWEN_LOCAL_MAX_IMAGES=8 QWEN_LOCAL_FIT_BUDGET=1 python -u -m backend.scripts.t1_kb_paired_replay ocr \\
        --plan kb_plan.json --ocr kb_ocr.jsonl          # le Portier lit les photos (reprenable, ~15 s par annonce)
  python -m backend.scripts.t1_kb_paired_replay ocr-check --plan kb_plan.json --ocr kb_ocr.jsonl   # seuil 70 %
  QWEN_LOCAL_MAX_IMAGES=8 QWEN_LOCAL_FIT_BUDGET=1 nohup python -u -m backend.scripts.t1_kb_paired_replay run \\
        --plan kb_plan.json --results kb_paired.jsonl --ocr kb_ocr.jsonl --stage screen  > kb_screen.log 2>&1 &
  QWEN_LOCAL_MAX_IMAGES=8 QWEN_LOCAL_FIT_BUDGET=1 nohup python -u -m backend.scripts.t1_kb_paired_replay run \\
        --plan kb_plan.json --results kb_paired.jsonl --ocr kb_ocr.jsonl --stage eval    > kb_eval.log 2>&1 &
  python -m backend.scripts.t1_kb_paired_replay report --plan kb_plan.json --results kb_paired.jsonl

DÉCISIONS DE LUDOVIC DU 2026-10-16, PRISES AVANT TOUT RÉSULTAT DU REJEU (à ne pas modifier après coup) :
  * Le seuil de lecture de 70 pour cent (`ocr-check`) n'est PAS atteint (11/22 = 50 pour cent, verdict LECTURE INSUFFISANTE
    le 2026-10-16) ; il est ABANDONNÉ en connaissance de cause : le détail montre que la référence (texte de l'Expert)
    contient des suppositions, pas seulement du texte lu ; ce seuil ne sert plus de condition au rejeu.
  * A n'a que 20 annonces (moins de 25) : la strate A ne sert plus à décider. Critère de décision : (1) NON-RÉGRESSION
    en B (borne haute de l'IC95 de la hausse du taux de rejet inférieure ou égale à +3 points, bras « portier ») ET
    (2) le cas connu (annonce Guerilla 7 cordes, mode « cas précis » ci-dessous) est corrigé par la fiche.

  * COMPLÉMENT DU 2026-10-16, APRÈS LE CAS GUERILLA (à lire avec ce qui précède, sans le remplacer) : l'annonce est déjà
    acceptée SANS fiche (0 rejet sur 10) ; l'erreur d'origine venait d'un ancien Portier (autre prompt, ancienne
    version de Flash) et n'existe plus avec le Portier actuel. Le critère (2) est donc SANS OBJET (ni atteint, ni raté) ;
    la décision repose sur le seul critère (1), la non-régression en B.

Mode « cas précis » (2026-10-15 : vérifier qu'une annonce connue, ex. la Guerilla 7 cordes, n'est plus rejetée à tort) :

  python -m backend.scripts.t1_kb_paired_replay plan --only-ids ID --out kb_case.json
  QWEN_LOCAL_MAX_IMAGES=8 QWEN_LOCAL_FIT_BUDGET=1 python -u -m backend.scripts.t1_kb_paired_replay ocr --plan kb_case.json --ocr kb_case_ocr.jsonl
  QWEN_LOCAL_MAX_IMAGES=8 QWEN_LOCAL_FIT_BUDGET=1 python -u -m backend.scripts.t1_kb_paired_replay run --stage case --reps-a 10 \\
        --plan kb_case.json --results kb_case.jsonl --ocr kb_case_ocr.jsonl
  python -m backend.scripts.t1_kb_paired_replay case-report --results kb_case.jsonl

Un cas montre que la fiche CORRIGE une erreur ; il ne mesure pas les dégâts ailleurs (strate B).

`run` est REPRENABLE (relancer la même commande après une coupure : les appels déjà faits sont sautés). 0 $ (Dell).
Les fichiers sont dans backend/benchmark/results/ (ignoré par git : le dépôt est public, ils contiennent des ids
d'annonces) ; ne contiennent ni titres ni liens.
"""
import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.getcwd())

# ── Critères FIXÉS D'AVANCE (ne pas modifier après avoir vu un résultat) ─────────────────────────────────────────────
MIN_GAIN_POINTS = 15.0          # A : la base doit faire baisser le taux de rejet d'au moins 15 points (moyenne par annonce)
MAX_RISE_POINTS = 3.0           # B : borne HAUTE de l'IC95 % de la hausse du taux de rejet ≤ 3 points (non-infériorité)
MIN_A_LISTINGS = 25             # A : en dessous, le test n'a pas la puissance de conclure (verdict « non concluant »)
MAX_FAILURE_RATE = 0.10         # part d'appels en échec tolérée par bras
SCREEN_MIN_REJECT_RATE = 0.30   # A : taux de rejet SANS base, sur les répétitions de sélection, pour entrer dans l'étude
DEFAULTS = {"screen_reps": 5, "reps_a": 10, "reps_b": 5, "n_b": 150, "max_a": 80, "seed": 42}
OCR_MIN_RECOVERY = 0.70         # lecture des photos : part des fiches trouvables grâce à l'Expert que le Portier retrouve
OCR_MIN_TARGETS = 15            # en dessous de ce nombre d'annonces-cibles, `ocr-check` ne conclut pas
OCR_MAX_FAILURE_RATE = 0.10     # lectures en échec tolérées
ARMS_A = ("without", "with", "photo", "portier")
ARMS_B = ("without", "with", "portier")


def is_rejected(verdict):
    from backend.scripts.compare_knowledge_effect import is_rejected as _r
    return _r(verdict)


# ── Statistiques (fonctions pures, testées) ──────────────────────────────────────────────────────────────────────────
def mean(xs):
    return sum(xs) / len(xs) if xs else None


def bootstrap_ci(diffs, n_boot=10000, seed=1, level=0.95):
    """IC par percentiles de la MOYENNE d'écarts par annonce (rééchantillonnage des annonces)."""
    if not diffs:
        return None
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    lo = means[int(((1 - level) / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - (1 - level) / 2) * n_boot))]
    return lo, hi


def sign_flip_p(diffs, n_perm=20000, seed=2):
    """p bilatéral d'un test de randomisation apparié (signes aléatoires) sur la moyenne des écarts."""
    nz = [d for d in diffs if d != 0]
    if not nz:
        return 1.0
    rng = random.Random(seed)
    obs = abs(sum(nz))
    hits = sum(1 for _ in range(n_perm) if abs(sum(d if rng.random() < 0.5 else -d for d in nz)) >= obs - 1e-12)
    return (hits + 1) / (n_perm + 1)


def reject_rates(rows):
    """{(id, arm): taux de rejet} sur des lignes de résultats valides (verdict non nul)."""
    acc = defaultdict(list)
    for r in rows:
        if r.get("verdict"):
            acc[(r["id"], r["arm"])].append(1.0 if r["rejected"] else 0.0)
    return {k: sum(v) / len(v) for k, v in acc.items()}, {k: len(v) for k, v in acc.items()}


def paired_diffs(rates, ids, arm_a, arm_b):
    """Écarts (taux arm_b − taux arm_a) par annonce, sur les annonces ayant les deux bras."""
    return [rates[(i, arm_b)] - rates[(i, arm_a)] for i in ids if (i, arm_a) in rates and (i, arm_b) in rates]


def summarize_diffs(diffs):
    if not diffs:
        return None
    ci = bootstrap_ci(diffs)
    return {"n": len(diffs), "mean_pts": 100 * mean(diffs), "ci_pts": (100 * ci[0], 100 * ci[1]), "p": sign_flip_p(diffs)}


def select_screened(results, plan_a_ids, min_rate=SCREEN_MIN_REJECT_RATE):
    """Annonces de la strate A retenues après le dépistage (bras « sans », étape screen) : taux de rejet ≥ min_rate."""
    rates, _ = reject_rates([r for r in results if r.get("stage") == "screen"])
    return [i for i in plan_a_ids if rates.get((i, "without"), 0.0) >= min_rate]


def placebo(rows, ids):
    """Écart entre les répétitions paires et impaires du bras « sans » : ce que donne le simple hasard du modèle."""
    by = defaultdict(lambda: {0: [], 1: []})
    for r in rows:
        if r["arm"] == "without" and r.get("verdict"):
            by[r["id"]][r["rep"] % 2].append(1.0 if r["rejected"] else 0.0)
    return [mean(v[1]) - mean(v[0]) for i, v in by.items() if i in ids and v[0] and v[1]]


def failure_rates(results):
    tot, bad = defaultdict(int), defaultdict(int)
    for r in results:
        tot[r["arm"]] += 1
        bad[r["arm"]] += 0 if r.get("verdict") else 1
    return {arm: bad[arm] / tot[arm] for arm in tot}


def analyze(plan, results):
    """Rapport chiffré selon les critères fixés d'avance."""
    strata = {l["id"]: l["stratum"] for l in plan["listings"]}
    a_plan = [i for i, s in strata.items() if s == "A"]
    a_ids = select_screened(results, a_plan)
    b_ids = [i for i, s in strata.items() if s == "B"]
    ev = [r for r in results if r.get("stage") == "eval"]
    rates, counts = reject_rates(ev)

    out = {"n_a_planned": len(a_plan), "n_a_selected": len(a_ids), "n_b": len(b_ids),
           "failure_rates": failure_rates(results), "criteria": {
               "min_gain_pts": MIN_GAIN_POINTS, "max_rise_pts": MAX_RISE_POINTS, "min_a": MIN_A_LISTINGS}}
    a_with = paired_diffs(rates, a_ids, "without", "with")
    a_photo = paired_diffs(rates, a_ids, "without", "photo")
    a_portier = paired_diffs(rates, a_ids, "without", "portier")
    b_with = paired_diffs(rates, b_ids, "without", "with")
    b_portier = paired_diffs(rates, b_ids, "without", "portier")
    out["A_with"] = summarize_diffs([-d for d in a_with])        # gain = baisse du taux de rejet (positif = bien)
    out["A_photo"] = summarize_diffs([-d for d in a_photo])
    out["A_portier"] = summarize_diffs([-d for d in a_portier])
    out["B_with"] = summarize_diffs(b_with)                      # hausse du taux de rejet (négatif/nul = bien)
    out["B_portier"] = summarize_diffs(b_portier)
    out["A_without_rate_pts"] = 100 * mean([rates[(i, "without")] for i in a_ids if (i, "without") in rates]) if a_ids else None
    out["placebo_A"] = summarize_diffs(placebo(ev, set(a_ids)))
    out["placebo_B"] = summarize_diffs(placebo(ev, set(b_ids)))
    out["min_reps"] = min(counts.values()) if counts else 0

    problems = [f"bras « {arm} » : {100 * f:.0f} % d'appels en échec (> {100 * MAX_FAILURE_RATE:.0f} %)"
                for arm, f in out["failure_rates"].items() if f > MAX_FAILURE_RATE]
    if len(a_ids) < MIN_A_LISTINGS:
        problems.append(f"strate A : {len(a_ids)} annonce(s) retenue(s) < {MIN_A_LISTINGS} (puissance insuffisante)")
    # Deux verdicts, mêmes critères : « avec » = recherche par titre + description seuls ; « portier » = en plus le
    # texte lu par le Portier sur les photos (le cas qu'on déploierait avec T1_KNOWLEDGE_PHOTO_TEXT).
    out["verdict"], out["A_met"], out["B_met"] = _verdict(out["A_with"], out["B_with"], problems)
    out["verdict_portier"], out["A_portier_met"], out["B_portier_met"] = _verdict(out["A_portier"], out["B_portier"], problems)
    out["problems"] = problems
    return out


def _verdict(a, b, problems):
    """(verdict, critère A atteint, critère B atteint) selon les critères fixés d'avance."""
    a_met = bool(a and a["mean_pts"] >= MIN_GAIN_POINTS and a["ci_pts"][0] > 0)
    b_met = bool(b and b["ci_pts"][1] <= MAX_RISE_POINTS)
    if problems:
        verdict = "NON CONCLUANT"
    elif a_met and b_met:
        verdict = "GAIN DÉMONTRÉ ET SANS RÉGRESSION"
    elif a and a["ci_pts"][1] < MIN_GAIN_POINTS:
        verdict = "GAIN D'AU MOINS 15 POINTS EXCLU" if (b and b_met) else "AUCUN GAIN ET RÉGRESSION POSSIBLE"
    elif a_met and not b_met:
        verdict = "GAIN MAIS RÉGRESSION POSSIBLE EN B"
    else:
        verdict = "NON CONCLUANT"
    return verdict, a_met, b_met


def _fmt(s, unit="points"):
    if not s:
        return "n/a"
    return f"{s['mean_pts']:+.1f} {unit} (IC95 % {s['ci_pts'][0]:+.1f} ; {s['ci_pts'][1]:+.1f}, n={s['n']}, p={s['p']:.3f})"


def print_report(rep):
    print(f"Strate A (faux rejets présumés) : {rep['n_a_selected']} retenues après dépistage sur {rep['n_a_planned']} prévues")
    print(f"Strate B (annonces acceptées, non-régression) : {rep['n_b']} annonces")
    if rep["A_without_rate_pts"] is not None:
        print(f"Taux de rejet SANS base en A (répétitions d'évaluation) : {rep['A_without_rate_pts']:.0f} %")
    print("\nGAIN en A — baisse du taux de rejet par annonce (critère : ≥ %.0f points ET borne basse de l'IC > 0)" % MIN_GAIN_POINTS)
    print(f"  avec fiches (titre + description) : {_fmt(rep['A_with'])}")
    print(f"  avec fiches + texte lu sur photo par l'EXPERT  : {_fmt(rep['A_photo'])}   ← borne haute d'un Portier qui lirait la marque")
    print(f"  avec fiches + texte lu sur photo par le PORTIER : {_fmt(rep['A_portier'])}   ← le cas qu'on déploierait")
    print("\nRÉGRESSION en B — hausse du taux de rejet par annonce (critère : borne HAUTE de l'IC ≤ +%.0f points)" % MAX_RISE_POINTS)
    print(f"  avec fiches (titre + description) : {_fmt(rep['B_with'])}")
    print(f"  avec fiches + photos lues par le Portier : {_fmt(rep['B_portier'])}")
    print("\nHasard du modèle (placebo : répétitions paires contre impaires du bras « sans », devrait être ≈ 0) :")
    print(f"  A : {_fmt(rep['placebo_A'])}")
    print(f"  B : {_fmt(rep['placebo_B'])}")
    print("\nAppels en échec : " + (", ".join(f"{a} {100 * f:.1f} %" for a, f in rep["failure_rates"].items()) or "aucun appel"))
    for p in rep["problems"]:
        print(f"  ⚠️ {p}")
    print("\n" + "=" * 70)
    print(f"VERDICT (recherche par titre + description)          : {rep['verdict']}")
    print(f"VERDICT (+ photos lues par le Portier, à déployer)    : {rep['verdict_portier']}")
    print(VERDICT_TEXT[rep["verdict_portier"] if rep["A_portier"] else rep["verdict"]])
    print(f"\nCRITÈRE DE DÉCISION DU 2026-10-16 (fixé par Ludovic avant les résultats) : non-régression en B, borne haute ≤ +{MAX_RISE_POINTS} points")
    for label, key in (("recherche par titre + description", "B_with"), ("+ photos lues par le Portier", "B_portier")):
        b = rep.get(key)
        ok = bool(b) and b["ci_pts"][1] <= MAX_RISE_POINTS
        print(f"  {label:36s}: {'NON-RÉGRESSION DÉMONTRÉE' if ok else 'NON-RÉGRESSION NON DÉMONTRÉE'}")
    print("  (+ le cas Guerilla doit être corrigé : voir `case-report`. A étant sous le seuil, son verdict « NON CONCLUANT » est attendu.)")


VERDICT_TEXT = {
    "GAIN DÉMONTRÉ ET SANS RÉGRESSION": "  → la base apporte un gain mesuré sans nuire : on peut discuter de valider la version "
                                        "(décision de Ludovic, après relecture des cas).",
    "GAIN D'AU MOINS 15 POINTS EXCLU": "  → avec ces fiches, un gain de cette taille est exclu par les données : la base n'aide pas le Portier "
                                       "(elle reste utile à l'Expert via lookup_brand).",
    "GAIN MAIS RÉGRESSION POSSIBLE EN B": "  → la base aide en A mais la non-infériorité en B n'est pas démontrée : relire les rejets de B.",
    "AUCUN GAIN ET RÉGRESSION POSSIBLE": "  → pas de gain et une régression ne peut pas être exclue : ne pas activer.",
    "NON CONCLUANT": "  → le test ne permet pas de trancher (voir les avertissements) : ne rien conclure, ni dans un sens ni dans l'autre.",
}


# ── Plan : choix des annonces ────────────────────────────────────────────────────────────────────────────────────────
def build_plan(conn, kb_version, gate, n_b, max_a, seed, exclude_ids=(), only_ids=()):
    from backend import guitar_knowledge as gk
    from backend.scripts.compare_knowledge_effect import reference_rejected
    from config import T1_KNOWLEDGE_MAX_FICHES
    gk.configure_version(kb_version)
    gk.configure_review_gate(gate)
    rows = conn.execute("""
        SELECT gd.id, gd.title, gd.description, gd.ai_analysis_raw, gd.initial_verdict, gd.verdict AS final_verdict
        FROM guitar_deals gd
        WHERE gd.id <> ALL(%s)
          AND (%s OR gd.id = ANY(%s) OR gd.ai_analysis_raw ->> 'gatekeeperVerdict' IS NOT NULL OR gd.initial_verdict IS NOT NULL)
          AND (NOT %s OR gd.id = ANY(%s))
        ORDER BY gd.id""", (list(exclude_ids), bool(only_ids), list(only_ids), bool(only_ids), list(only_ids))).fetchall()
    a, b = [], []
    for r in rows:
        ai = r["ai_analysis_raw"]
        ai = json.loads(ai) if isinstance(ai, str) else (ai or {})
        entry_final = {"final_verdict": r["final_verdict"], "cloud_verdict": r["initial_verdict"]}
        final_ok = not reference_rejected(entry_final) and (r["final_verdict"] or "").upper() not in ("",)
        photo_text = ai.get("visual_inspection") or ""
        with_fiches = gk.lookup(conn, r["title"], r["description"], limit=T1_KNOWLEDGE_MAX_FICHES)
        photo_fiches = (gk.lookup(conn, r["title"], r["description"], photo_text, limit=T1_KNOWLEDGE_MAX_FICHES)
                        if photo_text else with_fiches)
        item = {"id": r["id"], "kb_with": [f["id"] for f in with_fiches], "kb_photo": [f["id"] for f in photo_fiches]}
        # A : une fiche par le texte OU par la photo (la marque n'est souvent que sur la tête de manche) ;
        # B : une fiche par le texte (seul bras comparé, sinon le prompt est identique et il n'y a rien à mesurer).
        if only_ids:                                   # mode « cas précis » : annonces demandées, sans condition de strate
            a.append({**item, "stratum": "A"})
        elif is_rejected(r["initial_verdict"]) and final_ok and (with_fiches or photo_fiches):
            a.append({**item, "stratum": "A"})
        elif (with_fiches and ai.get("gatekeeperVerdict") and not is_rejected(ai.get("gatekeeperVerdict")) and final_ok
              and not is_rejected(r["initial_verdict"])):
            b.append({**item, "stratum": "B"})
    rng = random.Random(seed)
    if len(a) > max_a:
        a = rng.sample(a, max_a)
    if len(b) > n_b:
        b = rng.sample(b, n_b)
    return {"meta": {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "kb_version": gk.effective_version(conn),
                     "kb_version_mode": kb_version, "review_gate": gate, "seed": seed,
                     "n_a_candidates": len(a), "n_b_sampled": len(b)},
            "listings": sorted(a, key=lambda x: x["id"]) + sorted(b, key=lambda x: x["id"])}


# ── Exécution ────────────────────────────────────────────────────────────────────────────────────────────────────────
def check_fidelity(cq, allow_nonprod):
    problems = []
    if cq.MAX_IMAGES != 8:
        problems.append(f"QWEN_LOCAL_MAX_IMAGES={cq.MAX_IMAGES} (la prod envoie 8 photos)")
    if not cq.QWEN_LOCAL_FIT_BUDGET:
        problems.append("QWEN_LOCAL_FIT_BUDGET non activé (la prod réduit les photos pour tenir dans le contexte)")
    if cq.QWEN_LOCAL_NUM_CTX != 8192:
        problems.append(f"QWEN_LOCAL_NUM_CTX={cq.QWEN_LOCAL_NUM_CTX} (prod : 8192)")
    if cq.QWEN_LOCAL_MODEL == "qwen3-vl:8b":
        problems.append("modèle qwen3-vl:8b = variante THINKING (utiliser qwen3-vl:8b-instruct)")
    if problems and not allow_nonprod:
        raise SystemExit("Rejeu NON fidèle à la prod, refusé :\n  - " + "\n  - ".join(problems) +
                         "\nExporter QWEN_LOCAL_MAX_IMAGES=8 QWEN_LOCAL_FIT_BUDGET=1 (ou --allow-nonprod, consigné).")
    return problems


def load_results(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_ocr(path):
    """{id: dernière lecture RÉUSSIE du Portier} (une lecture en échec n'est jamais utilisée : elle sera refaite)."""
    out = {}
    for line in load_results(path):
        if not line.get("error") and "photo_text" in line:
            out[line["id"]] = line
    return out


def jobs_for(plan, results, stage, reps_screen, reps_a, reps_b, ocr=None):
    """Liste ordonnée de (id, stratum, arm, rep, stage) restant à faire. Les bras alternent à chaque répétition.
    `ocr` : {id: lecture du Portier} (voir `load_ocr`) ; sans lecture d'une annonce, pas de bras « portier » pour elle."""
    done = {(r["id"], r["arm"], r["rep"], r["stage"]) for r in results if r.get("verdict")}
    listings = {l["id"]: l for l in plan["listings"]}
    jobs = []
    if stage == "screen":
        for l in plan["listings"]:
            if l["stratum"] == "A":
                for rep in range(reps_screen):
                    jobs.append((l["id"], "A", "without", rep, "screen"))
    elif stage == "case":
        for l in plan["listings"]:
            for rep in range(reps_a):
                order = list(ARMS_A)
                random.Random(f"{l['id']}:{rep}").shuffle(order)
                for arm in order:
                    if arm == "photo" and l["kb_photo"] == l["kb_with"]:
                        continue
                    if arm == "with" and not l["kb_with"]:
                        continue
                    if arm == "portier":
                        read = (ocr or {}).get(l["id"])
                        if not read or not read["kb_portier"] or read["kb_portier"] == l["kb_with"]:
                            continue
                    jobs.append((l["id"], l["stratum"], arm, rep, "case"))
    else:
        a_ids = select_screened(results, [i for i, l in listings.items() if l["stratum"] == "A"])
        for lid in a_ids + [i for i, l in listings.items() if l["stratum"] == "B"]:
            l = listings[lid]
            arms = ARMS_A if l["stratum"] == "A" else ARMS_B
            for rep in range(reps_a if l["stratum"] == "A" else reps_b):
                order = list(arms)
                random.Random(f"{lid}:{rep}").shuffle(order)       # alternance : la dérive du Dell ne favorise aucun bras
                for arm in order:
                    if arm == "photo" and l["kb_photo"] == l["kb_with"]:
                        continue                                    # même prompt que « avec » : rien à mesurer
                    if arm == "with" and not l["kb_with"]:
                        continue                                    # aucune fiche par le texte : prompt identique à « sans »
                    if arm == "portier":
                        read = (ocr or {}).get(lid)
                        if not read or not read["kb_portier"] or read["kb_portier"] == l["kb_with"]:
                            continue                                # pas de lecture, ou même fiches que « avec » : rien à mesurer
                    jobs.append((lid, l["stratum"], arm, rep, "eval"))
    return [j for j in jobs if (j[0], j[2], j[3], j[4]) not in done]


def run(args):
    import psycopg
    from psycopg.rows import dict_row
    from backend import guitar_knowledge as gk
    from backend.scripts import compare_qwen_local_vs_prod as cq
    from backend.t1_image_budget import fit_images_to_budget
    from backend.t1_prompt import build_t1_gatekeeper_prompt
    from config import (DEFAULT_GATEKEEPER_INSTRUCTION, DEFAULT_TAXONOMY, T1_KNOWLEDGE_MAX_FICHES)

    nonprod = check_fidelity(cq, args.allow_nonprod)
    with open(os.path.join(cq.RESULTS_DIR, args.plan), encoding="utf-8") as fh:
        plan = json.load(fh)
    results_path = os.path.join(cq.RESULTS_DIR, args.results)
    results = load_results(results_path)
    meta = plan["meta"]
    gk.configure_version(meta["kb_version_mode"])
    gk.configure_review_gate(meta["review_gate"])
    cq.ACTIVE_T1_SCHEMA = cq.build_t1_schema("baseline")
    ocr = load_ocr(os.path.join(cq.RESULTS_DIR, args.ocr))
    if not ocr:
        print("Aucune lecture de photos du Portier (étape `ocr` non faite) : le bras « portier » est sauté.", flush=True)
    jobs = jobs_for(plan, results, args.stage, args.screen_reps, args.reps_a, args.reps_b, ocr=ocr)
    if args.limit:
        jobs = jobs[:args.limit]
    print(f"{len(jobs)} appel(s) à faire (étape {args.stage}) ; ~{len(jobs) * 20 / 3600:.1f} h à ~20 s/appel. "
          f"Écart avec la prod consigné : {nonprod or 'aucun'}", flush=True)
    if not jobs:
        return

    os.makedirs(cq.RESULTS_DIR, exist_ok=True)
    with open(results_path + ".meta.json", "w", encoding="utf-8") as fh:
        json.dump({"plan_meta": meta, "model": cq.QWEN_LOCAL_MODEL, "max_images": cq.MAX_IMAGES,
                   "fit_budget": cq.QWEN_LOCAL_FIT_BUDGET, "num_ctx": cq.QWEN_LOCAL_NUM_CTX, "temperature": None,
                   "nonprod_overrides": nonprod, "note": getattr(args, "note", ""),
                   "started": time.strftime("%Y-%m-%d %H:%M:%S")}, fh, indent=2)

    cache = {"id": None}
    consecutive_failures = 0
    with psycopg.connect(cq.DATABASE_URL, row_factory=dict_row) as conn, open(results_path, "a", encoding="utf-8") as out:
        for n, (lid, stratum, arm, rep, stage) in enumerate(jobs, 1):
            if cache["id"] != lid:
                row = conn.execute("SELECT gd.id, gd.title, gd.price, gd.description, gd.location, gd.image_urls, "
                                   "gd.storage_image_urls, gd.ai_analysis_raw, udm.user_id FROM guitar_deals gd "
                                   "LEFT JOIN LATERAL (SELECT user_id FROM user_deal_matches WHERE deal_id = gd.id LIMIT 1) udm ON true "
                                   "WHERE gd.id = %s", (lid,)).fetchone()
                if not row:
                    print(f"  ⚠️ {lid} introuvable, sautée", flush=True)
                    continue
                ai = row["ai_analysis_raw"]
                ai = json.loads(ai) if isinstance(ai, str) else (ai or {})
                urls = row.get("storage_image_urls") or row.get("image_urls") or []
                urls = json.loads(urls) if isinstance(urls, str) else urls
                images = [img for u in urls[:cq.MAX_IMAGES] if (img := cq._download_and_optimize_image(u))]
                cfg = cq._get_user_analysis_config(conn, row["user_id"], {})
                instruction = cfg.get("gatekeeperVerbosityInstruction", DEFAULT_GATEKEEPER_INSTRUCTION)
                if isinstance(instruction, list):
                    instruction = "\n".join(instruction)
                cache = {"id": lid, "row": row, "images": images, "taxonomy": cfg.get("taxonomy", DEFAULT_TAXONOMY),
                         "instruction": instruction, "photo_text": ai.get("visual_inspection") or ""}

            row = cache["row"]
            kb_block, fiches = "", []
            if arm in ("with", "photo", "portier"):
                extra = {"photo": cache["photo_text"], "portier": (ocr.get(lid) or {}).get("photo_text", "")}.get(arm)
                texts = [row["title"], row["description"]] + ([extra] if extra is not None else [])
                # « portier » : EXACTEMENT la recherche de la prod (tolérance aux fautes de lecture sur le texte des photos).
                fiches = gk.lookup(conn, *texts, limit=T1_KNOWLEDGE_MAX_FICHES,
                                   fuzzy_texts=(0, 2) if arm == "portier" else (0,))
                kb_block = gk.format_for_prompt(fiches)
            prompt = build_t1_gatekeeper_prompt(row, cache["taxonomy"], cache["instruction"], knowledge_block=kb_block)
            images, _info = fit_images_to_budget(cache["images"], prompt, cq.QWEN_LOCAL_NUM_CTX,
                                                 int(os.getenv("T1_LOCAL_RESPONSE_MARGIN_TOKENS", "600")))
            t0 = time.monotonic()
            result, err, json_valid, completion_tokens, _r, _raw = cq._call_qwen_local_json(
                prompt, images, cq.QWEN_LOCAL_MODEL, temperature=None, seed=None)
            latency = round(time.monotonic() - t0, 1)
            verdict = (result.get("status") or "UNKNOWN").upper() if (result and not err) else None
            line = {"id": lid, "stratum": stratum, "arm": arm, "rep": rep, "stage": stage, "verdict": verdict,
                    "rejected": bool(verdict) and is_rejected(verdict), "error": err, "kb_ids": [f["id"] for f in fiches],
                    "n_images": len(images), "latency_s": latency}
            out.write(json.dumps(line, ensure_ascii=False) + "\n")
            out.flush()
            consecutive_failures = 0 if verdict else consecutive_failures + 1
            print(f"[{n}/{len(jobs)}] {lid} {arm} #{rep} → {verdict or 'ÉCHEC'} ({latency}s)", flush=True)
            if consecutive_failures >= 8:
                raise SystemExit("8 échecs de suite : le Dell répond-il ? (ollama ps) Relancer la même commande pour reprendre.")


def case_report(results):
    """Taux de rejet par annonce et par bras pour les appels de l'étape `case` (fonction pure, testée)."""
    by = defaultdict(lambda: defaultdict(list))
    for r in results:
        if r.get("stage") == "case" and r.get("verdict"):
            by[r["id"]][r["arm"]].append(r)
    out = {}
    for lid, arms in by.items():
        out[lid] = {arm: {"n": len(rows), "rejected": sum(1 for x in rows if x["rejected"]),
                          "verdicts": dict(sorted(_count(x["verdict"] for x in rows).items())),
                          "kb_ids": rows[-1].get("kb_ids", [])} for arm, rows in arms.items()}
    return out


def _count(items):
    c = defaultdict(int)
    for i in items:
        c[i] += 1
    return c


def print_case_report(rep):
    for lid, arms in rep.items():
        print(f"\nAnnonce {lid}")
        for arm in ("without", "with", "photo", "portier"):
            if arm in arms:
                a = arms[arm]
                print(f"  {arm:8s}: rejetée {a['rejected']}/{a['n']} fois   verdicts {a['verdicts']}   fiches {len(a['kb_ids'])}")
    print("\n(Lecture : si « without » rejette souvent et que « with »/« portier » rejettent peu, la fiche corrige l'erreur. "
          "Un cas ne mesure pas les dégâts ailleurs : voir la strate B.)")


# ── Lecture des photos par le Portier : exécution et contrôle ─────────────────────────────────────────────────────────
def analyze_ocr(plan, ocr_lines):
    """Contrôle de la lecture des photos (fonction pure, testée). Référence = ce que l'EXPERT a lu sur les photos :
    pour les annonces où ce texte apporte des fiches que le titre et la description n'apportent pas (`kb_photo` ⊋
    `kb_with`), on regarde si le texte lu par le PORTIER retrouve ces fiches. Ce n'est pas une vérité terrain (l'Expert
    peut se tromper) mais la meilleure référence disponible sans étiqueter à la main."""
    last = {}
    for line in ocr_lines:                       # dernière tentative par annonce
        last[line["id"]] = line
    listings = {l["id"]: l for l in plan["listings"]}
    attempted = [i for i in last if i in listings]
    failed = [i for i in attempted if last[i].get("error")]
    ok = [i for i in attempted if i not in set(failed)]
    targets = [i for i in ok if set(listings[i]["kb_photo"]) - set(listings[i]["kb_with"])]
    recovered = [i for i in targets if (set(listings[i]["kb_photo"]) - set(listings[i]["kb_with"])) <= set(last[i]["kb_portier"])]
    extra = [i for i in ok if set(last[i]["kb_portier"]) - set(listings[i]["kb_photo"]) - set(listings[i]["kb_with"])]
    out = {"n_planned": len(listings), "n_attempted": len(attempted), "n_failed": len(failed), "n_ok": len(ok),
           "n_empty_text": sum(1 for i in ok if not last[i]["photo_text"]), "n_targets": len(targets),
           "n_recovered": len(recovered), "missed_ids": sorted(set(targets) - set(recovered)),
           "n_extra": len(extra), "extra_ids": sorted(extra),
           "recovery": (len(recovered) / len(targets)) if targets else None,
           "failure_rate": (len(failed) / len(attempted)) if attempted else None,
           "median_latency_s": sorted(last[i].get("latency_s") or 0 for i in ok)[len(ok) // 2] if ok else None}
    if len(attempted) < len(listings):
        verdict = "INCOMPLET"
    elif out["failure_rate"] > OCR_MAX_FAILURE_RATE:
        verdict = "NON CONCLUANT (trop de lectures en échec)"
    elif len(targets) < OCR_MIN_TARGETS:
        verdict = "NON CONCLUANT (pas assez d'annonces-cibles)"
    elif out["recovery"] >= OCR_MIN_RECOVERY:
        verdict = "LECTURE SUFFISANTE"
    else:
        verdict = "LECTURE INSUFFISANTE"
    out["verdict"] = verdict
    return out


def print_ocr_report(rep):
    print(f"Lectures faites : {rep['n_attempted']}/{rep['n_planned']} ({rep['n_failed']} en échec, "
          f"{rep['n_empty_text']} sans aucun texte lisible)")
    if rep["median_latency_s"] is not None:
        print(f"Durée médiane d'une lecture : {rep['median_latency_s']} s (s'ajoute à l'appel du Portier)")
    if rep["recovery"] is not None:
        print(f"Annonces-cibles (le texte lu par l'Expert apporte une fiche absente du titre/de la description) : {rep['n_targets']}")
        print(f"  fiches retrouvées par le Portier : {rep['n_recovered']}/{rep['n_targets']} = {100 * rep['recovery']:.0f} % "
              f"(seuil fixé d'avance : {100 * OCR_MIN_RECOVERY:.0f} %)")
        if rep["missed_ids"]:
            print(f"  ids manqués (à relire à la main) : {', '.join(rep['missed_ids'][:15])}{' …' if len(rep['missed_ids']) > 15 else ''}")
    print(f"Annonces où le Portier trouve une fiche que ni le titre ni l'Expert n'apportent : {rep['n_extra']} "
          f"(à relire : vrai gain ou fausse lecture)")
    if rep["extra_ids"]:
        print(f"  ids : {', '.join(rep['extra_ids'][:15])}{' …' if len(rep['extra_ids']) > 15 else ''}")
    print("\n" + "=" * 70)
    print(f"VERDICT LECTURE : {rep['verdict']}")
    print({"LECTURE SUFFISANTE": "  → on peut lancer le rejeu complet avec le bras « portier ».",
           "LECTURE INSUFFISANTE": "  → le Portier lit trop mal les photos : corriger la lecture (prompt, taille des photos) AVANT d'investir "
                                   "des heures de Dell dans le rejeu.",
           "INCOMPLET": "  → relancer la même commande `ocr` pour terminer les lectures.",
           }.get(rep["verdict"], "  → ne rien conclure (voir les chiffres ci-dessus)."))


def run_ocr(args):
    """Étape `ocr` : le Portier lit les photos de chaque annonce du plan (une fois, reprenable) et on enregistre le texte
    lu et les fiches qu'il permet de trouver. Même prompt, même schéma et mêmes photos que la prod."""
    import psycopg
    from psycopg.rows import dict_row
    from backend import guitar_knowledge as gk
    from backend.scripts import compare_qwen_local_vs_prod as cq
    from backend.t1_image_budget import fit_images_to_budget
    from backend.t1_photo_text import PHOTO_TEXT_JSON_SCHEMA, PHOTO_TEXT_PROMPT, parse_photo_text
    from config import T1_KNOWLEDGE_MAX_FICHES

    nonprod = check_fidelity(cq, args.allow_nonprod)
    with open(os.path.join(cq.RESULTS_DIR, args.plan), encoding="utf-8") as fh:
        plan = json.load(fh)
    path = os.path.join(cq.RESULTS_DIR, args.ocr)
    done = set(load_ocr(path))
    meta = plan["meta"]
    gk.configure_version(meta["kb_version_mode"])
    gk.configure_review_gate(meta["review_gate"])
    cq.ACTIVE_T1_SCHEMA = PHOTO_TEXT_JSON_SCHEMA
    todo = [l for l in plan["listings"] if l["id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} lecture(s) à faire ; ~{len(todo) * 15 / 60:.0f} min. Écart avec la prod : {nonprod or 'aucun'}", flush=True)
    os.makedirs(cq.RESULTS_DIR, exist_ok=True)
    failures = 0
    with psycopg.connect(cq.DATABASE_URL, row_factory=dict_row) as conn, open(path, "a", encoding="utf-8") as out:
        for n, l in enumerate(todo, 1):
            row = conn.execute("SELECT id, title, description, image_urls, storage_image_urls FROM guitar_deals WHERE id = %s",
                               (l["id"],)).fetchone()
            if not row:
                print(f"  ⚠️ {l['id']} introuvable, sautée", flush=True)
                continue
            urls = row.get("storage_image_urls") or row.get("image_urls") or []
            urls = json.loads(urls) if isinstance(urls, str) else urls
            images = [img for u in urls[:cq.MAX_IMAGES] if (img := cq._download_and_optimize_image(u))]
            images, _info = fit_images_to_budget(images, PHOTO_TEXT_PROMPT, cq.QWEN_LOCAL_NUM_CTX,
                                                 int(os.getenv("T1_LOCAL_RESPONSE_MARGIN_TOKENS", "600")))
            t0 = time.monotonic()
            result, err, *_rest = cq._call_qwen_local_json(PHOTO_TEXT_PROMPT, images, cq.QWEN_LOCAL_MODEL,
                                                           temperature=None, seed=None)
            latency = round(time.monotonic() - t0, 1)
            text = parse_photo_text(result) if (result and not err) else ""
            err = err or (None if result else "réponse vide")
            fiches = gk.lookup(conn, row["title"], row["description"], text, limit=T1_KNOWLEDGE_MAX_FICHES,
                               fuzzy_texts=(0, 2)) if text else gk.lookup(conn, row["title"], row["description"],
                                                                          limit=T1_KNOWLEDGE_MAX_FICHES)
            out.write(json.dumps({"id": l["id"], "stratum": l["stratum"], "photo_text": text,
                                  "kb_portier": [f["id"] for f in fiches], "error": err, "n_images": len(images),
                                  "latency_s": latency}, ensure_ascii=False) + "\n")
            out.flush()
            failures = failures + 1 if err else 0
            print(f"[{n}/{len(todo)}] {l['id']} → {'ÉCHEC' if err else (str(len(text)) + ' car.')} ({latency}s)", flush=True)
            if failures >= 8:
                raise SystemExit("8 échecs de suite : le Dell répond-il ? (ollama ps) Relancer la même commande pour reprendre.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="choisit les annonces des strates A et B")
    p.add_argument("--out", default="kb_plan.json")
    p.add_argument("--kb-version", default="latest")
    p.add_argument("--gate", choices=("strict", "none"), default="strict",
                   help="strict = seules les fiches relues/curées/manuelles (la prod) ; none = toutes (borne haute du contenu)")
    p.add_argument("--n-b", type=int, default=DEFAULTS["n_b"])
    p.add_argument("--max-a", type=int, default=DEFAULTS["max_a"])
    p.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    p.add_argument("--exclude-ids", default="")
    p.add_argument("--only-ids", default="", help="mode « cas précis » : ids séparés par des virgules (plan = ces annonces seulement)")
    r = sub.add_parser("run", help="rejoue les annonces du plan (reprenable)")
    r.add_argument("--plan", default="kb_plan.json")
    r.add_argument("--results", default="kb_paired.jsonl")
    r.add_argument("--ocr", default="kb_ocr.jsonl", help="lectures du Portier (bras « portier ») ; absent = bras sauté")
    r.add_argument("--stage", choices=("screen", "eval", "case"), required=True)
    r.add_argument("--screen-reps", type=int, default=DEFAULTS["screen_reps"])
    r.add_argument("--reps-a", type=int, default=DEFAULTS["reps_a"])
    r.add_argument("--reps-b", type=int, default=DEFAULTS["reps_b"])
    r.add_argument("--limit", type=int, default=0, help="n'exécute que N appels (essai)")
    r.add_argument("--allow-nonprod", action="store_true")
    r.add_argument("--note", default="", help="note consignée dans le fichier de méta (ex. dérogation décidée par l'utilisateur)")
    o = sub.add_parser("ocr", help="le Portier lit les photos des annonces du plan (reprenable)")
    o.add_argument("--plan", default="kb_plan.json")
    o.add_argument("--ocr", default="kb_ocr.jsonl")
    o.add_argument("--limit", type=int, default=0, help="ne fait que N lectures (essai)")
    o.add_argument("--allow-nonprod", action="store_true")
    c = sub.add_parser("ocr-check", help="contrôle de la lecture (seuil fixé d'avance), aucun appel IA")
    c.add_argument("--plan", default="kb_plan.json")
    c.add_argument("--ocr", default="kb_ocr.jsonl")
    k = sub.add_parser("case-report", help="taux de rejet par bras pour l'étape `case` (aucun appel IA)")
    k.add_argument("--results", default="kb_paired.jsonl")
    q = sub.add_parser("report", help="analyse (aucun appel IA)")
    q.add_argument("--plan", default="kb_plan.json")
    q.add_argument("--results", default="kb_paired.jsonl")
    args = ap.parse_args(argv)

    results_dir = os.path.join(os.path.dirname(__file__), "..", "benchmark", "results")
    if args.cmd == "plan":
        import psycopg
        from psycopg.rows import dict_row
        dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
        if not dsn:
            sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            conn.read_only = True
            plan = build_plan(conn, args.kb_version, args.gate == "strict", args.n_b, args.max_a, args.seed,
                              [x for x in args.exclude_ids.split(",") if x.strip()],
                              [x.strip() for x in args.only_ids.split(",") if x.strip()])
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, args.out), "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=1)
        n_a = sum(1 for l in plan["listings"] if l["stratum"] == "A")
        if args.only_ids:
            found = {l["id"] for l in plan["listings"]}
            missing = [x.strip() for x in args.only_ids.split(",") if x.strip() and x.strip() not in found]
            print(f"Plan « cas précis » écrit : {len(found)} annonce(s)" + (f" ; INTROUVABLE(S) : {missing}" if missing else "") + ".")
            for l in plan["listings"]:
                print(f"  {l['id']} : fiches par titre+description {len(l['kb_with'])}, avec le texte lu par l'Expert {len(l['kb_photo'])}")
            return
        print(f"Plan écrit : {n_a} annonce(s) en A, {len(plan['listings']) - n_a} en B ; base v{plan['meta']['kb_version']}, "
              f"porte {'active' if plan['meta']['review_gate'] else 'éteinte'}.")
        if n_a < MIN_A_LISTINGS:
            print(f"⚠️ A a {n_a} annonce(s) < {MIN_A_LISTINGS} avant même le dépistage : le test sera NON CONCLUANT. "
                  f"Relire plus de fiches (knowledge_gate_report) ou essayer --gate none.")
    elif args.cmd == "run":
        run(args)
    elif args.cmd == "case-report":
        print_case_report(case_report(load_results(os.path.join(results_dir, args.results))))
    elif args.cmd == "ocr":
        run_ocr(args)
    elif args.cmd == "ocr-check":
        with open(os.path.join(results_dir, args.plan), encoding="utf-8") as fh:
            plan = json.load(fh)
        print_ocr_report(analyze_ocr(plan, load_results(os.path.join(results_dir, args.ocr))))
    else:
        with open(os.path.join(results_dir, args.plan), encoding="utf-8") as fh:
            plan = json.load(fh)
        print_report(analyze(plan, load_results(os.path.join(results_dir, args.results))))


if __name__ == "__main__":
    main()
