"""Mesure du bruit naturel d'un candidat — question soulevée par l'analyse Opus du Chantier B
(JOURNAL.md 2026-09-12) et confirmée empiriquement par l'utilisateur sur deux paires réelles
d'annonces quasi-identiques (même guitare/bundle, titre légèrement différent, verdict/état
stables mais valeur/marge variant de ~50 points) : la cascade de production a une vraie variance
run-à-run, même sans changement de photo ni de config (`temperature=0.1`, jamais 0). Sans
connaître cette variance, un écart entre deux candidats ne peut pas être attribué avec confiance
à une vraie différence de qualité plutôt qu'au bruit normal du système.

Généralisé (2026-09-12) au-delà du seul `analyzer_prod` : la même question se pose pour la
priorité de l'utilisateur (remplacer `gemini_pro` par `claude_sonnet` au Tier 3) — le -17 points
d'identification mesuré entre les deux au comparatif à 10 candidats (run #27-29) n'a jamais été
testé en répétition, contrairement au Bras A/Bras B du Chantier B où le bruit s'est avéré aussi
grand que l'écart mesuré.

Ce script rejoue un ou plusieurs candidats N fois sur le même sous-ensemble d'items, juge chaque
répétition contre la vérité terrain, puis mesure le taux d'accord "avec soi-même" par axe — et,
si plusieurs candidats sont donnés, calcule directement si l'écart entre eux dépasse le bruit
propre à chacun.

Usage :
    python -m backend.benchmark.noise_floor_test --models analyzer_prod
    python -m backend.benchmark.noise_floor_test --models gemini_pro,claude_sonnet
"""
import argparse
import json
import os
from datetime import datetime, timezone

from backend.benchmark.candidates import CANDIDATES
from backend.benchmark.judge import JUDGE_AXES, evaluate_with_llm_judge
from backend.benchmark.run_benchmark import load_dataset

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
N_REPEATS = 3
N_ITEMS = 10


def run_noise_floor(model_key, call_fn, items):
    all_results = []
    for item in items:
        print(f"\n--- [{model_key}] {item['id']} ---")
        repeats = []
        for rep in range(N_REPEATS):
            candidate_result = call_fn(item)
            answer = candidate_result["answer"]
            verdict = evaluate_with_llm_judge(item["question"], item["ground_truth"], answer)
            scores = verdict["scores"]
            repeats.append({"answer": answer, "scores": scores, "latency_s": candidate_result.get("latency_s")})
            scores_str = " ".join(f"{axis}={scores[axis]}" for axis in JUDGE_AXES)
            print(f"  répétition {rep + 1}/{N_REPEATS} : {scores_str}")

        agreement = {}
        for axis in JUDGE_AXES:
            values = [r["scores"].get(axis) for r in repeats]
            agreement[axis] = len(set(values)) == 1  # les N répétitions tombent-elles d'accord ?

        all_results.append({"id": item["id"], "repeats": repeats, "agreement": agreement})
    return all_results


def summarize_noise(model_key, all_results):
    print(f"\n{'=' * 60}\nRÉSUMÉ — accord de {model_key} avec lui-même (bruit naturel), par axe\n{'=' * 60}")
    n = len(all_results)
    rep_rates = {axis: [] for axis in JUDGE_AXES}
    for axis in JUDGE_AXES:
        n_agree = sum(1 for r in all_results if r["agreement"][axis])
        print(f"  {axis:15s} : {n_agree}/{n} items où les {N_REPEATS} répétitions tombent d'accord ({100 * n_agree / n:.1f}%)")
        disagreements = [r["id"] for r in all_results if not r["agreement"][axis]]
        if disagreements:
            print(f"                    désaccord sur : {disagreements}")
        for rep_idx in range(N_REPEATS):
            vals = [r["repeats"][rep_idx]["scores"][axis] for r in all_results]
            rep_rates[axis].append(100 * sum(vals) / len(vals))
    print(f"  Taux par répétition (chacune un run indépendant) :")
    for axis in JUDGE_AXES:
        rates = rep_rates[axis]
        spread = max(rates) - min(rates)
        print(f"    {axis:15s} : {[f'{r:.1f}' for r in rates]} -> écart max = {spread:.1f} points")
    return rep_rates


def main():
    parser = argparse.ArgumentParser(description="Mesure du bruit naturel d'un ou plusieurs candidats")
    parser.add_argument("--models", default="analyzer_prod", help="Candidats séparés par des virgules (ex: gemini_pro,claude_sonnet)")
    args = parser.parse_args()

    requested = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in requested if m not in CANDIDATES]
    if unknown:
        print(f"Modèles inconnus ignorés : {unknown}")

    dataset = load_dataset()
    items = [i for i in dataset if i.get("stratum") in ("tier2", "tier3")][:N_ITEMS]
    print(f"Items sélectionnés : {len(items)} (sur {sum(1 for i in dataset if i.get('stratum') in ('tier2', 'tier3'))} tier2/tier3 disponibles)")

    all_rep_rates = {}
    all_out = {}
    for model_key in requested:
        if model_key not in CANDIDATES:
            continue
        results = run_noise_floor(model_key, CANDIDATES[model_key], items)
        rep_rates = summarize_noise(model_key, results)
        all_rep_rates[model_key] = rep_rates
        all_out[model_key] = results

    if len(all_rep_rates) >= 2:
        print(f"\n{'=' * 60}\nÉCART ENTRE CANDIDATS vs BRUIT PROPRE À CHACUN\n{'=' * 60}")
        keys = list(all_rep_rates.keys())
        for axis in JUDGE_AXES:
            means = {k: sum(all_rep_rates[k][axis]) / len(all_rep_rates[k][axis]) for k in keys}
            noises = {k: max(all_rep_rates[k][axis]) - min(all_rep_rates[k][axis]) for k in keys}
            gap = abs(means[keys[0]] - means[keys[1]])
            max_noise = max(noises.values())
            verdict = "ÉCART > BRUIT (signal probable)" if gap > max_noise else "écart <= bruit (non concluant)"
            print(f"  {axis:15s} : {keys[0]}={means[keys[0]]:.1f}% (bruit {noises[keys[0]]:.1f}) vs {keys[1]}={means[keys[1]]:.1f}% (bruit {noises[keys[1]]:.1f}) -> écart={gap:.1f} pts -> {verdict}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"noise_floor_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": all_out}, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
