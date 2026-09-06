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


_CONDITION_EXTRACTION_PROMPT = (
    "Décris uniquement l'état physique et les détails techniques visibles sur ces photos d'un "
    "instrument de musique : finition (rayures, éclats, ternissement, craquelures), état des "
    "pièces métalliques (oxydation, jeu, corrosion), condition apparente des cordes et frettes, "
    "défauts ou dommages visibles, qualité apparente de fabrication et d'assemblage. "
    "N'essaie PAS d'identifier la marque, le modèle, le luthier ou l'origine de l'instrument — "
    "ce n'est pas ton rôle ici, un autre expert s'en charge. Décris uniquement ce qui est "
    "observable factuellement, ne réponds à aucune question."
)

# Séparé de l'extraction d'état : consigne stricte de transcription/OCR pure, sans
# AUCUNE interprétation (ni sur la qualité de la marque, ni sur son positionnement
# gamme/origine) — c'est précisément le saut interprétatif ("marque budget OEM") qui a
# fait halluciner Qwen sur l'annonce Guerrilla Guitars, pas la lecture du logo elle-même.
_IDENTIFICATION_EXTRACTION_PROMPT = (
    "Fais un travail de pure transcription/OCR sur ces photos d'un instrument de musique, sans "
    "aucune interprétation : \n"
    "1. Transcris EXACTEMENT (lettre par lettre) tout texte lisible sur l'instrument (tête, "
    "corps, matériel) : nom de marque, modèle, numéro de série, tout inscription gravée ou "
    "imprimée.\n"
    "2. Décris en détail la forme, les couleurs et les symboles de tout logo/emblème visible "
    "(ex: formes géométriques, étoiles, animaux, etc.) sans essayer de le nommer ou de "
    "l'associer à une marque connue.\n"
    "3. Décris les caractéristiques de construction visibles qui pourraient indiquer une "
    "origine (qualité de finition des joints, type de vis/quincaillerie, style de découpe).\n"
    "N'émets AUCUN jugement sur la marque (ne dis jamais si c'est une marque \"connue\", "
    "\"budget\", \"artisanale\", \"OEM\" ou autre) — transcris et décris seulement ce que tu vois, "
    "laisse toute interprétation à un autre expert. Ne réponds à aucune question."
)


def call_hybrid_qwen_gemini(question: str, image_urls: list) -> str:
    """Candidat expérimental : division du travail par force de chaque modèle, SANS jamais
    envoyer les photos à Gemini (tout le coût vision reste sur Qwen, moins cher). Constat du
    2026-09-06 (annonce Guerrilla Guitars) : Qwen lit correctement le texte/logo (OCR fiable)
    mais hallucine dès qu'il interprète ce qu'il lit (a conclu "marque budget OEM" pour un
    luthier artisanal québécois réel) — le problème est l'interprétation, pas la perception.
    Architecture : Qwen produit deux rapports texte séparés, un sur l'état physique et un de
    pure transcription/OCR du logo et du texte SANS aucune interprétation de marque ; Gemini
    Tier 3 Expert Pro (l'"oracle") ne voit JAMAIS les images, seulement ces deux rapports texte,
    et fait l'identification (marque/modèle/origine) lui-même à partir de la transcription brute
    en s'appuyant sur ses propres connaissances, puis répond à la question."""
    condition_report = call_qwen_tokenrouter(_CONDITION_EXTRACTION_PROMPT, image_urls)
    identification_report = call_qwen_tokenrouter(_IDENTIFICATION_EXTRACTION_PROMPT, image_urls)
    oracle_prompt = (
        f"Un modèle de vision spécialisé a produit deux rapports factuels sur les photos d'une "
        f"annonce (il n'a JAMAIS tenté d'identifier la marque ni porté de jugement dessus — "
        f"c'est à toi de le faire à partir de ces éléments bruts, tu ne vois pas les photos "
        f"toi-même) :\n\n"
        f"--- Rapport 1 : état physique ---\n{condition_report}\n\n"
        f"--- Rapport 2 : transcription OCR / description du logo (sans interprétation) ---\n"
        f"{identification_report}\n\n"
        f"Question : {question}\n\n"
        f"En te basant sur tes propres connaissances des marques/luthiers, identifie d'abord "
        f"la marque, le modèle et l'origine probable de l'instrument à partir du Rapport 2, "
        f"puis réponds à la question en combinant cette identification avec le Rapport 1."
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
