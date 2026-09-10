"""Benchmark GuitarHunter — compare les modèles vision candidats (Gemini Tier 2
Analyste, Gemini Tier 3 Expert Pro, GPT-5-mini, Qwen3.8-flash via TokenRouter,
un candidat "hybrid" et un candidat "gemini_pro_compact" expérimentaux — voir
backend/benchmark/candidates.py pour les identifiants exacts et les surcharger
via BENCHMARK_GPT_MODEL/BENCHMARK_QWEN_MODEL) sur un jeu d'annonces réelles,
jugés par Claude contre une vérité terrain de lutherie. Inclure le Tier 3 sert
de plafond de référence : situer le Tier 2 (moins cher, utilisé en prod par
défaut) par rapport à la fois aux concurrents externes et à ce que Gemini fait
de mieux. Le candidat "hybrid" teste une architecture à deux étages : Qwen
décrit les photos en texte (extraction vision), puis Gemini Tier 3 répond à la
question à partir de ce texte seul (raisonnement) — à comparer aux candidats
mono-modèle pour voir si séparer perception et raisonnement apporte un gain.
Le candidat "gemini_pro_compact" teste si forcer le Tier 3 (dont le prompt de
prod exige un rapport "EXHAUSTIF", contrairement au Tier 2 déjà en puces) à
répondre en puces strictes, puis réécrire cette sortie en prose par un modèle
bon marché (gemini-3.5-flash-lite), dégrade le raisonnement par rapport à
`gemini_pro` — un score équivalent validerait ~55% d'économie sur le poste de
sortie du Tier 3 ($12/M tokens). Le candidat "claude_sonnet" compare Claude
Sonnet 5 (vision native) à Gemini sur le même jeu de questions — comparatif
coût ET qualité demandé par l'utilisateur (2026-09-07), pas seulement le rôle
de juge que Claude tient déjà (judge.py). Les candidats "perception_qwen" et
"perception_flash_lite" appliquent le contrat de perception formel du Chantier
B (`backend/benchmark/perception_contract.py`, dérivé champ par champ du JSON
de prod) via Qwen3.8-Flash ou le modèle du Tier 1 actuel, puis font raisonner
Gemini Tier 3 sur le texte seul — à comparer à `hybrid` (extraction plus
ancienne, non structurée) et aux candidats mono-modèle pour mesurer si la
perception bon marché égale la qualité actuelle, à quel coût (§0/§5 du plan).
Le candidat "analyzer_prod" est le Bras A (référence) du protocole §5 : il
appelle `DealAnalyzer.analyze_deal()` tel quel (vrai prompt/taxonomie/few-shot/
schéma JSON de production), contrairement à tous les autres candidats qui
posent la question en texte libre — sans lui, aucun score de ce harnais n'a
d'étalon de production (voir JOURNAL.md 2026-09-09, run complet #25 annulé
avant sa création précisément pour cette raison : l'axe "valeur" tombait à 0%
pour tous les candidats, y compris "gemini"/"gemini_pro", sans qu'on puisse
distinguer un vrai problème de candidat d'un protocole qui handicapait tout le
monde pareil).

Score par axe (CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md §0/§5) : identification/
etat/valeur/hallucination, jamais agrégés en un score composite. Le rapport de
perception d'un candidat (aujourd'hui : `hybrid`) est jugé séparément sur le
respect du garde-fou anti-interprétation (§2), indépendamment de sa réponse
finale. Usage (tokens) et latence sont capturés par candidate, pour l'étude des
paliers de longueur de description prévue au §5/§7.

Usage :
    python -m backend.benchmark.run_benchmark
    python -m backend.benchmark.run_benchmark --models gemini,qwen --limit 5
    python -m backend.benchmark.run_benchmark --models qwen,hybrid \
        --resume backend/benchmark/results/benchmark_20260909T153213Z.json

Clés API requises (.env), selon les candidats sélectionnés :
    GEMINI_API_KEY, OPENAI_API_KEY, TOKENROUTER_API_KEY, ANTHROPIC_API_KEY
    (ANTHROPIC_API_KEY sert à la fois au juge, toujours requis, et au candidat claude_sonnet)

`--resume` (ajouté 2026-09-10, incident de crédit Anthropic épuisé en cours du run complet
#27) : réutilise un fichier de résultats précédent (même format que celui produit dans
RESULTS_DIR) item par item, sans jamais rappeler un candidat ni un juge qui a déjà réussi.
Trois cas par item, décidés indépendamment pour la réponse candidate et pour chaque juge
(principal + garde-fou perception, tous deux exposés à la même panne car ils partagent
ANTHROPIC_API_KEY) : (1) réponse ET jugements déjà propres → réutilisé tel quel, zéro appel ;
(2) réponse propre mais un jugement contaminé (`justification` contient le message d'erreur
crédit Anthropic) → seul le juge concerné est rejoué, la réponse candidate déjà bonne n'est
pas repayée ; (3) réponse absente ou échouée (timeout ou crédit épuisé au moment de l'appel
candidat lui-même) → tout est rejoué comme un run normal. Permet de ne payer que ce qui a
réellement échoué plutôt qu'un rerun complet de chaque candidat concerné.
"""
import argparse
import json
import os
from datetime import datetime, timezone

