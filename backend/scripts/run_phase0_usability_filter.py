"""
Phase 0 du plan (docs/management/plans/NECK_RESET_VISION_PLAN.md §2/§7) — filtre d'utilisabilité :
pour chaque photo (toutes les image_urls de chaque annonce, pas seulement la première), détecte
si elle montre bien une guitare (OWLv2-base, validé sur un échantillon de 8 photos §7 étape 4 —
8/8, VRAM 10%) et évalue sa "mesurabilité" (pas juste sa présence) via 3 critères indépendants :
  - `usable` : score de détection "guitar" >= seuil (présence).
  - `low_resolution` : résolution min(largeur,hauteur) sous un seuil — reprend le mode de
    défaillance "vignette basse résolution, pas de photo HD stockée" identifié à la main (§3sexies,
    ex. 261×261px).
  - `cropped_suspect` : la boîte de détection touche un bord de l'image — proxy pour un cadrage
    incomplet (tête ou chevalet hors cadre), un des modes de défaillance identifiés §3sexies. Un
    proxy, pas une vérité terrain : une vraie guitare bien cadrée peut aussi toucher un bord par
    coïncidence, à valider empiriquement plutôt qu'à prendre pour acquis.
`measurable` = ET des trois. Ne couvre toujours PAS (§6, pistes non conçues) : détection des
photos générées par IA, estimation de l'angle de prise de vue (frontal vs 3/4).

Tester la fiabilité des algos de détection ne nécessite pas tout le Dataset A (5974 photos) — le
taux ne bouge pas significativement avec le volume une fois qu'on a un échantillon statistiquement
représentatif ; un run complet sert plutôt à produire un corpus de production (choisir les
meilleures photos par annonce pour la suite), pas à valider la fiabilité elle-même. Usage normal :
`--limit N` avec un tirage aléatoire (`--seed`) sur les ANNONCES pour rester diversifié plutôt que
biaisé vers le début du manifeste (ordre d'export non randomisé) — voir §7/§8 du plan pour le
contexte de cette décision (2026-08-20).

Entrée : backend/scripts/data/dataset_a_manifest.jsonl (versionné dans le dépôt — export figé du
2026-08-19, §3septies, pas régénéré automatiquement).
Sortie : dataset_a_phase0.jsonl (une ligne par PHOTO, pas par annonce — champ `image_idx` pour
distinguer les photos d'une même annonce ; deal_id, classification, résolution, bbox/score de la
détection, usable/low_resolution/cropped_suspect/measurable), écrite au fil de l'eau (une ligne
par photo traitée, pas seulement à la fin) pour ne rien perdre en cas d'interruption/timeout.

Usage (sur le Dell, venv avec torch/transformers/pillow/requests installés) :
  python3 -u backend/scripts/run_phase0_usability_filter.py --limit 50 --seed 42   # échantillon test
  python3 -u backend/scripts/run_phase0_usability_filter.py                        # tout le Dataset A
"""

import argparse
import json
import os
import random
import time
from io import BytesIO

import requests
import torch
from PIL import Image
from transformers import Owlv2ForObjectDetection, Owlv2Processor

MODEL_ID = "google/owlv2-base-patch16-ensemble"
TEXT_QUERIES = ["a photo of a guitar"]
USABLE_SCORE_THRESHOLD = 0.3
MIN_RESOLUTION_PX = 400  # sous ce seuil (min largeur/hauteur) : mode "vignette basse résolution" (§3sexies)
EDGE_MARGIN_FRAC = 0.02  # boîte à moins de 2% d'un bord = cadrage suspect

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "data", "dataset_a_manifest.jsonl")


def load_manifest(path, limit=None, seed=None):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    if limit and limit < len(records):
        return random.Random(seed).sample(records, limit)
    return records


