#!/usr/bin/env python3
"""
Auto-annotation de parties de guitare avec Grounding DINO (HuggingFace transformers).
Produit des labels au format YOLO pour entraîner un détecteur RT-DETR/YOLO.

Usage sur le Dell Linux :
  1. Copier ce script + le fichier dataset_a_phase0.jsonl sur le Dell
  2. Installer les dépendances :
     pip install transformers accelerate torch torchvision pillow requests
  3. Lancer :
     python auto_annotate_gdino.py --limit 5       # test rapide
     python auto_annotate_gdino.py --limit 300      # dataset complet
     python auto_annotate_gdino.py --limit 300 --verify  # + images vérification

Le script :
  - Tire 1 image par annonce (diversité max)
  - Télécharge chaque image depuis son URL Firebase
  - Passe chaque image dans Grounding DINO avec les prompts de parties de guitare
  - Convertit les bounding boxes au format YOLO
  - Sauvegarde images + labels dans yolo_dataset/
  - (optionnel) Dessine les boîtes sur les images pour vérification visuelle
"""

import os
import json
import random
import time
import argparse
import requests
from io import BytesIO
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

# ── Classes cibles ──────────────────────────────────────────────────
CLASSES = ["neck", "headstock", "heel", "soundhole", "saddle"]
CLASS_MAP = {name: i for i, name in enumerate(CLASSES)}

# Prompts Grounding DINO : phrases descriptives séparées par " . "
# On utilise des descriptions naturelles pour maximiser la pertinence
GDINO_PROMPTS = {
    "neck":      "guitar neck fretboard",
    "headstock": "guitar headstock with tuning pegs",
    "heel":      "guitar heel joint where neck meets body",
    "soundhole": "guitar sound hole",
    "saddle":    "guitar bridge saddle",
}

# Texte complet pour le modèle (toutes les classes en une seule query)
GDINO_TEXT = " . ".join(GDINO_PROMPTS.values()) + " ."

# Mapping des labels retournés par GDINO vers nos classes
# GDINO retourne le texte du prompt correspondant ; on doit le mapper
LABEL_TO_CLASS = {}
for cls_name, prompt_text in GDINO_PROMPTS.items():
    LABEL_TO_CLASS[prompt_text] = cls_name

COLORS = {
    "neck":      (0, 100, 255),    # Bleu
    "headstock": (0, 220, 0),      # Vert
    "heel":      (255, 0, 0),      # Rouge
    "soundhole": (255, 220, 0),    # Jaune
    "saddle":    (255, 0, 255),     # Magenta
}


def load_usable_images(manifest_path: str, max_per_deal: int = 1) -> list:
    """Charge les images 'usable', 1 par annonce max pour la diversité."""
    deals = {}
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("usable"):
                deal_id = data.get("deal_id")
                if deal_id not in deals:
                    deals[deal_id] = []
                deals[deal_id].append(data)

    results = []
    for deal_id, images in deals.items():
        random.shuffle(images)
        results.extend(images[:max_per_deal])

    return results


def download_image(url: str, max_size: int = 1024) -> Image.Image | None:
    """Télécharge et redimensionne une image."""
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img.thumbnail((max_size, max_size))
        return img
    except Exception as e:
        print(f"  ⚠ Erreur téléchargement {url}: {e}")
        return None


def box_to_yolo(box, img_width: int, img_height: int):
    """Convertit [xmin, ymin, xmax, ymax] (pixels) → YOLO (x_c, y_c, w, h) normalisé."""
    xmin, ymin, xmax, ymax = box
    w = (xmax - xmin) / img_width
    h = (ymax - ymin) / img_height
    x_c = (xmin + xmax) / 2.0 / img_width
    y_c = (ymin + ymax) / 2.0 / img_height
    return (
        round(max(0, min(1, x_c)), 5),
        round(max(0, min(1, y_c)), 5),
        round(max(0, min(1, w)), 5),
        round(max(0, min(1, h)), 5),
    )


def draw_boxes(img: Image.Image, detections: list) -> Image.Image:
    """Dessine les boîtes sur une copie de l'image pour vérification."""
    vis = img.copy()
    draw = ImageDraw.Draw(vis)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    for det in detections:
        cls_name = det["class"]
        box = det["box"]  # [xmin, ymin, xmax, ymax]
        color = COLORS.get(cls_name, (255, 255, 255))
        draw.rectangle(box, outline=color, width=3)
        draw.text((box[0] + 2, box[1] - 18), cls_name, fill=color, font=font)

    return vis


