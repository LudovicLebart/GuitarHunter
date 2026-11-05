# Bot — orchestration, threads, commandes, scan (référence)

> Vérifié le 2026-11-05 contre le commit `22e5a1b` : `main.py` (383 lignes), `backend/bot.py` (1 770 lignes), `backend/services.py` (123 lignes), `config.py`. Ce fichier remplace, pour le bot, les sections `main.py` / `backend/bot.py` / « Watchdog » d'`ARCHITECTURE.md` (qui restent en place, historiques, jusqu'au découpage). Le scraping lui-même (Facebook, Kijiji, CityFinder, santé des scrapers) est décrit en section 3 ; le pipeline IA (`analyzer.py`) en section 4.

## Rôle

Un processus Python unique (service systemd `guitare-hunter` sur le serveur) fait tourner **un thread par utilisateur**. Chaque thread pilote un objet `GuitarHunterBot` : il lit les commandes dans Postgres, planifie les scans, analyse les annonces trouvées et écrit les résultats.

## Fichiers

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée : un thread par utilisateur, découverte des utilisateurs, watchdog, boucle de commandes, tâches planifiées globales |
| `backend/bot.py` | `GuitarHunterBot` : scan Facebook/Kijiji, traitement d'une annonce, nettoyage des vendues, file de ré-analyse, ajout de ville, analyse manuelle |
| `backend/services.py` | `ConfigManager` (lit la config et les commandes), `TaskScheduler` (planifie scan, nettoyage, purge), `Command`, `SyncResult` |
| `config.py` | Variables d'environnement et valeurs par défaut |
| `backend/logging_config.py` | Logger par utilisateur `bot.{uid[:8]}` + `PostgresHandler` (voir `donnees.md`, rétention) |
| `backend/notifications.py` | ntfy et e-mail (`notify_deal`, `notify_scrape_health`, `notify_scan_url_finished`, alertes de modèle) |

## Démarrage (`main.py::main`)

