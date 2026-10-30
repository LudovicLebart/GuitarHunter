# CLAUDE.md — Guitar Hunter AI

## Identité du Projet

**Guitar Hunter** — Bot de scraping et d'analyse IA d'annonces marketplace (Facebook).

- **Backend :** Python, Playwright, Google GenAI/Gemini, Schedule
- **Frontend :** React 18, Vite, TailwindCSS
- **Données :** Postgres sur le serveur (annonces, config, commandes, journaux d'usage), exposé par l'API FastAPI `backend/api/` — la base n'est plus sur Firebase depuis la bascule de septembre 2026
- **Cloud :** Firebase **Auth** (connexion) et **Storage** (photos des annonces, pour l'instant) ; ntfy.sh. Plan de sortie de Firebase Storage et de GitHub Pages : `docs/management/plans/SELF_HOSTING_SITE_AND_PHOTOS_PLAN.md` (priorité basse)
- **Dépôt GitHub PUBLIC** : ne jamais y versionner d'identifiants utilisateur, de titres/URLs d'annonces ni de mots de passe (les jeux `backend/scripts/data/dataset_a_*.jsonl` sont locaux et dans `.gitignore`)

> Source de vérité : lire tous les fichiers dans `docs/` avant d'agir. Ne lire le code source que si la doc ne suffit pas.

---

## Protocole de Travail (OBLIGATOIRE)

Toute tâche **significative** suit **3 étapes** dans cet ordre. Impossible de sauter une étape sans validation explicite.

**Proportionnalité (décision utilisateur 2026-10-02)** : ne pas imposer un bloc de plan à chaque mini-étape. Le plan formel (Étape 1) est réservé aux tâches qui changent le comportement du système, touchent plusieurs fichiers, ou ont un effet en production/coût. Pour une petite étape (correctif ciblé, ajustement de doc, lecture/diagnostic, une étape découlant d'un plan déjà validé), **agir directement** puis résumer ce qui a été fait. En cas de doute sur la taille ou le risque, poser une question courte plutôt qu'un bloc complet. Les actions à effet externe (push, déploiement, suppression, accès production en écriture) restent soumises à confirmation explicite.

### Étape 1 — Plan (NE PAS CODER) — pour les tâches significatives

Pour chaque nouvelle demande significative, répondre **uniquement** avec ce bloc et s'arrêter :

```
🚦 AIGUILLAGE ET PLAN D'ACTION
- Périmètre : [résumé court]
- Modèle Requis : [FLASH ou PRO]
- Le Plan : [étapes de ce que je vais faire]

👉 Valides-tu ce modèle et ce plan pour que j'exécute la tâche ?
```

Attendre le "Oui" ou "Go" de l'utilisateur avant de coder une tâche significative.

### Étape 2 — Code (NE PAS METTRE À JOUR LA DOC)

Une fois le plan validé, générer uniquement les diffs :

```javascript
// ... existing code ...
[CHANGEMENT ICI]
// ... existing code ...
```

Attendre la confirmation de fonctionnement par l'utilisateur avant de passer à l'étape 3.

### Étape 3 — Documentation (UNIQUEMENT après validation)

Après "C'est bon" ou "Validé" de l'utilisateur, mettre à jour (arborescence Diataxis) :
- `docs/management/journal/AAAA-Wss.md` — **journal hebdomadaire** (semaine ISO de la date de l'entrée, entrées récentes en haut ; créer le fichier avec son en-tête si la semaine n'existe pas) ; `docs/management/JOURNAL.md` n'est que l'**index** (table des semaines + convention), à tenir à jour. Format d'une entrée : `[DATE] [MODÈLE] Action → Résultat`
- `docs/management/TODO.md`
- `docs/reference/ARCHITECTURE.md`
- `docs/reference/DATA_FLOW.md`
- `docs/explanation/` — si la vision/stratégie évolue (`PROJECT_OVERVIEW.md`, `STATS_REFLEXION.md`)
- `docs/management/plans/` — pour les plans d'implémentation dédiés (ex : `MULTI_USER_PLAN.md`)

**Interdit** : utiliser `echo`, `sed`, `cat` en terminal pour modifier la doc. Utiliser les outils d'édition directs.

---

## Aiguillage des Modèles

| Modèle | Cas d'usage |
|--------|-------------|
| **[FLASH]** | Lecture, analyse doc, réponses simples, rédaction documentation |
| **[PRO]** | Génération de code complexe, refactoring, debug multi-fichiers, audit |

---

## Règles de Frugalité

- Interdit d'analyser l'intégralité du code source au démarrage.
- Lire `docs/` en priorité. Lire le code source seulement si la doc ne suffit pas.
- Interdit de réécrire des fichiers complets — fournir uniquement les blocs modifiés.
- Ne pas ajouter de features, refactoring, ou "améliorations" non demandées.
- Ne pas créer de fichiers non nécessaires.

---

## Architecture Clé

### Modèle de données (multi-tenant)
Les données vivent dans **Postgres** (tables `users`, `guitar_deals`, `user_deal_matches`, `commands`, `cities`, `llm_usage`, `logs`…) depuis la bascule de septembre 2026 ; le frontend y accède par l'API (`src/services/apiService.js`). L'arborescence Firestore ci-dessous est le **modèle historique**, conservé parce que les noms de champs (`botStatus`, `analysisConfig`, `guitar_deals`, `commands`) sont restés les mêmes :
```
artifacts/{APP_ID}/users/{USER_ID}/
  ├── guitar_deals/     ← annonces analysées
  ├── commands/         ← bus de commandes Frontend → Backend
  └── (doc user)        ← botStatus, config, analysisConfig
```

### Statuts du Bot
`idle` | `scanning` | `paused` | `stopped`

### Pipeline IA (3-Tiers)
1. **Tier 1 — Portier** : filtre rapide. Depuis le 2026-09-29, **`qwen3-vl:8b-instruct` en local sur le Dell** (Ollama, chaîne `T1_PROVIDER_CHAIN=local,qwen`, Qwen cloud en secours) ; Gemini Flash-Lite n'est plus le décideur
2. **Tier 2 — Analyste** (`gemini-3.5-flash`, depuis 2026-07-09 — `gemini-2.5-flash` retiré par Google) : 5 scores numériques
3. **Tier 3 — Expert Pro** (`gemini-3.1-pro-preview`, depuis 2026-07-07) : analyse exhaustive (conditionnel)

### Commandes Backend
`REFRESH` | `ADD_CITY` | `ANALYZE_DEAL` | `CLEAR_LOGS` | `STOP_BOT` | `STOP_SCAN` | `START_BOT` | `SCAN_URL` | `CLEANUP`

---

## Points d'Attention Critiques

- Le backend Python tourne en **thread par utilisateur** avec watchdog de redémarrage (30s).
- Playwright n'est **pas thread-safe** — chaque thread crée sa propre instance de scraper localement.
- Le frontend n'utilise plus Firestore (2026-10-11) : tout passe par `src/services/apiService.js` (`firestoreService.js` supprimé le 2026-10-05). Ne plus importer `firebase/firestore` côté front ni appeler `.collection()`/`firestore.*` côté Python : ce sont des restes qui plantent (`NameError: firestore`) ou lisent des données figées. Seuls usages Firestore volontaires restants : le bail de haute disponibilité (`backend/ha/lease.py`, `watchdog.py`).
- Les images Facebook expirent → upload systématique vers **Firebase Storage** lors de `handle_deal_found`.
- `session_processed_ids` est isolé par thread via `threading.local()` pour éviter les collisions.
- Les prompts IA sont modifiables depuis l'app (ConfigPanel, stockés dans `users.config` Postgres) avec double fallback (`prompts.json`).
- **Piège logger (récurrent, trouvé 2026-07-09 dans `scraping/`, `analyzer.py`, `notifications.py`)** : seul le logger `bot.{user_id[:8]}` (créé dans `bot.py`, raccordé au `PostgresHandler` de `logging_config.py`) est visible dans le LogViewer de l'app. Tout module qui logue via `logging.getLogger(__name__)` sans recevoir ce logger en paramètre est **invisible pour l'utilisateur**, même si les logs apparaissent bien côté serveur (stdout/journalctl). Tout nouveau module backend qui doit logger quelque chose d'observable par l'utilisateur doit accepter un paramètre `logger` optionnel (repli sur le logger de module) et le faire propager depuis `bot.py`/`analyzer.py` — ne jamais supposer qu'un `logger.info(...)` isolé sera visible.
- **`GEMINI_MODELS["default_analyst"]` (`config.py`) câblé depuis le 2026-08-19** : `bot.py::_init_db_structure()` initialise désormais `mainModel` (en plus de `gatekeeperModel`/`expertModel`) pour tout nouvel utilisateur. Ne s'applique qu'aux nouveaux comptes — les utilisateurs existants sans `mainModel` dans `users.config` continuent de retomber sur le fallback codé en dur dans `analyzer.py::analyze_deal()` (`config.get('mainModel', '...')`), à garder en synchronisation manuelle avec `config.py` si un modèle Tier 2 devient indisponible.
- **Facebook peut gater le prix/les photos pour une session non authentifiée** (comportement intermittent, cause exacte non confirmée) : le scraper est 100% anonyme (aucun `storage_state`/cookies persistants). Une fiche détail peut alors n'exposer que titre/description (balises `og:*`) sans prix ni carrousel photo, même après un reload. `handle_deal_found()` ne stocke pas ces annonces (0 image ET prix à 0$) plutôt que de figer une fiche vide — voir `TODO.md` pour la décision produit non tranchée (accepter la limitation vs session Facebook authentifiée).
- **Le LogViewer peut afficher les logs dans un ordre différent de leur émission réelle** : `PostgresHandler` bufferise et envoie par lots toutes les 3s ; des logs émis à quelques centaines de ms d'écart peuvent recevoir un `timestamp` serveur identique/très proche, et leur ordre d'affichage n'est alors pas garanti. Ne pas déduire l'ordre d'exécution réel du code depuis l'ordre d'affichage du LogViewer sans vérifier le code source.
- **`BAD_DEAL` (verdict IA "Trop Cher") ≠ `REJECTED`** : `BAD_DEAL` garde `status: "analyzed"` (pas `"rejected"`) et est simplement masqué de la vue par défaut via son appartenance à `ARCHIVE_GROUP` (`src/constants.js`) — pas un vrai rejet de fond. Ce n'est **plus** produit par le pré-filtre de prix (`scanConfig.max_price`) depuis le 2026-07-27 : une annonce hors budget est désormais ignorée par `handle_deal_found()` sans écriture Firestore (`return "out_of_budget"`), pour Facebook **et** Kijiji — hors budget = hors périmètre de recherche, pas une "mauvaise annonce" à archiver. `BAD_DEAL` reste un verdict IA légitime (voir `prompts.json`) quand l'*analyse* elle-même juge le prix excessif relativement à la valeur estimée.
- **Kijiji en mode strict (`scanConfig.distance = 0`, 2026-10-09)** : `bot.py::_kijiji_strict_label()` décide par le GPS (≤ 5 km d'une ville listée, ≤ 15 km si le nom de localisation correspond) ; avant, toute annonce était rattachée à la ville la plus proche sans borne (annonces de Laval étiquetées « Sherbrooke »). Le nom `location.name` de Kijiji est le choix du vendeur, jamais un critère à lui seul. Une ville du catalogue aux coordonnées fausses (Sherbrooke avait celles de Montréal, id `edmonton`) fausse toute la zone : vérifier `cities.latitude/longitude` avant d'accuser le filtre.
- **Base de connaissances « univers des guitares » (2026-10-01) : construite et branchée au Portier mais ÉTEINTE** (`T1_KNOWLEDGE_ENABLED=false`, version 1 non validée) — la mesure n'a montré **aucun gain** (voir `STRATEGIE_IA.md` §3.8 bis). Ne pas valider la version ni activer l'interrupteur sans nouveau rejeu concluant, malgré la commande de validation que `compare_knowledge_effect.py` affiche automatiquement. Pièges : une analyse forcée écrase `ai_analysis_raw.gatekeeperVerdict` par `MANUAL_RETRY` (le verdict T1 d'origine est `guitar_deals.initial_verdict`) ; le tag Ollama `qwen3-vl:8b` est la variante *Thinking* (utiliser `qwen3-vl:8b-instruct`) ; les scripts de la base ne lisent pas `.env` (`export DATABASE_URL=...`).
- **Portier local (Dell) : contexte Ollama = 8192, à ne pas laisser retomber à 4096** (2026-10-02) : à 4096 le prompt était tronqué dès 4 photos (instruction perdue, rejets absurdes, JSON invalide). Il se règle par `OLLAMA_CONTEXT_LENGTH` dans l'environnement du service Ollama du Dell ; l'endpoint `/v1` **ignore** `options.num_ctx`. Mesurer le Portier avec `backend/scripts/t1_period_report.py`. **Même à 8192, le contexte déborde à 8 photos hautes** (2026-10-07) : une photo coûte (largeur ÷ 32) × (hauteur ÷ 32) tokens (867 pour 640×1386), le texte ≈ 2080 ; 8336 > 8192 → Ollama tronque en silence (`input_tokens` plafonné à 8192 dans `llm_usage`) et le Portier rejette au hasard. `backend/t1_image_budget.py` réduit alors les photos (jamais en retirer) pour le fournisseur local ; `T1_LOCAL_CONTEXT_TOKENS=0` le désactive. **Tout rejeu du Portier doit reproduire la prod** (`QWEN_LOCAL_MAX_IMAGES=8`, `--temperature -1`), sinon on mesure un Portier qui n'existe pas. Voir `STRATEGIE_IA.md` §2.5.
- **Piège de mesure : `guitar_deals.timestamp` est la date de dernière modification, pas la date de scan** (annonce passée en « vendue », ré-analyse…). Pour dater une décision du Portier, utiliser le premier appel T1 de `llm_usage` (`deal_id`, `created_at`, **en UTC** ; le serveur est en heure de Montréal, EDT UTC-4). Un mauvais rattachement a déjà faussé une mesure le 2026-10-03.
- **`backend/scripts/run_once.py` (ajouté 2026-08-06) — script "one-shot" exécuté à CHAQUE déploiement** (`.github/workflows/deploy.yml`, job `deploy`, seul contexte où les credentials Firebase sont en place sur le serveur) : sert à exécuter une action ponctuelle en production (ex: script de migration) depuis un environnement de dev sans accès Firestore. **No-op par défaut** (`ACTIVE = False`). Protocole strict : activer + écrire l'action → déployer → vérifier le résultat (logs GitHub Actions) → **repasser `ACTIVE = False` dans un commit séparé immédiatement après** — sinon l'action se répète à **chaque** déploiement futur (le job se déclenche sur push `master` **et** `dev`, donc généralement deux fois de suite à chaque usage : n'y écrire que des actions idempotentes).
- **Fiches techniques de restauration (2026-10-30) — la source est GIT, la base n'en est qu'une copie dérivée** : on écrit/modifie `docs/fiches/*.md` (gabarit et règles : `docs/fiches/README.md`) ; `backend/scripts/seed_guitar_fiches.py` les copie dans la base commune `guitar_knowledge` (`kind='fiche'`) **à chaque déploiement** (`deploy.yml`, étape non bloquante, une fois par base : bot, API prod, API staging) ou à la main (`export DATABASE_URL=...`, `--dry-run` d'abord). Ne jamais corriger une fiche directement en base : le prochain déploiement l'écraserait.
- **`guitar_knowledge*` : TOUTE nouvelle lecture doit filtrer par type** (`kind = ANY(BRAND_KINDS)` pour les marques, `FICHE_KINDS` pour les fiches ; voir `guitar_knowledge.py`). Sans filtre, une fiche technique pourrait entrer dans le prompt du Portier. Une fiche prend `kb_version = 0` et ne crée jamais de version. Garde-fou : `backend/test_knowledge_fiche_isolation.py`.
- **L'API de PRODUCTION n'est pas le dépôt entier** : `guitarhunter-api-prod` tourne dans `~/guitarhunter-api-prod`, où `deploy.yml` ne recopie qu'une **liste** de modules de `backend/` (`__init__.py`, `deal_mapping.py`, `guitar_knowledge.py`). Tout module importé (même par ricochet) par `backend/api/*.py` doit y figurer, sinon l'API de production ne démarre plus après le déploiement alors que tous les tests passent. Garde-fou : `backend/api/test_prod_sync.py`.
- **Tests automatiques** : `npm test` (`node --test` : fiches, `safeUrl`, recherche de fiches du chat, parité Python↔JS) et le job `tests` de `deploy.yml` (Postgres jetable : base de connaissances, fiches, API plan/chat/fiches, `test_analyzer`) **conditionnent les deux déploiements** — un test rouge bloque. En local, les tests qui exigent Postgres se sautent sans `KB_TEST_DATABASE_URL` (base JETABLE : ils la vident) et `DATABASE_URL`. Tout nouveau fichier de test Python utile doit être ajouté à la liste du job (`deploy.yml`).

---

## Fichiers Clés

| Fichier | Rôle |
|---------|------|
| `main.py` (racine) | Point d'entrée, boucle principale, watchdog, dispatching commandes |
| `backend/bot.py` | `GuitarHunterBot` — orchestration globale |
| `backend/analyzer.py` | `DealAnalyzer` — pipeline 3-Tiers Gemini |
| `backend/llm_clients.py` | `LLMClientsMixin` — appels Gemini / OpenAI-compatible (Qwen, Dell), schémas T1 (hérité par `DealAnalyzer`) |
| `backend/scraping/` | `FacebookScraper` — Playwright + stealth mode |
| `backend/notifications.py` | `NotificationService` — email SMTP + ntfy.sh |
| `backend/logging_config.py` | `setup_logging()`/`PostgresHandler` — logger par-utilisateur → table `logs` → LogViewer |
| `backend/pg_repository.py` | `PostgresRepository` — accès Postgres du bot (annonces, config, commandes) + envoi des photos vers Firebase Storage |
| `backend/api/` | API FastAPI (auth Firebase, REST + WebSocket) servie derrière Tailscale Funnel (`/` test, `/prod`) |
| `backend/auto_annotation/` | Détecteur de parties de guitare (YOLO-OBB) : export Label Studio, entraînement, pré-annotation — **non branché en production** (`docs/management/plans/PARTS_DETECTOR_AND_CROPS_PLAN.md`) |
| `backend/database.py` | `DatabaseService` — Firebase Storage (photos) et connexion Firestore pour le bail HA uniquement (hérité) |
| `src/services/apiService.js` | Couche d'accès à l'API FastAPI côté Frontend (remplace `firestoreService.js`, supprimé) |
| `backend/api/admin_repo.py` | Dashboard Administrateur sur Postgres (`/admin/*`, claim Firebase `admin`) |
| `src/hooks/useDealsManager.js` | Hook central — tri, filtres, actions |
| `src/components/Dashboard.jsx` | Interface principale — vues Liste/Carte/Stats |
| `src/components/DealCard.jsx` | Carte d'annonce avec analyse IA |
| `docs/fiches/` + `backend/scripts/seed_guitar_fiches.py` | Fiches techniques de restauration (source Markdown, chargeur vers la base commune), consultables sur le site (`#fiches`) et liées aux étapes/au chat |
| `docs/how-to/` | Guides pratiques (Diataxis) ; `FICHES_TECHNIQUES.md` = comment lire, créer, valider et publier une fiche (`.html` généré depuis le `.md`) |
| `docs/` (Diataxis : `reference/`, `explanation/`, `management/`) | **Source de vérité prioritaire** |
