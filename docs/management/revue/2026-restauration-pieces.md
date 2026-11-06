# Constats de revue — section 8 : plan de restauration, chat d'annonce, détecteur de parties

Relevés le 2026-11-06 pendant la passe « deepdocument » (commit `267684b`). Rien n'a été corrigé. Format : voir [README](README.md). Une grande partie des défauts du plan et du chat est déjà dans les sections 1, 6 et 7 (R-1-2, R-6-2, R-6-5, R-6-10) ; seuls les points propres à cette section sont listés.

### R-8-1 — Des photos d'annonces et des fichiers de travail non suivis, non ignorés, partiraient dans un `git add -A`
- Où : `git status` (non suivis, absents de `.gitignore`) : `backend/data/yolo_dataset/` (images d'annonces, 470 Ko), `backend/scripts/experiments/yolo_annotation/yolo_dataset/` (342 Ko), `backend/scripts/data/blind_answers/`, `frontal_filter_results/`, `img_0000.jpg`, `fable_prototype_results.jpg`, `gemini_genai_test.jpg`, `pydantic_test.jpg`, `firestore-debug.log`, `gemini_filter.log`, `cors.json`, `gemini_audit_*.html`, `GATEKEEPER_ERRORS_REPORT_2026-09-23.md`, `docs/SpecialisationLLM.txt`… Les skills `/git-push-dev` et `/git-push-dev-master` exécutent `git add -A`.
- Catégorie : sécurité / confidentialité · Gravité : haute (le dépôt est **public**)
- Constat : `CLAUDE.md` interdit de versionner des titres, URL ou identifiants d'annonces. Les photos de vendeurs de Marketplace, les identifiants d'annonces qui nomment les fichiers (`1127334693794334_0.txt`), des journaux locaux et des rapports d'audit se retrouveraient publiés au prochain push fait avec ces skills. Seul `scratch/` est ignoré parmi les dossiers de travail. Jusqu'ici les commits de cette passe ont utilisé des chemins explicites.
- Piste : ignorer `backend/data/`, `**/yolo_dataset/`, `frontal_filter_results/`, les `*.log`, les images à la racine et `cors.json` ; changer les skills pour montrer `git status` et exiger une liste de fichiers, jamais `add -A`.

### R-8-2 — L'interface propose le plan de restauration pour une guitare achetée par quelqu'un d'autre
- Où : `src/components/DealCard/DealAnalysisModal.jsx:55` (`canPlanRestoration = isPurchased || deal.isFavorite`), `src/hooks/useRestorationPlan.js:25`, `purchased_by_user_id` jamais comparé à l'utilisateur (une seule occurrence dans `src/`, `StatsView.jsx:149`).
- Catégorie : bug · Gravité : moyenne
- Constat : `isPurchased` est un fait global (voir `donnees.md`). Pour un utilisateur qui voit une annonce achetée par un autre, l'interface affiche le bloc « Achetée » et active le plan, qui appelle l'API ; celle-ci répond 404 (ni acheteur ni favori), ce que le hook affiche comme une erreur. Le bouton d'achat, lui, répondra 409.
- Piste : comparer `purchasedByUserId` à l'uid, et masquer les actions d'achat pour les annonces d'un autre.

### R-8-3 — Aucune validation serveur des catégories et statuts d'étape
- Où : `main.py:881-889, 925-932` (`category`, `status`, `label` en `str` libre), `restoration_repo.py:update_item`.
- Catégorie : robustesse · Gravité : basse
- Constat : un statut inconnu est accepté et enregistré, puis ignoré par les totaux (ni ouvert, ni terminé) et par `restoration_spent`. Les listes fermées n'existent que dans `constants/restorationPlan.js`.
- Piste : `Literal[...]` Pydantic ou contrainte `CHECK` en base.

### R-8-4 — Détecteur de parties : quasi inerte, ses fichiers de travail sont dispersés
- Où : `backend/auto_annotation/` (13 modules), `backend/production_pipeline/` (2 fichiers), `backend/crop_description.py`, `backend/data/yolo_dataset/dataset.yaml` (5 classes).
- Catégorie : code-mort / décision en suspens · Gravité : basse
- Constat : aucun modèle n'est entraîné, la Phase 1 n'a que 4 étiquettes, rien n'est appelé par le bot. Le `dataset.yaml` local décrit 5 classes alors que la taxonomie en vigueur en compte 10 ; `post_processing.py` est une redirection vers `production_pipeline/`, elle-même sans appelant. L'avancement réel est tenu dans les plans, pas dans le code. C'est un chantier assumé (priorité basse dans `TODO.md`), pas un défaut ; à garder pour la phase de décision (conserver, isoler dans une branche, ou archiver).

### R-8-5 — Tests du détecteur : dépendance silencieuse à un interpréteur précis, absents de la CI
- Où : `tests/auto_annotation/` (7 fichiers), `deploy.yml` (job `tests` : aucun test de ce dossier).
- Catégorie : test · Gravité : basse
- Constat (mesuré) : 151 tests passent avec `venv/`, la collecte échoue avec un autre Python (`No module named 'cv2'`). Le job `tests` de la CI ne les exécute pas : une casse du détecteur ne bloquerait aucun déploiement, ce qui est cohérent tant qu'il n'est pas branché.
- Piste : à décider avec R-8-4.

### R-8-6 — Scripts et en-têtes d'annotation avec des chemins locaux fixes
- Où : `labelstudio_export.py:28-31` (`scratch/label_studio_data/…`, `scratch/dataset_phase1`, projet « GuitarHunter OBB Phase 1 »), `config.py` (`OLLAMA_API_URL = http://localhost:11434`, `OUTPUT_DIR = dataset_v2`).
- Catégorie : hygiène · Gravité : basse
- Constat : les chemins supposent la machine de travail de l'auteur (`scratch/` est ignoré par Git). Sur une autre machine, les outils échouent sans message explicite, hormis `--sqlite`, `--images-dir` et `--out`.
