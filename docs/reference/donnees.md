# Données — schéma Postgres et accès (référence)

> Vérifié le 2026-11-05 contre le commit `22e5a1b` (`backend/api/schema.sql`, `backend/pg_repository.py`, `backend/deal_mapping.py`, `backend/api/*_repo.py`, `main.py`). Ce fichier **remplace** `DATA_FLOW.md` (Firestore) et `STATE_MODELS.md` (anciens contrats) pour tout ce qui concerne la base ; ceux-ci ne gardent que ce qui est encore vrai ou marqué historique.

## Rôle

La base Postgres du serveur est la seule source de vérité des annonces, de la configuration des utilisateurs, des commandes, des journaux et de la mesure d'usage des modèles. Firebase ne garde que **Auth** (connexion) et **Storage** (photos) ; Firestore ne sert plus qu'au bail de haute disponibilité (`backend/ha/`).

## Fichiers

| Fichier | Rôle |
|---|---|
| `backend/api/schema.sql` (747 lignes) | **Seule définition du schéma**, idempotente, rejouée en entier à chaque démarrage |
| `backend/api/db.py` | Pool asyncpg de l'API ; décodeurs JSON/JSONB ; joue `schema.sql` |
| `backend/pg_db.py` | Pool psycopg synchrone du bot, des scripts et de `analyzer.py` ; joue le même `schema.sql` |
| `backend/pg_repository.py` | `PostgresRepository` : accès SQL du bot (un objet par utilisateur) |
| `backend/api/*_repo.py` | Accès SQL de l'API, une table ou un domaine par fichier |
| `backend/deal_mapping.py` | Correspondance document d'annonce ↔ colonnes (`DEAL_COLUMNS`, `DEAL_FIELD_TO_COLUMN`, `build_deal_upsert_sql`) |
| `backend/api/index_version.py` | Compteur de version de l'index (ETag), alimenté par `LISTEN` |

Le DSN vient de `DATABASE_URL` (défaut `postgresql://guitarhunter@localhost/guitarhunter`) ; les deux pools retirent les `\r` et espaces parasites du DSN.

## Modèle multi-utilisateur

- **`guitar_deals` est un catalogue partagé** : une annonce réelle = une ligne, scrapée et analysée **une seule fois** quel que soit le nombre d'utilisateurs concernés.
- **Qui voit quoi** : `user_deal_matches (user_id, deal_id)`. Toute lecture ou mutation côté API passe par une jointure ou un `EXISTS` sur cette table.
- **Préférences personnelles** : `user_deal_state (user_id, deal_id, is_favorite, is_rejected)`. Pas de ligne = ni favori ni rejeté. Le rejet manuel est **par utilisateur** ; le rejet automatique par verdict IA reste un fait sur `guitar_deals`.
- **L'achat est un fait global** : `is_purchased`, `purchased_by_user_id`, `purchase_price`, `purchased_at` sur `guitar_deals` (une guitare achetée l'est pour tous). `user_sale_price`/`user_sold_at` : revente par l'acheteur.
- Isolation : pas de règles de sécurité en base, c'est le code qui filtre par `user_id` (uid Firebase).

## Tables

### Utilisateurs et commandes
| Table | Colonnes principales | Notes |
|---|---|---|
| `users` | `uid` (PK), `bot_status` (défaut `idle`), `config` JSONB, `created_at`, `updated_at` | `config` porte `scanConfig`, `analysisConfig`, `exclusionKeywords`, `availableModels`… (voir ci-dessous). Créée vide par `POST /users/me`, remplie par `PostgresRepository.ensure_initial_structure` |
| `commands` | `id`, `user_id` (FK cascade), `type`, `payload` JSONB, `status` (`pending` → `completed`/`failed`), `error_message`, `created_at`, `completed_at` | Bus Frontend → Bot. Le front écrit par `POST /commands`, le bot lit en SQL direct. Index partiel sur `status='pending'` |
| `logs` | `id`, `user_id` (FK cascade), `message`, `level`, `created_at` | Fenêtre glissante de 30 jours |
| `logs_archive` | mêmes colonnes, `id` repris tel quel | Rempli chaque jour à 03:20 par `log_retention.run_pg_log_archive_job`, purgée après 12 mois. Aucune API ne l'expose |
| `scrape_runs` | `user_id`, `source` (`facebook`/`kijiji`), `city_id`, `city_name`, `query`, `outcome`, `detail`, `cards_seen`, `out_of_list`, `kept`, `duration_ms`, `alerted_at` | Une ligne par scan de ville. Jamais de titre ni d'URL d'annonce. Purge à 90 jours (`purge_scrape_runs`, fin de cycle) |

