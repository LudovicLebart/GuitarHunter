import os
import json
import cv2
import numpy as np
import torch
from pathlib import Path
import requests
from io import BytesIO
from PIL import Image, ImageDraw

try:
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
    import sys
except ImportError:
    pass

def load_image(url: str, max_size: int = 1024):
    resp = requests.get(url, timeout=10)
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    img.thumbnail((max_size, max_size))
    return img

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="dataset_a_frontal.jsonl")
    parser.add_argument("--output_dir", default="yolo_dataset")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    
    out_dir = Path(args.output_dir)
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    dino_id = "IDEA-Research/grounding-dino-base"
    dino_processor = AutoProcessor.from_pretrained(dino_id)
    dino_model = AutoModelForZeroShotObjectDetection.from_pretrained(dino_id).to(device)

    records = []
    if os.path.exists(args.manifest):
        with open(args.manifest, "r", encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
    else:
        print(f"Waiting for {args.manifest} to be generated...")
        return
        
    if args.limit:
        records = records[:args.limit]
        
    print(f"Found {len(records)} perfect frontal images.")
    
    # YOLO Classes: 0: saddle, 1: headstock, 2: neck
    
    for i, data in enumerate(records):
        img_url = data["image_url"]
        print(f"\nProcessing {i+1}/{len(records)}: {img_url}")
        
        try:
            pil_img = load_image(img_url)
            img_np = np.array(pil_img)
            h, w = img_np.shape[:2]
        except Exception as e:
            print(f"Failed to load image: {e}")
            continue
            
        inputs = dino_processor(images=pil_img, text="guitar .", return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = dino_model(**inputs)
        results = dino_processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=0.15, text_threshold=0.15, target_sizes=[(h, w)]
        )[0]
        
        if len(results["boxes"]) == 0:
            print("No guitar found by DINO.")
            continue
            
        boxes = results["boxes"].cpu().numpy()
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        best_box = boxes[np.argmax(areas)]
        
        # Instead of just cropping, use SAM to mask the guitar exactly!
        x1, y1, x2, y2 = map(int, best_box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        try:
            from segment_anything import sam_model_registry, SamPredictor
            sam_checkpoint = str(Path.home() / "weights" / "sam_vit_h_4b8939.pth")
            sam = sam_model_registry["vit_h"](checkpoint=sam_checkpoint)
            sam.to(device=device)
            sam_predictor = SamPredictor(sam)
            
            sam_predictor.set_image(img_np)
            input_box = np.array([x1, y1, x2, y2])
            masks, _, _ = sam_predictor.predict(
                point_coords=None,
                point_labels=None,
                box=input_box[None, :],
                multimask_output=False,
            )
            mask = masks[0]
            masked_img = np.zeros_like(img_np)
            masked_img[mask] = img_np[mask]
        except Exception as e:
            print(f"SAM failed: {e}. Falling back to crop.")
            masked_img = np.zeros_like(img_np)
            masked_img[y1:y2, x1:x2] = img_np[y1:y2, x1:x2]
        
        
        gray = cv2.cvtColor(masked_img, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=150, maxLineGap=20)
        
        if lines is None or len(lines) == 0:
            print("No lines found.")
            continue
            
        lines = lines.reshape(-1, 4)
        good_lines = []
        for x1, y1, x2, y2 in lines:
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            if 80 < angle < 100: # vertical
                good_lines.append((x1, y1, x2, y2))
                
        if len(good_lines) < 2:
            print("Not enough string lines.")
            continue
            
        min_x = min([x1 for x1, _, _, _ in good_lines] + [x2 for _, _, x2, _ in good_lines])
        max_x = max([x1 for x1, _, _, _ in good_lines] + [x2 for _, _, x2, _ in good_lines])
        min_y = min([y1 for _, y1, _, _ in good_lines] + [y2 for _, _, _, y2 in good_lines])
        max_y = max([y1 for _, y1, _, _ in good_lines] + [y2 for _, _, _, y2 in good_lines])
        
        # Geometrical boxes
        hs_y1, hs_y2 = max(0, min_y - 100), min_y + 20
        hs_x1, hs_x2 = max(0, min_x - 50), min(w, max_x + 50)
        
        sd_y1, sd_y2 = max_y - 20, min(h, max_y + 40)
        sd_x1, sd_x2 = max(0, min_x - 40), min(w, max_x + 40)
        
        nk_y1, nk_y2 = min_y + 20, max_y - 150
        nk_x1, nk_x2 = max(0, min_x - 20), min(w, max_x + 20)
        
        img_id = f"img_{i:04d}"
        
        # Save raw image
        pil_img.save(images_dir / f"{img_id}.jpg")
        
        # Draw preview
        draw = ImageDraw.Draw(pil_img)
        draw.rectangle([sd_x1, sd_y1, sd_x2, sd_y2], outline="red", width=4)
        draw.text((sd_x1, max(0, sd_y1-15)), "saddle", fill="red")
        
        draw.rectangle([hs_x1, hs_y1, hs_x2, hs_y2], outline="green", width=4)
        draw.text((hs_x1, max(0, hs_y1-15)), "headstock", fill="green")
        
        draw.rectangle([nk_x1, nk_y1, nk_x2, nk_y2], outline="blue", width=4)
        draw.text((nk_x1, max(0, nk_y1-15)), "neck", fill="blue")
        
        preview_dir = out_dir / "previews"
        preview_dir.mkdir(exist_ok=True)
        pil_img.save(preview_dir / f"{img_id}_preview.jpg")
        
        with open(labels_dir / f"{img_id}.txt", "w") as f:
            def write_yolo(cls_id, x1, y1, x2, y2):
                if x2 <= x1 or y2 <= y1: return
                xc = ((x1 + x2) / 2) / w
                yc = ((y1 + y2) / 2) / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h
                f.write(f"{cls_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")
                
            write_yolo(0, sd_x1, sd_y1, sd_x2, sd_y2) # saddle
            write_yolo(1, hs_x1, hs_y1, hs_x2, hs_y2) # headstock
            write_yolo(2, nk_x1, nk_y1, nk_x2, nk_y2) # neck
            
        print(f"Saved YOLO labels and preview for {img_id}")

if __name__ == "__main__":
    main()