def main():
    parser = argparse.ArgumentParser(description="Filtre d'utilisabilité Phase 0 sur le Dataset A (toutes les photos, ou un échantillon avec --limit).")
    parser.add_argument("--manifest", default=MANIFEST_PATH, help="Chemin du manifeste Dataset A d'entrée.")
    parser.add_argument("--output", default="dataset_a_phase0.jsonl", help="Chemin de sortie.")
    parser.add_argument("--limit", type=int, default=None, help="Limiter à N annonces, tirées aléatoirement (test rapide/diversifié, cf. docstring).")
    parser.add_argument("--seed", type=int, default=42, help="Graine du tirage aléatoire pour --limit (reproductible par défaut).")
    parser.add_argument("--threshold", type=float, default=USABLE_SCORE_THRESHOLD, help="Seuil de score pour usable=true.")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("--- Environnement ---")
    print(f"torch {torch.__version__}, CUDA disponible : {torch.cuda.is_available()}")
    if device == "cuda":
        print(f"GPU : {torch.cuda.get_device_name(0)}")
        torch.cuda.reset_peak_memory_stats()

    print(f"\n--- Chargement du modèle {MODEL_ID} ---")
    t0 = time.time()
    processor = Owlv2Processor.from_pretrained(MODEL_ID)
    model = Owlv2ForObjectDetection.from_pretrained(MODEL_ID).to(device)
    model.eval()
    print(f"Modèle chargé en {time.time() - t0:.1f}s")

    records = load_manifest(args.manifest, args.limit, args.seed)
    n_listings = len(records)
    total_images = sum(len(r.get("image_urls", [])) for r in records)
    print(f"\n--- {n_listings} annonce(s) à traiter ({total_images} photo(s), manifeste : {args.manifest}) ---")

    n_usable = n_low_res = n_cropped = n_measurable = n_errors = 0
    t_start = time.time()
    img_count = 0

    with open(args.output, "w", encoding="utf-8") as out_f:
        for record in records:
            deal_id = record["deal_id"]
            classification = record.get("classification", "N/A")

            for img_idx, url in enumerate(record.get("image_urls", [])):
                img_count += 1
                entry = {"deal_id": deal_id, "image_idx": img_idx, "classification": classification, "image_url": url}
                try:
                    resp = requests.get(url, timeout=15)
                    resp.raise_for_status()
                    image = Image.open(BytesIO(resp.content)).convert("RGB")
                except Exception as e:
                    entry.update({"error": f"download_failed: {e}", "usable": False})
                    n_errors += 1
                    out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    out_f.flush()
                    continue

                try:
                    inputs = processor(text=[TEXT_QUERIES], images=image, return_tensors="pt").to(device)
                    with torch.no_grad():
                        outputs = model(**inputs)
                    target_sizes = torch.tensor([(image.height, image.width)])
                    detections = processor.post_process_grounded_object_detection(
                        outputs=outputs, target_sizes=target_sizes, threshold=0.1
                    )[0]
                except Exception as e:
                    entry.update({"error": f"inference_failed: {e}", "usable": False})
                    n_errors += 1
                    out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    out_f.flush()
                    continue

                n_boxes = len(detections["scores"])
                best_score = 0.0
                best_box = None
                if n_boxes:
                    best_idx = int(detections["scores"].argmax())
                    best_score = float(detections["scores"][best_idx])
                    best_box = [round(float(v), 1) for v in detections["boxes"][best_idx].tolist()]  # [x1,y1,x2,y2]

                usable = best_score >= args.threshold
                low_resolution = min(image.width, image.height) < MIN_RESOLUTION_PX
                cropped_suspect = False
                if best_box:
                    x1, y1, x2, y2 = best_box
                    mx, my = image.width * EDGE_MARGIN_FRAC, image.height * EDGE_MARGIN_FRAC
                    cropped_suspect = x1 <= mx or y1 <= my or x2 >= image.width - mx or y2 >= image.height - my
                measurable = usable and not low_resolution and not cropped_suspect

                n_usable += usable
                n_low_res += low_resolution
                n_cropped += cropped_suspect
                n_measurable += measurable

                entry.update({
                    "width": image.width,
                    "height": image.height,
                    "n_boxes": n_boxes,
                    "best_score": round(best_score, 4),
                    "best_box": best_box,
                    "usable": usable,
                    "low_resolution": low_resolution,
                    "cropped_suspect": cropped_suspect,
                    "measurable": measurable,
                })
                out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                out_f.flush()

                if img_count % 100 == 0:
                    elapsed = time.time() - t_start
                    rate = img_count / elapsed
                    eta = (total_images - img_count) / rate if rate > 0 else 0
                    print(f"  {img_count}/{total_images} photo(s) traitée(s) ({elapsed:.0f}s écoulées, ETA {eta:.0f}s)", flush=True)

    print(f"\n--- Résumé ---")
    print(f"{img_count} photo(s) traitée(s) sur {n_listings} annonce(s) → {args.output}")
    print(f"Usable (score >= {args.threshold}) : {n_usable}/{img_count} ({100 * n_usable / img_count:.1f}%)")
    print(f"Basse résolution (< {MIN_RESOLUTION_PX}px) : {n_low_res}/{img_count} ({100 * n_low_res / img_count:.1f}%)")
    print(f"Cadrage suspect (boîte touchant un bord) : {n_cropped}/{img_count} ({100 * n_cropped / img_count:.1f}%)")
    print(f"Measurable (usable ET pas basse résolution ET pas cadrage suspect) : {n_measurable}/{img_count} ({100 * n_measurable / img_count:.1f}%)")
    print(f"Erreurs (téléchargement/inférence) : {n_errors}/{img_count}")

    if device == "cuda":
        peak_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)
        total_mb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        print(f"VRAM pic utilisée : {peak_mb:.0f} Mo / {total_mb:.0f} Mo disponibles ({100 * peak_mb / total_mb:.1f}%)")


if __name__ == "__main__":
    main()
