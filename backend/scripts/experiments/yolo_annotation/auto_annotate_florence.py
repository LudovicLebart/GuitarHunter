#!/usr/bin/env python3
"""
Auto-annotation de parties de guitare avec Florence-2 (Microsoft).
Florence-2 a un grounding spatial nettement meilleur que Grounding DINO
pour les objets fins/spécialisés grâce à son architecture unified.

Usage:
  python3 auto_annotate_florence.py --limit 5 --verify --output yolo_florence_test
"""

import os
import json
import random
import argparse
import requests
from io import BytesIO
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont
from transformers import AutoProcessor, AutoModelForCausalLM

# ── Classes cibles ──────────────────────────────────────────────────
CLASSES = ["neck", "headstock", "heel", "soundhole", "saddle"]
CLASS_MAP = {name: i for i, name in enumerate(CLASSES)}

# Florence-2 utilise <OPEN_VOCABULARY_DETECTION> avec une liste de classes
# On fait UNE requête par classe pour avoir des boxes plus précises
FLORENCE_QUERIES = {
    "neck":      "guitar neck",
    "headstock": "headstock",
    "heel":      "heel joint",
    "soundhole": "sound hole",
    "saddle":    "bridge saddle",
}

COLORS = {
    "neck":      (0, 100, 255),
    "headstock": (0, 220, 0),
    "heel":      (255, 0, 0),
    "soundhole": (255, 220, 0),
    "saddle":    (255, 0, 255),
}


def load_usable_images(manifest_path: str, max_per_deal: int = 1) -> list:
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
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img.thumbnail((max_size, max_size))
        return img
    except Exception as e:
        print(f"  ⚠ Erreur téléchargement: {e}")
        return None


def box_to_yolo(box, img_width: int, img_height: int):
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
    vis = img.copy()
    draw = ImageDraw.Draw(vis)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    for det in detections:
        cls_name = det["class"]
        box = det["box"]
        color = COLORS.get(cls_name, (255, 255, 255))
        draw.rectangle(box, outline=color, width=3)
        draw.text((box[0] + 2, box[1] - 18), cls_name, fill=color, font=font)
    return vis


def run_florence_detection(model, processor, image, text_query, device):
    """Run Florence-2 open vocabulary detection for a single query."""
    task = "<OPEN_VOCABULARY_DETECTION>"
    prompt = task + text_query

    inputs = processor(text=prompt, images=image, return_tensors="pt").to(device)

    with torch.no_grad():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            num_beams=3,
        )

    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    result = processor.post_process_generation(
        generated_text,
        task=task,
        image_size=(image.width, image.height),
    )

    return result.get(task, {})


def main():
    parser = argparse.ArgumentParser(description="Auto-annotation Florence-2 → YOLO")
    parser.add_argument("--manifest", default="dataset_a_phase0.jsonl")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", default="yolo_florence")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_dir = Path(args.output)
    img_dir = out_dir / "images" / "train"
    lbl_dir = out_dir / "labels" / "train"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    if args.verify:
        verify_dir = out_dir / "verify"
        verify_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "dataset.yaml", "w") as f:
        f.write(f"path: {out_dir.resolve()}\n")
        f.write("train: images/train\nval: images/train\n")
        f.write(f"nc: {len(CLASSES)}\nnames: {json.dumps(CLASSES)}\n")

    # ── Charger Florence-2 ──
    print("🔧 Chargement de Florence-2-large...")
    model_id = "microsoft/Florence-2-large"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   Device: {device}")

    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, trust_remote_code=True
    ).to(device).eval()
    print("✅ Florence-2 chargé.\n")

    # ── Charger les images ──
    all_images = load_usable_images(args.manifest)
    print(f"📂 {len(all_images)} annonces uniques.")
    random.seed(args.seed)
    random.shuffle(all_images)
    sample = all_images[:args.limit]
    print(f"   Échantillon : {len(sample)} images.\n")

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
            print("⚠ SKIP")
            continue

        w, h = img.size
        detections = []

        # ── Une requête par classe ──
        for cls_name, query in FLORENCE_QUERIES.items():
            try:
                result = run_florence_detection(model, processor, img, query, device)
                bboxes = result.get("bboxes", [])
                labels = result.get("bboxes_labels", [])

                if bboxes:
                    # Garder seulement la meilleure détection (la première)
                    box = bboxes[0]
                    # Vérifier que la boîte est raisonnable (pas trop grande)
                    box_w = (box[2] - box[0]) / w
                    box_h = (box[3] - box[1]) / h
                    box_area = box_w * box_h

                    # Filtrer les boîtes qui couvrent > 70% de l'image (trop vagues)
                    if box_area < 0.7:
                        detections.append({
                            "class": cls_name,
                            "class_id": CLASS_MAP[cls_name],
                            "box": box,
                        })
                        stats[cls_name] += 1
            except Exception as e:
                pass  # Silencieux pour ne pas polluer la sortie

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
        print(f"✓ {', '.join(found) if found else '(rien)'}")
        success += 1

    print(f"\n{'='*50}")
    print(f"Terminé ! {success}/{len(sample)} images.")
    print(f"Sauvegardé dans : {out_dir.resolve()}")
    print(f"\nDétections par classe :")
    for cls, count in stats.items():
        print(f"  {cls}: {count}")


if __name__ == "__main__":
    main()
