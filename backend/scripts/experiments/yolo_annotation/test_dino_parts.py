import os
import json
import random
import requests
from io import BytesIO
from pathlib import Path
import torch
from PIL import Image, ImageDraw, ImageFont
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

def load_image(url: str, max_size: int = 1024):
    resp = requests.get(url, timeout=10)
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    img.thumbnail((max_size, max_size))
    return img

def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    print("Chargement Grounding DINO...")
    dino_id = "IDEA-Research/grounding-dino-base"
    processor = AutoProcessor.from_pretrained(dino_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(dino_id).to(device)

    manifest = "dataset_a_phase0.jsonl"
    with open(manifest, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    usable_data = [json.loads(line) for line in lines if json.loads(line).get("usable")]
    random.shuffle(usable_data)
    
    out_dir = Path("dino_parts_results")
    out_dir.mkdir(exist_ok=True)
    
    # We want to find these specific parts
    text_prompt = "guitar bridge . guitar sound hole . guitar headstock . guitar neck ."
    
    for i, data in enumerate(usable_data[:30]):
        img = load_image(data["image_url"])
        if img is None: continue
        w, h = img.size
        
        inputs = processor(images=img, text=text_prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
            
        results = processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=0.15, text_threshold=0.15, target_sizes=[(h, w)]
        )[0]
        
        vis = img.copy()
        draw = ImageDraw.Draw(vis)
        
        boxes = results["boxes"].cpu().tolist()
        scores = results["scores"].cpu().tolist()
        labels = results["labels"]
        
        for box, score, label in zip(boxes, scores, labels):
            draw.rectangle(box, outline="red", width=3)
            draw.text((box[0], box[1]-10), f"{label} {score:.2f}", fill="red")
            
        vis.save(out_dir / f"result_{i}.jpg")
        print(f"[{i+1}/30] Trouvé {len(boxes)} objets.")

if __name__ == "__main__":
    main()
