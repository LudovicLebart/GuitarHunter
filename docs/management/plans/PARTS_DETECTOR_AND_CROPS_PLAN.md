# Plan — Détecteur de parties de guitare et crops (tronc commun)
_Rédigé le 2026-10-02. Remplace et complète `YOLO_OBB_AUTO_ANNOTATION_PLAN.md` (V2.1), dont les phases restent la référence technique d'exécution._

## 1. Objectif et périmètre

Un **détecteur de parties** entraîné (YOLO-OBB) qui découpe chaque photo d'annonce en crops : tête, manche, talon, caisse, chevalet, sillet, rosace, micros, plaque/étiquette. Ces crops servent :

1. **Au Portier (T1)** : garder **toutes** les photos sous le contexte du Dell (8192) en envoyant des crops utiles plutôt que des photos entières ; Qwen local décrit chaque crop sans interpréter (`STRATEGIE_IA.md` §4).
2. **Au projet neck reset** (chantier à part, voir §6) : localisation du chevalet, du sillet et du talon pour ses mesures.

Décision utilisateur actée (2026-10-02) : **ne pas réduire la résolution ni le nombre d'images** ; les crops s'ajoutent à la photo entière réduite.

## 2. Pourquoi un détecteur entraîné (résultats déjà acquis)

Tout ce qui est zéro-shot a été essayé et n'est pas fiable (détail : `NECK_RESET_VISION_PLAN.md` §8bis, §9, §10) :

| Piste | Résultat |
|---|---|
| OWLv2 multi-parties | « nut » seul cohérent ; « saddle » se verrouille sur la tête ; « soundhole » hallucine sur les électriques |
| SAM 2.1 point-guidé | contour précis, mais choix du masque non fiable (bon sur 2 acoustiques, raté sur 2 électriques) |
| Détection des frettes (LSD/RANSAC) | échoue sur le bruit de fond |
| Gemini Flash/Pro annotateur | 20/20 images « 3/3 parties présentes » : mesure de complétude, **pas de précision** (aucun IoU relevé) |

→ Conclusion : il faut une vérité-terrain humaine. D'où les 150 images.

## 3. Le dataset d'amorçage (Phase 1)

- **150 images** : `scratch/dataset_phase1/` (92 acoustiques, 55 électriques, 3 basses ; seed 42), tirées de `scratch/dataset_brut/` (3 258 images « usable »).
- **Couverture vérifiée** : toutes les positions de photo (0 à 8) ; 27 % de premières photos contre 32 % dans la population. **105/150 sont `cropped_suspect`** : beaucoup de plans serrés et de vues partielles, ce qui est voulu ici.
- **Annotation : aucune image annotée à ce jour** (confirmé le 2026-10-02). Outil : Label Studio (`scratch/start_label_studio.ps1`, template `scratch/label_studio_template_obb.xml`, guide `scratch/GUIDE_ANNOTATION_PHASE1.md`).

### 3.1 Taxonomie commune (à figer avant d'annoter)

`headstock`, `neck`, `heel`, `body`, `bridge`, `saddle`, `nut`, `soundhole`, `pickups`, `plate` (étiquette / plaque de série).

Le template Label Studio actuel (6 classes : headstock, neck, body, bridge, pickups, soundhole) et le `dataset.yaml` des essais (5 classes : neck, headstock, heel, soundhole, saddle) divergent ; ni l'un ni l'autre ne couvre les besoins du neck reset (`heel`, `saddle`, `nut`) ni celui du Portier (`plate`). **Mettre à jour le template avec la liste ci-dessus, puis régénérer `dataset.yaml`.**

### 3.2 Règles d'annotation

- Boîtes **orientées** (`canRotate`), au plus près de la pièce.
- **Partie coupée par le bord de l'image : ne pas l'annoter** (règle du 2026-09-11, conservée).
- Une boîte par micro.
- Ne pas annoter ce qui n'est pas visible ou pas identifiable (une photo sans rosace n'a pas de `soundhole`).

### 3.2 bis Outil d'export et de suivi (ajouté le 2026-10-02)

