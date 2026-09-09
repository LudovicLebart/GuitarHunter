import aiohttp
import asyncio
import cv2
import base64
import logging
from .config import OLLAMA_API_URL, VLM_MODEL, CLASS_NAMES

logger = logging.getLogger(__name__)

async def query_ollama(image_b64, prompt):
    """Effectue une requête POST asynchrone à l'API locale d'Ollama."""
    payload = {
        "model": VLM_MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_API_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "").strip().upper()
                return "ERROR"
    except Exception as e:
        logger.error(f"Erreur Ollama: {e}")
        return "ERROR"

async def validate_with_vlm(image, rects, classes, valid_indices, geometry_module):
    """
    Filtre 2: Oracle VLM Local.
    Valide chaque crop redressé via une classification binaire (TRUE/FALSE).
    """
    final_indices = []
    tasks = []
    
    for i in valid_indices:
        rect = rects[i]
        c_name = CLASS_NAMES[int(classes[i])]
        
        # Redressement et crop via le module de géométrie
        crop = geometry_module.rotate_and_crop(image, rect)
        if crop.size == 0:
            continue
            
        # Encodage Base64
        _, buffer = cv2.imencode('.jpg', crop)
        img_b64 = base64.b64encode(buffer).decode('utf-8')
        
        # Définition du prompt strict
        prompt = f"L'image montre-t-elle exclusivement un(e) {c_name} de guitare ? Réponds uniquement par TRUE ou FALSE."
        tasks.append((i, query_ollama(img_b64, prompt)))
    
    if not tasks:
        return []
        
    # Exécution parallèle
    results = await asyncio.gather(*(t[1] for t in tasks))
    
    for (i, _), result in zip(tasks, results):
        if "TRUE" in result:
            final_indices.append(i)
            
    return final_indices