from backend.benchmark.candidates import CANDIDATES
from backend.benchmark.judge import JUDGE_AXES, evaluate_perception_report, evaluate_with_llm_judge

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Message d'erreur exact renvoyé par l'API Anthropic à crédit épuisé (voir JOURNAL.md
# 2026-09-10) — sert à distinguer, dans un fichier de résultats précédent, un échec de panne
# de facturation (à rejouer via --resume) d'un vrai échec de qualité (scores 0 légitimes,
# jamais rejoués silencieusement par --resume).
_CREDIT_ERROR_MARKER = "credit balance is too low"


def _is_credit_contaminated(justification):
    return bool(justification) and _CREDIT_ERROR_MARKER in justification.lower()


def load_dataset(path=DATASET_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_previous_results(path):
    """Charge un fichier de résultats précédent (format RESULTS_DIR) en {model_key: {id: résultat}}
    pour un accès direct par item dans run_candidate(). `path` peut être None (pas de --resume)."""
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        model_key: {r["id"]: r for r in results}
        for model_key, results in data.get("details", {}).items()
    }


def run_candidate(model_key, call_fn, dataset, previous=None):
    results = []
    for item in dataset:
        prev = (previous or {}).get(item["id"])
        call_failed_before = prev is not None and prev.get("candidate_answer") is None
        need_full_rerun = prev is None or call_failed_before

        if need_full_rerun:
            try:
                candidate_result = call_fn(item)
            except Exception as e:
                print(f"  [{model_key}] {item['id']} : échec appel modèle ({e})")
                results.append({
                    "id": item["id"],
                    "candidate_answer": None,
                    "perception_report": None,
                    "usage": None,
                    "latency_s": None,
                    "scores": {axis: 0 for axis in JUDGE_AXES},
                    "justification": f"Échec appel modèle : {e}",
                    "perception_verdict": None,
                })
                continue
            answer = candidate_result["answer"]
            perception_report = candidate_result.get("perception_report")
            usage = candidate_result.get("usage")
            latency_s = candidate_result.get("latency_s")
            need_rejudge = True
            need_re_perception_judge = True
        else:
            answer = prev["candidate_answer"]
            perception_report = prev.get("perception_report")
            usage = prev.get("usage")
            latency_s = prev.get("latency_s")
            need_rejudge = _is_credit_contaminated(prev.get("justification"))
            need_re_perception_judge = _is_credit_contaminated((prev.get("perception_verdict") or {}).get("justification"))

        if not need_full_rerun and not need_rejudge and not need_re_perception_judge:
            results.append(prev)
            print(f"  [{model_key}] {item['id']} : réutilisé tel quel (déjà propre)")
            continue

        if need_rejudge:
            if item.get("ground_truth"):
                verdict = evaluate_with_llm_judge(item["question"], item["ground_truth"], answer)
            else:
                # Rejet Tier 1 sans transcription manuelle dans le Banc d'Essai (rien à comparer) :
                # le candidat tourne quand même (utile pour une mesure future du comportement du
                # garde-fou Tier 1), mais hors scoring identification/etat/valeur/hallucination —
                # un axe à None (pas 0) pour ne pas fausser silencieusement le taux de réussite.
                verdict = {
                    "scores": {axis: None for axis in JUDGE_AXES},
                    "justification": "Pas de vérité terrain (rejet Tier 1 non transcrit) — hors scoring, exécuté à titre informatif.",
                }
        else:
            verdict = {"scores": prev["scores"], "justification": prev.get("justification", "")}

        if need_re_perception_judge:
            perception_verdict = evaluate_perception_report(perception_report)
        else:
            perception_verdict = prev.get("perception_verdict") if prev else None

        results.append({
            "id": item["id"],
            "candidate_answer": answer,
            "perception_report": perception_report,
            "usage": usage,
            "latency_s": latency_s,
            "scores": verdict["scores"],
            "justification": verdict.get("justification", ""),
            "perception_verdict": perception_verdict,
        })
        tag = "rejoué entièrement" if need_full_rerun else "rejugé seulement"
        scores_str = " ".join(f"{axis}={verdict['scores'][axis]}" for axis in JUDGE_AXES)
        print(f"  [{model_key}] {item['id']} ({tag}) : {scores_str} — {verdict.get('justification', '')}")
    return results


def summarize(results):
    """Une ligne par axe, jamais un score composite (§0). Ajoute les totaux d'usage/latence
    pour situer le coût réel — informatif, pas agrégé avec les scores de qualité."""
    total = len(results)
    # Un axe à None (pas de vérité terrain, ex. rejet Tier 1 non transcrit) est exclu du
    # dénominateur de son propre taux de réussite plutôt que compté comme un échec.
    axis_pass_rate = {}
    for axis in JUDGE_AXES:
        scored = [r["scores"].get(axis) for r in results if r["scores"].get(axis) is not None]
        axis_pass_rate[axis] = round(100 * sum(scored) / len(scored), 1) if scored else None
    perception_items = [r for r in results if (r.get("perception_verdict") or {}).get("contains_judgment") is not None]
    perception_summary = None
    if perception_items:
        judgment_leaks = sum(1 for r in perception_items if r["perception_verdict"]["contains_judgment"])
        identifiable = sum(1 for r in perception_items if r["perception_verdict"]["identification_possible"])
        perception_summary = {
            "items_avec_perception_report": len(perception_items),
            "fuites_interpretation": judgment_leaks,
            "identification_possible_depuis_texte_seul": identifiable,
        }
    input_tokens = [r["usage"]["input_tokens"] for r in results if r.get("usage") and r["usage"].get("input_tokens") is not None]
    output_tokens = [r["usage"]["output_tokens"] for r in results if r.get("usage") and r["usage"].get("output_tokens") is not None]
    latencies = [r["latency_s"] for r in results if r.get("latency_s") is not None]
    return {
        "n_items": total,
        "taux_reussite_par_axe": axis_pass_rate,
        "garde_fou_perception": perception_summary,
        "tokens_entree_moyen": round(sum(input_tokens) / len(input_tokens), 1) if input_tokens else None,
        "tokens_sortie_moyen": round(sum(output_tokens) / len(output_tokens), 1) if output_tokens else None,
        "latence_moyenne_s": round(sum(latencies) / len(latencies), 2) if latencies else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark GuitarHunter — comparaison de modèles vision")
    parser.add_argument(
        "--models",
        default="analyzer_prod,gemini,gemini_pro,gemini_pro_compact,gpt4o_mini,qwen,hybrid,claude_sonnet,perception_qwen,perception_flash_lite",
        help="Modèles candidats séparés par des virgules",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limiter le nombre d'items du dataset")
    parser.add_argument(
        "--resume",
        default=None,
        help="Chemin vers un fichier de résultats JSON précédent : ne rejoue que ce qui a "
             "échoué ou a été contaminé (voir docstring du module)",
    )
    args = parser.parse_args()

    dataset = load_dataset()
    if args.limit:
        dataset = dataset[: args.limit]

    previous_by_model = load_previous_results(args.resume)
    if args.resume:
        print(f"Mode resume : {args.resume}")

    requested = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in requested if m not in CANDIDATES]
    if unknown:
        print(f"Modèles inconnus ignorés : {unknown} (disponibles : {list(CANDIDATES.keys())})")

    summary = {}
    all_results = {}
    for model_key in requested:
        if model_key not in CANDIDATES:
            continue
        print(f"\n--- Évaluation de : {model_key} ---")
        results = run_candidate(model_key, CANDIDATES[model_key], dataset, previous=previous_by_model.get(model_key))
        all_results[model_key] = results
        summary[model_key] = summarize(results)

    print("\n" + "=" * 60)
    print("RÉSULTATS FINAUX — une ligne par axe, jamais un score composite")
    print("=" * 60)
    for model_key, s in summary.items():
        print(f"\n{model_key} ({s['n_items']} items) :")
        for axis, rate in s["taux_reussite_par_axe"].items():
            print(f"   {axis:15s} : {rate:.1f}%" if rate is not None else f"   {axis:15s} : n/a (aucune vérité terrain)")
        if s["garde_fou_perception"]:
            print(f"   garde-fou perception : {s['garde_fou_perception']}")
        if s["tokens_entree_moyen"] is not None:
            print(f"   tokens (in/out, moy.) : {s['tokens_entree_moyen']}/{s['tokens_sortie_moyen']}")
        if s["latence_moyenne_s"] is not None:
            print(f"   latence moyenne : {s['latence_moyenne_s']}s")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"benchmark_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": all_results}, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
