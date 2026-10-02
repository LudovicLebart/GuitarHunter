#!/usr/bin/env python3
"""
Application web d'annotation assistée par SAM (Segment Anything) via Gradio.
À exécuter sur le Dell Linux avec GPU.
"""

import os
import json
import random
import argparse
import requests
from io import BytesIO
from pathlib import Path

import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import gradio as gr
from transformers import SamModel, SamProcessor

# ── Configuration ──────────────────────────────────────────────────
CLASSES = ["neck", "headstock", "heel", "soundhole", "saddle"]
CLASS_MAP = {name: i for i, name in enumerate(CLASSES)}
COLORS = {
    "neck":      (0, 100, 255),
    "headstock": (0, 220, 0),
    "heel":      (255, 0, 0),
    "soundhole": (255, 220, 0),
    "saddle":    (255, 0, 255),
}

class AnnotatorState:
    def __init__(self):
        self.images = []
        self.current_idx = 0
        self.current_image = None
        self.current_boxes = {} # cls_name -> [xmin, ymin, xmax, ymax]
        self.img_w = 0
        self.img_h = 0
        self.out_dir = Path("yolo_sam_dataset")
        self.img_dir = self.out_dir / "images" / "train"
        self.lbl_dir = self.out_dir / "labels" / "train"

state = AnnotatorState()

# ── Modèle SAM ──
print("🔧 Chargement de SAM (facebook/sam-vit-base)...")
device = "cuda" if torch.cuda.is_available() else "cpu"
processor = SamProcessor.from_pretrained("facebook/sam-vit-base")
model = SamModel.from_pretrained("facebook/sam-vit-base").to(device)
print("✅ SAM chargé.")

def load_usable_images(manifest_path: str, limit: int = 300, seed: int = 42):
    deals = {}
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            data = json.loads(line)
            if data.get("usable"):
                did = data.get("deal_id")
                if did not in deals: deals[did] = []
                deals[did].append(data)
    
    results = []
    for did, imgs in deals.items():
        random.shuffle(imgs)
        results.append(imgs[0]) # 1 par deal
    
    random.seed(seed)
    random.shuffle(results)
    return results[:limit]

def get_image_data(idx):
    if idx >= len(state.images):
        return None, None
    data = state.images[idx]
    url = data.get("image_url")
    deal_id = data.get("deal_id")
    img_idx = data.get("image_idx", 0)
    basename = f"{deal_id}_{img_idx}"
    
    # Check if already annotated
    if (state.lbl_dir / f"{basename}.txt").exists():
        # Skip this image automatically
        return "SKIP", None
        
    try:
        resp = requests.get(url, timeout=10)
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img.thumbnail((800, 800))
        return img, basename
    except:
        return "SKIP", None

def load_next_image():
    while state.current_idx < len(state.images):
        img, basename = get_image_data(state.current_idx)
        if img == "SKIP":
            state.current_idx += 1
            continue
        if img is not None:
            state.current_image = img
            state.img_w, state.img_h = img.size
            state.current_boxes = {}
            return img, f"Image {state.current_idx + 1} / {len(state.images)} ({basename})"
        state.current_idx += 1
    return None, "Terminé ! Plus d'images."

def draw_current_state():
    if state.current_image is None: return None
    vis = state.current_image.copy()
    draw = ImageDraw.Draw(vis)
    for cls_name, box in state.current_boxes.items():
        color = COLORS.get(cls_name, (255, 255, 255))
        draw.rectangle(box, outline=color, width=4)
        draw.text((box[0] + 5, box[1] + 5), cls_name, fill=color)
    return vis

