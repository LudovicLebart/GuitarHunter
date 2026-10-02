#!/usr/bin/env python3
"""
Application web d'annotation rapide "2 Clics" via Gradio.
À exécuter sur le Dell Linux (ou n'importe où).
"""

import os
import json
import random
import argparse
import requests
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import gradio as gr

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
        self.first_point = None # Pour le mode 2 clics
        self.img_w = 0
        self.img_h = 0
        self.out_dir = Path("yolo_dataset_phase0")
        self.img_dir = self.out_dir / "images" / "train"
        self.lbl_dir = self.out_dir / "labels" / "train"

state = AnnotatorState()

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
    
    if (state.lbl_dir / f"{basename}.txt").exists():
        return "SKIP", None
        
    try:
        resp = requests.get(url, timeout=10)
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img.thumbnail((1024, 1024))
        return img, basename
    except:
        return "SKIP", None

def load_next_image():
    state.first_point = None
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
    
    # Dessiner les boîtes
    for cls_name, box in state.current_boxes.items():
        color = COLORS.get(cls_name, (255, 255, 255))
        draw.rectangle(box, outline=color, width=4)
        draw.text((box[0] + 5, box[1] + 5), cls_name, fill=color)
        
    # Dessiner le premier point si en attente du 2eme
    if state.first_point is not None:
        x, y = state.first_point
        r = 5
        draw.ellipse([x-r, y-r, x+r, y+r], fill=(255, 0, 0))
        
    return vis

def on_click(evt: gr.SelectData, current_class: str):
    if state.current_image is None: return draw_current_state(), "Terminé"
    
    x, y = evt.index
    
    if state.first_point is None:
        # Premier clic : on enregistre le point
        state.first_point = (x, y)
        status = f"Point 1 (Haut-Gauche) de '{current_class}' posé. Clique sur le Bas-Droit."
    else:
        # Deuxième clic : on trace la boîte
        x1, y1 = state.first_point
        x2, y2 = x, y
        xmin, xmax = min(x1, x2), max(x1, x2)
        ymin, ymax = min(y1, y2), max(y1, y2)
        
        # Ignorer les clics accidentels (boîte trop petite)
        if (xmax - xmin) > 5 and (ymax - ymin) > 5:
            state.current_boxes[current_class] = [xmin, ymin, xmax, ymax]
            status = f"Boîte '{current_class}' enregistrée !"
        else:
            status = "Boîte trop petite, annulée."
            
        state.first_point = None
        
    return draw_current_state(), status

def save_and_next():
    if state.current_image is not None:
        data = state.images[state.current_idx]
        basename = f"{data['deal_id']}_{data.get('image_idx', 0)}"
        
        # Ne sauvegarder que s'il y a au moins 1 boîte
        if len(state.current_boxes) > 0:
            img_path = state.img_dir / f"{basename}.jpg"
            state.current_image.save(img_path)
            
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
        return img, info, "Image suivante."
    else:
        return Image.new("RGB", (400, 300), (255, 255, 255)), info, "Fini."

def skip():
    state.current_idx += 1
    img, info = load_next_image()
    if img is not None:
        return img, info, "Image passée."
    else:
        return Image.new("RGB", (400, 300), (255, 255, 255)), info, "Fini."

def undo(current_class):
    state.first_point = None # Annule aussi un point en cours
    if current_class in state.current_boxes:
        del state.current_boxes[current_class]
    return draw_current_state(), f"Boîte '{current_class}' supprimée."

def build_app(manifest_path="dataset_a_phase0.jsonl", limit=300):
    state.img_dir.mkdir(parents=True, exist_ok=True)
    state.lbl_dir.mkdir(parents=True, exist_ok=True)
    
    with open(state.out_dir / "dataset.yaml", "w") as f:
        f.write(f"path: {state.out_dir.resolve()}\n")
        f.write("train: images/train\nval: images/train\n")
        f.write(f"nc: {len(CLASSES)}\nnames: {json.dumps(CLASSES)}\n")
        
    state.images = load_usable_images(manifest_path, limit=limit)
    print(f"Dataset de {len(state.images)} images chargé.")
    
    with gr.Blocks(title="Fast Guitar Annotator") as demo:
        gr.Markdown("## Annotation Rapide (Mode 2 Clics)")
        gr.Markdown("**Mode d'emploi :** 1. Choisis la classe ➔ 2. Clique sur le bord Haut-Gauche ➔ 3. Clique sur le bord Bas-Droit.")
        
        with gr.Row():
            with gr.Column(scale=3):
                img_comp = gr.Image(type="pil", interactive=False)
            with gr.Column(scale=1):
                info_txt = gr.Textbox(label="Image Actuelle", interactive=False)
                status_txt = gr.Textbox(label="Action", interactive=False)
                
                class_radio = gr.Radio(choices=CLASSES, value="neck", label="Classe à annoter")
                btn_undo = gr.Button("🗑️ Recommencer cette classe")
                
                gr.Markdown("---")
                btn_save = gr.Button("✅ Sauvegarder & Suivant", variant="primary")
                btn_skip = gr.Button("⏭ Passer l'image (Skip)")

        # Events
        img_comp.select(on_click, inputs=[class_radio], outputs=[img_comp, status_txt])
        btn_save.click(save_and_next, outputs=[img_comp, info_txt, status_txt])
        btn_skip.click(skip, outputs=[img_comp, info_txt, status_txt])
        btn_undo.click(undo, inputs=[class_radio], outputs=[img_comp, status_txt])
        
        # Changer de classe annule le clic en cours
        class_radio.change(lambda: (state.__setattr__('first_point', None), draw_current_state())[1], outputs=[img_comp])
        
        demo.load(lambda: load_next_image() + ("Prêt.",), outputs=[img_comp, info_txt, status_txt])
        
    return demo

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()
    
    app = build_app(limit=args.limit)
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
