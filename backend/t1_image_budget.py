"""Budget de tokens des photos du Portier LOCAL (Dell, Ollama) — empêche le dépassement du contexte.

Pourquoi (diagnostic 2026-10-07, `llm_usage` + rejeu `diag_t1_image_budget.py`) : le contexte Ollama du Dell est
8192 tokens (texte + photos + réponse). Chaque photo coûte (largeur ÷ 32) × (hauteur ÷ 32) tokens (+ ~7) : une
photo 640×1386 px = 867 tokens ; 8 photos hautes + le texte (≈ 2100 tokens) = 8336 > 8192. Ollama TRONQUE alors
silencieusement le prompt (`prompt_tokens` plafonne à 8192) et le Portier répond n'importe quoi (REJECTED_ITEM
aléatoires, raisonnement en chinois). Sur 801 appels de prod, les 3 appels saturés ont tous donné un mauvais
verdict (dont un lot « Fender Squier + accessoires » rejeté à tort et la Catania notée BAD_DEAL).

Règle : si les photos tiennent dans le budget (contexte − texte − marge pour la réponse), RIEN ne change. Sinon, on
réduit TOUTES les photos du même coefficient (jamais de photo retirée, sauf cas extrême où même 25 % ne suffit pas :
on retire alors les dernières). Module sans dépendance lourde (stdlib + Pillow) : utilisé par la prod
(`LLMClientsMixin._call_t1_provider`, fournisseur « local » seulement) et par le rejeu
(`compare_qwen_local_vs_prod.py`, `QWEN_LOCAL_FIT_BUDGET=1`).

Constantes calibrées sur des MESURES (Catania, qwen3-vl:8b-instruct) : 640×1386 → 867 tokens, 640×296 → 187 tokens,
texte 6788 caractères → 2080 tokens (≈ 3,3 caractères/token ; on prend 3,0 par prudence)."""
import math

from PIL import Image

PATCH_PIXELS = 32                # Qwen3-VL : un token par carré de 32×32 px (après arrondi à un multiple de 32)
IMAGE_TOKEN_OVERHEAD = 7         # balises de début/fin d'image, mesuré
TEXT_CHARS_PER_TOKEN = 3.0       # prudent : mesuré ≈ 3,3 sur le prompt Portier (français + JSON)
TEXT_TEMPLATE_OVERHEAD = 100     # gabarit de conversation, mesuré ≈ marge
MIN_SCALE = 0.25                 # en dessous, la photo ne sert plus à rien : on retire les dernières plutôt
SEARCH_STEPS = 14


def estimate_image_tokens(width, height):
    """Tokens d'une photo `width`×`height` px (arrondi au multiple de 32 le plus proche, comme le prétraitement)."""
    return max(1, round(width / PATCH_PIXELS)) * max(1, round(height / PATCH_PIXELS)) + IMAGE_TOKEN_OVERHEAD


def estimate_text_tokens(text):
    return math.ceil(len(text or "") / TEXT_CHARS_PER_TOKEN) + TEXT_TEMPLATE_OVERHEAD


def _scaled_size(size, scale):
    return max(PATCH_PIXELS, round(size[0] * scale)), max(PATCH_PIXELS, round(size[1] * scale))


def _tokens_at(images, scale):
    return sum(estimate_image_tokens(*_scaled_size(img.size, scale)) for img in images)


def fit_images_to_budget(images, prompt_text, context_tokens, response_margin):
    """Renvoie `(images, info)`. `images` est la liste d'origine (mêmes objets) si tout tient ou si la correction est
    désactivée (`context_tokens <= 0`) ; sinon une NOUVELLE liste de photos réduites (les originaux ne sont pas
    modifiés). `info` : applied, budget, text_tokens, before, after, scale, dropped. Peut lever (photo non
    standard) : l'appelant de prod attrape et garde les photos d'origine (échec ouvert)."""
    info = {"applied": False, "budget": None, "text_tokens": None, "before": 0, "after": 0, "scale": 1.0, "dropped": 0}
    if not images or context_tokens <= 0:
        return images, info
    text_tokens = estimate_text_tokens(prompt_text)
    budget = context_tokens - text_tokens - response_margin
    before = _tokens_at(images, 1.0)
    info.update(budget=budget, text_tokens=text_tokens, before=before, after=before)
    if before <= budget or budget <= 0:       # tout tient ; ou le texte seul ne tient déjà pas (rien à sauver ici)
        return images, info

    lo, hi = MIN_SCALE, 1.0                   # plus grand coefficient dont le total tient dans le budget
    for _ in range(SEARCH_STEPS):
        mid = (lo + hi) / 2
        if _tokens_at(images, mid) <= budget:
            lo = mid
        else:
            hi = mid
    kept = list(images)
    scale = lo
    while kept and _tokens_at(kept, scale) > budget:   # extrême : même à MIN_SCALE ça ne tient pas → retire la dernière
        kept.pop()
    fitted = [img.resize(_scaled_size(img.size, scale), Image.Resampling.LANCZOS) for img in kept]
    info.update(applied=True, scale=round(scale, 3), after=_tokens_at(kept, scale), dropped=len(images) - len(kept))
    return fitted, info
