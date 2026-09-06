"""Appels aux modèles vision candidats du benchmark GuitarHunter.

Isolé du pipeline de production (analyzer.py) : sert à comparer les deux tiers
Gemini actuels (Tier 2 Analyste et Tier 3 Expert Pro) à des concurrents externes
(GPT-5-mini, Qwen3.8-flash via TokenRouter) et à un candidat hybride expérimental
(Qwen en extracteur vision + Gemini Tier 3 en oracle de raisonnement) sur un même
jeu de questions/photos.
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


_VISUAL_EXTRACTION_PROMPT = (
    "Décris de façon factuelle et détaillée tout ce qui est visible sur ces photos d'un "
    "instrument de musique : état général, finition, composants matériels (chevalet, "
    "mécaniques, électronique, etc.), marques/logos/numéros de série lisibles, défauts ou "
    "dommages visibles. Ne réponds à aucune question, décris uniquement ce que tu observes."
)


def call_hybrid_qwen_gemini(question: str, image_urls: list) -> str:
    """Candidat expérimental : Qwen (spécialiste vision, moins cher) décrit finement les photos
    en texte, puis Gemini Tier 3 Expert Pro (l'"oracle") répond à la question à partir de cette
    description SEULE, sans revoir les images. Teste l'hypothèse qu'un spécialiste vision dédié
    à la perception + un modèle fort dédié au raisonnement peut battre un seul modèle qui fait
    les deux — au prix d'un risque de "téléphone arabe" (l'oracle ne peut pas vérifier contre
    l'image un détail halluciné par le spécialiste) et d'un appel API supplémentaire."""
    visual_description = call_qwen_tokenrouter(_VISUAL_EXTRACTION_PROMPT, image_urls)
    oracle_prompt = (
        f"Voici la description factuelle des photos d'une annonce, produite par un modèle de "
        f"vision spécialisé :\n\n{visual_description}\n\n"
        f"Question : {question}\n\n"
        f"Réponds à la question en te basant uniquement sur cette description."
    )
    return _call_gemini(oracle_prompt, [], GEMINI_MODELS["default_expert"])


# Registre des candidats disponibles pour le runner (clé utilisée en CLI --models).
CANDIDATES = {
    "gemini": call_gemini,
    "gemini_pro": call_gemini_pro,
    "gpt4o_mini": call_gpt4o_mini,
    "qwen": call_qwen_tokenrouter,
    "hybrid": call_hybrid_qwen_gemini,
}
