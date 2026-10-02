#!/usr/bin/env python3
"""
FABLE Prototype: DINO (masking) + Hough Transform (geometrical strings).
This script runs on the Dell, loads an image, masks the background, 
and finds strings using Hough Transform to locate the saddle/neck.
"""

import os
import json
import random
import requests
from io import BytesIO
from pathlib import Path

import torch
import numpy as np
import cv2
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt

from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
from transformers import SamModel, SamProcessor

def load_image(url: str, max_size: int = 1024):
    print(f"Téléchargement {url}...")
    resp = requests.get(url, timeout=10)
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    img.thumbnail((max_size, max_size))
    return img

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    
    out_dir = Path("fable_results")
    out_dir.mkdir(exist_ok=True)
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    print("Chargement Grounding DINO...")
    dino_id = "IDEA-Research/grounding-dino-base"
    dino_processor = AutoProcessor.from_pretrained(dino_id)
    dino_model = AutoModelForZeroShotObjectDetection.from_pretrained(dino_id).to(device)

    print("Chargement SAM...")
    sam_id = "facebook/sam-vit-base"
    sam_processor = SamProcessor.from_pretrained(sam_id)
    sam_model = SamModel.from_pretrained(sam_id).to(device)

    manifest = "dataset_a_phase0.jsonl"
    with open(manifest, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    usable_data = [json.loads(line) for line in lines if json.loads(line).get("usable")]
    random.shuffle(usable_data)
    
    for i, data in enumerate(usable_data[:args.limit]):
        print(f"\n--- Traitement {i+1}/{args.limit} ---")
        img = load_image(data["image_url"])
        if img is None:
            continue
            
        w, h = img.size
        print(f"Image size: {w}x{h}")

        # 1. Grounding DINO -> Guitar Bounding Box
        inputs = dino_processor(images=img, text="guitar.", return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = dino_model(**inputs)
        results = dino_processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=0.3, text_threshold=0.3, target_sizes=[(h, w)]
        )[0]

        boxes = results["boxes"].cpu().tolist()
        if not boxes:
            print("Aucune guitare détectée par DINO.")
            continue
        box = max(boxes, key=lambda b: (b[2]-b[0])*(b[3]-b[1]))

        # 2. SAM -> Mask using bounding box prompt
        inputs = sam_processor(img, input_boxes=[[[box]]], return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = sam_model(**inputs)
        
        masks = sam_processor.image_processor.post_process_masks(
            outputs.pred_masks.cpu(), inputs["original_sizes"].cpu(), inputs["reshaped_input_sizes"].cpu()
        )
        mask = masks[0][0][0].numpy()
        
        # 3. Apply mask to remove background
        img_np = np.array(img)
        mask_bool = mask > 0
        clean_img = np.zeros_like(img_np)
        clean_img[mask_bool] = img_np[mask_bool]
        
        # 4. Hough Transform
        gray = cv2.cvtColor(clean_img, cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        gray_clahe = clahe.apply(gray)
        gray = np.where(mask_bool, gray_clahe, 0).astype(np.uint8)

        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi/180, threshold=80, minLineLength=h//4, maxLineGap=20)
        
        # Visualization
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        axes[0].imshow(img)
        axes[0].set_title("Original + DINO")
        rect = plt.Rectangle((box[0], box[1]), box[2]-box[0], box[3]-box[1], fill=False, color="green", linewidth=2)
        axes[0].add_patch(rect)
        axes[1].imshow(clean_img)
        axes[1].set_title("SAM Masked")
        
        line_img = img_np.copy()
        if lines is not None:
            valid_lines = []
            for line in lines:
                x1, y1, x2, y2 = line.flatten()
                length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
                if length > h // 5:
                    valid_lines.append(line.flatten())
                    cv2.line(line_img, (x1, y1), (x2, y2), (255, 0, 0), 2)
            print(f"{len(valid_lines)} lignes conservées.")
        else:
            print("Aucune ligne détectée.")
            
        axes[2].imshow(line_img)
        axes[2].set_title("Hough Lines")
        for ax in axes: ax.axis("off")
        plt.tight_layout()
        out_path = out_dir / f"result_{i}.jpg"
        plt.savefig(out_path)
        plt.close()
        print(f"Sauvegardé: {out_path}")

if __name__ == "__main__":
    main()
