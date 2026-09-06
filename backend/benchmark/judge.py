"""Juge LLM (Claude) du benchmark GuitarHunter.

Sanctionne la réponse d'un modèle candidat contre une vérité terrain de
lutherie, avec un score binaire et une justification technique courte.
"""
import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

JUDGE_MODEL = os.getenv("BENCHMARK_JUDGE_MODEL", "claude-sonnet-5")

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY manquant")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


JUDGE_PROMPT_TEMPLATE = """Tu es un expert intraitable en lutherie et un juge d'évaluation de modèles d'IA.
Ta tâche est de sanctionner la réponse d'un modèle candidat par rapport à une vérité terrain (Ground Truth).

Question posée : {question}
Vérité terrain : {ground_truth}
Réponse du modèle candidat : {candidate_answer}

Règles de jugement :
1. Ignore les différences de style ou de syntaxe.
2. Pénalise sévèrement toute hallucination technique (ex: confondre un Floyd Rose avec un Tune-o-matic, ou rater une fissure structurelle).
3. Si le candidat omet un détail critique présent dans la vérité terrain, le score est 0.

Réponds UNIQUEMENT avec un objet JSON strict :
{{
    "score": 1,
    "justification": "Explication technique courte de la décision."
}}
"""


def evaluate_with_llm_judge(question: str, ground_truth: str, candidate_answer: str) -> dict:
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        question=question, ground_truth=ground_truth, candidate_answer=candidate_answer
    )
    try:
        # SDK anthropic >= 1.0 (2026-08-20) : temperature/top_p/top_k retirés de la
        # signature de messages.create() (non déplacés, supprimés) — impossible de
        # fixer la température pour la reproductibilité du juge avec cette version.
        # claude-sonnet-5 a l'"adaptive thinking" activé par défaut, qui peut consommer
        # tout le budget max_tokens en réflexion avant de produire le JSON attendu (pas
        # besoin de raisonnement long pour ce verdict court) — désactivé explicitement.
        response = _get_client().messages.create(
            model=JUDGE_MODEL,
            max_tokens=300,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        # Filet de sécurité : même thinking désactivé, on cherche le premier bloc texte
        # plutôt que de supposer content[0].
        text_block = next((b for b in response.content if getattr(b, "type", None) == "text"), None)
        if text_block is None:
            raise ValueError("Aucun bloc texte dans la réponse du juge (contenu : thinking uniquement ?)")
        text = text_block.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"score": 0, "justification": "Erreur critique : le juge n'a pas renvoyé un JSON valide."}
    except Exception as e:
        logger.error(f"Échec de l'appel au juge LLM : {e}")
        return {"score": 0, "justification": f"Échec de l'appel API : {e}"}
