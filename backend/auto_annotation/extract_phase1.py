"""
Phase 1 — Extraction de l'Échantillon d'Amorçage (150 images)
==============================================================
Stratification proportionnelle stricte depuis un dossier local structuré par catégorie.

Structure attendue du dossier source :
    dossier_source/
    ├── electrique/          <- une catégorie par sous-dossier
    │   ├── photo1.jpg
    │   └── ...
    ├── acoustique/
    │   └── ...
    └── basse/
        └── ...

Le quota de chaque catégorie est proportionnel à son poids dans le dataset total.
Les fichiers sont copiés avec un préfixe de catégorie pour éviter les conflits de nom.
"""
import os
import random
import shutil
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(name)s | %(message)s')
logger = logging.getLogger(__name__)

EXTENSIONS_VALIDES = {'.jpg', '.jpeg', '.png', '.webp'}


def extraire_echantillon_stratifie(
    dossier_source: str,
    dossier_destination: str,
    total_cible: int = 150,
    seed: int = 42,
):
    """
    Extrait `total_cible` images depuis `dossier_source` avec une stratification
    proportionnelle stricte : chaque catégorie (sous-dossier) contribue
    proportionnellement à son poids dans la distribution totale.

    Args:
        dossier_source:      Dossier racine contenant un sous-dossier par catégorie.
        dossier_destination: Dossier de sortie pour Label Studio (sera créé si absent).
        total_cible:         Nombre total d'images à extraire (défaut : 150).
        seed:                Graine aléatoire pour la reproductibilité (défaut : 42).
                             Changer la valeur produit un échantillon différent mais
                             toujours déterministe.
    """
    source_path = Path(dossier_source)
    dest_path = Path(dossier_destination)

    if not source_path.exists():
        raise FileNotFoundError(f"Dossier source introuvable : {dossier_source}")

    dest_path.mkdir(parents=True, exist_ok=True)

    # Reproductibilité : graine fixée pour des expériences comparables
    random.seed(seed)
    logger.info(f"Graine aléatoire fixée à {seed}")

    # 1. Recenser les catégories et les images valides
    categories = {}
    total_images_disponibles = 0

    for dossier_cat in sorted(d for d in source_path.iterdir() if d.is_dir()):
        images = [f for f in dossier_cat.iterdir() if f.suffix.lower() in EXTENSIONS_VALIDES]
        if images:
            categories[dossier_cat.name] = images
            total_images_disponibles += len(images)

    if not categories:
        raise ValueError(f"Aucun sous-dossier avec des images trouvé dans {dossier_source}")

    if total_images_disponibles < total_cible:
        raise ValueError(
            f"Pas assez d'images. Disponibles : {total_images_disponibles}, Cible : {total_cible}"
        )

    logger.info(f"{len(categories)} catégories | {total_images_disponibles} images disponibles")
    for cat, imgs in sorted(categories.items()):
        logger.info(f"  {cat}: {len(imgs)} images")

    # 2. Calculer les quotas proportionnels exacts
    quotas = {}
    for cat, images in categories.items():
        proportion = len(images) / total_images_disponibles
        quotas[cat] = int(proportion * total_cible)

    # Corriger les erreurs d'arrondi pour atteindre exactement le total cible
    images_manquantes = total_cible - sum(quotas.values())
    # Distribuer le reste aux catégories les plus représentées (ordre décroissant)
    categories_triees = sorted(categories.keys(), key=lambda k: len(categories[k]), reverse=True)
    for i in range(images_manquantes):
        quotas[categories_triees[i % len(categories_triees)]] += 1

    logger.info("Quotas calculés :")
    for cat in sorted(quotas):
        logger.info(f"  {cat}: {quotas[cat]} images ({quotas[cat]/total_cible*100:.1f}%)")

    # 3. Extraction aléatoire et copie avec préfixe de catégorie
    images_selectionnees = 0
    for cat, images in categories.items():
        quota = quotas.get(cat, 0)
        if quota == 0:
            continue

        echantillon = random.sample(images, quota)

        for img_path in echantillon:
            # Préfixage pour éviter les conflits de nom entre catégories
            # ex: "electrique_photo1.jpg"
            nouveau_nom = f"{cat}_{img_path.name}"
            destination = dest_path / nouveau_nom
            shutil.copy2(img_path, destination)
            images_selectionnees += 1

    logger.info(
        f"Extraction terminée : {images_selectionnees} images copiées dans '{dossier_destination}'."
    )


if __name__ == "__main__":
    # ─── À CONFIGURER ────────────────────────────────────────────────────────
    # Dossier local structuré : un sous-dossier par catégorie de guitare
    DOSSIER_SOURCE = "chemin/vers/le/dossier/brut"
    # Dossier de sortie que tu importeras dans Label Studio
    DOSSIER_AMORCAGE = "dataset_phase1"
    # ─────────────────────────────────────────────────────────────────────────

    extraire_echantillon_stratifie(DOSSIER_SOURCE, DOSSIER_AMORCAGE, total_cible=150)

