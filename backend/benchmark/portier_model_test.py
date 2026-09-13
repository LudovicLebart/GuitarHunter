"""Chantier G (validation) : le Portier (Tier 1) est-il remplaçable par un modèle moins cher ?

Contexte : run #37 a mesuré que T1 pèse 50,5% de la facture Gemini réelle — pas parce qu'il
est cher à l'appel (c'est le moins cher des 3 tiers), mais parce qu'il tourne sur 100% des
annonces. Le comparatif à 10 candidats déjà fait (runs #27-29) teste l'identification/
évaluation complète (rôle T2/T3) — PAS le rôle réel du Portier (accept/reject + marque +
classification grossière, schéma JSON à 4 champs). Sans candidat T1 fidèle, on ne peut pas
dire si un modèle moins cher ferait un bon Portier.

Ce script teste 3 candidats avec EXACTEMENT le même prompt que le vrai Portier de production
(`candidates.py::_build_t1_prompt`, réutilise `_construct_base_user_prompt` +
`gatekeeper_verbosity_instruction`) :
- `t1_gemini_flash_lite` : le vrai modèle de prod (`gemini-3.5-flash-lite`) — baseline.
- `t1_qwen` : Qwen3.8-flash (déjà intégré, ~0,14$/0,42$ par M — nettement moins cher).
- `t1_gpt5_mini` : GPT-5-mini (déjà intégré, 0,25$/2,00$ par M — légèrement moins cher).

Deux axes de jugement, jamais agrégés en un seul score (même discipline que judge.py) :
1. Accord accept/reject sur les 40 items du Banc d'Essai — les 13 `rejet_t1` DOIVENT être
   rejetés, les 27 `tier2`/`tier3` DOIVENT être acceptés. C'est le rôle premier du Portier :
   un faux négatif ici (rejette une annonce qui aurait dû passer) cache une pépite potentielle ;
   un faux positif (accepte ce qui aurait dû être rejeté) laisse du bruit inutile vers T2/T3.
2. Précision marque/classification sur les items à `ground_truth` non vide (27 tier2/tier3) —
   jugée par `judge.py::evaluate_with_llm_judge` (axe "identification" uniquement, les 3 autres
   axes du juge — état/valeur/hallucination — ne s'appliquent pas à la sortie sparse de T1).

Usage : python -m backend.benchmark.portier_model_test [--models t1_gemini_flash_lite,t1_qwen,t1_gpt5_mini]
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone

from backend.benchmark.candidates import CANDIDATES, is_t1_rejected
from backend.benchmark.judge import evaluate_with_llm_judge
from backend.benchmark.run_benchmark import load_dataset

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DEFAULT_MODELS = "t1_gemini_flash_lite,t1_qwen,t1_gpt5_mini"


def _parse_t1_answer(answer):
    """Extrait le JSON {status, reasoning, brand, classification} de la réponse brute d'un
    candidat — tolère les blocs ```json``` (tous les candidats ne forcent pas le mode JSON,
    voir candidates.py::call_t1_qwen/call_t1_gpt5_mini, contrairement à Gemini)."""
    if not answer or answer.startswith("ERREUR:"):
        return None
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', answer)
    text = match.group(1).strip() if match else answer.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            result = result[0] if result and isinstance(result[0], dict) else {}
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Teste des candidats T1 (Portier) sur le vrai rôle de gate")
    parser.add_argument("--models", default=DEFAULT_MODELS, help="Candidats T1 séparés par des virgules")
    args = parser.parse_args()

    requested = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in requested if m not in CANDIDATES]
    if unknown:
        print(f"Modèles inconnus ignorés : {unknown}")
    requested = [m for m in requested if m in CANDIDATES]

    dataset = load_dataset()
    print(f"Dataset : {len(dataset)} items ({sum(1 for i in dataset if i.get('stratum') == 'rejet_t1')} rejet_t1, "
          f"{sum(1 for i in dataset if i.get('stratum') in ('tier2', 'tier3'))} tier2/tier3).")

    all_results = {}

    for model_key in requested:
        print(f"\n{'=' * 60}\n{model_key}\n{'=' * 60}")
        call_fn = CANDIDATES[model_key]
        per_item = []
        gate_correct = 0
        gate_total = 0
        identification_scored = []
        parse_failures = 0
        total_latency = 0.0

        for item in dataset:
            candidate_result = call_fn(item)
            total_latency += candidate_result.get("latency_s") or 0
            parsed = _parse_t1_answer(candidate_result["answer"])

            expected_reject = item.get("stratum") == "rejet_t1"
            gate_total += 1

            if parsed is None:
                parse_failures += 1
                gate_agree = False
                brand = classification = None
            else:
                actual_reject = is_t1_rejected(parsed.get("status"))
                gate_agree = actual_reject == expected_reject
                brand = parsed.get("brand")
                classification = parsed.get("classification")

            if gate_agree:
                gate_correct += 1

            id_score = None
            if item.get("ground_truth") and parsed is not None:
                candidate_answer_text = f"Marque : {brand or 'Inconnue'}. Classification : {classification or 'Inconnue'}."
                verdict = evaluate_with_llm_judge(item["question"], item["ground_truth"], candidate_answer_text)
                id_score = verdict["scores"].get("identification", 0)
                identification_scored.append(id_score)

            per_item.append({
                "id": item["id"], "stratum": item.get("stratum"),
                "expected_reject": expected_reject, "parsed": parsed,
                "gate_agree": gate_agree, "identification_score": id_score,
            })
            flag = "✅" if gate_agree else "❌"
            print(f"  {flag} {item['id']} ({item.get('stratum')}) : attendu={'REJET' if expected_reject else 'ACCEPT'} "
                  f"-> statut={parsed.get('status') if parsed else 'PARSE_FAIL'}"
                  + (f", identification={id_score}" if id_score is not None else ""))

        gate_pct = round(100 * gate_correct / gate_total, 1) if gate_total else None
        id_pct = round(100 * sum(identification_scored) / len(identification_scored), 1) if identification_scored else None
        avg_latency = round(total_latency / gate_total, 1) if gate_total else None

        print(f"\n  Accord accept/reject : {gate_correct}/{gate_total} ({gate_pct}%)")
        print(f"  Précision identification (sur {len(identification_scored)} items à ground_truth) : {id_pct}%")
        print(f"  Échecs de parsing JSON : {parse_failures}/{gate_total}")
        print(f"  Latence moyenne : {avg_latency}s")

        all_results[model_key] = {
            "gate_accuracy_pct": gate_pct,
            "identification_pct": id_pct,
            "parse_failures": parse_failures,
            "avg_latency_s": avg_latency,
            "items": per_item,
        }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"portier_model_test_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
