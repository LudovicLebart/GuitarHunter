"""
Test ponctuel (docs/management/plans/NECK_RESET_VISION_PLAN.md §8) : OWLv2 en détection
multi-parties, pas juste présence globale — teste s'il peut localiser le manche (et
accessoirement tête/chevalet/rosace) sur de vraies photos d'annonces, en réutilisant
exactement le même modèle déjà validé (§7 étape 4 : VRAM confortable, pas de risque de
compatibilité comme Florence-2 — voir test_dell_vision_inference.py).

Objectif direct : réparer le prototype Phase 1 (`experiments/phase1_fret_detection_prototype.py`),
qui échoue sans région d'intérêt sur le manche et dont le recadrage est actuellement manuel — si
OWLv2 localise correctement le manche, sa boîte remplace le recadrage manuel.

Échantillon : les 2 mêmes photos utilisées pour le prototype Phase 1 (une où la détection de
frettes fonctionnait après recadrage manuel, une où elle échouait), pour un test directement
comparable.

Sortie : une image annotée par photo (boîte + étiquette + score par partie), à inspecter
visuellement — pas de métrique chiffrée automatique, l'évaluation est manuelle à ce stade.

Usage (sur le Dell, venv avec torch/transformers/pillow/requests installés) :
  python3 backend/scripts/experiments/test_owlv2_parts_detection.py
"""

from io import BytesIO

import requests
import torch
from PIL import Image, ImageDraw
from transformers import Owlv2ForObjectDetection, Owlv2Processor

MODEL_ID = "google/owlv2-base-patch16-ensemble"
SCORE_THRESHOLD = 0.1

PARTS = [
    "the headstock of a guitar",
    "the neck of a guitar",
    "the bridge of a guitar",
    "the soundhole of a guitar",
]
COLORS = {
    "the headstock of a guitar": (255, 80, 80),
    "the neck of a guitar": (80, 160, 255),
    "the bridge of a guitar": (80, 220, 120),
    "the soundhole of a guitar": (230, 200, 60),
}

SAMPLE_IMAGES = [
    # Même photo que le prototype Phase 1 où le recadrage manuel + LSD/RANSAC fonctionnait.
    ("fender_frontal_ok", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1735588974289650/0_7f520d92.jpg"),
    # Même photo où le prototype Phase 1 échouait (angle légèrement de travers).
    ("yamaha_angle_fail", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1349593020616490/0_5693fb9c.jpg"),
]


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("--- Environnement ---")
    print(f"torch {torch.__version__}, CUDA disponible : {torch.cuda.is_available()}")
    if device == "cuda":
        print(f"GPU : {torch.cuda.get_device_name(0)}")

    print(f"\n--- Chargement du modèle {MODEL_ID} ---")
    processor = Owlv2Processor.from_pretrained(MODEL_ID)
    model = Owlv2ForObjectDetection.from_pretrained(MODEL_ID).to(device)
    model.eval()

    for name, url in SAMPLE_IMAGES:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        image = Image.open(BytesIO(resp.content)).convert("RGB")

        inputs = processor(text=[PARTS], images=image, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        target_sizes = torch.tensor([(image.height, image.width)])
        detections = processor.post_process_grounded_object_detection(
            outputs=outputs, target_sizes=target_sizes, threshold=SCORE_THRESHOLD
        )[0]

        vis = image.copy()
        draw = ImageDraw.Draw(vis)
        print(f"\n{name} ({image.width}x{image.height}px) :")
        for part_idx, part in enumerate(PARTS):
            mask = detections["labels"] == part_idx
            scores = detections["scores"][mask]
            boxes = detections["boxes"][mask]
            if len(scores) == 0:
                print(f"  {part:30s} : aucune détection (seuil {SCORE_THRESHOLD})")
                continue
            best = int(scores.argmax())
            box = [float(v) for v in boxes[best].tolist()]
            score = float(scores[best])
            color = COLORS[part]
            draw.rectangle(box, outline=color, width=4)
            draw.text((box[0] + 4, box[1] + 4), f"{part.split(' of ')[0]} {score:.2f}", fill=color)
            print(f"  {part:30s} : score={score:.3f} box={[round(v) for v in box]}")

        out_path = f"owlv2_parts_output/{name}_parts.jpg"
        import os
        os.makedirs("owlv2_parts_output", exist_ok=True)
        vis.save(out_path)
        print(f"  -> {out_path}")


if __name__ == "__main__":
    main()
