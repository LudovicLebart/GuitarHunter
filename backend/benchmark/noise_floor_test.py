"""Mesure du bruit naturel de `analyzer_prod` (Bras A) — question soulevée par l'analyse Opus
du Chantier B (JOURNAL.md 2026-09-12) et confirmée empiriquement par l'utilisateur sur deux
paires réelles d'annonces quasi-identiques (même guitare/bundle, titre légèrement différent,
verdict/état stables mais valeur/marge variant de ~50 points) : le pipeline de production a une
vraie variance run-à-run, même sans changement de photo ni de config (`temperature=0.1`, jamais
0). Sans connaître cette variance, un écart Bras A/Bras B ne peut pas être attribué avec
confiance à la perception plutôt qu'au bruit normal du système.

Ce script rejoue `analyzer_prod` (cascade réelle sur vraies photos, aucune perception) 3 fois sur
un sous-ensemble d'items, juge chaque répétition contre la vérité terrain (même juge, mêmes 4 axes
que les runs précédents), puis mesure le taux d'accord "avec soi-même" entre les 3 répétitions —
directement comparable à l'écart Bras A/Bras B déjà mesuré (run #31 : -11 à -18 points sur
l'identification, run #30 : 92,3%/84,6% d'accord Portier).

Usage :
    python -m backend.benchmark.noise_floor_test
"""
import json
import os
from datetime import datetime, timezone

from backend.benchmark.candidates import call_analyzer_prod
from backend.benchmark.judge import JUDGE_AXES, evaluate_with_llm_judge
from backend.benchmark.run_benchmark import load_dataset

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
N_REPEATS = 3
N_ITEMS = 10


def main():
    dataset = load_dataset()
    # Sous-ensemble des 27 items tier2/tier3 déjà testés au run #31 (comparable directement à
    # l'écart Bras A/Bras B mesuré dessus) — les 10 premiers dans l'ordre du dataset, pas un
    # tirage aléatoire, pour rester reproductible.
    items = [i for i in dataset if i.get("stratum") in ("tier2", "tier3")][:N_ITEMS]
    print(f"Items sélectionnés : {len(items)} (sur {sum(1 for i in dataset if i.get('stratum') in ('tier2', 'tier3'))} tier2/tier3 disponibles)")

    all_results = []
    for item in items:
        print(f"\n--- {item['id']} ---")
        repeats = []
        for rep in range(N_REPEATS):
            candidate_result = call_analyzer_prod(item)
            answer = candidate_result["answer"]
            verdict = evaluate_with_llm_judge(item["question"], item["ground_truth"], answer)
            scores = verdict["scores"]
            repeats.append({"answer": answer, "scores": scores, "latency_s": candidate_result.get("latency_s")})
            scores_str = " ".join(f"{axis}={scores[axis]}" for axis in JUDGE_AXES)
            print(f"  répétition {rep + 1}/{N_REPEATS} : {scores_str}")

        agreement = {}
        for axis in JUDGE_AXES:
            values = [r["scores"].get(axis) for r in repeats]
            agreement[axis] = len(set(values)) == 1  # les 3 répétitions tombent-elles d'accord ?

        all_results.append({"id": item["id"], "repeats": repeats, "agreement": agreement})

    print("\n" + "=" * 60)
    print("RÉSUMÉ — accord de analyzer_prod avec lui-même (bruit naturel), par axe")
    print("=" * 60)
    for axis in JUDGE_AXES:
        n_agree = sum(1 for r in all_results if r["agreement"][axis])
        n = len(all_results)
        print(f"  {axis:15s} : {n_agree}/{n} items où les {N_REPEATS} répétitions tombent d'accord ({100 * n_agree / n:.1f}%)")
        disagreements = [r["id"] for r in all_results if not r["agreement"][axis]]
        if disagreements:
            print(f"                    désaccord sur : {disagreements}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"noise_floor_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": all_results}, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
