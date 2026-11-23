# Plan de restauration, chat d'annonce et détecteur de parties (référence)

> Vérifié le 2026-11-06 contre le commit `267684b`. Cette section regroupe trois sujets dont la plus grande partie est **déjà décrite ailleurs** : le plan de restauration et le chat (tables dans `donnees.md`, routes dans `api.md`, interface dans `frontend.md`) et le détecteur de parties (`backend/auto_annotation/`, lu ici en entier, 13 modules, 50 Ko). Ce fichier ne répète pas ces trois références : il relie les morceaux, donne les règles qui traversent plusieurs couches, et décrit l'état réel du détecteur.

## 1. Plan de restauration

### Rôle
Une liste d'étapes (réparer, régler, remplacer) **personnelle à chaque utilisateur** pour une annonce : préparer l'achat et négocier (guitare aimée), puis suivre les travaux (guitare achetée). Elle alimente la marge réalisée d'une guitare revendue.

### Où c'est défini
| Couche | Fichier | Rôle |
|---|---|---|
| Base | `restoration_plan_items` (`schema.sql`) | une ligne par étape : `deal_id`, `user_id` (sans clé étrangère), `label`, `category`, `status`, `estimated_cost`, `actual_cost`, `notes`, `source` (`user`/`ai`), `proposed_by_message_id`, `item_order`, `photo_urls`, `fiche_slug` |
| API | `restoration_repo.py`, routes `/deals/{id}/restoration-plan…`, `/ws/deals/{id}/restoration-plan` | accès, écritures filtrées par `deal_id` **et** `user_id` |
| Interface | `useRestorationPlan.js`, `DealCard/RestorationPlanPanel.jsx`, `constants/restorationPlan.js` | liste triable par glisser-déposer, photos, totaux |
| Chat | `geminiChatService.js`, `useDealChat.js` | propositions d'étapes et de réordonnancement faites par le modèle |

### Valeurs fermées (côté interface)
Catégories : `structurel`, `cosmetique`, `electronique`, `quincaillerie`, `reglage`, `autre`. Statuts : `pending`, `waiting`, `in_progress`, `done`, `skipped`. **Le serveur ne valide aucune des deux listes** (`category` et `status` sont des chaînes libres dans `main.py`).

### Règles
- **Accès** : l'acheteur de l'annonce, ou un utilisateur qui la voit et l'a mise en favori (`has_plan_access`). Toute écriture exige aussi `user_id = appelant`.
- **Totaux** (calculés dans le navigateur, `useRestorationPlan`) : `totalEstimatedCost` exclut `skipped` ; `remainingCost` somme les coûts estimés des statuts `pending`, `waiting`, `in_progress` ; `spentCost` somme `actualCost` (sinon `estimatedCost`) des étapes `done`.
- **Dépense réalisée côté serveur** : l'index des annonces calcule `restoration_spent` avec la **même règle** en SQL (étapes `done`, coût réel sinon estimé), **pour l'acheteur seulement**. Marge réalisée = revente − prix d'achat − `restoration_spent`. Toute modification de la règle doit se faire des deux côtés.
- **Ordre** : `item_order` ; une étape créée sans ordre déclenche un rattrapage de tout le plan par le premier client qui le charge ; `PATCH …/order` réécrit tous les ordres en une requête.
- **Fiche liée** : `fiche_slug` (slug sans le préfixe `fiche:`) validé à l'écriture (422 si inconnu) ; la lecture du plan efface un lien devenu mort.
- **Étape terminée** : `completed_at` posé et effacé selon le statut (`update_item`).
- **Photos d'étape** : URL dans `photo_urls` (envoi vers Storage `restoration_*`, ou photo déjà présente dans la galerie de l'annonce).
- **Propositions de l'IA** : le modèle propose (`propose_restoration_step`, `propose_restoration_reorder`) ; l'interface valide la forme, affiche Appliquer ou Ignorer, et l'état est gardé dans la proposition elle-même (`deal_chat.restoration_proposals`), jamais appliqué sans clic.

