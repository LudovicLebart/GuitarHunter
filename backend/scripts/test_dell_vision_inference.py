"""
Test ponctuel (docs/management/plans/NECK_RESET_VISION_PLAN.md §7, étape 4) : valide qu'un
modèle de détection open-vocabulaire (Florence-2-base, MIT — retenu après la revue Fable, §2ter)
tourne bien en inférence sur le GPU du Dell (8192 Mo VRAM, confirmé §7) et mesure la VRAM pic
réellement utilisée, sur un petit échantillon réel du Dataset A (§3septies).

Volontairement autonome (pas de dépendance Firestore/Firebase) : les URLs d'images sont un
échantillon fixe de 8 annonces (2 par grande famille : acoustique, classique, électrique, basse),
tiré une fois de `dataset_a_manifest.jsonl` — ce n'est pas un outil réutilisable, juste la
validation Phase 0 de l'étape 4 du plan. Les images sont déjà en Firebase Storage (upload
pass-through confirmé, `backend/repository.py`), donc accessibles par URL publique directe sans
credentials.

Usage (sur le Dell, dans un venv avec torch/transformers/pillow/requests/timm/einops installés) :
  python3 backend/scripts/test_dell_vision_inference.py
"""

import time
from io import BytesIO

import requests
import torch
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

MODEL_ID = "microsoft/Florence-2-base"
TASK_PROMPT = "<CAPTION_TO_PHRASE_GROUNDING>"
TEXT_INPUT = "guitar"

SAMPLE_IMAGES = [
    ("guitare.acoustique_acier.formes_standard.Dreadnought.Slope Shoulder",
     "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/2606003983180354/0_275d66bc.jpg"),
    ("guitare.acoustique_acier.formes_standard.Dreadnought.Dreadnought Standard",
     "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1074166101792776/0_9f68984a.jpg"),
    ("guitare.classique_nylon.types.Classique Standard",
     "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/3212839288915337/0_93138ff7.jpg"),
    ("guitare.classique_nylon.types.Classique Standard",
     "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1489522875709537/0_21fad04e.jpg"),
    ("guitare.electrique.solid_body.S_Style",
     "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1420495349618059/0_b65cbe17.jpg"),
    ("guitare.electrique.solid_body.Double_Cut",
     "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1394905612414565/0_4d63437f.jpg"),
    ("guitare.basse.solid_body.Modern Soapbar (BTB/SR)",
     "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1366333381749087/0_0dd683fe.jpg"),
    ("guitare.basse.solid_body.Precision Bass (P)",
     "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1334507658724089/0_3f3065a1.jpg"),
]


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"--- Environnement ---")
    print(f"torch {torch.__version__}, CUDA disponible : {torch.cuda.is_available()}")
    if device == "cuda":
        print(f"GPU : {torch.cuda.get_device_name(0)}")
        torch.cuda.reset_peak_memory_stats()

    print(f"\n--- Chargement du modèle {MODEL_ID} ---")
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, trust_remote_code=True, torch_dtype=torch.float16 if device == "cuda" else torch.float32).to(device)
    processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    print(f"Modèle chargé en {time.time() - t0:.1f}s")

    results = []
    for classification, url in SAMPLE_IMAGES:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            image = Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            print(f"⚠️  Échec téléchargement {url} : {e}")
            continue

        t0 = time.time()
        inputs = processor(text=TASK_PROMPT + TEXT_INPUT, images=image, return_tensors="pt").to(device, torch.float16 if device == "cuda" else torch.float32)
        with torch.no_grad():
            generated_ids = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=256,
                num_beams=1,
            )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed = processor.post_process_generation(generated_text, task=TASK_PROMPT, image_size=(image.width, image.height))
        elapsed = time.time() - t0

        boxes = parsed.get(TASK_PROMPT, {}).get("bboxes", [])
        print(f"{classification[:55]:55s} {image.width}x{image.height}px  {len(boxes)} boîte(s) 'guitar'  {elapsed:.2f}s")
        results.append((classification, len(boxes)))

    print(f"\n--- Résumé ---")
    detected = sum(1 for _, n in results if n > 0)
    print(f"{detected}/{len(results)} images avec au moins une boîte 'guitar' détectée.")

    if device == "cuda":
        peak_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)
        total_mb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        print(f"VRAM pic utilisée : {peak_mb:.0f} Mo / {total_mb:.0f} Mo disponibles ({100 * peak_mb / total_mb:.1f}%)")


if __name__ == "__main__":
    main()
