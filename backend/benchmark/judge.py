"""Juge LLM (Claude) du benchmark GuitarHunter.

Note la réponse d'un modèle candidat contre une vérité terrain de lutherie, par
axe indépendant plutôt qu'en un score binaire unique (CHANTIER_B_PERCEPTION_
RAISONNEMENT_PLAN.md §0 : les axes ne s'agrègent jamais entre eux). Fournit
aussi une passe de jugement séparée sur un rapport de perception seul (le
garde-fou anti-interprétation §2 se vérifie sur la perception, indépendamment
de la qualité du raisonnement final qui la consomme).
"""
import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

JUDGE_MODEL = os.getenv("BENCHMARK_JUDGE_MODEL", "claude-sonnet-5")

JUDGE_AXES = ("identification", "etat", "valeur", "hallucination")

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY manquant")
        # Timeout explicite (le SDK par défaut, ~10 min, masque un raccroché jusqu'au
        # timeout externe de run_script.yml — même correctif que candidates.py).
        _client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
    return _client


def _call_judge(prompt: str, error_result: dict) -> dict:
    """Appelle le juge, parse son JSON, et renvoie `error_result` (avec la justification
    remplie) si l'appel échoue ou si le JSON est invalide — jamais d'exception remontée."""
    try:
        # SDK anthropic >= 1.0 (2026-08-20) : temperature/top_p/top_k retirés de la
        # signature de messages.create() (non déplacés, supprimés) — impossible de
        # fixer la température pour la reproductibilité du juge avec cette version.
        # claude-sonnet-5 a l'"adaptive thinking" activé par défaut, qui peut consommer
        # tout le budget max_tokens en réflexion avant de produire le JSON attendu (pas
        # besoin de raisonnement long pour ce verdict court) — désactivé explicitement.
        response = _get_client().messages.create(
            model=JUDGE_MODEL,
            # 400 (valeur précédente) tronquait le JSON avant sa fermeture dès que le juge
            # détaillait sa justification "axe par axe" comme le prompt l'y invite — 6 des ~18
            # évaluations réelles du smoke test #22 (2026-09-09) ont échoué au parsing pour
            # cette raison, faussant silencieusement les scores (tout à 0) de candidats par
            # ailleurs corrects (ex. hybrid : ses 2 seules fiches notées ont échoué ainsi).
            max_tokens=1024,
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
        # `text` est toujours défini ici (l'exception vient forcément de json.loads(text),
        # la ligne juste avant) — extrait conservé plutôt qu'un message générique, pour
        # diagnostiquer une éventuelle récidive directement depuis les résultats du run.
        return {**error_result, "justification": f"Erreur critique : le juge n'a pas renvoyé un JSON valide. Extrait : {text[:200]!r}"}
    except Exception as e:
        logger.error(f"Échec de l'appel au juge LLM : {e}")
        return {**error_result, "justification": f"Échec de l'appel API : {e}"}


JUDGE_PROMPT_TEMPLATE = """Tu es un expert intraitable en lutherie et un juge d'évaluation de modèles d'IA.
Ta tâche est de noter la réponse d'un modèle candidat par rapport à une vérité terrain (Ground Truth), un axe à la fois — les axes sont indépendants, ne les mélange pas dans un score unique.

Question posée : {question}
Vérité terrain : {ground_truth}
Réponse du modèle candidat : {candidate_answer}

Note chacun de ces 4 axes indépendamment, avec un score 0 (échec) ou 1 (réussite) :
- "identification" : la marque/le modèle/le type d'instrument identifié est-il correct par rapport à la vérité terrain ?
- "etat" : l'évaluation de l'état physique correspond-elle à la vérité terrain ?
- "valeur" : l'estimation de valeur ou du rapport prix/valeur est-elle cohérente avec la vérité terrain ?
- "hallucination" : 1 si la réponse ne contient AUCUNE affirmation technique fausse ou inventée, 0 sinon (ex: confondre un Floyd Rose avec un Tune-o-matic, inventer un défaut ou une caractéristique absente de la vérité terrain).

Règles de jugement :
1. Ignore le style, la longueur et le niveau de détail — juge le CONTENU des affirmations, jamais la forme.
2. Une différence de formulation ou l'omission d'un détail mineur ne fait JAMAIS, à elle seule, baisser un score. Ne pénalise une omission sur un axe que si elle change la conclusion pratique de CET axe précis (ex : omettre une fissure structurelle change la conclusion de l'axe "etat", pas celle de l'axe "identification").
3. Pénalise sévèrement toute affirmation technique fausse, sur l'axe "hallucination" uniquement — ne fais pas baisser les autres axes à cause d'une hallucination si le reste de leur contenu est correct.

Réponds UNIQUEMENT avec un objet JSON strict :
{{
    "scores": {{"identification": 1, "etat": 1, "valeur": 1, "hallucination": 1}},
    "justification": "Explication technique courte, axe par axe si pertinent."
}}
"""


def evaluate_with_llm_judge(question: str, ground_truth: str, candidate_answer: str) -> dict:
    """Renvoie {"scores": {axe: 0|1, ...}, "justification": str}. En cas d'échec, tous les
    axes sont mis à 0 (échec sévère par défaut, jamais une exception qui interromprait le run)."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        question=question, ground_truth=ground_truth, candidate_answer=candidate_answer
    )
    error_result = {"scores": {axis: 0 for axis in JUDGE_AXES}}
    result = _call_judge(prompt, error_result)
    scores = result.get("scores") or {}
    # Défensif : un axe manquant dans la réponse du juge compte comme un échec sur cet axe,
    # jamais une absence silencieuse qui fausserait l'agrégat (voir run_benchmark.py).
    result["scores"] = {axis: int(scores.get(axis, 0)) for axis in JUDGE_AXES}
    result.setdefault("justification", "")
    return result


PERCEPTION_JUDGE_PROMPT_TEMPLATE = """Tu es un expert en lutherie chargé de vérifier qu'un rapport de perception visuelle respecte une règle stricte : il doit décrire ce qui est vu, jamais conclure une identification ou porter un jugement de qualité — cette conclusion revient à un autre modèle, qui ne voit que ce rapport, pas les photos.

Rapport à vérifier :
{perception_report}

Réponds UNIQUEMENT avec un objet JSON strict :
{{
    "contains_judgment": false,
    "identification_possible": true,
    "justification": "Explication courte."
}}

- "contains_judgment" : true si le rapport contient une conclusion ou un jugement plutôt qu'une observation factuelle (ex : nomme une marque au lieu de transcrire un logo, utilise un adjectif évaluatif comme "qualité", "soigné", "artisanal", "bon marché", ou affirme une origine plutôt que de décrire les indices qui y mènent).
- "identification_possible" : true si, à partir de cette seule description écrite (sans jamais voir les photos), un expert en lutherie pourrait identifier ou au moins restreindre significativement la marque/le modèle de l'instrument.
"""


def evaluate_perception_report(perception_report: str) -> dict:
    """Juge le garde-fou anti-interprétation (§2) sur un rapport de perception seul,
    indépendamment de la réponse finale du raisonneur qui le consomme. Renvoie un dict neutre
    (aucune évaluation possible) si le candidat ne produit pas de rapport de perception séparé."""
    if not perception_report:
        return {
            "contains_judgment": None,
            "identification_possible": None,
            "justification": "Aucun rapport de perception à évaluer (candidat sans étape de perception séparée).",
        }
    prompt = PERCEPTION_JUDGE_PROMPT_TEMPLATE.format(perception_report=perception_report)
    error_result = {"contains_judgment": None, "identification_possible": None}
    return _call_judge(prompt, error_result)
