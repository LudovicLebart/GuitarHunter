"""Export des annotations Label Studio (rectangles pivotés) vers le format YOLO-OBB.

Trois commandes (depuis la racine du projet, avec `venv/`) :
  python -m backend.auto_annotation.labelstudio_export progress   # avancement, boîtes par classe
  python -m backend.auto_annotation.labelstudio_export export     # dataset train/val + dataset.yaml
  python -m backend.auto_annotation.labelstudio_export preview    # images avec boîtes dessinées (contrôle visuel)

Source par défaut : la base SQLite locale de Label Studio (aucune clé d'API nécessaire) ; `--json` accepte
à la place un export « JSON » du projet (Export > JSON dans l'interface).

Convention Label Studio : x, y, width, height en % de l'image ; `rotation` en degrés, sens horaire, autour du
coin HAUT-GAUCHE (x, y) du rectangle. Les rotations se font en pixels (pas en %), sinon l'angle est faussé
dès que l'image n'est pas carrée.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

from .config import CLASS_NAMES

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE = ROOT / "scratch" / "label_studio_data" / "label_studio.sqlite3"
DEFAULT_IMAGES = ROOT / "scratch" / "dataset_phase1"
DEFAULT_OUT = ROOT / "scratch" / "yolo_dataset_phase1"
DEFAULT_PROJECT_TITLE = "GuitarHunter OBB Phase 1"
# Nombre de boîtes en dessous duquel une classe est signalée comme rare (trop peu d'exemples pour apprendre).
RARE_CLASS_MIN_BOXES = 15

_UPLOAD_PREFIX = re.compile(r"^[0-9a-f]{8}-")


def ls_rect_to_corners(value, width_px, height_px):
    """Rectangle Label Studio → 4 coins normalisés [x1,y1,...,x4,y4] (ordre haut-gauche, haut-droit,
    bas-droit, bas-gauche avant rotation), bornés à [0, 1]."""
    x0 = value["x"] / 100.0 * width_px
    y0 = value["y"] / 100.0 * height_px
    w = value["width"] / 100.0 * width_px
    h = value["height"] / 100.0 * height_px
    theta = math.radians(value.get("rotation", 0.0) or 0.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    corners = []
    for dx, dy in ((0, 0), (w, 0), (w, h), (0, h)):
        px = x0 + dx * cos_t - dy * sin_t
        py = y0 + dx * sin_t + dy * cos_t
        corners.append(min(max(px / width_px, 0.0), 1.0))
        corners.append(min(max(py / height_px, 0.0), 1.0))
    return corners


def image_name_from_task(task_data):
    """`/data/upload/1/28858522-acoustique_123_0.jpg` → `acoustique_123_0.jpg` (Label Studio préfixe un hash)."""
    name = Path(task_data.get("image", "")).name
    return _UPLOAD_PREFIX.sub("", name)


def _boxes_from_result(result):
    """Liste de (classe, valeur, largeur_px, hauteur_px) pour les rectangles étiquetés d'une annotation."""
    boxes = []
    for item in result or []:
        value = item.get("value", {})
        labels = value.get("rectanglelabels")
        if item.get("type") != "rectanglelabels" or not labels:
            continue
        boxes.append((labels[0], value, item["original_width"], item["original_height"]))
    return boxes


def load_annotations_sqlite(db_path, project_title=DEFAULT_PROJECT_TITLE):
    """{nom_image: [boîtes]} pour les tâches annotées (non ignorées) ; une tâche annotée sans boîte = image
    volontairement vide (exemple négatif). En cas de plusieurs annotations, la plus récente gagne."""
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT id FROM project WHERE title = ?", (project_title,)).fetchone()
        if row is None:
            raise SystemExit(f"Projet « {project_title} » introuvable dans {db_path}")
        tasks = {tid: image_name_from_task(json.loads(data)) for tid, data in
                 conn.execute("SELECT id, data FROM task WHERE project_id = ?", (row[0],))}
        latest = {}
        for tid, result, was_cancelled in conn.execute(
                "SELECT task_id, result, was_cancelled FROM task_completion "
                "WHERE project_id = ? ORDER BY updated_at", (row[0],)):
            latest[tid] = (json.loads(result or "[]"), bool(was_cancelled))
    finally:
        conn.close()
    annotated = {}
    for tid, (result, cancelled) in latest.items():
        if not cancelled and tid in tasks:
            annotated[tasks[tid]] = _boxes_from_result(result)
    return annotated, sorted(tasks.values())


def load_annotations_json(json_path):
    """Même sortie à partir d'un export JSON du projet (liste de tâches avec `annotations`)."""
    with open(json_path, encoding="utf-8") as f:
        tasks = json.load(f)
    annotated, names = {}, []
    for t in tasks:
        name = image_name_from_task(t.get("data", {}))
        names.append(name)
        done = [a for a in t.get("annotations", []) if not a.get("was_cancelled")]
        if done:
            annotated[name] = _boxes_from_result(done[-1].get("result"))
    return annotated, sorted(names)


def _category(image_name):
    """acoustique / electrique / basse : préfixe des noms de fichiers de l'échantillon Phase 1."""
    return image_name.split("_", 1)[0]


