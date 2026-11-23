# Scripts d'exploitation, de diagnostic et de rejeu (référence)

> Vérifié le 2026-11-06 contre le commit `7630193` : les 69 fichiers de `backend/scripts/` (68 `.py`, `.sh`, `.ps1`, `.sql`, plus un fichier d'état LeBonCoin) et ses dossiers `data/`, `dataset_b/`, `experiments/`, `backend/benchmark/` (4 fichiers), `scripts/build_deals_index.py`, les références croisées avec la doc, la CI et le code. Méthode : première ligne de docstring et date du dernier commit de **chacun** (relevées par programme), détection des imports cassés (par analyse syntaxique puis essai d'import avec `venv/`), recherche des appels Firestore et des écritures. **Les scripts n'ont pas été relus ligne à ligne et aucun n'a été exécuté.** Un agent Haiku a relevé en parallèle les options et les écritures ; ses résultats ne sont utilisés que pour contrôle.

## Règles communes
- **Les scripts ne lisent pas `.env`** : exporter `DATABASE_URL` avant de lancer (`export DATABASE_URL="$(grep -h '^DATABASE_URL=' .env | tail -1 | cut -d= -f2- | tr -d '\r')"` sur le serveur).
- Lancer depuis la racine du dépôt, avec `venv/` (certains exigent OpenCV, Ultralytics ou Playwright).
- Ceux qui écrivent ont presque tous un mode d'essai (`--dry-run`, ou `--apply` pour `repair_fb_city_ids.py`) : l'utiliser d'abord. Fiches et base de connaissances : voir `connaissances.md`.
- Les fichiers de résultats (`backend/benchmark/results/`, `backend/scripts/data/dataset_a_*.jsonl`, `truth_candidates*.jsonl`, `t3_replay*`) sont **locaux et ignorés par Git** (titres et identifiants d'annonces, dépôt public).

## 1. Exploitation (actifs, utilisés par le déploiement, le cron ou systemd)
| Script | Rôle |
|---|---|
| `run_once.py` | action ponctuelle exécutée à chaque déploiement, inactif par défaut (`ACTIVE = False`) ; son corps contient encore du code de la migration Firestore, jamais réutilisé |
| `backup_postgres.py` | `pg_dump` vers Firebase Storage, 14 copies, cron nocturne (voir `exploitation.md`) |
| `run_ha_watchdog.py`, `ha_return_to_normal.sh` | démon de haute disponibilité et retour à la normale manuel |
| `seed_guitar_fiches.py` | chargement des fiches à chaque déploiement |
| `set_admin_claim.py` | pose ou retire le claim Firebase `admin` d'un compte |
| `install_ollama_qwen_dell.sh` | installation d'Ollama et de Qwen3-VL sur le Dell |
| `list_users.py` | liste des utilisateurs (lit Firestore : voir §6) |

## 2. Catalogue de villes
| Script | Rôle |
|---|---|
| `audit_city_catalog_duplicates.py`, `merge_city_catalog_duplicates.py` | diagnostic des doublons du catalogue, puis fusion (`--dry-run`) |
| `fix_cities_missing_coords.py` (`--dry-run`) | complète les coordonnées manquantes |
| `audit_fb_city_ids.py`, `list_fb_city_candidates.py`, `repair_fb_city_ids.py` | vérifient les identifiants Facebook des villes avec `CityFinder` ; la réparation exige `--apply`, après lecture du rapport |
| `fetch_kijiji_locations.py` | régénère `backend/resources/kijiji_locations.json` (arbre de lieux de Kijiji) |
| `diag_kijiji_locations_scope.py` | diagnostic ponctuel du paramètre `q` de Kijiji (terminé) |
| `enrich_cities_coords.py`, `migrate_cities_to_shared_catalog.py` | migrations d'avril 2026 sur Firestore (terminées, voir §6) |

## 3. Mesure, coût et santé (lecture seule sur Postgres)
`cost_dashboard.py` (coût par poste, tarifs de `llm_pricing.py`), `t1_period_report.py` (qualité du Portier par période), `scrape_health_report.py` (table `scrape_runs`), `study_visual_dependence.py` (part des verdicts de l'Analyste qui dépend des photos), `diag_t1_image_budget.py` (pourquoi 8 photos faisaient halluciner le Portier local), `diag_seller_id.py` (les pages exposent-elles un identifiant de vendeur ?), `truth_candidates.py` (annonces où l'utilisateur a laissé une trace humaine, pour une vérité terrain).

## 4. Rejeux et évaluation des modèles
| Script | Rôle |
|---|---|
| `replay_t3.py`, `replay_t3_digest.py`, `replay_t3_links.py`, `replay_t3_blind.py` | rejeu de l'Expert (Gemini Pro contre Claude Sonnet 5.5), lecture des résultats, liens des annonces, page d'examen à l'aveugle (le HTML généré lit une base Firestore côté navigateur) |
| `t1_kb_paired_replay.py`, `compare_knowledge_effect.py` | rejeu apparié du Portier sans/avec la base de connaissances et comparaison (critères dans `connaissances.md`) |
| `compare_qwen_local_vs_prod.py`, `crop_manifest.py` | comparaison du Portier local au verdict de production ; manifeste de crops pour le banc « photos entières contre crops » |
| `compare_qwen_flashlite_agreement.py`, `audit_rejected_gems.py`, `check_active_search_filter_logs.py` | diagnostics des chantiers G et H (Firestore : voir §6) |
| `backend/benchmark/` | banc d'essai du chantier B : `run_benchmark.py`, modèles candidats (`candidates.py`), juge Claude (`judge.py`), jeu `dataset.json`, trois consignes de Portier (`instructions/`) ; huit fichiers de résultats locaux |
| `analyze_funnel_by_user.py`, `compare_image_resolution_by_source.py` | entonnoir par utilisateur ; résolution des images par source (Firestore) |

## 5. Base de connaissances
`import_guitar_knowledge_wikidata.py`, `seed_guitar_knowledge.py`, `knowledge_*.py` (7 fichiers) : décrits dans `connaissances.md`.

## 6. Vision (neck reset, détecteur de parties) et essais
| Script | Rôle |
|---|---|
| `export_dataset_a.py`, `export_neck_reset_sample.py`, `download_phase1_images.py`, `run_phase0_usability_filter.py` | constitution du « Dataset A » et filtre d'utilisabilité OWLv2 (les deux premiers lisent Firestore) |
| `dataset_b/` | collecte manuelle de mesures réelles : 4 CSV, générateurs des deux fiches imprimables, `build_db.py` |
| `experiments/` | prototypes de détection de frettes, d'OWLv2 et de SAM 2, `yolo_annotation/` (une douzaine d'essais d'annotation automatique : Florence, Grounding DINO, Gemini, un annotateur web) |
| `setup_auto_annotation.ps1` | installation du pipeline d'annotation (voir `restauration_et_pieces.md`) |
| `test_dell_vision_inference.py`, `test_kijiji_scraper.py`, `test_notification.py` | **essais manuels**, malgré leur nom : ce ne sont pas des tests automatiques |
| `leboncoin_login_once.py`, `leboncoin_probe.py` | calibration et sondage LeBonCoin (non branché, voir `scraping.md`) |
| `compare_fb_anon_vs_auth.py` | compare le scraper Facebook anonyme et connecté (script unique) |

## 7. Migration Firestore → Postgres et reliquats Firestore
Terminée en septembre 2026. Depuis le 2026-11-08 (R-10-2), `export_firestore_to_postgres.py`, `compare_firestore_postgres.py`, `migrate_cities_to_shared_catalog.py`, `migrate_firestore_prompts.py`, `enrich_cities_coords.py` et les deux essais de l'export (renommés `essai_export_firestore_to_postgres*.py`) sont dans `backend/scripts/archive/` (voir son `README.md` : **ne pas les relancer**). Reste en place : `migrate_images.py` (**import cassé** : `backend.repository` n'existe plus).
**Scripts qui interrogent encore Firestore pour des données qui vivent maintenant dans Postgres** (`CLAUDE.md` signale ce piège : ils lisent des données figées ou vides) : `analyze_funnel_by_user.py`, `audit_rejected_gems.py`, `check_active_search_filter_logs.py`, `compare_image_resolution_by_source.py`, `compare_qwen_flashlite_agreement.py`, `export_dataset_a.py`, `export_neck_reset_sample.py`, `fetch_deal.py`, `find_deal_by_id.py`, `list_users.py`, et `scripts/build_deals_index.py` à la racine (reconstruit l'ancien index en 20 blocs Firestore, supprimé).

Depuis le 2026-11-10 (R-10-1), ces onze scripts portent un avertissement en tête et l'affichent sur `stderr` à l'exécution ; aucun n'a été porté sur Postgres ni archivé.

## 8. Tests dans ce dossier
`test_repair_fb_city_ids.py` (dans la CI) ; les trois essais manuels du §6 ne sont pas des tests (liste d'exclusion explicite dans `backend/test_ci_coverage.py`).

## Scripts cités dans la doc mais absents du dépôt
`audit_cities.py`, `audit_city_coordinates.py`, `audit_classifications.py`, `audit_facebook_cycles.py`, `backfill_gs_uris.py`, `backfill_sold_scores.py`, `rebuild_index.py`, `register_user.py`, `sample_benchmark_dataset.py` (cités par `ARCHITECTURE.md`, `DATA_FLOW.md`, `TODO.md` ou des plans ; le dernier n'existe que sur la branche du benchmark).
