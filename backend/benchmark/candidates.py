"""Appels aux modèles vision candidats du benchmark GuitarHunter.

Isolé du pipeline de production (analyzer.py) : sert uniquement à comparer
Gemini (modèle actuel) à GPT-4o-mini et Qwen2.5-VL (via OpenRouter, API
compatible OpenAI) sur un même jeu de questions/photos.
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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# gpt-4o-mini est retiré de l'API OpenAI depuis février 2026 ; gpt-5-mini est son
# remplaçant direct (vision confirmée, $0.25/$2.00 par M tokens in/out).
GPT_MODEL = os.getenv("BENCHMARK_GPT_MODEL", "gpt-5-mini")
# qwen2.5-vl-72b-instruct n'existe plus sur OpenRouter (lignée Qwen3 depuis 2026) ;
# qwen3.8-flash offre le meilleur compromis prix/vision de la lignée à date de vérification
# (2026-09-06) — $0.15/$0.47 par M tokens, nettement meilleur que qwen3.7-flash sur
# RealWorldQA pour un surcoût minime. Vérifier la disponibilité sur openrouter.ai/models
# si ce candidat échoue (la lignée Qwen tourne vite).
QWEN_MODEL = os.getenv("BENCHMARK_QWEN_MODEL", "qwen/qwen3.8-flash")


def _download_image_bytes(url: str):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.warning(f"Impossible de télécharger l'image {url}: {e}")
        return None


def call_gemini(question: str, image_urls: list) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY manquant")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODELS["default_analyst"])
    parts = [question]
    for url in image_urls:
        image_bytes = _download_image_bytes(url)
        if image_bytes:
            parts.append({"mime_type": "image/jpeg", "data": image_bytes})
    response = model.generate_content(parts)
    return response.text.strip()


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


def call_qwen_openrouter(question: str, image_urls: list) -> str:
    return _call_openai_compatible(
        question, image_urls, QWEN_MODEL, OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )


# Registre des candidats disponibles pour le runner (clé utilisée en CLI --models).
CANDIDATES = {
    "gemini": call_gemini,
    "gpt4o_mini": call_gpt4o_mini,
    "qwen": call_qwen_openrouter,
}