def on_click(evt: gr.SelectData, current_class: str):
    if state.current_image is None: return draw_current_state()
    x, y = evt.index
    
    # Inférence SAM
    inputs = processor(state.current_image, input_points=[[[x, y]]], return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    
    masks = processor.image_processor.post_process_masks(
        outputs.pred_masks.cpu(),
        inputs["original_sizes"].cpu(),
        inputs["reshaped_input_sizes"].cpu()
    )
    
    # Prendre le masque le plus confiant (index 0 de la 2e dim)
    mask = masks[0][0][outputs.iou_scores[0][0].argmax()].numpy()
    
    # Trouver la bounding box du masque
    y_indices, x_indices = np.where(mask > 0)
    if len(x_indices) > 0:
        xmin, xmax = int(np.min(x_indices)), int(np.max(x_indices))
        ymin, ymax = int(np.min(y_indices)), int(np.max(y_indices))
        
        # Le manche est souvent fin et long, SAM fait bien le boulot
        state.current_boxes[current_class] = [xmin, ymin, xmax, ymax]
        
    return draw_current_state()

def save_and_next():
    if state.current_image is not None:
        data = state.images[state.current_idx]
        basename = f"{data['deal_id']}_{data.get('image_idx', 0)}"
        
        # Sauvegarde image
        img_path = state.img_dir / f"{basename}.jpg"
        state.current_image.save(img_path)
        
        # Sauvegarde labels YOLO
        with open(state.lbl_dir / f"{basename}.txt", "w") as f:
            for cls_name, box in state.current_boxes.items():
                xmin, ymin, xmax, ymax = box
                w_norm = (xmax - xmin) / state.img_w
                h_norm = (ymax - ymin) / state.img_h
                xc_norm = ((xmin + xmax) / 2.0) / state.img_w
                yc_norm = ((ymin + ymax) / 2.0) / state.img_h
                f.write(f"{CLASS_MAP[cls_name]} {xc_norm:.5f} {yc_norm:.5f} {w_norm:.5f} {h_norm:.5f}\n")
    
    state.current_idx += 1
    img, info = load_next_image()
    if img is not None:
        return img, info
    else:
        # Image blanche de fin
        return Image.new("RGB", (400, 300), (255, 255, 255)), info

def skip():
    state.current_idx += 1
    img, info = load_next_image()
    if img is not None:
        return img, info
    else:
        return Image.new("RGB", (400, 300), (255, 255, 255)), info

def undo(current_class):
    if current_class in state.current_boxes:
        del state.current_boxes[current_class]
    return draw_current_state()

def build_app(manifest_path="dataset_a_phase0.jsonl", limit=300):
    state.img_dir.mkdir(parents=True, exist_ok=True)
    state.lbl_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup dataset.yaml
    with open(state.out_dir / "dataset.yaml", "w") as f:
        f.write(f"path: {state.out_dir.resolve()}\n")
        f.write("train: images/train\nval: images/train\n")
        f.write(f"nc: {len(CLASSES)}\nnames: {json.dumps(CLASSES)}\n")
        
    state.images = load_usable_images(manifest_path, limit=limit)
    print(f"Dataset de {len(state.images)} images chargé.")
    
    with gr.Blocks(title="SAM Guitar Annotator") as demo:
        gr.Markdown("## Annotation Assistée par SAM (Segment Anything)")
        gr.Markdown("1. Choisis la classe. 2. Clique sur l'objet. 3. SAM génère la boîte.")
        
        with gr.Row():
            with gr.Column(scale=3):
                img_comp = gr.Image(type="pil", interactive=False)
            with gr.Column(scale=1):
                info_txt = gr.Textbox(label="Statut", interactive=False)
                class_radio = gr.Radio(choices=CLASSES, value="neck", label="Classe actuelle")
                btn_undo = gr.Button("Annuler cette classe (Undo)")
                gr.Markdown("---")
                btn_save = gr.Button("✅ Sauvegarder & Suivant", variant="primary")
                btn_skip = gr.Button("⏭ Passer l'image (Skip)")

        # Events
        img_comp.select(on_click, inputs=[class_radio], outputs=[img_comp])
        btn_save.click(save_and_next, outputs=[img_comp, info_txt])
        btn_skip.click(skip, outputs=[img_comp, info_txt])
        btn_undo.click(undo, inputs=[class_radio], outputs=[img_comp])
        
        # Load first image on startup
        demo.load(lambda: load_next_image(), outputs=[img_comp, info_txt])
        
    return demo

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()
    
    app = build_app(limit=args.limit)
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
