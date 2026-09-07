"""Appels aux modèles vision candidats du benchmark GuitarHunter.

Isolé du pipeline de production (analyzer.py) : sert à comparer les deux tiers
Gemini actuels (Tier 2 Analyste et Tier 3 Expert Pro) à des concurrents externes
(GPT-5-mini, Qwen3.8-flash via TokenRouter), à un candidat hybride expérimental
(Qwen en extracteur vision + Gemini Tier 3 en oracle de raisonnement) et à un
candidat de compression expérimental (Tier 3 forcé en puces + réécriture par
Gemini Flash-Lite) sur un même jeu de questions/photos.

Contrat de retour des candidats (CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md §7,
étape 4) : chaque fonction enregistrée dans CANDIDATES renvoie un dict, jamais
un `str` nu — `{"answer": str, "perception_report": str|None, "usage": {...},
"latency_s": float, "calls": int}`. `perception_report` n'est renseigné que par
les candidats qui font une étape de perception distincte du raisonnement final
(aujourd'hui : `hybrid`) — c'était auparavant jeté après usage
(`extraction_report`, jamais retourné), rendant impossible de juger le
garde-fou anti-interprétation séparément de la réponse finale.
"""
import base64
import json
import logging
import os
import time

import anthropic
import requests
import google.generativeai as genai
from openai import OpenAI

from backend.benchmark.perception_contract import PERCEPTION_INSTRUCTION, build_reasoning_prompt, parse_perception_json
from config import GEMINI_API_KEY, GEMINI_MODELS

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# TokenRouter (tokenrouter.com) plutôt qu'OpenRouter : compte déjà créé par l'utilisateur,
# API compatible OpenAI Chat Completions, endpoint confirmé par l'utilisateur (2026-09-06).
TOKENROUTER_API_KEY = os.getenv("TOKENROUTER_API_KEY")
TOKENROUTER_BASE_URL = "https://api.tokenrouter.com/v1"
# gpt-4o-mini est retiré de l'API OpenAI depuis février 2026 ; gpt-5-mini est son
# remplaçant direct (vision confirmée, $0.25/$2.00 par M tokens in/out).
GPT_MODEL = os.getenv("BENCHMARK_GPT_MODEL", "gpt-5-mini")
# qwen2.5-vl-72b-instruct n'existe plus (lignée Qwen3 depuis 2026). qwen3.8-flash
# retenu (vérifié 2026-09-06 sur le catalogue OpenRouter — le nom "qwen3-vl-32b-instruct"
# cité par un classement OCRBench-V2 public n'existe PAS chez ce fournisseur, à ne pas
# réutiliser) : dans la lignée Qwen3.x réellement listée (aucune ne porte "VL" dans le
# nom, la vision est native), qwen3.8-flash offre le meilleur compromis prix/vision
# confirmé — nettement meilleur que qwen3.7-flash sur RealWorldQA (88.5) pour un coût
# encore très bas. Vérifier la disponibilité sur le tableau de bord TokenRouter si ce
# candidat échoue (la lignée Qwen tourne vite, et le catalogue de modèles diffère d'un
# agrégateur à l'autre).
QWEN_MODEL = os.getenv("BENCHMARK_QWEN_MODEL", "qwen/qwen3.8-flash")

# Chemin OpenAI-compatible (GPT/Qwen via TokenRouter) : aucun timeout auparavant, sur un
# appel qui peut être rejoué en série sur 30-50 items — un fournisseur qui pend bloque tout
# le run. CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md §1 (repli obligatoire de l'étage de
# perception en production) part du même constat.
CANDIDATE_TIMEOUT_S = 30


def _download_image_bytes(url: str):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.warning(f"Impossible de télécharger l'image {url}: {e}")
        return None


def _candidate_result(answer, usage, latency_s, perception_report=None, calls=1):
    return {
        "answer": answer,
        "perception_report": perception_report,
        "usage": usage,
        "latency_s": latency_s,
        "calls": calls,
    }


