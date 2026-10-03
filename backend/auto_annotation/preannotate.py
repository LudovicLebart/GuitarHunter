"""Pré-annotation Label Studio : un modèle YOLO-OBB propose des boîtes, l'utilisateur les corrige.

Boucle prévue (PARTS_DETECTOR_AND_CROPS_PLAN.md) :
  1. annoter ~30-40 images à la main ; 2. `labelstudio_export export` ; 3. `train_phase0` (sur le Dell, hors heures de
  scan) ; 4. `preannotate` sur les images restantes ; 5. corriger dans Label Studio ; répéter à ~80 images.

Commandes (le modèle `weights` vient de `train_phase0`) :
  python -m backend.auto_annotation.preannotate weights.pt --out predictions.json
  python -m backend.auto_annotation.preannotate weights.pt --post          # envoie à Label Studio (localhost:8080)

`--post` utilise l'API `POST /api/predictions` avec un jeton (variable `LABEL_STUDIO_TOKEN`, Account Settings >
Access Token). Non testé contre un Label Studio réel au moment de l'écriture : en cas d'échec, `predictions.json` reste
exploitable (format « tâches avec prédictions » de l'import Label Studio ; attention, réimporter des tâches existantes
les duplique — préférer l'API).

La conversion de géométrie (4 coins → rectangle pivoté Label Studio) est pure et testée ; ultralytics n'est importé
qu'au moment de la prédiction.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

from .config import CLASS_NAMES
from .labelstudio_export import (DEFAULT_IMAGES, DEFAULT_PROJECT_TITLE, DEFAULT_SQLITE, load_annotations_sqlite)

DEFAULT_CONF = 0.25
DEFAULT_LS_URL = "http://localhost:8080"


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def corners_to_ls_rect(corners_px):
    """4 coins en pixels (dans l'ordre autour du rectangle) → (x, y, largeur, hauteur, rotation°) en PIXELS,
    selon la convention Label Studio : (x, y) = coin haut-gauche avant rotation = pivot ; rotation en degrés, sens
    horaire (axe y vers le bas). Parmi les 4 coins possibles comme origine, on prend celui qui donne la plus petite
    rotation, pour des boîtes lisibles et faciles à corriger."""
    pts = [tuple(map(float, p)) for p in corners_px]
    if len(pts) != 4:
        raise ValueError("4 coins attendus")
    # Orientation : le sens (p0→p1, p0→p3) doit être direct dans le repère image (comme (w,0) et (0,h)).
    edge_a = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    edge_b = (pts[3][0] - pts[0][0], pts[3][1] - pts[0][1])
    if _cross(edge_a, edge_b) < 0:
        pts = [pts[0], pts[3], pts[2], pts[1]]
    best = None
    for shift in range(4):
        p = pts[shift:] + pts[:shift]
        dx, dy = p[1][0] - p[0][0], p[1][1] - p[0][1]
        theta = math.degrees(math.atan2(dy, dx))
        theta = (theta + 180.0) % 360.0 - 180.0
        width = math.hypot(dx, dy)
        height = math.hypot(p[3][0] - p[0][0], p[3][1] - p[0][1])
        if best is None or abs(theta) < abs(best[4]):
            best = (p[0][0], p[0][1], width, height, theta)
    return best


def prediction_result(label, corners_px, width_px, height_px, score=None):
    """Un élément `result` Label Studio (pourcentages) pour une boîte prédite."""
    x, y, w, h, rotation = corners_to_ls_rect(corners_px)
    item = {
        "type": "rectanglelabels", "from_name": "label", "to_name": "image",
        "original_width": width_px, "original_height": height_px, "image_rotation": 0,
        "value": {"x": 100.0 * x / width_px, "y": 100.0 * y / height_px,
                  "width": 100.0 * w / width_px, "height": 100.0 * h / height_px,
                  "rotation": rotation, "rectanglelabels": [label]},
    }
    if score is not None:
        item["score"] = float(score)
    return item


def predict_image(model, image_path, conf=DEFAULT_CONF):
    """Boîtes prédites pour une image : liste de dicts {label, corners_px, score} ; (largeur, hauteur)."""
    result = model.predict(str(image_path), conf=conf, verbose=False)[0]
    height_px, width_px = result.orig_shape
    out = []
    if result.obb is not None and len(result.obb):
        corners = result.obb.xyxyxyxy.cpu().numpy()
        for pts, cls, score in zip(corners, result.obb.cls.cpu().numpy(), result.obb.conf.cpu().numpy()):
            out.append({"label": CLASS_NAMES[int(cls)], "corners_px": pts.reshape(4, 2).tolist(), "score": float(score)})
    return out, (width_px, height_px)


def task_ids_by_image(db_path, project_title=DEFAULT_PROJECT_TITLE):
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT id FROM project WHERE title = ?", (project_title,)).fetchone()
        if row is None:
            raise SystemExit(f"Projet « {project_title} » introuvable")
        import re
        prefix = re.compile(r"^[0-9a-f]{8}-")
        return {prefix.sub("", Path(json.loads(data).get("image", "")).name): tid
                for tid, data in conn.execute("SELECT id, data FROM task WHERE project_id = ?", (row[0],))}
    finally:
        conn.close()


def post_prediction(ls_url, token, task_id, results, model_version):
    import requests
    response = requests.post(f"{ls_url.rstrip('/')}/api/predictions/",
                             headers={"Authorization": f"Token {token}"}, timeout=30,
                             json={"task": task_id, "result": results, "model_version": model_version})
    response.raise_for_status()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("weights", help="poids YOLO-OBB (best.pt issu de train_phase0)")
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    parser.add_argument("--project", default=DEFAULT_PROJECT_TITLE)
    parser.add_argument("--images-dir", default=str(DEFAULT_IMAGES))
    parser.add_argument("--conf", type=float, default=DEFAULT_CONF, help="seuil de confiance (défaut 0,25)")
    parser.add_argument("--out", default="predictions.json")
    parser.add_argument("--post", action="store_true", help="envoyer les prédictions à Label Studio par l'API")
    parser.add_argument("--ls-url", default=DEFAULT_LS_URL)
    args = parser.parse_args(argv)

    annotated, all_names = load_annotations_sqlite(args.sqlite, args.project)
    todo = [n for n in all_names if n not in annotated]       # jamais d'écrasement : seules les images non annotées
    if not todo:
        sys.exit("Aucune image restante à pré-annoter.")
    from ultralytics import YOLO                              # import différé (dépendance lourde)
    model = YOLO(args.weights)
    version = f"{Path(args.weights).stem}-conf{args.conf}"

    tasks, n_boxes = [], 0
    for name in todo:
        boxes, (w_px, h_px) = predict_image(model, Path(args.images_dir) / name, args.conf)
        results = [prediction_result(b["label"], b["corners_px"], w_px, h_px, b["score"]) for b in boxes]
        n_boxes += len(results)
        tasks.append({"image": name, "results": results})
    Path(args.out).write_text(json.dumps(
        [{"data": {"image": t["image"]}, "predictions": [{"model_version": version, "result": t["results"]}]} for t in tasks],
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(todo)} image(s), {n_boxes} boîte(s) proposée(s) -> {args.out}")

    if args.post:
        token = os.environ.get("LABEL_STUDIO_TOKEN")
        if not token:
            sys.exit("LABEL_STUDIO_TOKEN absent (Label Studio > Account Settings > Access Token)")
        ids = task_ids_by_image(args.sqlite, args.project)
        for t in tasks:
            post_prediction(args.ls_url, token, ids[t["image"]], t["results"], version)
        print(f"{len(tasks)} prédiction(s) envoyée(s) à {args.ls_url}")


if __name__ == "__main__":
    main()
