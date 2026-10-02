import os
import json
import random
import time
import requests
import argparse
from io import BytesIO
from PIL import Image

import google.generativeai as genai
from config import GEMINI_API_KEY

CLASSES = ["neck", "headstock", "heel", "soundhole", "saddle"]
CLASS_MAP = {name: i for i, name in enumerate(CLASSES)}

SYSTEM_PROMPT = """Tu es un expert en vision par ordinateur spécialisé dans les guitares.
Ta tâche est de trouver les boîtes englobantes des 5 parties suivantes d'une guitare, SI ELLES SONT VISIBLES sur la photo :
- neck (le manche, de la base de la tête jusqu'à la jonction avec le corps)
- headstock (la tête, où se trouvent les mécaniques)
- heel (le talon, la jonction à l'arrière entre le manche et la caisse)
- soundhole (la rosace, le trou au milieu de la caisse)
- saddle (le sillet de chevalet, où reposent les cordes sur le corps de la guitare)

Retourne UNIQUEMENT un tableau JSON. Chaque objet du tableau doit avoir le format suivant :
{"box_2d": [ymin, xmin, ymax, xmax], "label": "nom_de_la_classe"}

Les coordonnées doivent être des entiers entre 0 et 1000 représentant les proportions x1000 (ex: 500 = milieu de l'image).
Si une partie n'est pas visible ou est trop tronquée, ne l'inclus pas dans le JSON.
N'ajoute aucun texte avant ou après le JSON.
"""

def load_usable_images(manifest_path, max_per_deal=1):
    deals = {}
    if not os.path.exists(manifest_path):
        print(f"Erreur : le fichier {manifest_path} n'existe pas.")
        return []
        
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
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

def convert_to_yolo(ymin, xmin, ymax, xmax):
    # Gemini returns coords in [0, 1000]
    # YOLO format: x_center, y_center, width, height in [0, 1]
    ymin_norm = max(0.0, min(1.0, ymin / 1000.0))
    xmin_norm = max(0.0, min(1.0, xmin / 1000.0))
    ymax_norm = max(0.0, min(1.0, ymax / 1000.0))
    xmax_norm = max(0.0, min(1.0, xmax / 1000.0))
    
    width = xmax_norm - xmin_norm
    height = ymax_norm - ymin_norm
    x_center = xmin_norm + width / 2.0
    y_center = ymin_norm + height / 2.0
    
    return round(x_center, 5), round(y_center, 5), round(width, 5), round(height, 5)

def main():
    parser = argparse.ArgumentParser(description="Auto-annotation YOLO via Gemini")
    parser.add_argument("--limit", type=int, default=5, help="Nombre d'images à annoter")
    args = parser.parse_args()
    
    if not GEMINI_API_KEY:
        print("Erreur: GEMINI_API_KEY introuvable.")
        return
        
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Check if 2.5-pro exists, else fallback to 1.5-pro
    model_name = "gemini-1.5-pro"
    for m in genai.list_models():
        if "2.5-pro" in m.name:
            model_name = "gemini-2.5-pro"
            break
            
    print(f"Utilisation du modèle : {model_name}")
    model = genai.GenerativeModel(model_name, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
    
    # Load dataset
    images_list = load_usable_images("dataset_a_phase0.jsonl")
    print(f"Trouvé {len(images_list)} annonces uniques avec au moins une image 'usable'.")
    
    random.seed(42)
    random.shuffle(images_list)
    sample = images_list[:args.limit]
    
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data", "yolo_dataset")
    img_dir = os.path.join(base_dir, "images", "train")
    lbl_dir = os.path.join(base_dir, "labels", "train")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)
    
    # Write dataset.yaml
    with open(os.path.join(base_dir, "dataset.yaml"), "w", encoding="utf-8") as f:
        f.write("path: ../data/yolo_dataset\n")
        f.write("train: images/train\n")
        f.write("val: images/train\n")
        f.write(f"nc: {len(CLASSES)}\n")
        f.write(f"names: {json.dumps(CLASSES)}\n")
        
    success_count = 0
    for idx, data in enumerate(sample):
        url = data.get("image_url")
        deal_id = data.get("deal_id")
        img_idx = data.get("image_idx")
        basename = f"{deal_id}_{img_idx}"
        
        print(f"[{idx+1}/{len(sample)}] Traitement de {basename}...")
        
        try:
            resp = requests.get(url, timeout=10)
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            
            # Redimensionner pour économiser l'API si l'image est énorme, tout en gardant une bonne résolution
            img.thumbnail((1024, 1024))
            
            # Appel Gemini
            response = model.generate_content(img)
            
            # Nettoyer et parser JSON
            text = response.text
            if text.startswith("```json"):
                text = text.replace("```json", "").replace("```", "").strip()
            boxes = json.loads(text)
            
            if not isinstance(boxes, list):
                print(f"  Avertissement: Gemini n'a pas renvoyé un tableau pour {basename}")
                continue
                
            # Sauvegarder image
            img_path = os.path.join(img_dir, f"{basename}.jpg")
            img.save(img_path)
            
            # Sauvegarder labels
            lbl_path = os.path.join(lbl_dir, f"{basename}.txt")
            with open(lbl_path, "w", encoding="utf-8") as f:
                for b in boxes:
                    label = b.get("label")
                    box_2d = b.get("box_2d")
                    if label in CLASS_MAP and box_2d and len(box_2d) == 4:
                        class_id = CLASS_MAP[label]
                        ymin, xmin, ymax, xmax = box_2d
                        x_c, y_c, w, h = convert_to_yolo(ymin, xmin, ymax, xmax)
                        f.write(f"{class_id} {x_c} {y_c} {w} {h}\n")
                        print(f"  Trouvé : {label}")
                        
            success_count += 1
            
        except Exception as e:
            print(f"  Erreur sur {basename}: {e}")
            
        time.sleep(2) # Rate limit simple
        
    print(f"\nTerminé ! {success_count}/{args.limit} annotées et sauvegardées dans {base_dir}")

if __name__ == "__main__":
    main()
