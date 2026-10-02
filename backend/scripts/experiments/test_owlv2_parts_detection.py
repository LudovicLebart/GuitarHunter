"""
Test ponctuel (docs/management/plans/NECK_RESET_VISION_PLAN.md §8/§9) : OWLv2 en détection
multi-parties, pas juste présence globale — teste s'il peut localiser le manche (et
accessoirement tête/chevalet/rosace/sillet) sur de vraies photos d'annonces, en réutilisant
exactement le même modèle déjà validé (§7 étape 4 : VRAM confortable, pas de risque de
compatibilité comme Florence-2 — voir test_dell_vision_inference.py).

Objectif direct : réparer le prototype Phase 1 (`experiments/phase1_fret_detection_prototype.py`),
qui échoue sans région d'intérêt sur le manche et dont le recadrage est actuellement manuel — si
OWLv2 localise correctement le manche, sa boîte remplace le recadrage manuel. Objectif secondaire
(§6, décision 2026-08-24) : localisation sillet/chevalet, nécessaire pour mesurer la hauteur de
selle au-dessus du chevalet (proposition Fable) et pour un vrai test de "mesurabilité" (§8quater).

§9 (2026-08-24) : première passe (requêtes "headstock"/"neck"/"bridge"/"soundhole") jugée peu
fiable après inspection visuelle réelle par l'utilisateur (correction : la boîte "soundhole" sur
la photo Fender couvrait en fait le manche + une bonne partie de la caisse, pas juste la rosace —
voir JOURNAL.md). Ce test ajoute 4 nouvelles formulations de requête ("fretboard"/"fingerboard with
frets"/"saddle of a guitar bridge"/"nut of a guitar neck") en conservant les anciennes pour
comparaison directe, et 2 photos de guitares électriques en plus des 2 acoustiques déjà testées,
pour varier les formes de manche/chevalet.

Échantillon : les 2 mêmes photos acoustiques utilisées pour le prototype Phase 1 (une où la
détection de frettes fonctionnait après recadrage manuel, une où elle échouait) + 2 photos de
guitares électriques solid body tirées aléatoirement (seed=1) de l'échantillon Phase 0 déjà
téléchargé, pour un test directement comparable et diversifié.

Sortie : une image annotée par photo (boîte + étiquette + score par partie, ancien+nouveau jeu de
requêtes), à inspecter visuellement — pas de métrique chiffrée automatique, l'évaluation est
manuelle à ce stade (leçon du §8bis : ne jamais conclure sur les scores seuls, toujours regarder
l'image).

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
    # Requêtes initiales (§8/§8bis).
    "the headstock of a guitar",
    "the neck of a guitar",
    "the bridge of a guitar",
    "the soundhole of a guitar",
    # Nouvelles formulations (§9, 2026-08-24) — reformulation vers la zone de mesure réelle
    # (sillet/chevalet/touche) plutôt que les parties génériques déjà testées et jugées peu fiables.
    "the fretboard of a guitar",
    "the fingerboard with frets",
    "the saddle of a guitar bridge",
    "the nut of a guitar neck",
]
COLORS = {
    "the headstock of a guitar": (255, 80, 80),
    "the neck of a guitar": (80, 160, 255),
    "the bridge of a guitar": (80, 220, 120),
    "the soundhole of a guitar": (230, 200, 60),
    "the fretboard of a guitar": (200, 80, 255),
    "the fingerboard with frets": (255, 150, 60),
    "the saddle of a guitar bridge": (60, 220, 220),
    "the nut of a guitar neck": (255, 255, 255),
}

SAMPLE_IMAGES = [
    # Même photo que le prototype Phase 1 où le recadrage manuel + LSD/RANSAC fonctionnait.
    ("fender_frontal_ok", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1735588974289650/0_7f520d92.jpg"),
    # Même photo où le prototype Phase 1 échouait (angle légèrement de travers).
    ("yamaha_angle_fail", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1349593020616490/0_5693fb9c.jpg"),
    # 2 guitares électriques solid body, tirées aléatoirement (seed=1) de l'échantillon Phase 0,
    # pour varier les formes de manche/chevalet (§9, absentes des 2 photos acoustiques ci-dessus).
    ("electrique_s_style_1", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1532369785179505/0_c15ba2a9.jpg"),
    ("electrique_s_style_2", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/2370518256811527/0_dfea8e4c.jpg"),
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