## 2. Chat d'annonce : galerie et requalification
Fonctionnement général : `api.md` (routes, SSE, validation) et `frontend.md` (hook, modèles). Mécanismes propres à cette section :
- **Photo du chat vers la galerie** : le navigateur envoie la photo à Storage (`chat_*`), puis appelle `POST /deals/{id}/gallery` (la galerie de l'annonce est **commune** à tous les utilisateurs) et `PATCH …/chat/{msg}/gallery` (marque la photo comme ajoutée, évite le doublon).
- **Requalification** : le modèle propose de corriger des champs de l'analyse (verdict, un des cinq scores, identification) ; `validateDealRequalificationProposal` borne les valeurs **dans le navigateur** ; « Appliquer » appelle `PATCH …/analysis-overrides` (correction **globale** de la ligne partagée, liste blanche de colonnes, aucune validation de valeur côté serveur) et mémorise la correction dans `manual_analysis_overrides`, que le bot relit à chaque ré-analyse.

## 3. Détecteur de parties de guitare (`backend/auto_annotation/`)

### Rôle prévu
Un détecteur **YOLO-OBB** (boîtes orientées) des parties d'une guitare, pour découper chaque photo en crops utiles (tête, manche, chevalet…), d'abord pour le Portier (garder toutes les photos sous le contexte de 8 192 tokens du Dell), ensuite pour les mesures du projet « neck reset ». Plan d'ensemble : `plans/PARTS_DETECTOR_AND_CROPS_PLAN.md` ; référence technique des phases : `plans/YOLO_OBB_AUTO_ANNOTATION_PLAN.md`.

### État réel au 2026-11-06 : **non branché en production, aucun modèle entraîné**
- Seul `backend/crop_description.py` (lui-même sans appelant hors test, voir `tests/test_crop_manifest_and_description.py`) importe `auto_annotation` ; ni le bot, ni l'API, ni `main.py` ne l'utilisent. Il n'est lancé qu'à la main. Aucun fichier de poids du projet n'est présent (`yolov8n-obb.pt`, `runs/` : absents du dépôt local).
- L'annotation manuelle de la Phase 1 est **à peine commencée** : le dossier local `backend/data/yolo_dataset/` contient 4 fichiers d'étiquettes et un `dataset.yaml` à **5 classes** (`neck`, `headstock`, `heel`, `soundhole`, `saddle`), reliquat d'un essai antérieur, différent de la taxonomie à 10 classes en vigueur.
- Tous ces fichiers sont **non suivis par Git et non ignorés** (voir constat R-8-1).

### Taxonomie (10 classes, figée le 2026-10-02)
`headstock`, `neck`, `heel`, `body`, `bridge`, `saddle`, `nut`, `soundhole`, `pickups`, `plate`. Même ordre dans `config.py::CLASS_NAMES`, `classes.txt` et `label_studio_template_obb.xml`. Règles d'annotation : boîtes orientées, une pièce coupée par le bord de l'image n'est pas annotée, une boîte par micro.

### Deux usages dans le même dossier
**A. Boucle d'annotation assistée (voie actuelle)** : annoter à la main dans Label Studio (SQLite local ou export JSON) → `labelstudio_export` (`progress`, `export` en train/val 80/20 par catégorie avec `dataset.yaml`, `preview`) → `train_phase0` (Ultralytics, `yolov8n-obb.pt`, 50 époques, 640 px, lot de 8, critère **mAP50-OBB ≥ 0,5**) → `preannotate` (propose des boîtes dans Label Studio, seuil 0,25, `--post` par l'API avec `LABEL_STUDIO_TOKEN`, **non testé contre un vrai Label Studio** selon son en-tête) → correction manuelle → répétition. `extract_phase1.py` tire l'échantillon stratifié de 150 images.

**B. Pipeline d'annotation automatique (`main.py`, plan V2.1)** : pour chaque URL de `guitar_deals.storage_image_urls` (curseur serveur), télécharge l'image (≥ 300 px de côté court), inférence YOLO-OBB, **filtre géométrique** (`heuristics.py` : micros et rosace dans le corps s'il est détecté ; manche de ratio ≥ 2 touchant au moins une pièce voisine ; autres classes sans règle), **oracle VLM** (`vlm_client.py` : Moondream via Ollama local, crop redressé, réponse TRUE/FALSE, 30 s), puis export YOLO-OBB (`exporter.py`) vers `dataset_v2/`. Reprise possible (les images déjà exportées sont sautées), 4 images en parallèle. Un avertissement est journalisé si les noms de classes du modèle ne correspondent pas à `CLASS_NAMES`.

### Autres éléments
- `geometry.py` : `parse_obb` (boîte vers rectangle orienté OpenCV), `rotate_and_crop` (crop redressé).
- `post_processing.py` : simple **redirection** vers `backend/production_pipeline/post_processing.py` (route OCR Surya pour `headstock`, route vision pour le reste), elle-même sans appelant.
- `backend/production_pipeline/` : 2 fichiers (76 lignes), `route_crop` et deux fonctions de pré-traitement ; non utilisés.
- Dépendances propres : `backend/auto_annotation/requirements.txt` (`ultralytics`, `opencv-python`, `aiohttp`, `requests`, `numpy`, `torch`, `pytest`), hors `requirements.txt` du bot.

### Tests
`tests/auto_annotation/` : 7 fichiers (configuration, extraction, géométrie, heuristiques, export Label Studio, post-traitement, pré-annotation). **151 tests passent avec l'interpréteur `venv/`** (2026-11-06) ; avec un autre interpréteur sans OpenCV, la collecte échoue (`No module named 'cv2'`). Ces tests ne sont pas dans le job `tests` de `deploy.yml`.

## Pièges et invariants
- Une étape de plan n'existe que pour un couple (annonce, utilisateur) : ne jamais lire ou écrire par le seul `item_id`.
- La galerie, la classification, l'analyse et l'achat d'une annonce sont **communs** ; seuls le favori, le rejet et le plan sont personnels.
- `CLASS_NAMES` doit suivre exactement l'ordre du `dataset.yaml` de l'entraînement, sinon les étiquettes sont fausses sans erreur.
