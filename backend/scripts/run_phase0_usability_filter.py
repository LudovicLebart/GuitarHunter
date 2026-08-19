"""
Phase 0 du plan (docs/management/plans/NECK_RESET_VISION_PLAN.md §2/§7) — filtre d'utilisabilité
à l'échelle du Dataset A : pour chaque annonce, détecte si la première photo du carrousel montre
bien une guitare (OWLv2-base, validé sur un échantillon de 8 photos §7 étape 4 — 8/8, VRAM 10%)
et enregistre sa résolution.

Volontairement limité à **la première photo par annonce** (comme l'échantillon manuel §3sexies),
pas les 5974 photos du Dataset A complet — reste comparable au taux mesuré à la main (51%/70% sur
47 annonces) et suffisant pour une première mesure à l'échelle. Élargir à plus de photos par
annonce est un choix a posteriori, pas fait ici.

Ne couvre PAS (§6, pistes non conçues) : détection des photos générées par IA, estimation de
l'angle de prise de vue (frontal vs 3/4). Le score de présence "guitare" est le seul critère
d'utilisabilité mesuré par ce script.

Entrée : backend/scripts/data/dataset_a_manifest.jsonl (versionné dans le dépôt — export figé du
2026-08-19, §3septies, pas régénéré automatiquement).
Sortie : dataset_a_phase0.jsonl (une ligne par annonce : deal_id, classification, résolution,
score de détection, nombre de boîtes, usable).

Usage (sur le Dell, venv avec torch/transformers/pillow/requests installés) :
  python3 backend/scripts/run_phase0_usability_filter.py
  python3 backend/scripts/run_phase0_usability_filter.py --limit 50   # test rapide
"""

import argparse
import json
import os
import time
from io import BytesIO

import requests
import torch
from PIL import Image
from transformers import Owlv2ForObjectDetection, Owlv2Processor

MODEL_ID = "google/owlv2-base-patch16-ensemble"
TEXT_QUERIES = ["a photo of a guitar"]
USABLE_SCORE_THRESHOLD = 0.3

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "data", "dataset_a_manifest.jsonl")


def load_manifest(path, limit=None):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    return records[:limit] if limit else records


def main():
    parser = argparse.ArgumentParser(description="Filtre d'utilisabilité Phase 0 à l'échelle du Dataset A.")
    parser.add_argument("--manifest", default=MANIFEST_PATH, help="Chemin du manifeste Dataset A d'entrée.")
    parser.add_argument("--output", default="dataset_a_phase0.jsonl", help="Chemin de sortie.")
    parser.add_argument("--limit", type=int, default=None, help="Limiter à N annonces (test rapide).")
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

    records = load_manifest(args.manifest, args.limit)
    print(f"\n--- {len(records)} annonce(s) à traiter (manifeste : {args.manifest}) ---")

    results = []
    t_start = time.time()
    for i, record in enumerate(records):
        deal_id = record["deal_id"]
        classification = record.get("classification", "N/A")
        url = record["image_urls"][0]

        entry = {"deal_id": deal_id, "classification": classification, "image_url": url}
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            image = Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            entry.update({"error": f"download_failed: {e}", "usable": False})
            results.append(entry)
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
            results.append(entry)
            continue

        n_boxes = len(detections["scores"])
        best_score = float(detections["scores"].max()) if n_boxes else 0.0
        entry.update({
            "width": image.width,
            "height": image.height,
            "n_boxes": n_boxes,
            "best_score": round(best_score, 4),
            "usable": best_score >= args.threshold,
        })
        results.append(entry)

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed
            eta = (len(records) - i - 1) / rate if rate > 0 else 0
            print(f"  {i + 1}/{len(records)} traitées ({elapsed:.0f}s écoulées, ETA {eta:.0f}s)")

    with open(args.output, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_usable = sum(1 for r in results if r.get("usable"))
    n_errors = sum(1 for r in results if "error" in r)
    print(f"\n--- Résumé ---")
    print(f"{len(results)} annonce(s) traitée(s) → {args.output}")
    print(f"Usable (score >= {args.threshold}) : {n_usable}/{len(results)} ({100 * n_usable / len(results):.1f}%)")
    print(f"Erreurs (téléchargement/inférence) : {n_errors}/{len(results)}")

    if device == "cuda":
        peak_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)
        total_mb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        print(f"VRAM pic utilisée : {peak_mb:.0f} Mo / {total_mb:.0f} Mo disponibles ({100 * peak_mb / total_mb:.1f}%)")


if __name__ == "__main__":
    main()
