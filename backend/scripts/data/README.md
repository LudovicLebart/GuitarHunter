# Données « Dataset A » (photos d'annonces pour les projets vision)

> **Fichiers `dataset_a_*.jsonl` : locaux uniquement, non versionnés** (décision du 2026-10-02). Le dépôt GitHub est public et ces fichiers contiennent des `user_id` Firebase, des titres d'annonces et des URLs de photos. Ils sont dans `.gitignore`. À ré-exporter depuis la base si on change de machine. Ce README documente leur structure.

Trois fichiers qui forment **une chaîne, pas des doublons** (réconciliés le 2026-10-02) :

| Étage | Fichier | Granularité | Contenu |
|---|---|---|---|
| 1. Annonces | `dataset_a_manifest.jsonl` | 1 ligne = 1 annonce | `deal_id, user_id, title, classification, verdict, image_urls`. 1 066 lignes pour **1 061 annonces** (5 doublons de `deal_id` ; 61 identifiants non numériques = annonces Kijiji). |
| 2. Photos | `dataset_a_phase0.jsonl` | 1 ligne = 1 photo | **5 974 photos** des mêmes 1 061 annonces, avec le filtre OWLv2 : `usable` (une guitare est détectée : **3 263**), `low_resolution`, `cropped_suspect`, `measurable`, boîte « guitar ». Source du détecteur de parties (le dossier `scratch/dataset_brut/` et les 150 images à annoter en viennent). |
| 3. Vues frontales | `experiments/yolo_annotation/dataset_a_frontal.jsonl` (non versionné) | 1 ligne = 1 photo | **606 photos** (507 annonces) jugées « vue frontale » par Gemini ; toutes sont dans l'étage 2 avec `usable=True`. Sous-ensemble pour le neck reset, pas une source indépendante. |

**Source de vérité pour le détecteur de parties : `dataset_a_phase0.jsonl`** (le plus complet au niveau photo).

Limites connues :
- 28 lignes de `dataset_a_phase0.jsonl` n'ont pas la clé `measurable` (produites avant son ajout) ; sans effet sur `usable`, seul critère utilisé pour l'échantillon d'amorçage.
- `cropped_suspect` (2 523 photos) est un proxy trop agressif pour juger la mesurabilité du neck reset (voir `NECK_RESET_VISION_PLAN.md` §8quater) ; pour le détecteur de parties, c'est au contraire utile (vues partielles).
- Les images elles-mêmes (URLs Firebase Storage) ne sont pas dans le dépôt : `backend/scripts/download_phase1_images.py` les télécharge dans `scratch/dataset_brut/`.
