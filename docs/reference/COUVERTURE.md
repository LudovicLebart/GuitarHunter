# Couverture documentaire — passe « deepdocument » (démarrée le 2026-11-05)

Objectif : la doc décrit **ce que fait réellement le code de `master`/`dev`**. Chaque section est relue contre le code, corrigée, puis marquée ici. Les constats de code (bugs, dette, simplifications) ne sont **pas** mêlés à la doc : ils vont dans `docs/management/revue/` pour la phase d'analyse et de code reviews qui suivra.

## Règles de la passe

- Le code est la source de vérité. Valeurs de configuration, noms de champs et de fichiers sont **recopiés du code**, jamais de la doc existante.
- Une affirmation non vérifiée est marquée `(non vérifié)` ou supprimée.
- Aucune modification de code pendant cette passe. Les écarts de code vont dans `revue/`.
- Journaux et plans historiques ne sont pas réécrits : on ajoute en tête un **statut** (appliqué / en cours / abandonné / branche).
- Édition avec l'outil Edit uniquement (règle `CLAUDE.md`).

## Statut des sections

| # | Section | Statut | Doc touchée | Constats (`revue/`) |
|---|---|---|---|---|
| 0 | Cadrage | fait 2026-11-05 | ce fichier, `revue/README.md` | — |
| 1 | Données et schéma Postgres | fait 2026-11-05 (commit `22e5a1b`) | `donnees.md` (nouveau, référence), `STATE_MODELS.md` (réécrit), `DATA_FLOW.md` (tableau de statut des sections, reste historique en dessous), `ARCHITECTURE.md` (périmètre de la suppression corrigé) | `revue/2026-donnees.md` (8 constats) |
| 2 | Bot : orchestration | fait 2026-11-05 (commit `22e5a1b`) | `bot.md` (nouveau, référence), `ARCHITECTURE.md` (sous-section `main.py` corrigée + renvoi) ; `backend/ha/` renvoyé à la section 9 | `revue/2026-bot.md` (10 constats) |
| 3 | Scraping | fait 2026-11-05 (commit `f1075b3`) | `scraping.md` (nouveau, référence), `ARCHITECTURE.md` (renvoi) ; `scrape_health.py` y est résumé, table `scrape_runs` dans `donnees.md` | `revue/2026-scraping.md` (11 constats) |
| 4 | Pipeline IA 3 tiers | fait 2026-11-05 (commit `c499ca0`) | `ia.md` (nouveau, référence), `ARCHITECTURE.md` (renvoi) ; `STRATEGIE_IA.md` non touché (stratégie et mesures) | `revue/2026-ia.md` (11 constats) |
| 5 | Base de connaissances et fiches | fait 2026-11-05 (commit `c5a5f05`) | `connaissances.md` (nouveau, référence, avec l'état mesuré de la base) ; `how-to/FICHES_TECHNIQUES.md` et `docs/fiches/README.md` relus, cohérents, non modifiés | `revue/2026-connaissances.md` (7 constats) |
| 6 | API FastAPI | fait 2026-11-06 (commit `d9f919e`) | `api.md` (nouveau, référence : 54 routes, auth, WebSocket, chat Claude, alertes) | `revue/2026-api.md` (12 constats, dont 6 de sécurité) |
| 7 | Frontend | fait 2026-11-06 (commit `48d8784`), **relecture partielle** des gros composants | `frontend.md` (nouveau, référence) ; `ARCHITECTURE.md` §3 reste l'historique | `revue/2026-frontend.md` (10 constats) |
| 8 | Plan de restauration, chat, détecteur de pièces | fait 2026-11-06 (commit `267684b`) | `restauration_et_pieces.md` (nouveau : plan de restauration de bout en bout, mécanismes galerie et requalification, détecteur de parties) ; plans `RESTORATION_PLAN_PLAN.md` et `CHAT_GALLERY_REQUALIFICATION_PLAN.md` non relus | `revue/2026-restauration-pieces.md` (6 constats, dont R-8-1 haute) |
| 9 | Exploitation (CI/CD, HA, secrets) | fait 2026-11-06 (commit `96fb034`) | `exploitation.md` (nouveau, avec l'état réel du serveur relevé en lecture seule) ; `scraping.md` (tests) corrigé | `revue/2026-exploitation.md` (11 constats, dont R-9-1 haute) + R-3-12 |
| 10 | Scripts | fait 2026-11-06 (commit `3f4592b`), **inventaire, scripts non relus ligne à ligne** | `scripts.md` (nouveau : classement par famille, état Firestore, scripts absents) | `revue/2026-scripts.md` (7 constats) |
| 11 | Plans, TODO, journal, aperçu | fait 2026-11-06, **plans non relus en entier** | `plans/README.md` (nouveau : état réel des 21 plans et des branches) ; `TODO.md` (lien cassé corrigé, item « dérive » mis à jour, pas de purge) ; `PROJECT_OVERVIEW.md` vérifié | `revue/2026-plans-todo.md` (7 constats) |
| 12 | Clôture | fait 2026-11-06 | liens relatifs contrôlés (0 réellement cassé) ; fichiers cités absents inventoriés (voir `revue/SYNTHESE.md`) | `revue/SYNTHESE.md` (101 constats classés en 4 lots) |

## Carte module → doc

| Code | Doc actuelle | Section |
|---|---|---|
| `main.py`, `backend/bot.py`, `backend/services.py`, `config.py` (hors `T1_*`/`T3_*`) | `reference/bot.md` (référence) ; `ARCHITECTURE.md` §2 = historique | 2 |
| `backend/ha/` | `ARCHITECTURE.md` (sous-section `backend/ha/`), `plans/DB_REDUNDANCY_DELL_PLAN.md` | 9 |
| `backend/scraping/` (Facebook, Kijiji), `scraping_leboncoin/`, `scrape_health.py` | `reference/scraping.md` (référence) ; `ARCHITECTURE.md` = historique | 3 |
| `backend/analyzer.py`, `llm_clients.py`, `t1_*.py`, `t3_claude_tools.py`, `taxonomy.py`, `llm_usage.py`, `prompts.json`, `config.py` (`T1_*`/`T3_*`) | `reference/ia.md` (référence) ; `plans/STRATEGIE_IA.md` = stratégie et mesures ; `ARCHITECTURE.md` = historique | 4 |
| `backend/guitar_knowledge.py`, `api/fiches_repo.py`, `backend/knowledge/`, `docs/fiches/`, `seed_*`, `import_guitar_knowledge_wikidata.py`, `knowledge_*.py`, `t1_kb_paired_replay.py` | `reference/connaissances.md` (référence) ; `how-to/FICHES_TECHNIQUES.md` (guide) ; `STRATEGIE_IA.md` §3 (stratégie) | 5 |
| `backend/pg_repository.py`, `pg_db.py`, `deal_mapping.py`, `api/schema.sql`, `api/db.py` | `reference/donnees.md` (référence), `STATE_MODELS.md` ; `DATA_FLOW.md` = historique + logique métier | 1 |
| `backend/api/*` | `reference/api.md` (référence) ; `plans/PERF_API_INDEX_PLAN.md` ; `ARCHITECTURE.md` = historique | 6 |
| `src/`, `index.html`, `main.jsx`, `storage.rules` | `reference/frontend.md` (référence) ; `UI_UX_ANALYSIS.md` ; `ARCHITECTURE.md` §3 = historique | 7 |
| `backend/api/restoration_repo.py`, `chat_*`, `backend/auto_annotation/`, `production_pipeline/`, `crop_description.py` | `reference/restauration_et_pieces.md` (référence) ; `plans/RESTORATION_PLAN_PLAN.md`, `PARTS_DETECTOR_AND_CROPS_PLAN.md` ; `ARCHITECTURE.md` §5 = historique | 8 |
| `.github/workflows/*`, `backend/scripts/run_once.py`, `backend/ha/`, `run_ha_watchdog.py`, `backup_postgres.py`, `ha_return_to_normal.sh` | `reference/exploitation.md` (référence) ; `plans/DB_REDUNDANCY_DELL_PLAN.md`, `CUTOVER_RUNBOOK.md` ; `ARCHITECTURE.md` = historique | 9 |
| `backend/scripts/`, `backend/benchmark/`, `scripts/` | `reference/scripts.md` (référence) | 10 |
| `docs/management/*`, `docs/explanation/*` | — | 11 |

## Branches actives (état relevé le 2026-11-05)

Aucune de ces branches n'est dans `master`. Elles ont forké **avant** la bascule Postgres : elles utilisent encore `repository.py`/`services.py` (Firestore). La doc de `master` ne les décrit donc pas ; leur contenu est décrit dans les plans.

| Branche | Sujet | Avance / retard sur `origin/master` | Dernier commit | Doc de référence |
|---|---|---|---|---|
| `claude/guitar-condition-vision-pipeline-uj6jj4` | Reconnaissance par image (état du manche, Dataset A/B, SAM2/OWLv2, détection de frettes) | +20 / −633 | 2026-10-10 | `plans/NECK_RESET_VISION_PLAN.md`, `NECK_RESET_FABLE.md` |
| `claude/guitarhunter-benchmark-setup-h9q9gr` | Évaluation et amélioration des IA (benchmark, juge, Qwen, perception, coûts) | +80 / −519 | 2026-10-10 | `plans/CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md`, `COST_OPTIMIZATION_CHANTIERS.md` |
| `claude/guitar-hunter-leboncoin-1prbyl` | LeBonCoin, base commune `scraping_common` | +33 / −734 | 2026-10-10 | `ARCHITECTURE.md` de la branche |
| `claude/scraper-stealth-mutualization` | Furtivité mutualisée (`scraping/stealth.py`) | +1 / −589 | 2026-08-24 | journal de branche |
| `ccr-e759704a-jpvqmr` | Portier : normalisation de la classification, ré-évaluation des NOT_PROMOTED | +3 / −157 | 2026-10-30 | — (à vérifier : fusionné ou non) |
| `ccr-a6708397-9dr6ta` | Brouillon de fiche (fissure de table) | 0 / −50 | 2026-10-30 | déjà contenu dans `master` |

À noter : le `master` **local** est resté au 2026-09-24 (`bac63b1`) ; `origin/master` est à jour. Toute comparaison doit se faire contre `origin/master`.

Le RAG (mentor, perception locale) est décrit dans `plans/LOCAL_PERCEPTION_AND_MENTOR_RAG_PLAN.md` ; aucune branche dédiée n'existe (confirmé par l'utilisateur le 2026-11-06).

## Gabarit d'une section de référence

Chaque fichier de référence produit pendant la passe suit ce plan, dans cet ordre :

1. **Rôle** — une phrase.
2. **Fichiers** — chemins, avec la taille ou le nombre de lignes.
3. **Fonctionnement** — flux réel, pas l'historique.
4. **Interfaces** — fonctions/routes/tables exposées, entrées/sorties, erreurs.
5. **Configuration** — variables, valeurs par défaut (relevées dans le code).
6. **Pièges et invariants.**
7. **Tests** — quels fichiers couvrent quoi.
8. **Vérifié le AAAA-MM-JJ contre le commit `xxxxxxx`.**

## Découpage prévu d'`ARCHITECTURE.md` (197 Ko, 680 lignes)

Plus gros blocs mesurés : `DealCard.jsx` 47 Ko, `analyzer.py` 25 Ko, `bot.py` 21 Ko, `useDealsManager.js` 13 Ko, Kijiji 12 Ko, scraping 8 Ko. Les sections « Firestore : cœur du système » et « Security Rules » décrivent l'état d'avant la bascule Postgres : à vérifier et à réécrire ou archiver en section 1.

Le découpage se fait au fil des sections (un fichier par section, `ARCHITECTURE.md` devient un sommaire) :
`reference/bot.md`, `scraping.md`, `ia.md`, `api.md`, `frontend.md`, `exploitation.md`, `donnees.md`.
