"""
Test ponctuel (docs/management/plans/NECK_RESET_VISION_PLAN.md §9/§10) : SAM 2.1 en
segmentation point-guidée, comme piste de repli après l'échec de OWLv2 en détection
multi-parties (test_owlv2_parts_detection.py, §9) — aucune des 8 formulations de requête
testées n'a localisé de façon fiable le manche/sillet/chevalet ; seule "the nut of a
guitar neck" donnait une zone plausible de façon répétée, et "the saddle of a guitar
bridge" se verrouillait systématiquement sur la tête au lieu du chevalet.

Principe différent : SAM 2.1 n'est pas open-vocabulary (pas de requête texte), il segmente
l'objet contenant un point donné en entrée, à 3 niveaux de granularité (masque le plus
probable = "sous-partie" / "partie" / "objet entier", classés par score IoU prédit). Ce test
n'automatise pas encore le choix du point : les points de départ sont dérivés du HAUT de la
boîte OWLv2 "the nut of a guitar neck" déjà obtenue (la requête la plus fiable du test
précédent), pas cliqués à la main sur l'image brute — à documenter comme tel, ce n'est pas
une validation d'un pipeline automatique, juste un test de qualité de segmentation à partir
d'un point déjà à peu près bon.

Échantillon : les mêmes 4 photos que test_owlv2_parts_detection.py (2 acoustiques + 2
électriques ; electrique_s_style_1 reste une photo de mur de magasin avec plusieurs guitares
en arrière-plan, donc à interpréter avec prudence pour cette photo spécifiquement).

Sortie : par photo, une image annotée par masque candidat (jusqu'à 3, avec score IoU), à
inspecter visuellement — même règle que pour OWLv2 : ne jamais conclure sur le score seul.

Usage (sur le Dell, venv avec torch/transformers/pillow/requests installés) :
  python3 backend/scripts/experiments/test_sam2_point_segmentation.py
"""

import os
from io import BytesIO

import numpy as np
import requests
import torch
from PIL import Image, ImageDraw
from transformers import Sam2Model, Sam2Processor

MODEL_ID = "facebook/sam2.1-hiera-large"

# (nom, url, point [x, y]) — le point est dérivé du haut de la boîte OWLv2 "the nut of a
# guitar neck" obtenue dans test_owlv2_parts_detection.py (§9), pas cliqué à la main.
SAMPLE_POINTS = [
    ("fender_frontal_ok", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1735588974289650/0_7f520d92.jpg", [380, 240]),
    ("yamaha_angle_fail", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1349593020616490/0_5693fb9c.jpg", [228, 295]),
    ("electrique_s_style_1", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/1532369785179505/0_c15ba2a9.jpg", [348, 195]),
    ("electrique_s_style_2", "https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/2370518256811527/0_dfea8e4c.jpg", [358, 170]),
]

MASK_COLORS = [(255, 80, 80), (80, 160, 255), (80, 220, 120)]


def overlay_mask(image, mask, color, alpha=110):
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    mask_img = Image.fromarray((mask * alpha).astype(np.uint8), mode="L")
    color_layer = Image.new("RGBA", image.size, color + (0,))
    color_layer.putalpha(mask_img)
    overlay = Image.alpha_composite(overlay, color_layer)
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("--- Environnement ---")
    print(f"torch {torch.__version__}, CUDA disponible : {torch.cuda.is_available()}")
    if device == "cuda":
        print(f"GPU : {torch.cuda.get_device_name(0)}")
        torch.cuda.reset_peak_memory_stats()

    print(f"\n--- Chargement du modèle {MODEL_ID} ---")
    processor = Sam2Processor.from_pretrained(MODEL_ID)
    model = Sam2Model.from_pretrained(MODEL_ID).to(device)
    model.eval()

    out_dir = "sam2_points_output"
    os.makedirs(out_dir, exist_ok=True)

    for name, url, point in SAMPLE_POINTS:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        image = Image.open(BytesIO(resp.content)).convert("RGB")

        input_points = [[[point]]]
        input_labels = [[[1]]]
        inputs = processor(images=image, input_points=input_points, input_labels=input_labels, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model(**inputs, multimask_output=True)

        masks = processor.post_process_masks(
            outputs.pred_masks.cpu(), inputs["original_sizes"].cpu()
        )[0][0]  # (num_masks, H, W) pour ce point/objet
        scores = outputs.iou_scores.squeeze().tolist()
        if isinstance(scores, float):
            scores = [scores]

        print(f"\n{name} ({image.width}x{image.height}px), point={point} :")
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        for rank, i in enumerate(order):
            mask_np = masks[i].numpy().astype(np.uint8)
            coverage = 100 * mask_np.sum() / mask_np.size
            print(f"  masque {rank} (indice {i}) : score IoU prédit={scores[i]:.3f}, couverture image={coverage:.1f}%")

            vis = overlay_mask(image, mask_np, MASK_COLORS[rank % len(MASK_COLORS)])
            draw = ImageDraw.Draw(vis)
            r = 8
            draw.ellipse([point[0] - r, point[1] - r, point[0] + r, point[1] + r], outline=(255, 255, 0), width=3)
            draw.text((10, 10), f"masque {rank} - IoU={scores[i]:.2f} - couverture={coverage:.1f}%", fill=(255, 255, 0))

            out_path = f"{out_dir}/{name}_mask{rank}.jpg"
            vis.save(out_path)
            print(f"    -> {out_path}")

    if device == "cuda":
        peak_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)
        total_mb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        print(f"\nVRAM pic utilisée : {peak_mb:.0f} Mo / {total_mb:.0f} Mo disponibles ({100 * peak_mb / total_mb:.1f}%)")


if __name__ == "__main__":
    main()
