# Plan d'Implémentation Technique — YOLO-OBB Auto-Annotation V2.1
_Correction et formalisation du plan original V2 — 2026-09-09_

## Objectif

Construire un dataset d'annotation YOLO-OBB (boîtes orientées) des pièces de guitare avec **zéro supervision humaine** après la Phase 1. Le pipeline est entièrement déterministe et local.

---

## Phase 0 — Validation du Modèle d'Amorçage _(ajouté V2.1)_

> **Étape obligatoire avant Phase 2. Absente du plan original — risque bloquant.**

Le modèle `yolov8n-obb.pt` est pré-entraîné sur **DOTA** (détection d'objets aériens : avions, bateaux, texte). Il ne connaît pas les guitares. Utiliser ces poids directement en Phase 2 produirait des prédictions aléatoires et invalides.

**Livrable de Phase 0 :** Un checkpoint fine-tuné YOLO-OBB sur les 150 images annotées manuellement (Phase 1). C'est **ce checkpoint** qui est désigné `YOLO_V1_OBB_WEIGHTS`, pas les poids nano DOTA.

**Workflow :**
```
yolo obb train model=yolov8n-obb.pt data=dataset_phase1/data.yaml epochs=50 imgsz=640
```

Critère de passage : **mAP50-OBB >= 0.50** sur le split de validation (20% des 150 images).
Si non atteint → augmenter epochs ou annoter 50 images supplémentaires.

---

## Phase 1 — Amorçage (Ground Truth Orientée)

**Intervention humaine unique.** Extraction d'un échantillon de 150 images depuis un **dossier local structuré par catégorie** via `extract_phase1.py`.

**Structure attendue du dossier source :**
```
dossier_brut/
├── electrique/
│   ├── photo1.jpg
│   └── ...
├── acoustique/
│   └── ...
└── basse/
    └── ...
```

**Algorithme : Stratification Proportionnelle Stricte**
- Chaque catégorie contribue proportionnellement à son poids dans le dataset total (ex: si "electrique" représente 60% des images disponibles, elle obtient 90 des 150 slots).
- Sélection aléatoire (`random.sample`) au sein de chaque quota pour garantir le chaos.
- Correction des erreurs d'arrondi distribuée aux catégories les plus représentées pour atteindre **exactement 150** images.
- Fichiers renommés avec préfixe de catégorie (`electrique_photo1.jpg`) pour éviter tout conflit de nom dans Label Studio.

**Label Studio — Configuration OBB :** Attribut `canRotate="true"`. Les boîtes doivent être dessinées inclinées pour border parfaitement la pièce (zéro arrière-plan).

Classes : `headstock`, `neck`, `body`, `bridge`, `pickups`, `soundhole`

**Livrable :** Dataset `dataset_phase1/` au format YOLO-OBB + checkpoint fine-tuné (voir Phase 0).

---

## Phase 2 — Inférence de Masse (Modèle OBB V1)

Le script `main.py` parcourt les photos stockées dans Firebase Storage.

- `stream=True` est **OBLIGATOIRE** pour ne pas charger tous les résultats en RAM.
- Le pipeline vérifie si une image a déjà été traitée (existence du label dans `dataset_v2/labels/`) et la saute. Un crash ne repart pas de zéro.

---

## Phase 3 — Filtre 1 : Heuristiques Spatiales

Script `heuristics.py`. Filtres sur `RotatedRect` OpenCV réels (pas des AABB).

| Règle | Pièce | Condition d'élimination |
|-------|-------|------------------------|
| Inclusion | pickups, soundhole | < 80% de la surface incluse dans body → supprimée |
| Ratio forme | neck | max(w/h, h/w) < 2.0 → manche carré aberrant |
| Connectivité | neck | Ne touche pas body ET headstock → supprimé |
| Aucune | body, headstock, bridge | Toujours conservées |

---

## Phase 4 — Filtre 2 : Redressement & Oracle Local

**VLM choisi : Moondream (2B)** via Ollama — _choix acté V2.1._

Justification : Moondream est spécialisé pour la classification visuelle binaire légère (2B params vs 7B+ pour LLaVA). 3x plus rapide, latence < 500ms sur CPU. LLaVA écarté : surcapacité pour une réponse TRUE/FALSE.

Workflow :
1. Redressement (OpenCV via `geometry.py`) : angle OBB → getRotationMatrix2D → canvas agrandi → crop orthogonal.
2. Validation Binaire (Moondream) : "L'image montre-t-elle exclusivement un(e) {class_name} de guitare ? Réponds uniquement par TRUE ou FALSE." Si FALSE → boîte détruite.

---

## Phase 5 — Création du Dataset Pur (YOLO V2)

Export via `exporter.py` au format YOLO-OBB 4-coins normalisés : `class x1 y1 x2 y2 x3 y3 x4 y4`

**Critères de passage vers l'entraînement V2 :**
- Volume minimal : **500 images validées** dans `dataset_v2/`
- mAP50-OBB >= **0.70** sur split de validation (15% du dataset V2)
- mAP50-OBB >= **0.60** sur set de test hors-distribution

---

## Phase 6 — Post-Processing Déterministe (Pipeline de Production)

> ATTENTION : Cette phase appartient au pipeline de **PRODUCTION** (après déploiement YOLO V2), pas au pipeline d'annotation. Le code doit résider dans `backend/production_pipeline/post_processing.py`.

**Routage (décision explicite V2.1) :**

| Condition | Route | Traitement |
|-----------|-------|------------|
| Classe `headstock` | OCR (Surya) | Niveaux de gris → CLAHE extrême (clipLimit=4.0) → Unsharp Masking |
| Toutes autres classes | Vision LLM | Filtre bilatéral → CLAHE sur canal L (LAB, clipLimit=2.0) |

Justification : Le headstock porte les inscriptions de marque (OCR). Les autres pièces requièrent l'analyse visuelle colorimétrique du bois/accastillage.

---

## Structure des Fichiers

```
backend/auto_annotation/          <- Pipeline d'annotation (Phases 0-5)
  config.py, data_loader.py, extract_phase1.py,
  geometry.py, heuristics.py, vlm_client.py,
  exporter.py, main.py

backend/production_pipeline/      <- Pipeline de production (Phase 6) - A CREER
  post_processing.py              <- Déplacé depuis auto_annotation/
  router.py                       <- Dispatche headstock→OCR, autres→Vision
```

