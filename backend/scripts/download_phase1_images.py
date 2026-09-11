"""
Download Phase 1 — Constitution du dossier source pour extract_phase1.py
=========================================================================
Lit dataset_a_phase0.jsonl (déjà présent à la racine du projet),
télécharge les images `usable=True` et les range dans :

    scratch/dataset_brut/
    ├── electrique/
    ├── acoustique/
    └── basse/

Idempotent : si le fichier destination existe déjà, on le saute.
Reprise sur crash : relancer le script continue là où il s'est arrêté.

Les URLs sont publiques (Firebase Storage signées, valides) — aucune
authentification requise.

Usage :
    python -m backend.scripts.download_phase1_images
    python -m backend.scripts.download_phase1_images --output scratch/dataset_brut --workers 8
    python -m backend.scripts.download_phase1_images --dry-run   # compte sans télécharger
"""

import argparse
import json
import sys
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error

# ─── Mapping classification → catégorie dossier ───────────────────────────────

def classification_to_category(classification: str) -> str | None:
    """
    Mappe la classification taxonomique vers une des 3 catégories YOLO.

    Règles (ordre de priorité descendant) :
    - 'basse'       → basse
    - 'electrique'  → electrique
    - 'acoustique'  ou 'classique' ou 'electro_acoustique' → acoustique

    Retourne None si la classification ne correspond à aucune catégorie connue.
    """
    c = classification.lower()
    if "basse" in c:
        return "basse"
    if "electrique" in c and "electro_acoustique" not in c:
        return "electrique"
    if "acoustique" in c or "classique" in c or "electro_acoustique" in c:
        return "acoustique"
    return None


# ─── Téléchargement d'une image ───────────────────────────────────────────────

def download_image(url: str, dest: Path, timeout: int = 15) -> tuple[str, bool, str]:
    """
    Télécharge `url` vers `dest`.

    Returns:
        (filename, success, message)
    """
    if dest.exists():
        return dest.name, True, "skip (already exists)"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GuitarHunter/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dest.write_bytes(resp.read())
        return dest.name, True, "ok"
    except urllib.error.HTTPError as e:
        return dest.name, False, f"HTTP {e.code}"
    except Exception as e:
        return dest.name, False, str(e)[:80]


# ─── Construction de la liste de travail ──────────────────────────────────────

def build_work_list(jsonl_path: Path, output_dir: Path) -> list[tuple[str, Path]]:
    """
    Lit le JSONL et retourne la liste des (url, dest_path) à traiter.
    Seules les entrées `usable=True` sont retenues.
    """
    work = []
    skipped_not_usable = 0
    skipped_no_category = 0

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)

            if not entry.get("usable"):
                skipped_not_usable += 1
                continue

            category = classification_to_category(entry.get("classification", ""))
            if category is None:
                skipped_no_category += 1
                continue

            url = entry["image_url"]
            deal_id = entry["deal_id"]
            image_idx = entry["image_idx"]

            # Nom de fichier : deal_id + idx pour garantir l'unicité
            ext = Path(url.split("?")[0]).suffix or ".jpg"
            filename = f"{deal_id}_{image_idx}{ext}"
            dest = output_dir / category / filename

            work.append((url, dest))

    print(f"  Entrées non-usable ignorées   : {skipped_not_usable}")
    print(f"  Entrées hors catégorie ignorées: {skipped_no_category}")
    return work


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    project_root = Path(__file__).parent.parent.parent

    parser = argparse.ArgumentParser(
        description="Télécharge les images Phase 1 depuis dataset_a_phase0.jsonl."
    )
    parser.add_argument(
        "--jsonl",
        default=str(project_root / "dataset_a_phase0.jsonl"),
        help="Chemin du fichier JSONL source (défaut: dataset_a_phase0.jsonl à la racine)",
    )
    parser.add_argument(
        "--output",
        default=str(project_root / "scratch" / "dataset_brut"),
        help="Dossier de sortie racine (défaut: scratch/dataset_brut/)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Nombre de threads parallèles (défaut: 6)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compte et affiche les stats sans télécharger",
    )
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    output_dir = Path(args.output)

    if not jsonl_path.exists():
        print(f"❌ Fichier JSONL introuvable : {jsonl_path}")
        sys.exit(1)

    # Créer les sous-dossiers catégorie
    for cat in ("electrique", "acoustique", "basse"):
        (output_dir / cat).mkdir(parents=True, exist_ok=True)

    print(f"[OUT] Dossier de sortie : {output_dir}")
    print(f"[...] Lecture de {jsonl_path.name} ...")
    work = build_work_list(jsonl_path, output_dir)

    already = sum(1 for _, dest in work if dest.exists())
    to_download = len(work) - already

    print(f"\n[STATS] Resume :")
    print(f"  Total a traiter  : {len(work)}")
    print(f"  Deja presents    : {already} (seront sautes)")
    print(f"  A telecharger    : {to_download}")

    # Répartition par catégorie
    from collections import Counter
    cat_counts = Counter(dest.parent.name for _, dest in work)
    print(f"\n  Par catégorie :")
    for cat in ("electrique", "acoustique", "basse"):
        print(f"    {cat:12s}: {cat_counts.get(cat, 0)}")

    if args.dry_run:
        print("\n[DRY-RUN] Aucun telechargement effectue.")
        return

    if to_download == 0:
        print("\n[OK] Tout est deja telecharge.")
        return

    print(f"\n[DOWN] Telechargement avec {args.workers} threads paralleles...")
    ok = 0
    skipped = 0
    errors = []

    # Barre de progression manuelle (pas de dépendance tqdm)
    total = len(work)
    done = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_image, url, dest): dest for url, dest in work}
        for future in as_completed(futures):
            name, success, msg = future.result()
            done += 1
            if msg.startswith("skip"):
                skipped += 1
            elif success:
                ok += 1
            else:
                errors.append((name, msg))

            # Progress toutes les 50 images ou à la fin
            if done % 50 == 0 or done == total:
                pct = done / total * 100
                print(f"  [{done:4d}/{total}] {pct:5.1f}%  ok={ok} skip={skipped} err={len(errors)}", end="\r")

    print()  # newline après le \r
    print(f"\n[DONE] Termine.")
    print(f"  Telecharges : {ok}")
    print(f"  Sautes      : {skipped}")
    print(f"  Erreurs     : {len(errors)}")

    if errors:
        print("\n[WARN] Erreurs (10 premieres) :")
        for name, msg in errors[:10]:
            print(f"  {name}: {msg}")
        # Sauvegarder la liste complète des erreurs
        err_path = output_dir / "download_errors.txt"
        with open(err_path, "w") as f:
            for name, msg in errors:
                f.write(f"{name}\t{msg}\n")
        print(f"  Liste complete -> {err_path}")

    # Afficher le compte final par catégorie
    print(f"\n[STATS] Fichiers presents par categorie :")
    for cat in ("electrique", "acoustique", "basse"):
        n = len(list((output_dir / cat).glob("*.jpg"))) + len(list((output_dir / cat).glob("*.png"))) + len(list((output_dir / cat).glob("*.webp")))
        print(f"  {cat:12s}: {n}")


if __name__ == "__main__":
    main()
