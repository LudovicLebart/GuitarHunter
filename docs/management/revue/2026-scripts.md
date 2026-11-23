# Constats de revue — section 10 : scripts

Relevés le 2026-11-06 pendant la passe « deepdocument » (commit `7630193`), par docstring, date de commit, analyse syntaxique des imports, essais d'import avec `venv/` et recherche d'appels Firestore ou d'écritures. Les scripts n'ont pas été relus ligne à ligne ni exécutés. Rien n'a été corrigé. Format : voir [README](README.md).

### R-10-1 — Onze scripts interrogent Firestore pour des données qui vivent dans Postgres
- Où : `analyze_funnel_by_user.py`, `audit_rejected_gems.py`, `check_active_search_filter_logs.py`, `compare_image_resolution_by_source.py`, `compare_qwen_flashlite_agreement.py`, `export_dataset_a.py`, `export_neck_reset_sample.py`, `fetch_deal.py`, `find_deal_by_id.py`, `list_users.py` (tous dans `backend/scripts/`), `scripts/build_deals_index.py` ; chacun contient au moins un `.collection(` sur `artifacts/{APP_ID}/users/…`.
- Catégorie : doc-code / bug · Gravité : moyenne
- Constat : `CLAUDE.md` le dit explicitement (« ne plus appeler `.collection()` côté Python : ce sont des restes qui plantent ou lisent des données figées »). Les annonces et les analyses de ces scripts s'arrêtent à septembre 2026 ou sont vides. Les plus sensibles sont ceux qui nourrissent une décision : `export_dataset_a.py` et `export_neck_reset_sample.py` (jeu de données du projet vision), `find_deal_by_id.py` (outil de diagnostic courant), `analyze_funnel_by_user.py` (entonnoir par utilisateur ; `cost_dashboard.py` lit, lui, Postgres).
- Piste : les porter sur `pg_db` ou les archiver ; ajouter un avertissement en tête de ceux qui restent.
- **Corrigé en partie le 2026-11-10** (local, non poussé) : un avertissement en tête des 11 scripts (aucun archivé ni porté : `export_dataset_a.py` est encore cité par `run_script.yml`).

### R-10-2 — Les scripts de la migration terminée peuvent écraser des données vivantes avec des données figées
- Où : `export_firestore_to_postgres.py` (upsert `ON CONFLICT DO UPDATE` via `deal_mapping.build_deal_upsert_sql`, 35 mentions de Firestore), `migrate_cities_to_shared_catalog.py`, `migrate_firestore_prompts.py`, `enrich_cities_coords.py`.
- Catégorie : risque opérationnel · Gravité : moyenne (latent)
- Constat : relancé par erreur contre la base de production avec un `DATABASE_URL` exporté, l'export réécrirait les lignes d'annonces d'après le dernier contenu de Firestore (septembre), c'est-à-dire des analyses plus anciennes que celles de Postgres. Aucun garde-fou ne demande une confirmation ni ne vérifie la date du dernier export. La doc de la migration (`CUTOVER_RUNBOOK.md`) est, elle, marquée « bascule faite ».
- Piste : déplacer ces scripts dans `archive/` (ou les supprimer, Git les garde) ; à défaut, un `--i-know-this-overwrites-production` explicite.

### R-10-3 — Quatre fichiers `test_*.py` de ce dossier sont des essais manuels, pas des tests
- Où : `test_dell_vision_inference.py` (appelle le Dell, installe des modèles), `test_kijiji_scraper.py` (ouvre un navigateur sur Kijiji), `test_notification.py` (envoie des notifications réelles ntfy et e-mail), et `test_export_firestore_to_postgres_integration.py` (écrit dans une base réelle).
- Catégorie : hygiène / piège · Gravité : moyenne
- Constat : leur nom les fait ramasser par `pytest` ou `unittest discover`. La CI utilise des listes explicites, donc rien ne se déclenche aujourd'hui, mais la piste « découverte automatique » du constat R-9-5 les lancerait, avec leurs effets de bord.
- Piste : les renommer (`essai_*.py`, `manual_*.py`) avant toute découverte automatique.

### R-10-4 — `migrate_images.py` ne s'importe plus
- Où : `backend/scripts/migrate_images.py:30` (`from backend.repository import FirestoreRepository`, module supprimé).
- Catégorie : code-mort · Gravité : basse
- Constat (mesuré) : `ModuleNotFoundError: No module named 'backend.repository'`. `ARCHITECTURE.md` le décrit encore comme un outil de migration utilisable.
- Piste : supprimer.

### R-10-5 — Neuf scripts cités par la doc n'existent plus
- Où : `audit_cities.py`, `audit_city_coordinates.py`, `audit_classifications.py`, `audit_facebook_cycles.py`, `backfill_gs_uris.py`, `backfill_sold_scores.py`, `rebuild_index.py`, `register_user.py`, `sample_benchmark_dataset.py` (cités par `ARCHITECTURE.md`, `DATA_FLOW.md`, `TODO.md`, `MULTI_USER_PLAN.md`, `CHANTIER_B_…_PLAN.md`).
- Catégorie : doc-code · Gravité : basse
- Constat : des protocoles de la doc (reconstruire l'index, rétro-remplir des scores) renvoient à des outils absents ; `sample_benchmark_dataset.py` n'existe que sur la branche du benchmark.
- Piste : retirer ou annoter ces mentions (les index de blocs Firestore n'existent plus).

### R-10-6 — `run_once.py` embarque du code de la migration qui n'a plus d'objet
- Où : `backend/scripts/run_once.py` (`_MIGRATION_BRANCH = "claude/firestore-postgres-migration"`, `_extract_branch_files`).
- Catégorie : code-mort / piège · Gravité : basse
- Constat : le script exécuté à chaque déploiement contient une fonction qui extrait des fichiers d'une branche de migration disparue. Un `ACTIVE = True` posé par inattention ferait tenter un `git fetch` de cette branche sur le serveur de production, puis écrire dans `backend/api`.
- Piste : réduire le fichier à un gabarit vide.

### R-10-7 — Pas de documentation d'usage des scripts avant cette passe
- Où : `docs/how-to/` (seul `FICHES_TECHNIQUES.md`), `backend/scripts/data/README.md` et `dataset_b/README.md` pour deux familles.
- Catégorie : doc · Gravité : basse
- Constat : 69 fichiers, dont une dizaine sont utiles tous les jours (coût, qualité du Portier, santé des scrapers, catalogue de villes), sans guide. `scripts.md` en est le premier inventaire ; il manque encore pour chaque script les arguments et un exemple de sortie.
- Piste : un guide `how-to/SCRIPTS.md` pour la dizaine d'outils courants, rédigé avec leurs options réelles.