def split_train_val(names, val_ratio=0.2, seed=42):
    """Découpage reproductible ET stable : le camp d'une image ne dépend que de son nom et de la graine,
    jamais des autres images. Indispensable ici, car on ré-exporte pendant que les annotations arrivent
    (boucle de pré-annotation, réentraînements) : un découpage qui bougerait ferait passer des images de
    train à val, fausserait la comparaison des mAP entre entraînements et ferait fuiter des images
    d'entraînement dans la validation."""
    train, val = [], []
    for name in sorted(names):
        digest = hashlib.sha1(f"{seed}:{name}".encode("utf-8")).hexdigest()
        in_val = (int(digest[:8], 16) / 0x100000000) < val_ratio
        (val if in_val else train).append(name)
    return train, val


def class_id(label):
    if label not in CLASS_NAMES:
        raise ValueError(f"Classe inconnue « {label} » (attendues : {CLASS_NAMES})")
    return CLASS_NAMES.index(label)


def write_dataset_yaml(out_dir):
    lines = [f"path: {Path(out_dir).resolve().as_posix()}", "train: images/train", "val: images/val", "names:"]
    lines += [f"  {i}: {name}" for i, name in enumerate(CLASS_NAMES)]
    (Path(out_dir) / "dataset.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_dataset(annotated, images_dir, out_dir, val_ratio=0.2, seed=42):
    """Écrit images/ + labels/ (train, val) et dataset.yaml. Retourne un résumé.
    `images/` et `labels/` de la destination sont recréés de zéro : sans cela, une image qui change de
    camp entre deux exports resterait dans les deux. Les classes sont validées avant toute écriture."""
    images_dir, out_dir = Path(images_dir), Path(out_dir)
    for boxes in annotated.values():
        for label, *_ in boxes:
            class_id(label)
    train, val = split_train_val(list(annotated), val_ratio, seed)
    for sub in ("images", "labels"):
        shutil.rmtree(out_dir / sub, ignore_errors=True)
    missing, n_boxes = [], 0
    for split, names in (("train", train), ("val", val)):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
        for name in names:
            src = images_dir / name
            if not src.exists():
                missing.append(name)
                continue
            shutil.copy2(src, out_dir / "images" / split / name)
            lines = []
            for label, value, w_px, h_px in annotated[name]:
                coords = ls_rect_to_corners(value, w_px, h_px)
                lines.append(f"{class_id(label)} " + " ".join(f"{c:.6f}" for c in coords))
                n_boxes += 1
            (out_dir / "labels" / split / (Path(name).stem + ".txt")).write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    write_dataset_yaml(out_dir)
    return {"train": len(train), "val": len(val), "boxes": n_boxes, "missing": missing}


def progress_report(annotated, all_names):
    """Texte d'avancement : images faites, boîtes par classe, classes trop rares, par catégorie."""
    counts = Counter(label for boxes in annotated.values() for label, *_ in boxes)
    cats_done = Counter(_category(n) for n in annotated)
    cats_all = Counter(_category(n) for n in all_names)
    lines = [f"Images annotées : {len(annotated)} / {len(all_names)}  ({100 * len(annotated) / max(1, len(all_names)):.0f} %)",
             f"Boîtes au total : {sum(counts.values())}", "", "Par catégorie :"]
    lines += [f"  {c:<11} {cats_done[c]:>3} / {cats_all[c]}" for c in sorted(cats_all)]
    lines += ["", "Boîtes par classe :"]
    for name in CLASS_NAMES:
        flag = "   <- rare" if counts[name] < RARE_CLASS_MIN_BOXES and annotated else ""
        lines.append(f"  {name:<10} {counts[name]:>4}{flag}")
    return "\n".join(lines)


def _draw_preview(image_path, boxes, out_path):
    import cv2
    import numpy as np
    img = cv2.imread(str(image_path))
    if img is None:
        return False
    h, w = img.shape[:2]
    for label, value, w_px, h_px in boxes:
        pts = np.array(ls_rect_to_corners(value, w_px, h_px), dtype=np.float32).reshape(4, 2)
        pts = (pts * np.array([w, h])).astype(np.int32)
        cv2.polylines(img, [pts], True, (0, 255, 0), 2)
        cv2.putText(img, label, tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return cv2.imwrite(str(out_path), img)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["progress", "export", "preview"])
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE), help="base SQLite de Label Studio")
    parser.add_argument("--json", help="export JSON du projet (remplace --sqlite)")
    parser.add_argument("--project", default=DEFAULT_PROJECT_TITLE)
    parser.add_argument("--images-dir", default=str(DEFAULT_IMAGES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    if args.json:
        annotated, all_names = load_annotations_json(args.json)
    else:
        annotated, all_names = load_annotations_sqlite(args.sqlite, args.project)

    if args.command == "progress":
        print(progress_report(annotated, all_names))
    elif args.command == "export":
        summary = export_dataset(annotated, args.images_dir, args.out, args.val_ratio, args.seed)
        print(f"Export : {summary['train']} train, {summary['val']} val, {summary['boxes']} boîtes -> {args.out}")
        if summary["missing"]:
            print(f"ATTENTION : {len(summary['missing'])} image(s) introuvable(s) dans {args.images_dir} "
                  f"(ex. {summary['missing'][:3]})")
    else:
        out = Path(args.out) / "previews"
        out.mkdir(parents=True, exist_ok=True)
        done = sum(_draw_preview(Path(args.images_dir) / n, b, out / n) for n, b in annotated.items())
        print(f"{done} aperçu(s) écrit(s) dans {out}")


if __name__ == "__main__":
    main()