def _sum_usage(usage_dicts):
    """Additionne plusieurs relevés d'usage (candidat multi-appels, ex. `hybrid`).
    None si aucun des appels sommés n'a de valeur pour ce champ (distinct de 0)."""
    input_tokens = [u["input_tokens"] for u in usage_dicts if u and u.get("input_tokens") is not None]
    output_tokens = [u["output_tokens"] for u in usage_dicts if u and u.get("output_tokens") is not None]
    return {
        "input_tokens": sum(input_tokens) if input_tokens else None,
        "output_tokens": sum(output_tokens) if output_tokens else None,
    }


def _call_gemini(question: str, image_urls: list, model_name: str):
    """Renvoie (texte, usage_dict, latence_s). Usage lu sur `usage_metadata`, mêmes
    champs que `analyzer.py::_call_gemini_json` (`prompt_token_count`/`candidates_token_count`)."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY manquant")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name)
    parts = [question]
    for url in image_urls:
        image_bytes = _download_image_bytes(url)
        if image_bytes:
            parts.append({"mime_type": "image/jpeg", "data": image_bytes})
    t0 = time.monotonic()
    response = model.generate_content(parts)
    latency_s = time.monotonic() - t0
    usage = getattr(response, "usage_metadata", None)
    usage_dict = {
        "input_tokens": getattr(usage, "prompt_token_count", None) if usage else None,
        "output_tokens": getattr(usage, "candidates_token_count", None) if usage else None,
    }
    return response.text.strip(), usage_dict, latency_s


def call_gemini(question: str, image_urls: list) -> dict:
    """Tier 2 (Analyste) — modèle utilisé aujourd'hui en production pour l'analyse standard."""
    answer, usage, latency_s = _call_gemini(question, image_urls, GEMINI_MODELS["default_analyst"])
    return _candidate_result(answer, usage, latency_s)


def call_gemini_pro(question: str, image_urls: list) -> dict:
    """Tier 3 (Expert Pro) — modèle exhaustif, déclenché conditionnellement en production.
    Ajouté à la comparaison pour situer le Tier 2 (moins cher) par rapport au plafond de
    qualité actuel de Gemini, pas seulement par rapport aux concurrents externes."""
    answer, usage, latency_s = _call_gemini(question, image_urls, GEMINI_MODELS["default_expert"])
    return _candidate_result(answer, usage, latency_s)


_COMPACT_INSTRUCTION_SUFFIX = (
    "\n\nIMPORTANT : réponds UNIQUEMENT par une liste à puces stricte et compacte, sans phrases "
    "longues ni transitions — un maximum d'information factuelle en un minimum de mots."
)

_REWRITE_PROMPT_TEMPLATE = (
    "Voici une réponse technique rédigée en liste à puces compacte, produite par un expert :\n\n"
    "{compact_answer}\n\n"
    "Réécris ce contenu en langage naturel, sous forme de paragraphes fluides et lisibles par un "
    "humain, SANS ajouter aucune information, aucun fait ou aucune nuance qui ne soit pas déjà "
    "présent ci-dessus. Conserve exactement le même niveau de détail et les mêmes conclusions — "
    "reformule uniquement le style, ne complète rien."
)


def call_gemini_pro_compact(question: str, image_urls: list) -> dict:
    """Candidat expérimental : teste si compresser la sortie du Tier 3 (Expert Pro, $12/M
    tokens de sortie, prompt de prod exigeant un "rapport Markdown EXHAUSTIF") en puces
    strictes, puis la faire réécrire en prose par un modèle bon marché (gemini-3.5-flash-lite,
    déjà utilisé comme Portier Tier 1 en prod), dégrade la qualité de l'analyse par rapport au
    rapport exhaustif habituel (`gemini_pro`). Discussion du 2026-09-06 : le Tier 2 est déjà
    contraint à des puces en prod, mais pas le Tier 3 — c'est donc là que se trouve le vrai
    gain potentiel ($12/M en sortie, 6x le tarif du Tier 2). Le risque n'est pas dans l'étape
    de réécriture (elle ne fait que reformuler des faits déjà posés, sans invention) mais dans
    l'étape de compression elle-même : si forcer la brièveté sur Gemini Pro l'empêche de
    "réfléchir en écrivant" et dégrade son raisonnement, ce candidat devrait obtenir un score
    nettement inférieur à `gemini_pro` sur le même jeu de questions — sinon la compression est
    sans risque et fait économiser environ 55% du coût de sortie du Tier 3."""
    compact_answer, usage1, latency1 = _call_gemini(
        question + _COMPACT_INSTRUCTION_SUFFIX, image_urls, GEMINI_MODELS["default_expert"]
    )
    rewrite_prompt = _REWRITE_PROMPT_TEMPLATE.format(compact_answer=compact_answer)
    final_answer, usage2, latency2 = _call_gemini(rewrite_prompt, [], GEMINI_MODELS["default_gatekeeper"])
    return _candidate_result(
        final_answer, _sum_usage([usage1, usage2]), latency1 + latency2, calls=2
    )


# Comparatif demandé par l'utilisateur (2026-09-07) : Claude Sonnet 5 comme candidat vision
# à part entière (pas seulement comme juge, voir judge.py) — motivé par une déception
# croissante envers la qualité perçue de Gemini. Tarif $2,00/$10,00 par M tokens (in/out,
# skill claude-api vérifié 2026-09-07) contre $2,00/$12,00 pour gemini-3.1-pro-preview :
# entrée identique, sortie ~17% moins chère chez Claude. Tokenisation image ≈ (largeur×hauteur)/750
# (formule Anthropic documentée) : pour une photo d'annonce moyenne ~650x960px, ≈830 tokens —
# du même ordre de grandeur que le calibrage Gemini (~900 tokens/photo, run_once.py).
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("BENCHMARK_CLAUDE_MODEL", "claude-sonnet-5")

_claude_client = None


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY manquant")
        _claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _claude_client


def call_claude_sonnet(question: str, image_urls: list) -> dict:
    """Claude Sonnet 5 (vision native) sur le même jeu de questions/photos que les candidats
    Gemini/GPT/Qwen — comparatif coût ET qualité, pas seulement un rôle de juge."""
    client = _get_claude_client()
    content = []
    for url in image_urls:
        image_bytes = _download_image_bytes(url)
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
            })
    content.append({"type": "text", "text": question})

    # thinking désactivé : comparaison à budget de raisonnement équivalent aux autres
    # candidats (aucun ne "réfléchit" avant de répondre), et coût/latence prévisibles.
    t0 = time.monotonic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": content}],
    )
    latency_s = time.monotonic() - t0
    text_block = next((b for b in response.content if getattr(b, "type", None) == "text"), None)
    if text_block is None:
        raise RuntimeError("Aucun bloc texte dans la réponse Claude (thinking seul ?)")
    usage = getattr(response, "usage", None)
    usage_dict = {
        "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
        "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
    }
    return _candidate_result(text_block.text.strip(), usage_dict, latency_s)


def _call_openai_compatible(question: str, image_urls: list, model_name: str, api_key: str, base_url: str = None):
    """Renvoie (texte, usage_dict, latence_s)."""
    if not api_key:
        raise RuntimeError(f"Clé API manquante pour le modèle {model_name}")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=CANDIDATE_TIMEOUT_S)
    content = [{"type": "text", "text": question}]
    for url in image_urls:
        image_bytes = _download_image_bytes(url)
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    t0 = time.monotonic()
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": content}],
        temperature=0.0,
    )
    latency_s = time.monotonic() - t0
    usage = getattr(response, "usage", None)
    usage_dict = {
        "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
    }
    return response.choices[0].message.content.strip(), usage_dict, latency_s


def call_gpt4o_mini(question: str, image_urls: list) -> dict:
    answer, usage, latency_s = _call_openai_compatible(question, image_urls, GPT_MODEL, OPENAI_API_KEY)
    return _candidate_result(answer, usage, latency_s)


def call_qwen_tokenrouter(question: str, image_urls: list) -> dict:
    answer, usage, latency_s = _call_openai_compatible(
        question, image_urls, QWEN_MODEL, TOKENROUTER_API_KEY,
        base_url=TOKENROUTER_BASE_URL,
    )
    return _candidate_result(answer, usage, latency_s)


# Un seul appel Qwen, deux sections distinctes dans le même prompt : la consigne
# "pas d'interprétation" ne s'applique qu'à la section logo/marque — c'est précisément le
# saut interprétatif ("marque budget OEM") qui a fait halluciner Qwen sur l'annonce
# Guerrilla Guitars (2026-09-06), pas la lecture du logo elle-même (OCR fiable).
_EXTRACTION_PROMPT = (
    "Analyse ces photos d'un instrument de musique en deux parties distinctes, sans répondre "
    "à aucune question.\n\n"
    "PARTIE 1 — État physique : décris l'état et les détails techniques visibles (finition : "
    "rayures/éclats/ternissement/craquelures ; pièces métalliques : oxydation/jeu/corrosion ; "
    "état apparent des cordes et frettes ; défauts ou dommages ; qualité apparente de "
    "fabrication et d'assemblage).\n\n"
    "PARTIE 2 — Transcription OCR du logo/marque, SANS AUCUNE INTERPRÉTATION : "
    "(a) transcris EXACTEMENT (lettre par lettre) tout texte lisible (tête, corps, matériel) : "
    "marque, modèle, numéro de série, inscriptions gravées ou imprimées ; "
    "(b) décris en détail la forme, les couleurs et les symboles de tout logo/emblème visible, "
    "sans essayer de le nommer ou de l'associer à une marque connue ; "
    "(c) décris les caractéristiques de construction qui pourraient indiquer une origine "
    "(qualité des joints, type de vis/quincaillerie, style de découpe). "
    "N'émets AUCUN jugement sur la marque dans cette partie (ne dis jamais si c'est une marque "
    "\"connue\", \"budget\", \"artisanale\", \"OEM\" ou autre) — transcris et décris seulement ce "
    "que tu vois, laisse toute interprétation à un autre expert."
)


def call_hybrid_qwen_gemini(question: str, image_urls: list) -> dict:
    """Candidat expérimental : division du travail par force de chaque modèle, SANS jamais
    envoyer les photos à Gemini (tout le coût vision reste sur Qwen, moins cher). Constat du
    2026-09-06 (annonce Guerrilla Guitars) : Qwen lit correctement le texte/logo (OCR fiable)
    mais hallucine dès qu'il interprète ce qu'il lit (a conclu "marque budget OEM" pour un
    luthier artisanal québécois réel) — le problème est l'interprétation, pas la perception.
    Architecture : un seul appel Qwen produit un rapport texte en deux parties (état physique +
    transcription/OCR du logo SANS interprétation de marque) ; Gemini Tier 3 Expert Pro
    (l'"oracle") ne voit JAMAIS les images, seulement ce rapport texte, et fait l'identification
    (marque/modèle/origine) lui-même à partir de la transcription brute en s'appuyant sur ses
    propres connaissances, puis répond à la question. Le rapport d'extraction est retourné dans
    `perception_report` (auparavant jeté après usage) pour être jugé séparément sur le respect
    du garde-fou anti-interprétation, indépendamment de la réponse finale de l'oracle."""
    extraction_report, extraction_usage, extraction_latency = _call_openai_compatible(
        _EXTRACTION_PROMPT, image_urls, QWEN_MODEL, TOKENROUTER_API_KEY,
        base_url=TOKENROUTER_BASE_URL,
    )
    oracle_prompt = (
        f"Un modèle de vision spécialisé a produit ce rapport factuel en deux parties sur les "
        f"photos d'une annonce (il n'a JAMAIS tenté d'identifier la marque ni porté de jugement "
        f"dessus — c'est à toi de le faire à partir de ces éléments bruts, tu ne vois pas les "
        f"photos toi-même) :\n\n{extraction_report}\n\n"
        f"Question : {question}\n\n"
        f"En te basant sur tes propres connaissances des marques/luthiers, identifie d'abord "
        f"la marque, le modèle et l'origine probable de l'instrument à partir de la Partie 2 "
        f"(transcription OCR/logo), puis réponds à la question en combinant cette "
        f"identification avec la Partie 1 (état physique)."
    )
    answer, oracle_usage, oracle_latency = _call_gemini(oracle_prompt, [], GEMINI_MODELS["default_expert"])
    return _candidate_result(
        answer,
        _sum_usage([extraction_usage, oracle_usage]),
        extraction_latency + oracle_latency,
        perception_report=extraction_report,
        calls=2,
    )


# Contrat de perception formel (Chantier B, CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md §7 étape
# 10 / "8.3") — dérivé champ par champ du JSON de production réel (prompts.json), contrairement
# à _EXTRACTION_PROMPT ci-dessus (candidat `hybrid`, expérimental, plus ancien, qui ne couvrait
# que l'état physique général et le logo en texte libre non structuré). Portée strictement
# limitée au benchmark : aucun de ces candidats ne touche analyzer.py/prompts.json de production
# (§7 étape 12 : l'implémentation en production n'a lieu qu'après un résultat favorable du
# benchmark sur l'axe verrou).


def _perception_reasoning_candidate(question: str, image_urls: list, perception_call_fn) -> dict:
    """Squelette commun aux candidats perception+raisonnement : `perception_call_fn(image_urls)`
    fait l'appel de perception brut (renvoie un triplet (texte, usage, latence), même contrat que
    `_call_gemini`/`_call_openai_compatible`) ; cette fonction parse son JSON, construit le prompt
    du raisonneur (Gemini Tier 3, comme l'oracle du candidat `hybrid`) et combine l'usage/latence
    des deux appels. Le rapport de perception (JSON sérialisé, clés triées pour une comparaison
    stable) est retourné dans `perception_report` pour être jugé séparément (garde-fou §2)."""
    raw_perception, perception_usage, perception_latency = perception_call_fn(image_urls)
    perception = parse_perception_json(raw_perception)
    reasoning_prompt = build_reasoning_prompt(question, perception)
    answer, oracle_usage, oracle_latency = _call_gemini(reasoning_prompt, [], GEMINI_MODELS["default_expert"])
    return _candidate_result(
        answer,
        _sum_usage([perception_usage, oracle_usage]),
        perception_latency + oracle_latency,
        perception_report=json.dumps(perception, ensure_ascii=False, sort_keys=True),
        calls=2,
    )


def call_perception_reasoning_qwen(question: str, image_urls: list) -> dict:
    """Candidat perception (§4, option 2) : Qwen3.8-Flash applique le contrat de perception
    complet, Gemini Tier 3 raisonne ensuite sur le texte seul — le candidat le moins cher des
    deux variantes testées ici."""
    def perception_call(urls):
        return _call_openai_compatible(
            PERCEPTION_INSTRUCTION, urls, QWEN_MODEL, TOKENROUTER_API_KEY,
            base_url=TOKENROUTER_BASE_URL,
        )
    return _perception_reasoning_candidate(question, image_urls, perception_call)


def call_perception_reasoning_flash_lite(question: str, image_urls: list) -> dict:
    """Candidat perception (§4, option 1) : réutilise le modèle du Tier 1 actuel
    (gemini-3.5-flash-lite, déjà appelé sur 100% des photos en production) pour le contrat de
    perception complet, Gemini Tier 3 raisonne ensuite sur le texte seul — zéro nouveau
    fournisseur, à comparer au coût marginal réel plutôt qu'à un tarif théorique."""
    def perception_call(urls):
        return _call_gemini(PERCEPTION_INSTRUCTION, urls, GEMINI_MODELS["default_gatekeeper"])
    return _perception_reasoning_candidate(question, image_urls, perception_call)


# Registre des candidats disponibles pour le runner (clé utilisée en CLI --models).
CANDIDATES = {
    "gemini": call_gemini,
    "gemini_pro": call_gemini_pro,
    "gemini_pro_compact": call_gemini_pro_compact,
    "gpt4o_mini": call_gpt4o_mini,
    "qwen": call_qwen_tokenrouter,
    "hybrid": call_hybrid_qwen_gemini,
    "claude_sonnet": call_claude_sonnet,
    "perception_qwen": call_perception_reasoning_qwen,
    "perception_flash_lite": call_perception_reasoning_flash_lite,
}
