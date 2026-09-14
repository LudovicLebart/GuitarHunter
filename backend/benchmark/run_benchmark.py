"""Benchmark GuitarHunter — compare les modèles vision candidats (Gemini Tier 2
Analyste, Gemini Tier 3 Expert Pro, GPT-5-mini, Qwen3.8-flash via TokenRouter —
voir backend/benchmark/candidates.py pour les identifiants exacts et les
surcharger via BENCHMARK_GPT_MODEL/BENCHMARK_QWEN_MODEL) sur un jeu d'annonces
réelles, jugés par Claude contre une vérité terrain de lutherie. Inclure le
Tier 3 sert de plafond de référence : situer le Tier 2 (moins cher, utilisé en
prod par défaut) par rapport à la fois aux concurrents externes et à ce que
Gemini fait de mieux.

Usage :
    python -m backend.benchmark.run_benchmark
    python -m backend.benchmark.run_benchmark --models gemini,qwen --limit 5

Clés API requises (.env), selon les candidats sélectionnés :
    GEMINI_API_KEY, OPENAI_API_KEY, TOKENROUTER_API_KEY, ANTHROPIC_API_KEY (juge, toujours requis)
"""
import argparse
import json
import os
from datetime import datetime, timezone

from backend.benchmark.candidates import CANDIDATES
from backend.benchmark.judge import evaluate_with_llm_judge

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def load_dataset(path=DATASET_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_candidate(model_key, call_fn, dataset):
    results = []
    for item in dataset:
        try:
            answer = call_fn(item["question"], item.get("image_urls", []))
        except Exception as e:
            print(f"  [{model_key}] {item['id']} : échec appel modèle ({e})")
            results.append({
                "id": item["id"], "candidate_answer": None,
                "score": 0, "justification": f"Échec appel modèle : {e}",
            })
            continue

        verdict = evaluate_with_llm_judge(item["question"], item["ground_truth"], answer)
        results.append({
            "id": item["id"],
            "candidate_answer": answer,
            "score": verdict.get("score", 0),
            "justification": verdict.get("justification", ""),
        })
        print(f"  [{model_key}] {item['id']} : score={verdict.get('score', 0)} — {verdict.get('justification', '')}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Benchmark GuitarHunter — comparaison de modèles vision")
    parser.add_argument("--models", default="gemini,gemini_pro,gpt4o_mini,qwen", help="Modèles candidats séparés par des virgules")
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
        total = len(results)
        score_sum = sum(r["score"] for r in results)
        summary[model_key] = round((score_sum / total) * 100, 2) if total else 0.0

    print("\n" + "=" * 40)
    print("RÉSULTATS FINAUX")
    print("=" * 40)
    for model_key, accuracy in summary.items():
        print(f"{model_key:15s} : {accuracy:.2f}%")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"benchmark_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": all_results}, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
