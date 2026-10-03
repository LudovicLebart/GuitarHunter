"""Fine-tuning Phase 0 du détecteur de parties (YOLO-OBB) sur les images annotées à la main.

À lancer sur le Dell (GPU) **hors des heures de scan** : la carte est partagée avec le Portier (Ollama). Les poids de
départ sont ceux du plan V2.1 (`yolov8n-obb.pt`, pré-entraîné DOTA) ; le critère de passage est mAP50-OBB ≥ 0,50 sur
la validation (PARTS_DETECTOR_AND_CROPS_PLAN.md, étape 3).

Étapes :
  1. `python -m backend.auto_annotation.labelstudio_export export`   (sur le poste qui a Label Studio)
  2. copier `scratch/yolo_dataset_phase1/` sur le Dell (le chemin `path:` de dataset.yaml est ABSOLU : utiliser --data
     avec un yaml dont `path:` pointe vers le dossier copié, ou `--rewrite-path`)
  3. `python -m backend.auto_annotation.train_phase0 --data /chemin/dataset.yaml --rewrite-path`

Dépendance : `pip install ultralytics` (importée au dernier moment, pas nécessaire aux tests).
"""
import argparse
import sys
from pathlib import Path

MAP50_TARGET = 0.50
DEFAULT_WEIGHTS = "yolov8n-obb.pt"


def rewrite_dataset_path(yaml_path):
    """Remplace la ligne `path:` du dataset.yaml par le dossier qui le contient (utile après une copie de machine)."""
    yaml_path = Path(yaml_path)
    lines = yaml_path.read_text(encoding="utf-8").splitlines()
    out = [f"path: {yaml_path.parent.resolve().as_posix()}" if line.startswith("path:") else line for line in lines]
    yaml_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def verdict(map50, target=MAP50_TARGET):
    """Phrase de conclusion selon le critère du plan."""
    if map50 >= target:
        return f"mAP50-OBB {map50:.3f} ≥ {target} : critère de la Phase 0 atteint."
    return (f"mAP50-OBB {map50:.3f} < {target} : critère NON atteint — augmenter les epochs ou annoter ~50 images de "
            f"plus (plan V2.1, Phase 0).")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="dataset.yaml produit par labelstudio_export")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8, help="petit par défaut : 8 Go de VRAM partagés avec Ollama")
    parser.add_argument("--device", default="0")
    parser.add_argument("--project", default="runs/parts_detector")
    parser.add_argument("--name", default="phase0")
    parser.add_argument("--rewrite-path", action="store_true", help="corriger `path:` du dataset.yaml (copie entre machines)")
    args = parser.parse_args(argv)

    if args.rewrite_path:
        rewrite_dataset_path(args.data)
    from ultralytics import YOLO                      # import différé
    model = YOLO(args.weights)
    model.train(data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device=args.device,
                project=args.project, name=args.name, exist_ok=True)
    metrics = model.val(data=args.data, imgsz=args.imgsz, device=args.device)
    map50 = float(metrics.box.map50)
    print(verdict(map50))
    best = Path(args.project) / args.name / "weights" / "best.pt"
    print(f"Poids : {best}")
    sys.exit(0 if map50 >= MAP50_TARGET else 2)


if __name__ == "__main__":
    main()