def main():
    parser = argparse.ArgumentParser(description="Auto-annotation Grounding DINO → YOLO")
    parser.add_argument("--manifest", default="dataset_a_phase0.jsonl",
                        help="Chemin vers le fichier JSONL du dataset")
    parser.add_argument("--limit", type=int, default=5,
                        help="Nombre d'images à annoter")
    parser.add_argument("--output", default="yolo_dataset",
                        help="Dossier de sortie")
    parser.add_argument("--verify", action="store_true",
                        help="Générer des images de vérification avec boîtes dessinées")
    parser.add_argument("--threshold", type=float, default=0.25,
                        help="Seuil de confiance Grounding DINO (défaut: 0.25)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # ── Setup dirs ──
    out_dir = Path(args.output)
    img_dir = out_dir / "images" / "train"
    lbl_dir = out_dir / "labels" / "train"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    if args.verify:
        verify_dir = out_dir / "verify"
        verify_dir.mkdir(parents=True, exist_ok=True)

    # ── dataset.yaml ──
    with open(out_dir / "dataset.yaml", "w") as f:
        f.write(f"path: {out_dir.resolve()}\n")
        f.write("train: images/train\n")
        f.write("val: images/train\n")
        f.write(f"nc: {len(CLASSES)}\n")
        f.write(f"names: {json.dumps(CLASSES)}\n")

    # ── Charger le modèle ──
    print("🔧 Chargement de Grounding DINO (IDEA-Research/grounding-dino-base)...")
    model_id = "IDEA-Research/grounding-dino-base"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   Device: {device}")

    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
    model.eval()
    print("✅ Modèle chargé.\n")

    # ── Charger les images ──
    print(f"📂 Chargement du manifest {args.manifest}...")
    all_images = load_usable_images(args.manifest)
    print(f"   {len(all_images)} annonces uniques avec images 'usable'.")

    random.seed(args.seed)
    random.shuffle(all_images)
    sample = all_images[:args.limit]
    print(f"   Échantillon : {len(sample)} images.\n")

    # ── Boucle d'annotation ──
    success = 0
    stats = {c: 0 for c in CLASSES}

    for idx, data in enumerate(sample):
        url = data.get("image_url")
        deal_id = data.get("deal_id")
        img_idx = data.get("image_idx", 0)
        basename = f"{deal_id}_{img_idx}"

        print(f"[{idx+1}/{len(sample)}] {basename}...", end=" ", flush=True)

        img = download_image(url)
        if img is None:
            print("⚠ SKIP (téléchargement échoué)")
            continue

        w, h = img.size

        # ── Inférence Grounding DINO ──
        inputs = processor(images=img, text=GDINO_TEXT, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)

        results = processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=args.threshold,
            text_threshold=args.threshold,
            target_sizes=[(h, w)],
        )[0]

        boxes = results["boxes"].cpu().tolist()
        scores = results["scores"].cpu().tolist()
        labels = results["labels"]

        # ── Mapper les labels vers nos classes ──
        detections = []
        for box, score, label in zip(boxes, scores, labels):
            # GDINO retourne le texte du prompt ; on cherche la meilleure correspondance
            cls_name = None
            label_lower = label.lower().strip()
            for prompt_text, cname in LABEL_TO_CLASS.items():
                if prompt_text.lower() in label_lower or label_lower in prompt_text.lower():
                    cls_name = cname
                    break

            # Fallback : chercher par mot-clé
            if cls_name is None:
                for cname in CLASSES:
                    if cname in label_lower:
                        cls_name = cname
                        break

            if cls_name is not None:
                detections.append({
                    "class": cls_name,
                    "class_id": CLASS_MAP[cls_name],
                    "box": box,
                    "score": score,
                })
                stats[cls_name] += 1

        # ── Dédupliquer : garder la meilleure détection par classe ──
        best_per_class = {}
        for det in detections:
            cname = det["class"]
            if cname not in best_per_class or det["score"] > best_per_class[cname]["score"]:
                best_per_class[cname] = det
        detections = list(best_per_class.values())

        # ── Sauvegarder ──
        img.save(img_dir / f"{basename}.jpg")

        with open(lbl_dir / f"{basename}.txt", "w") as f:
            for det in detections:
                x_c, y_c, bw, bh = box_to_yolo(det["box"], w, h)
                f.write(f"{det['class_id']} {x_c} {y_c} {bw} {bh}\n")

        if args.verify:
            vis = draw_boxes(img, detections)
            vis.save(verify_dir / f"{basename}.jpg")

        found = [d["class"] for d in detections]
        print(f"✓ {', '.join(found) if found else '(rien détecté)'}")
        success += 1

    # ── Résumé ──
    print(f"\n{'='*50}")
    print(f"Terminé ! {success}/{len(sample)} images annotées.")
    print(f"Sauvegardé dans : {out_dir.resolve()}")
    print(f"\nDétections par classe :")
    for cls, count in stats.items():
        print(f"  {cls}: {count}")
    if args.verify:
        print(f"\nImages de vérification dans : {verify_dir.resolve()}")


if __name__ == "__main__":
    main()
