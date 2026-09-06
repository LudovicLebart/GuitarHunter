"""Appels aux modèles vision candidats du benchmark GuitarHunter.

Isolé du pipeline de production (analyzer.py) : sert à comparer les deux tiers
Gemini actuels (Tier 2 Analyste et Tier 3 Expert Pro) à des concurrents externes
(GPT-5-mini, Qwen3.8-flash via TokenRouter), à un candidat hybride expérimental
(Qwen en extracteur vision + Gemini Tier 3 en oracle de raisonnement) et à un
candidat de compression expérimental (Tier 3 forcé en puces + réécriture par
Gemini Flash-Lite) sur un même jeu de questions/photos.
"""
import base64
import logging
import os

import requests
import google.generativeai as genai
from openai import OpenAI

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


def _download_image_bytes(url: str):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.warning(f"Impossible de télécharger l'image {url}: {e}")
        return None


def _call_gemini(question: str, image_urls: list, model_name: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY manquant")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name)
    parts = [question]
    for url in image_urls:
        image_bytes = _download_image_bytes(url)
        if image_bytes:
            parts.append({"mime_type": "image/jpeg", "data": image_bytes})
    response = model.generate_content(parts)
    return response.text.strip()


def call_gemini(question: str, image_urls: list) -> str:
    """Tier 2 (Analyste) — modèle utilisé aujourd'hui en production pour l'analyse standard."""
    return _call_gemini(question, image_urls, GEMINI_MODELS["default_analyst"])


def call_gemini_pro(question: str, image_urls: list) -> str:
    """Tier 3 (Expert Pro) — modèle exhaustif, déclenché conditionnellement en production.
    Ajouté à la comparaison pour situer le Tier 2 (moins cher) par rapport au plafond de
    qualité actuel de Gemini, pas seulement par rapport aux concurrents externes."""
    return _call_gemini(question, image_urls, GEMINI_MODELS["default_expert"])


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


def call_gemini_pro_compact(question: str, image_urls: list) -> str:
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
    compact_answer = _call_gemini(
        question + _COMPACT_INSTRUCTION_SUFFIX, image_urls, GEMINI_MODELS["default_expert"]
    )
    rewrite_prompt = _REWRITE_PROMPT_TEMPLATE.format(compact_answer=compact_answer)
    return _call_gemini(rewrite_prompt, [], GEMINI_MODELS["default_gatekeeper"])


def _call_openai_compatible(question: str, image_urls: list, model_name: str, api_key: str, base_url: str = None) -> str:
    if not api_key:
        raise RuntimeError(f"Clé API manquante pour le modèle {model_name}")
    client = OpenAI(api_key=api_key, base_url=base_url)
    content = [{"type": "text", "text": question}]
    for url in image_urls:
        image_bytes = _download_image_bytes(url)
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": content}],
        temperature=0.0,
    )
    return response.choices[0].message.content.strip()


def call_gpt4o_mini(question: str, image_urls: list) -> str:
    return _call_openai_compatible(question, image_urls, GPT_MODEL, OPENAI_API_KEY)


def call_qwen_tokenrouter(question: str, image_urls: list) -> str:
    return _call_openai_compatible(
        question, image_urls, QWEN_MODEL, TOKENROUTER_API_KEY,
        base_url=TOKENROUTER_BASE_URL,
    )


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


def call_hybrid_qwen_gemini(question: str, image_urls: list) -> str:
    """Candidat expérimental : division du travail par force de chaque modèle, SANS jamais
    envoyer les photos à Gemini (tout le coût vision reste sur Qwen, moins cher). Constat du
    2026-09-06 (annonce Guerrilla Guitars) : Qwen lit correctement le texte/logo (OCR fiable)
    mais hallucine dès qu'il interprète ce qu'il lit (a conclu "marque budget OEM" pour un
    luthier artisanal québécois réel) — le problème est l'interprétation, pas la perception.
    Architecture : un seul appel Qwen produit un rapport texte en deux parties (état physique +
    transcription/OCR du logo SANS interprétation de marque) ; Gemini Tier 3 Expert Pro
    (l'"oracle") ne voit JAMAIS les images, seulement ce rapport texte, et fait l'identification
    (marque/modèle/origine) lui-même à partir de la transcription brute en s'appuyant sur ses
    propres connaissances, puis répond à la question."""
    extraction_report = call_qwen_tokenrouter(_EXTRACTION_PROMPT, image_urls)
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
    return _call_gemini(oracle_prompt, [], GEMINI_MODELS["default_expert"])


# Registre des candidats disponibles pour le runner (clé utilisée en CLI --models).
CANDIDATES = {
    "gemini": call_gemini,
    "gemini_pro": call_gemini_pro,
    "gemini_pro_compact": call_gemini_pro_compact,
    "gpt4o_mini": call_gpt4o_mini,
    "qwen": call_qwen_tokenrouter,
    "hybrid": call_hybrid_qwen_gemini,
}