1. `DatabaseService` (Firebase Auth + Storage) ; sortie immédiate si le mode hors ligne s'est activé.
2. Pool Postgres synchrone (`pg_db.init_pool`, joue `schema.sql`).
3. Utilisateurs à démarrer : `SELECT uid FROM users` **plus** `USER_IDS_TARGET` (variable d'environnement, liste séparée par des virgules). Un bot par uid.
4. Deux jobs globaux dans le `schedule` : 03:15 compression/suppression des fichiers `logs/*.log` (`run_log_retention_job`), 03:20 archivage de la table `logs` (`run_pg_log_archive_job`).
5. Boucle du thread principal, toutes les 30 s (`WATCHDOG_INTERVAL`) : `schedule.run_pending()`, nouvelle découverte, retrait des bots dont l'utilisateur a disparu de Postgres, démarrage des nouveaux, redémarrage des threads morts.

## Un bot par utilisateur

`start_user_bot` crée un logger rattaché à `PostgresHandler`, un `GuitarHunterBot` et trois événements (`stop_event`, `start_event`, `scan_stop_event`), puis lance `main_loop` dans un thread démon nommé `bot-<email> (<uid[:8]>)`. Le contexte est gardé dans `user_contexts[uid]`.

Constructeur de `GuitarHunterBot` : logger `bot.{uid[:8]}`, mémoire de session `session_processed_ids` **propre à chaque thread** (`threading.local`), sémaphore Playwright **global** partagé par tous les bots (`MAX_CONCURRENT_BROWSERS`, défaut 3), verrou de statut, `PostgresRepository`, `DealAnalyzer`, `ConfigManager`, e-mail résolu par Firebase Auth. Il pose la structure initiale (`ensure_initial_structure`) puis lit la config (`sync_and_apply_config(initial=True)`).

Configuration de scan par défaut (`initial_scan_config`, écrite seulement si `users.config` est vide) : `max_ads` 5, `frequency` 60, `location` `montreal`, `distance` 10, `min_price` 0, `max_price` 150, `search_query` `electric guitar`, `kijiji_enabled` `false`. `facebook_enabled` est absent : **absent = activé**.

## Boucle d'un utilisateur (`main_loop`)

Threads lancés au démarrage de la boucle : `monitor_retries` (file de ré-analyse, toutes les 5 s).

À chaque tour (≈ 5 s) :
1. `scheduler.run_pending()` (voir « Planification »).
2. `bot.sync_and_apply_config()` : relit `users.config` et lit les commandes `pending` de Postgres.
3. Pour chaque commande : ignorée si son id est déjà « en vol » ; sinon exécutée, puis marquée `completed` ou `failed` (avec le message d'exception).
   - **Dans un thread séparé** : `REFRESH`, `REANALYZE_ALL`, `SCAN_URL`, `ADD_CITY`, `REEVALUATE_NOT_PROMOTED`.
   - **Dans la boucle, de façon synchrone** : `CLEANUP`, `ANALYZE_DEAL`, `CLEAR_LOGS`, `STOP_BOT`, `STOP_SCAN`, `START_BOT`.
   - Type inconnu : `failed` avec « Type de commande inconnu ».
4. Si la fréquence de scan a changé, `scheduler.update_scan_frequency`.
5. `time.sleep(5)`, puis test de `stop_event`.

### Pause (`STOP_BOT`)
`STOP_BOT` pose `stop_event`. Le bot passe en `paused` et attend jusqu'à 12 h (`PAUSE_DURATION_SECONDS`) : reprise immédiate sur `START_BOT`, ou dès qu'une autre commande arrive (sondée toutes les 5 s) ; ces commandes de réveil sont alors exécutées **de façon synchrone**, y compris un scan complet. À la sortie le statut repasse à `idle`. Le redémarrage du service ne conserve pas la pause.

### Arrêt d'un scan (`STOP_SCAN`)
Pose `scan_stop_event` puis le remet à zéro 3 s plus tard (thread démon). Tout le code de scan teste `_is_stop_requested()` (`stop_event` **ou** `scan_stop_event`).

### Watchdog
Toutes les 30 s le thread principal : `list(user_contexts)`, redémarre tout thread mort (nouveau handler de logs, nouveau bot, nouveau thread, **sans temporisation** : un bot qui plante à chaque démarrage est relancé toutes les 30 s), retire les bots dont l'uid n'est plus dans `users` (et pas dans `USER_IDS_TARGET`) en posant leur `stop_event`.

## Statut du bot (`set_status`)

`users.bot_status` est mis à jour par `set_status(statut, task_name)` sous verrou. Les tâches actives sont suivies dans `_active_tasks` : une tâche qui se termine demande `idle`, mais si d'autres tâches tournent encore le statut affiché devient `scanning` (prioritaire) ou la première tâche restante.

| Statut | Posé par | `task_name` |
|---|---|---|
| `idle` | fin de tâche, constructeur | — |
| `scanning` | `run_scan` | `scanning` |
| `scanning_url` | `scan_specific_url` | `scanning_url` |
| `cleaning` | `_perform_cleanup` | `cleaning` |
| `reanalyzing` | `process_retry_queue` | `retry_queue` |
| `reanalyzing_all` | `reanalyze_all_listings` | `reanalyzing_all` |
| `reevaluating_not_promoted` | `reevaluate_not_promoted` | `reevaluate_not_promoted` |
| `paused` | pause `STOP_BOT` | `paused` |

## Planification (`TaskScheduler`)

Utilise la bibliothèque `schedule` : scan toutes les `fréquence ± 20 %` minutes (intervalle aléatoire tiré à chaque exécution, `SCAN_FREQUENCY_JITTER_RATIO = 0.2`, contre la régularité robotique), nettoyage des annonces vendues toutes les 6 h, purge des photos d'annonces rejetées chaque semaine. `ConfigManager.get_valid_scan_frequency` renvoie 60 si la fréquence est absente ou invalide.

**Attention : ces jobs sont enregistrés dans le planificateur global de la bibliothèque, partagé par tous les threads** (voir constat R-2-1).

## Traitement d'une annonce (`handle_deal_found`)

Appelé pour chaque annonce par le scan (via un pool de threads) et par le scan d'URL. Dans l'ordre :

1. Scraping incomplet (aucune photo **et** prix 0) → `scrape_failed`, rien d'écrit.
2. Doublon inter-plateforme (hors scan manuel) → `duplicate_cross_platform`. Critères : prix normalisé identique, similarité de Jaccard des titres ≥ 0,6, et distance GPS ≤ 5 km (sinon, repli sur le nom de ville normalisé). Compare à tout le catalogue de l'**autre** source (préfixe `kijiji_`).
3. Si la ligne existe déjà : `record_deal_match` (elle devient visible pour cet utilisateur).
4. Marqueur de vente dans le titre ou les 200 premiers caractères de la description (hors scan manuel) → `marked_sold` (annonce existante) ou `sold_marker` (ignorée).
5. Annonce existante : `already_rejected` si `status = 'rejected'` ; `duplicate_unchanged` si le prix est identique ; sinon mise à jour avec `original_price` et `price_drop_amount`.
6. Mots-clés d'exclusion (hors scan manuel) → analyse `REJECTED` (`model_used = 'pre-filter'`), écrite, `rejected_prefilter`. Prix supérieur à `scanConfig.max_price` (si > 0, hors scan manuel) → `out_of_budget`, **rien d'écrit**.
7. `analyzer.analyze_deal(...)`. Verdict `GATEKEEPER_FAILED_SKIP` (échec du Portier) → `gatekeeper_failed`, rien d'écrit, sera retentée au scan suivant.
8. Garde-fou : une ré-analyse **sur changement de prix** ne déclasse jamais une `PEPITE` existante en `NOT_PROMOTED` (seul le prix est mis à jour).
9. `NotificationService.notify_deal(...)` (ntfy / e-mail selon le verdict).
10. Photos envoyées vers Firebase Storage (`upload_images_to_storage`), puis `create_new_deal` ou `update_deal_data_and_analysis`. Retourne `processed`.

L'ordre réel place donc la **notification avant** l'envoi des photos et l'écriture en base.

Codes de retour : `scrape_failed`, `duplicate_cross_platform`, `marked_sold`, `sold_marker`, `already_rejected`, `duplicate_unchanged`, `rejected_prefilter`, `out_of_budget`, `gatekeeper_failed`, `processed`, plus `stopped` et `error` (posés par le pool). Les codes `scrape_failed`, `duplicate_cross_platform`, `marked_sold`, `sold_marker`, `stopped`, `error`, `gatekeeper_failed` **ne marquent pas** l'id comme traité, pour permettre une nouvelle tentative.

### Analyse en parallèle (`_dispatch_analysis_batch`)
Les annonces d'une ville ou d'un ancrage sont analysées par un pool de `ANALYSIS_WORKERS = 5` threads. Le scraping est entièrement terminé avant, donc aucun scraper n'est partagé. Le thread appelant alimente `session_processed_ids` d'après l'issue réelle. Un log mesure l'accélération (temps cumulé ÷ temps mur).

## Scan planifié (`run_scan`)

1. Ignoré si un arrêt est demandé. Statut `scanning`.
2. Villes : `repo.get_cities()` (catalogue partagé, villes actives de l'utilisateur). Aucune → scan ignoré avec avertissement.
3. `_run_sources_in_parallel` : un thread Facebook (si `facebook_enabled`, défaut vrai) et un thread Kijiji (si `kijiji_enabled`), joints avant la fin du cycle. Aucune source activée → cycle ignoré.

**Facebook (`_run_facebook_scan`)** : regroupe les villes en **points d'ancrage** (`compute_anchor_clusters`, rayon `FACEBOOK_ANCHOR_RADIUS_KM = 80`), mélange l'ordre des ancrages, et pour chacun : prend un permis du sémaphore Playwright, crée un `FacebookScraper` local avec l'ID `fbLocationId or id`, scanne, enregistre la santé du scan (`scrape_runs`), filtre par zone, analyse le lot, ferme le scraper. Pause de 2 s entre ancrages.
- Mode **strict** (`distance = 0`) : une annonce est gardée si sa localisation correspond à la ville de l'ancrage ou à une autre ville listée ; décision par GPS de la fiche (5 km, 15 km si le nom est reconnu, constantes `FACEBOOK_STRICT_*`).
- Mode **rayon** (`distance > 0`) : distance mesurée à la ville membre du cluster la plus proche.
- Arrêt « scan rattrapé » (`FACEBOOK_CATCHUP_KNOWN_RUN`) : **désactivé** (valeur 0) ; une passe complète toutes les `FACEBOOK_FULL_PASS_EVERY = 6` quand il sera actif.

**Kijiji (`_run_kijiji_scan`)** : ignore les villes hors Canada, regroupe les villes sans rayon personnalisé en ancrages (80 km), scanne les villes avec `kijijiRadiusKm` seules avec ce rayon. Rayon envoyé = le plus grand de `scanConfig.distance` et du rayon minimal du cluster. Un seul permis du sémaphore pour tout le cycle. Les identifiants reçoivent le préfixe `kijiji_`. Mode strict : `_kijiji_strict_label` (5 km ou 15 km si le nom correspond). Le nom de ville stocké est le libellé d'affichage déjà connu d'après les annonces existantes (`_build_city_display_names`).

Chaque cycle se termine par un journal `📊 Résumé du cycle …` et la purge de `scrape_runs` (90 jours).

## Scan d'une URL (`SCAN_URL`)
`scan_specific_url` choisit `KijijiScraper` (domaine `kijiji.ca`) ou `FacebookScraper`, attend un permis jusqu'à 5 minutes (sinon abandon), appelle `handle_deal_found(is_manual_scan=True)` qui contourne prix, mots-clés, doublon inter-plateforme, marqueur de vente et la Recherche Active, puis notifie la fin du scan.

## Nettoyage des annonces vendues (`CLEANUP`, toutes les 6 h)
Lance `_perform_cleanup` dans un thread : prend un permis, liste les annonces de **cet utilisateur** au statut `analyzed`, vérifie chaque lien avec le scraper de sa source (0,5 s entre deux) et marque `sold` (global) toute annonce indisponible. Un seul nettoyage à la fois par bot (`is_cleaning`).

## File de ré-analyse (`process_retry_queue`)
Le thread `monitor_retries` lit toutes les 5 s les annonces `status = 'retry_analysis'` (file **globale**, tous utilisateurs), applique les mots-clés d'exclusion, ré-analyse (`analyze_deal`) et écrit le résultat ; en cas d'exception, `status = 'analysis_failed'`. `REANALYZE_ALL` ne fait que passer en `retry_analysis` les annonces `analyzed` visibles de l'utilisateur.

## Autres commandes
- `ANALYZE_DEAL` (`analyze_single_deal`) : relit l'annonce en base, enregistre la visibilité (`record_deal_match`), analyse avec `force_expert` et `userComment` éventuels, écrit ; échec → `analysis_failed`.
- `REEVALUATE_NOT_PROMOTED` : pour les annonces `NOT_PROMOTED` visibles de l'utilisateur dont la classification du Portier correspond maintenant à la Recherche Active (`analysisConfig.activeSearchFamilies`), relance l'analyse en sautant le Portier (`force_expert=True`) et restaure les champs `gatekeeper*` et l'observation Qwen/Flash-Lite.
- `ADD_CITY` (`add_city_auto`) : dédoublonne par nom normalisé ; si la ville a des coordonnées elle est simplement activée ; sinon `CityFinder` trouve et **vérifie** l'ID Facebook. Coordonnées : celles confirmées par l'utilisateur, sinon Facebook, sinon Nominatim (marquée `needsReview`). Un ID non vérifié lève une exception (commande `failed`) au lieu d'enregistrer la ville.
- `CLEAR_LOGS` : supprime les lignes de `logs` de l'utilisateur.

## Configuration utilisée par le bot

| Variable | Défaut | Effet |
|---|---|---|
| `MAX_CONCURRENT_BROWSERS` | 3 | Permis Playwright partagés par tous les bots |
| `USER_IDS_TARGET` (ou `USER_ID_TARGET`) | vide | Uid démarrés même absents de `users` |
| `APP_ID_TARGET` | — | Identifiant d'application hérité de Firestore |
| `IMAGE_RETENTION_REJECTED_DAYS` | 30 | Purge des photos d'annonces rejetées |
| `PROXIES` | vide | Liste de proxys (tirage aléatoire dans `scraping/core.py`) |
| `HA_NODE_ID` | vide | Si défini, `scraped_by_node` est posé sur chaque annonce |
| `SMTP_*`, `NTFY_TOPIC` | — | Notifications |
| `KIJIJI_GUITARS_CATEGORY_ID` | 613 | Catégorie Kijiji |

Les variables `T1_*`, `T3_*` et les modèles relèvent du pipeline IA (section 4).

## Pièges et invariants
- Playwright n'est pas thread-safe : chaque scan crée son propre scraper et prend un permis du sémaphore global.
- Le permis est conservé pendant l'analyse IA du lot (le scraper n'est fermé qu'après) : voir constat R-2-3.
- `session_processed_ids` est local à chaque thread ; les threads du pool d'analyse ne l'alimentent pas.
- Le `LogViewer` n'affiche pas les logs dans l'ordre d'émission (lots de 3 s).
- Tout module qui doit être visible dans le LogViewer reçoit le logger du bot en paramètre.

## Tests
`backend/test_bot.py` (53 Ko), `backend/test_analyzer.py`, `backend/test_pg_repository.py`.
