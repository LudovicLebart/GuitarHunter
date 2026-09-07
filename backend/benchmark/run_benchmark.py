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

Score par axe (CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md §0/§5) : identification/
etat/valeur/hallucination, jamais agrégés en un score composite. Le rapport de
perception d'un candidat (aujourd'hui : `hybrid`) est jugé séparément sur le
respect du garde-fou anti-interprétation (§2), indépendamment de sa réponse
finale. Usage (tokens) et latence sont capturés par candidate, pour l'étude des
paliers de longueur de description prévue au §5/§7.

Usage :
    python -m backend.benchmark.run_benchmark
    python -m backend.benchmark.run_benchmark --models gemini,qwen --limit 5

Clés API requises (.env), selon les candidats sélectionnés :
    GEMINI_API_KEY, OPENAI_API_KEY, TOKENROUTER_API_KEY, ANTHROPIC_API_KEY
    (ANTHROPIC_API_KEY sert à la fois au juge, toujours requis, et au candidat claude_sonnet)
"""
import argparse
import json
import os
from datetime import datetime, timezone

from backend.benchmark.candidates import CANDIDATES
from backend.benchmark.judge import JUDGE_AXES, evaluate_perception_report, evaluate_with_llm_judge

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def load_dataset(path=DATASET_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_candidate(model_key, call_fn, dataset):
    results = []
    for item in dataset:
        try:
            candidate_result = call_fn(item["question"], item.get("image_urls", []))
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
        verdict = evaluate_with_llm_judge(item["question"], item["ground_truth"], answer)
        perception_report = candidate_result.get("perception_report")
        perception_verdict = evaluate_perception_report(perception_report)
        results.append({
            "id": item["id"],
            "candidate_answer": answer,
            "perception_report": perception_report,
            "usage": candidate_result.get("usage"),
            "latency_s": candidate_result.get("latency_s"),
            "scores": verdict["scores"],
            "justification": verdict.get("justification", ""),
            "perception_verdict": perception_verdict,
        })
        scores_str = " ".join(f"{axis}={verdict['scores'][axis]}" for axis in JUDGE_AXES)
        print(f"  [{model_key}] {item['id']} : {scores_str} — {verdict.get('justification', '')}")
    return results


def summarize(results):
    """Une ligne par axe, jamais un score composite (§0). Ajoute les totaux d'usage/latence
    pour situer le coût réel — informatif, pas agrégé avec les scores de qualité."""
    total = len(results)
    axis_pass_rate = {
        axis: round(100 * sum(r["scores"].get(axis, 0) for r in results) / total, 1) if total else 0.0
        for axis in JUDGE_AXES
    }
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
        default="gemini,gemini_pro,gemini_pro_compact,gpt4o_mini,qwen,hybrid,claude_sonnet,perception_qwen,perception_flash_lite",
        help="Modèles candidats séparés par des virgules",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limiter le nombre d'items du dataset")
    args = parser.parse_args()

    dataset = load_dataset()
    if args.limit:
        dataset = dataset[: args.limit]

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
        results = run_candidate(model_key, CANDIDATES[model_key], dataset)
        all_results[model_key] = results
        summary[model_key] = summarize(results)

    print("\n" + "=" * 60)
    print("RÉSULTATS FINAUX — une ligne par axe, jamais un score composite")
    print("=" * 60)
    for model_key, s in summary.items():
        print(f"\n{model_key} ({s['n_items']} items) :")
        for axis, rate in s["taux_reussite_par_axe"].items():
            print(f"   {axis:15s} : {rate:.1f}%")
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