`backend/auto_annotation/labelstudio_export.py` (lit la base SQLite locale de Label Studio, ou un export JSON) :
- `progress` : images faites, boîtes par classe, classes rares (< 15 boîtes), par catégorie ;
- `export` : dataset YOLO-OBB (`images/` et `labels/` en train/val, découpage 80/20 par catégorie, `dataset.yaml` à 10 classes) dans `scratch/yolo_dataset_phase1/` ; une image annotée sans boîte est conservée comme exemple négatif, une image ignorée (« Skip ») est exclue ;
- `preview` : images avec les boîtes dessinées, pour contrôle visuel.

Convention de rotation de Label Studio (degrés, sens horaire, autour du coin haut-gauche) implémentée mais **à confirmer visuellement sur les premières boîtes pivotées** (`preview`) : l'unique annotation existante a une rotation de 0,4°, donc ne la prouve pas.

### 3.3 Mutualisation avec le neck reset

La TODO prévoit un « sprint d'annotation manuelle sur Dataset A » (100-200 photos, points sillet/12e frette/chevalet). **Un seul passage sur les 150 images** doit servir les deux besoins : boîtes orientées pour les 10 classes, et, pour `saddle`, `nut` et la 12e frette, les points demandés par le neck reset. À trancher au moment d'ajuster le template : champs de points dans le même projet Label Studio, ou second passage restreint aux images où le manche est visible.

## 4. Corrections à la logique du plan V2.1

1. **Règle Phase 3 « neck connecté à body ET headstock »** : incompatible avec la règle d'annotation (une tête hors cadre n'est pas annotée). Corrigé : un `neck` est conservé s'il touche **au moins une** des deux classes présentes, ou si aucune des deux n'est visible mais que le ratio d'élongation tient.
2. **Oracle de la Phase 4** : Moondream (2B) a été choisi avant l'installation de Qwen3-VL sur le Dell. À réévaluer sur un petit lot avec Qwen3-VL-8B (déjà en place, VRAM partagée).
3. **GPU partagé avec le Portier** : l'entraînement et l'inférence de masse sur le Dell se font **hors des heures de scan**, ou sur une machine louée. Le contexte 8192 laisse déjà ~26 % du modèle sur CPU.
4. **OCR Surya sur les têtes (Phase 6)** : probablement redondant si Qwen local transcrit les crops de tête et de plaque. Décision après les premiers crops réels.
5. **Trois jeux `dataset_a_*` : réconciliés le 2026-10-02.** Ce n'est pas un conflit mais une chaîne : manifeste (1 061 annonces) → `dataset_a_phase0.jsonl` (5 974 photos, filtre OWLv2) → `dataset_a_frontal.jsonl` (606 vues frontales, sous-ensemble). **Source de vérité : `dataset_a_phase0.jsonl`**, déplacé dans `backend/scripts/data/` avec un `README.md` qui détaille les trois étages et leurs limites.

## 5. Étapes

| # | Étape | Qui | Critère de sortie |
|---|---|---|---|
| 1 | Figer la taxonomie, mettre à jour le template Label Studio et `dataset.yaml` | agent | template importé sans erreur |
| 2 | Annoter les 150 images | utilisateur | 150 images traitées, `scratch/verify_yolo_labels.py` OK |
| 3 | Fine-tuning Phase 0 (`yolov8n-obb`, 50 epochs, `imgsz=640`), Dell hors heures de scan | agent | **mAP50-OBB ≥ 0,50** sur 20 % de validation |
| 4 | Inférence de masse + filtres (Phases 2-4 corrigées) | agent | dataset V2 ≥ 500 images validées |
| 5 | Entraînement V2 | agent | mAP50-OBB ≥ 0,70 (val 15 %) et ≥ 0,60 (hors distribution) |
| 6 | Crops décrits par Qwen local, rejeu du Portier sur le lot de référence | agent | gain mesuré face aux photos entières (taux de rejets absurdes, JSON invalides, latence) |

Si l'étape 3 échoue (< 0,50) : +50 images annotées, puis réexamen. Rien n'est branché en production avant l'étape 6.

## 6. Ce qui reste hors du tronc commun (chantier neck reset)

Plan propre : `NECK_RESET_VISION_PLAN.md` et `NECK_RESET_FABLE.md` (v5). Il garde : localisation du chevalet par les cordes, étalon E-E, catalogue de signaux (hauteur de saddle, belly bulge, talon…), Dataset B (fiches, mesures sur les guitares de l'utilisateur), probabilité calibrée. Il **consomme** le détecteur de parties (boîtes de `bridge`, `saddle`, `nut`, `heel`) mais n'en pilote pas le calendrier.