### Annonces
| Table | Contenu |
|---|---|
| `guitar_deals` (clé `id` texte) | Identité (`title`, `link`, `location`, `latitude`, `longitude`, `description`, `published_at_raw`, `published_at_ts` epoch en secondes), prix (`price`, `original_price`, `price_drop_amount`), cycle de vie (`status`, `sold_at`, `sold_notes`, `timestamp`), analyse IA (`verdict`, `classification`, `classification_rejected`, `brand`, `model_name`, `production_year`, `country_of_origin`, `color`, `finish_*`, 5 scores `SMALLINT`, `model_used`, `tier3_trigger`, `also_qualifies_pepite`, `estimated_gross_margin`), verdict d'origine du Portier (`gatekeeper_verdict/brand/classification`, `initial_verdict`, `initial_model_used`), corrections manuelles (`manual_classification`, `manual_analysis_overrides`), achat/revente, photos (`image_urls` CDN Facebook périssables, `storage_image_urls` et `storage_image_gs_uris` Firebase Storage), `ai_analysis_raw` JSONB (tout le reste de l'analyse, dont `reasoning`), `scraped_by_node` |
| `user_deal_matches` | `(user_id, deal_id)` PK, `matched_at` ; cascade des deux côtés |
| `user_deal_state` | `(user_id, deal_id)` PK, `is_favorite`, `is_rejected`, `updated_at` ; index partiels sur favoris et rejets |
| `deal_chat` | `id`, `deal_id` (cascade), `role`, `parts` JSONB, `display_text`, `created_at` + `attached_image_part_indices`, `restoration_proposals` (l'état Appliquer/Ignorer est **dans** chaque élément), `added_to_gallery_urls`, `photo_recall`, `is_error`, `requalification_proposal` |
| `restoration_plan_items` | `id`, `deal_id` (cascade), `user_id` (**sans clé étrangère**), `label`, `category`, `status` (défaut `pending`), `estimated_cost`, `actual_cost`, `notes`, `source` (`user`/`ai`), `proposed_by_message_id` (→ `deal_chat`, `SET NULL`), `item_order`, `photo_urls`, `fiche_slug` (sans clé étrangère), `created_at`, `updated_at`, `completed_at` |
| `shared_deals` | `id` = id de l'annonce, `snapshot` JSONB opaque, `created_at`. Lisible sans authentification (page de partage) |

### Villes
- `cities` : catalogue partagé (`id`, `name`, `latitude`, `longitude`, `needs_review`, `created_by`, `fb_location_id`). Le scraper Facebook utilise `COALESCE(fb_location_id, id)`.
- `user_city_prefs` : `(user_id, city_id)` PK, `active` (défaut `false`), `kijiji_radius_km`. Pas de ligne = ville non scannée.

### Modèles et connaissances
- `llm_usage` : une ligne par appel de modèle (backend **et** chat) : `source`, `provider`, `model`, `action`, `deal_id` (sans clé étrangère), `user_ref`, `images`, tokens (`input` qui inclut `cached`, `output`, `thoughts`, `cache_write`), `latency_ms`, `ok`, `error_type`. Écrite au mieux : un échec d'insertion ne bloque jamais une analyse.
- `guitar_knowledge` (marques, séries, usines, **et fiches** via `kind='fiche'`), `guitar_knowledge_alias`, `guitar_knowledge_source`, `guitar_knowledge_versions`, `guitar_knowledge_fiche` (corps Markdown, catégorie, statut, `content_hash`). Colonnes importées (réécrites à chaque import) et colonnes curées (jamais touchées par l'import) ne se mélangent pas. Toute lecture filtre par `kind`. Détail en section 5.

## Notifications temps réel (`pg_notify`)

Des triggers au niveau base notifient quelle que soit l'origine de l'écriture (bot ou API).

| Canal | Trigger | Déclencheurs | Consommateur |
|---|---|---|---|
| `deal_changes` | `guitar_deals_notify` | INSERT, UPDATE, DELETE de `guitar_deals` | `ws_deals`, `index_version` |
| `deal_changes` | `user_deal_state_notify` | INSERT, UPDATE de `user_deal_state` | idem |
| `deal_changes` | `user_deal_matches_notify` | INSERT, DELETE de `user_deal_matches` | idem (une annonce neuve devenait invisible au WebSocket sans lui) |
| `user_config_changes` | `users_notify` | INSERT, UPDATE de `users` | `ws_user_config` (`/ws/users/me/config`) |
| `chat_changes` | `deal_chat_notify` | INSERT, UPDATE de `deal_chat` | WebSocket du chat d'une annonce |
| `restoration_plan_changes` | `restoration_plan_items_notify` | INSERT, UPDATE, DELETE | WebSocket du plan, `index_version` |
| `city_prefs_changes` | `user_city_prefs_notify` | INSERT, UPDATE, DELETE | `/ws/cities` |
| `cities_catalog_changes` | `cities_notify` | INSERT, UPDATE de `cities` | `/ws/cities` (diffusé à tous) |

Le payload ne porte que des identifiants (`{"id"}`, `{"deal_id","id"}`, …) : le client relit ensuite par REST. Le filtrage par utilisateur se fait côté serveur WebSocket, pas par un canal par uid.

## Valeurs d'état relevées dans le code

### `users.bot_status`
Écrit par `set_status` du bot : `idle`, `scanning`, `scanning_url`, `cleaning`, `reanalyzing`, `reanalyzing_all`, `reevaluating_not_promoted`, `paused`. L'interface de l'administrateur colore aussi `stopped`. La suppression d'un utilisateur est refusée en `scanning`/`scanning_url`.

### `commands.type` (table de dispatch de `main.py`)
`REFRESH`, `CLEANUP`, `REANALYZE_ALL`, `SCAN_URL`, `ADD_CITY`, `ANALYZE_DEAL`, `REEVALUATE_NOT_PROMOTED`, `CLEAR_LOGS`, `STOP_BOT`, `STOP_SCAN`, `START_BOT`. Les commandes longues partent dans un thread démon ; `STOP_BOT` et `START_BOT` posent des événements.

### `guitar_deals.status`
- Écrits à la création/ré-analyse : `analyzed`, `rejected` (verdict `REJECTED`, mot-clé d'exclusion).
- Autres : `sold` (posé avec `sold_at`), `retry_analysis` (file de ré-analyse, posée par `mark_all_for_reanalysis`), `analysis_failed` (échec, avec message).
- `analyzing` / `analyzing_expert` : états transitoires du **front** avant l'envoi de `ANALYZE_DEAL` (non relevés côté bot).

### `guitar_deals.verdict`
Verdicts affichés par le front (`src/constants.js`) : `PEPITE`, `FAST_FLIP`, `LUTHIER_PROJ`, `CASE_WIN`, `COLLECTION`, `FAIR`, `BAD_DEAL`, `REJECTED_ITEM`, `REJECTED_SERVICE`, `INCOMPLETE_DATA`, `NOT_PROMOTED`, plus les verdicts hérités `GOOD_DEAL` et `REJECTED`. `ARCHIVE_GROUP` (masqués de la vue par défaut) : `BAD_DEAL`, `REJECTED_ITEM`, `REJECTED_SERVICE`, `INCOMPLETE_DATA`, `REJECTED`, `SOLD`, `NOT_PROMOTED`. `ERROR` et `MANUAL_RETRY` apparaissent dans l'analyse brute (voir `CLAUDE.md`). Sémantique détaillée des verdicts : section 4.

## Contenu de `users.config`
Initialisé par `bot.py::_init_db_structure` : `exclusionKeywords`, `scanConfig`, `botStatus`, `analysisConfig` (`gatekeeperModel`, `mainModel`, `expertModel` — clé héritée —, `mainAnalysisPrompt`, `gatekeeperVerbosityInstruction`, `analystVerbosityInstruction`, `expertProContextInstruction`), `availableModels`. D'autres clés sont ajoutées ensuite par l'application (inventaire complet en section 2 : `scanConfig`, Recherche Active, `chatModel`…). `get_user_config()` renvoie `config` + `botStatus` tiré de la colonne `bot_status`.

## Cycle d'une annonce (côté bot)
1. `handle_deal_found` : écarte une fiche vide (0 photo **et** prix 0), les annonces hors budget (rien d'écrit), applique les mots-clés d'exclusion (`rejected`).
2. Si `get_deal_by_id` trouve déjà la ligne (autre utilisateur) : pas d'appel IA, seulement `record_deal_match`.
3. Sinon photos vers Firebase Storage, `analyze_deal`, puis `create_new_deal` : upsert via `build_deal_upsert_sql`, `initial_verdict` et `initial_model_used` figés, puis `record_deal_match`.
4. Ré-analyse : `update_deal_analysis` ne touche que les colonnes issues de l'analyse, `ai_analysis_raw`, `status` et `timestamp`. Les corrections manuelles (`manual_classification`, `manual_analysis_overrides`) sont relues et re-superposées avant chaque écriture.
5. `mark_deal_as_sold` (global) : `status='sold'`, `sold_at`, note optionnelle dans `sold_notes`.

## Index léger de la liste
`GET /deals/index` (`deals_repo.list_deals_index`) renvoie l'annonce sans les colonnes lourdes (`image_urls`, `storage_image_urls`, `storage_image_gs_uris`, `ai_analysis_raw`, `description`, `manual_analysis_overrides`, `sold_notes`) ni cinq colonnes inutilisées côté client (`scraped_by_node`, `tier3_trigger`, `published_at_raw`, `gatekeeper_brand`, `gatekeeper_classification`). Une seule vignette est conservée (`storage_image_urls[0]`, sinon `image_urls[0]`), plus `restoration_spent` (étapes `done` du plan de l'acheteur) et les préférences de l'utilisateur. `?ids=a,b` ne renvoie que ces annonces (si visibles). Pas d'`ORDER BY` : le client trie. ETag et 304 : `index_version.py`. Détails de transport en section 6.

## Rétention et purges
| Quoi | Règle | Où |
|---|---|---|
| `logs` | 30 jours, puis `logs_archive` | job 03:20, `log_retention.py` |
| `logs_archive` | 12 mois | idem |
| fichiers `logs/*.log` | compressés à 30 jours, supprimés à 1 an | job 03:15 |
| `scrape_runs` | 90 jours | `purge_scrape_runs` |
| photos d'annonces rejetées | supprimées après `IMAGE_RETENTION_REJECTED_DAYS` (30) pour les verdicts `BAD_DEAL`, `REJECTED_ITEM`, `REJECTED_SERVICE`, `INCOMPLETE_DATA`, `REJECTED` | `purge_rejected_images` |

## Pièges et invariants
- **`CREATE TABLE IF NOT EXISTS` ne modifie jamais une table existante** : toute colonne ajoutée après coup doit passer par un `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. Le fichier est rejoué à chaque démarrage de l'API **et** du bot : une instruction qui échoue sur une ligne de données (cast sur du JSON libre) empêche le service de démarrer — d'où les filtres de forme avant les `UPDATE` de rattrapage.
- `guitar_deals.timestamp` est la **date de dernière modification**, pas la date de scan. Dater une décision du Portier : premier appel T1 de `llm_usage` (UTC).
- `llm_usage.cached_tokens` est **inclus** dans `input_tokens` (même convention que Gemini et OpenAI).
- Les photos Facebook expirent ; seules `storage_image_*` sont durables.
- Les colonnes `image_urls` et `storage_image_*` sont des JSONB : le décodeur est enregistré par connexion (`_register_json_codecs`), sans lui asyncpg renvoie des chaînes.

## Tests
`backend/test_pg_repository.py`, `backend/test_log_archive.py`, `backend/test_scrape_health.py`, `backend/api/test_*` (index, sérialisation, ETag…). Les tests qui exigent Postgres se sautent sans `KB_TEST_DATABASE_URL` (base jetable, elle est vidée) et `DATABASE_URL`.
