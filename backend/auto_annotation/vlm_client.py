import aiohttp
import asyncio
import cv2
import base64
import logging
from .config import OLLAMA_API_URL, VLM_MODEL, VLM_PROMPT, CLASS_NAMES, OLLAMA_TIMEOUT_S, MIN_CROP_DIM
from .geometry import rotate_and_crop

logger = logging.getLogger(__name__)

async def query_ollama(session: aiohttp.ClientSession, image_b64: str, prompt: str) -> str:
    """
    Effectue une requête POST asynchrone à l'API locale d'Ollama.
    Utilise la session partagée passée en argument — ne jamais créer de session par appel.
    """
    payload = {
        "model": VLM_MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False
    }
    try:
        async with session.post(OLLAMA_API_URL, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("response", "").strip().upper()
            logger.warning(f"Ollama HTTP {resp.status}")
            return "ERROR"
    except asyncio.TimeoutError:
        logger.error("Ollama: timeout dépassé")
        return "ERROR"
    except Exception as e:
        logger.error(f"Erreur Ollama: {e}")
        return "ERROR"

async def validate_with_vlm(image, rects, classes, valid_indices):
    """
    Filtre 2: Oracle VLM Local.
    Valide chaque crop redressé via une classification binaire (TRUE/FALSE).
    Session aiohttp unique partagée entre toutes les requêtes parallèles.
    """
    final_indices = []
    tasks = []

    timeout = aiohttp.ClientTimeout(total=OLLAMA_TIMEOUT_S)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for i in valid_indices:
            rect = rects[i]
            c_name = CLASS_NAMES[int(classes[i])]

            # Redressement et crop (import direct — plus de passage de module en argument)
            crop = rotate_and_crop(image, rect)

            # Filtrer les crops dégénérés (< MIN_CROP_DIM px sur un côté)
            if (crop is None or crop.size == 0
                    or crop.shape[0] < MIN_CROP_DIM
                    or crop.shape[1] < MIN_CROP_DIM):
                logger.debug(
                    f"Crop dégénéré ignoré pour '{c_name}' "
                    f"(shape={getattr(crop, 'shape', 'N/A')})"
                )
                continue

            # Encodage Base64
            _, buffer = cv2.imencode('.jpg', crop)
            img_b64 = base64.b64encode(buffer).decode('utf-8')

            # Prompt depuis config (modifiable sans toucher au code)
            prompt = VLM_PROMPT.format(class_name=c_name)
            tasks.append((i, query_ollama(session, img_b64, prompt)))

        if not tasks:
            return []

        # Exécution parallèle dans la même session
        results = await asyncio.gather(*(t[1] for t in tasks))

    for (i, _), result in zip(tasks, results):
        if "TRUE" in result:
            final_indices.append(i)

    return final_indices
