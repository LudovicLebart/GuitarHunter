# Architecture Technique - Guitar Hunter AI

Ce document détaille le fonctionnement interne du projet.

## 0. 🔐 Firestore Security Rules (Session 2026-03-29)

Les règles Firestore assurent l'isolation multi-utilisateur. Chaque utilisateur n'accède qu'à ses données.

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Document utilisateur (botStatus, config, etc.)
    match /artifacts/{appId}/users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
    // Sous-collections (guitar_deals, commands, cities, logs)
    match /artifacts/{appId}/users/{userId}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
    // Document racine app (lecture seule)
    match /artifacts/{appId} {
      allow read: if request.auth != null;
      allow write: if false;
    }
    // Annonces partagées publiquement (lecture sans auth, écriture auth requise)
    match /shared_deals/{dealId} {
      allow read: if true;
      allow write: if request.auth != null;
    }
  }
}
```

**Note:** Le backend (Admin SDK) contourne ces règles par design — aucun impact sur l'API serveur.

> ⚠️ **Compatibilité ascendante (2026-04-07)** : Le frontend implémente un fallback dans `onCitiesUpdate` — si le catalogue partagé `artifacts/{APP_ID}/cities` est vide, il lit depuis `users/{uid}/cities` (ancienne architecture où les métadonnées sont stockées avec `isScannable`). Ce fallback sera retiré une fois le serveur migré vers la nouvelle architecture.

---

## 1. 🔄 Firestore : Le Cœur du Système (Event Bus)

Le projet utilise une architecture où **Firestore n'est pas seulement une base de données, mais un bus d'événements et de commandes**.

⚠️ **IMPORTANT**

### 2.0 🚀 Onboarding Dynamique (Multi-tenant)
Le backend n'est plus limité à une liste statique d'UIDs. 
- **Découverte** : `main.py` scanne périodiquement (toutes les 30s) la collection Firestore `artifacts/{APP_ID}/users/`.
- **Instanciation** : Pour chaque nouvel UID découvert, un thread de bot dédié est démarré "à chaud".
- **Fallback** : La variable d'environnement `USER_IDS_TARGET` sert de "seed" (liste initiale) au démarrage.
- **Isolation** : Chaque bot possède son propre logger, ses propres événements d'arrêt et son propre cycle de scan.

**Structure Imbriquée (Multi-tenant)**
Toutes les données sont isolées par application et par utilisateur. Le chemin de base pour toutes les collections est :
`artifacts/{APP_ID}/users/{USER_ID}/...`

- **`guitar_deals` (Collection):** (Chemin: `.../guitar_deals`). Contient toutes les annonces. Le frontend écoute cette collection en temps réel. Les annonces peuvent avoir plusieurs statuts : `analyzed` (par défaut), `rejected` (masqué totalement), ou `sold` (**Soft Delete** - masqué du flux principal mais conservé en base).
  - **`initialVerdict`/`initialModelUsed` (2026-07-11) :** Snapshot du verdict et de la chaîne `model_used` du tout premier passage IA, écrit une seule fois par `repository.py::create_new_deal()` et jamais réécrit par les réanalyses ultérieures (contrairement à `aiAnalysis`, qui est remplacé à chaque réanalyse). Sert de référence pour détecter les annonces initialement arrêtées au Portier (Tier 1) seul puis validées après réanalyse manuelle — voir `StatsView.jsx` ci-dessous. Absent sur les annonces créées avant cette date (pas de backfill).
- **`commands` (Collection):** (Chemin: `.../commands`). Le frontend écrit des documents ici pour demander toutes les actions au backend (ex: `ANALYZE_DEAL`, `REFRESH`, `CLEANUP`, `STOP_BOT`, `STOP_SCAN`, `START_BOT`). Le backend écoute cette collection, traite la commande de manière unifiée, puis la marque comme complétée.
  - **`STOP_BOT` :** Commande qui déclenche un état de "Sommeil" (pause de 12h interruptible) dans `main.py`. Utilise `stop_event` pour interrompre le travail en cours et change le statut du bot en `paused`. Le bot ne s'éteint plus totalement mais attend un réveil ou l'expiration du délai.
  - **`STOP_SCAN` :** Interrompt uniquement le cycle de scraping Playwright en cours via un `scan_stop_event` dédié. Le bot reste actif et prêt pour d'autres commandes (ex: Refresh, Reanalyse).
  - **`START_BOT` :** Réveil immédiat. Interrompt la boucle de pause via `start_event`. Note : toute autre commande actionnable (`REFRESH`, `SCAN_URL`, `CLEANUP`, `CLEAR_LOGS`, etc.) reçue pendant la pause réveille également le bot automatiquement (sondage Firestore toutes les 5s) et est exécutée immédiatement après le réveil.
  - **`MANUAL_SCAN` :** Déclenche un cycle de scan immédiat (`run_scan`) sans attendre le prochain intervalle du scheduler. Accessible via le bouton "Lancer le scan" dans le panneau de configuration.
- **`users/{userID}` (Document):** (Chemin: `artifacts/{APP_ID}/users/{USER_ID}`). Contient la configuration et le statut dynamique du bot (`botStatus`: `idle`, `scanning`, `paused`, `stopped`).


## 2. 🔐 Authentification (Firebase Auth)

Le système utilise **Firebase Authentication** pour gérer l'accès multi-utilisateurs.
- **Méthode :** Email / Mot de passe.
- **Persistance :** Gérée par le SDK Firebase (Session locale).
- **Lien avec Firestore :** Le `uid` généré par Firebase Auth sert de `USER_ID` pour l'isolation des données dans Firestore.
- **Onboarding Automatique :** Le hook `useAuth.js` utilise une fonction centralisée `ensureUserDoc` pour garantir la création/mise à jour du document utilisateur lors du login, signup ou restauration de session. 
- **Feedback de Robustesse :** En cas d'échec de l'accès Firestore (ex: permissions rules), le statut Auth passe en mode `warning` avec un message d'erreur explicite, alertant l'utilisateur que le bot backend ne pourra pas le découvrir.
- **Migration :** Un mécanisme spécial dans `firestoreService.js` permet de migrer les données d'un ancien ID statique vers le nouveau UID Firebase d'un utilisateur spécifique (administrateur).

## 2. 🐍 Backend (Python)

Le backend est un "worker" persistant qui tourne en boucle.

### `main.py`
- **Point d'entrée:** Initialise le `GuitarHunterBot` et le `DatabaseService` (Firestore + Firebase Storage).
- **Boucle principale:**
  1. Vérifie les commandes dans Firestore (`sync_and_apply_config`).
  2. Exécute les tâches planifiées (scan, nettoyage) via `TaskScheduler`.
  3. Gère un `command_handlers` pour router les commandes Firestore vers les bonnes méthodes du bot.
- **`run.bat`:** Script de lancement à la racine du projet. Utilise toujours le venv Python (`\venv\Scripts\python.exe`) et force l'encodage UTF-8 (`PYTHONUTF8=1`). Commandes : `run.bat` (bot), `run.bat migrate` (migration dry-run), `run.bat migrate --real` (migration réelle).
- **Déploiement Tailscale (OAuth):** Le workflow de déploiement GitHub Actions utilise des identifiants OAuth Tailscale (`TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`) pour se connecter au Tailnet et accéder au serveur via SSH.

### `.github/workflows/deploy.yml`
- **`deploy` (backend) :** Sur push `master`/`dev`, se connecte au serveur via Tailscale + SSH, `git reset --hard` sur la branche poussée, réinstalle les dépendances Python/Playwright, redémarre le service systemd `guitare-hunter`.
- **`deploy-frontend` (2026-07-07) :** Job indépendant (en parallèle du backend), sur les mêmes branches. `npm ci` → écrit `.env` depuis `secrets.DOT_ENV` (**requis** : `src/services/firebase.js` lit `import.meta.env.VITE_FIREBASE_*` au build, sans quoi `initializeApp()` échoue et l'app entière plante avec `TypeError: Cannot read properties of undefined (reading 'onAuthStateChanged')` — vécu en production le 2026-07-07) → `npm run build` → publication de `dist/` sur la branche `gh-pages` via `peaceiris/actions-gh-pages@v4` (utilise le `GITHUB_TOKEN` intégré, `permissions: contents: write` scopé à ce job). Avant cet ajout, le déploiement frontend était **manuel** (`npm run deploy`) et le site en ligne pouvait accumuler plusieurs mois de retard sans que personne ne s'en aperçoive — c'est ce qui s'est produit (dernier déploiement manuel : 2026-05-06, redéployé manuellement le 2026-07-07 avant l'automatisation).
- **Prérequis GitHub** : Settings → Actions → General → "Workflow permissions" doit être sur "Read and write permissions" pour que `deploy-frontend` puisse pousser sur `gh-pages`. Le secret `DOT_ENV` (déjà utilisé par le job backend) doit contenir les clés `VITE_FIREBASE_*`.
- **`force_orphan: true`** : `gh-pages` est republiée avec un commit unique à chaque déploiement CI (pas d'historique conservé). Nécessaire pour que le job ne dépende jamais de l'état précédent de la branche — un déploiement manuel (`npm run deploy`) intercalé entre deux runs CI causait sinon un rejet Git (`! [rejected] gh-pages -> gh-pages (fetch first)`), vécu le 2026-07-07.

### `backend/bot.py` (`GuitarHunterBot`)
- **Classe centrale:** Orchestre toutes les opérations du backend.
- **Multi-utilisateur:** Accepte `app_id`, `user_id`, `browser_semaphore` en paramètres. Logger isolé par user : `logging.getLogger(f"bot.{user_id[:8]}")`.
- **Gestionnaire d'état robuste:** Utilise un accès concurrent sécurisé via `threading.Lock()` et `set_status()` pour gérer l'étiquetage du `botStatus` en fonction des threads actifs (ex: `_active_tasks`), empêchant les processus asynchrones d'écraser prématurément des états prioritaires comme `scanning`.
- **Session isolée par thread:** `session_processed_ids` → `@property` sur `threading.local()`. Chaque thread (scan, refresh) a sa propre mémoire de session pour éviter les collisions.
- **Sémaphore Playwright:** Chaque instanciation de `FacebookScraper` acquiert/libère le sémaphore global. Limite `MAX_CONCURRENT_BROWSERS` navigateurs simultanés (défaut 3).
- **`run_scan()`:** Déclenche le scraping des villes configurées. Régulé par le `scheduler`. Scraper instancié localement par city avec sémaphore protection.
- **`handle_deal_found()`:** Callback appelé par le scraper (`scan_marketplace()` et `scan_specific_url()`) pour chaque annonce trouvée. Orchestre : (1) upload des images vers Firebase Storage (`repo.upload_images_to_storage()`), (2) injection de `storageImageUrls` dans les données, (3) appel à l'analyseur IA, (4) sauvegarde dans Firestore.
  - **Garde-fou scraping raté (2026-07-09)** : Si `imageUrls` est vide ET prix à 0$, la fonction `return` immédiatement — aucun appel IA, aucune écriture Firestore. L'annonce reste absente de la base et sera retraitée comme nouvelle à la prochaine session/scan plutôt que de figer une fiche vide comme "déjà traitée".
  - **Pré-filtres avant analyse IA** : en plus de `_check_exclusion()` (mots-clés → `verdict: REJECTED`), un plafond de prix défensif compare le prix scrapé à `scanConfig.max_price` — filet de sécurité indépendant du filtre de prix Facebook côté UI (peut échouer silencieusement, ex: timeout sur le champ de saisie). Contrairement à l'exclusion par mot-clé, ceci produit `verdict: "BAD_DEAL"` (pas `REJECTED`) : l'annonce reste `status: "analyzed"`, catégorisée "Trop Cher" (`ARCHIVE_GROUP` côté frontend, masquée par défaut mais consultable via son propre filtre) plutôt que traitée comme un rejet de fond.
- **`analyze_single_deal(payload)`:** Méthode spécifique pour traiter une commande de réanalyse (`ANALYZE_DEAL`). Elle récupère l'annonce et appelle `analyzer.analyze_deal`.
- **`sync_and_apply_config()`:** Lit la configuration depuis Firestore et applique les changements (fréquence, etc.).
- **`add_city_auto(city_name)`:** Pilote le scraper pour découvrir une nouvelle ville globalement. Utilise `FacebookScraper.get_city_id_and_coords` pour naviguer dans le sélecteur de lieu de Facebook et extraire l'ID numérique de la ville.

### `backend/analyzer.py` (`DealAnalyzer`)
- **Responsabilité unique:** Analyser une annonce en cascade.
- **SDK (2026-07-07)** : Utilise `google.generativeai`, dont le support est **officiellement terminé** (`FutureWarning` explicite au chargement du module). Remplacé par `google-genai`. Migration non faite — planifiée séparément.
- **`_call_gemini_json(model_name, content_parts, user_email=None)`:** Méthode utilitaire DRY. Centralise l'appel Gemini, le parsing JSON et la gestion d'erreur. Utilisée par les 3 Tiers. Détecte les erreurs "modèle introuvable" (404/not found/not supported) via `_is_model_unavailable_error()` et déclenche `NotificationService.notify_model_error()` (throttlé à 1×/24h/modèle via `self._model_error_last_notified`) — utile pour les modèles Preview qui peuvent être retirés avec 2 semaines de préavis (préavis envoyé par email Google directement, non interceptable par l'API). **(2026-07-09)** Normalise aussi tout résultat JSON de type liste (`[{...}]`, réponse Gemini occasionnelle) en `dict` avant de le retourner — évite un `TypeError` sur les 3 Tiers, qui font tous `result["clé"] = ...`/`.get(...)`.
- **`_construct_base_user_prompt()`:** Construit le prompt de base (taxonomie + détails + few-shot) **une seule fois** par analyse.
- **`analyze_deal(listing_data, firestore_config, force_expert=False, user_comment=None, user_email=None)` — Cascade 3-Tiers :**
  1. **Tier 1 — Portier (`gemini-2.5-flash-lite`) :** Filtre rapide/peu coûteux. Rejette bruit et services. Produit un verdict statut simple (`PEPITE`, `BAD_DEAL`, etc.). Si rejet → fin immédiate.
  2. **Tier 2 — Analyste (`gemini-3.5-flash`, 2026-07-09 — anciennement `gemini-2.5-flash`, retiré par Google) :** Si T1 passe, analyse structurée avec 5 scores numériques (`deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, `restoration_interest_score`). Format compacté (puces).
  3. **Carrefour Logique :** Évalue les scores du T2 et le prix extrait via `ListingParser.extract_price_from_text`. Déclenche le T3 si :
     - Prix > 1000€ ET deal_score >= 4
     - deal_score >= 8
     - Combo : deal_score >= 6 ET restoration_interest_score >= 7
     - authenticity_score <= 7 (doute d'authenticité)
     - confidence < 0.75
     - verdict == 'COLLECTION'
     - `force_expert=True` (demande manuelle)
  4. **Tier 3 — Expert Pro (`gemini-3.1-pro-preview`, 2026-07-07) [Conditionnel] :** Analyse exhaustive avec rapport Markdown complet. Écrase le résultat du T2. En cas d'échec : fallback sur le T2. Modèle Preview choisi pour sa puissance malgré le risque de dépréciation (2 semaines de préavis) — voir alerte email ci-dessus.
  - Le champ `model_used` retrace le chemin complet (ex: `"gemini-2.5-flash-lite -> gemini-3.5-flash -> gemini-3.1-pro-preview"`).
  - Le champ `tier3_trigger` indique le motif de déclenchement du T3 (si applicable).
  - **`user_comment` (2026-07-07)** : Si fourni (réanalyse manuelle avec correction utilisateur, ex: "Tu as identifié une PRS mais c'est une GWD"), injecté en priorité dans `base_prompt` — visible par tous les tiers exécutés.
  - **Double appartenance "Pépite" (2026-07-06)** : Le champ `also_qualifies_pepite` (booléen, dans le JSON T2/T3) est positionné par l'IA elle-même quand le verdict principal (`FAST_FLIP`/`LUTHIER_PROJ`/`CASE_WIN`/`COLLECTION`) remplit *aussi* les critères Pépite (Marge > 100% et > 150$ OU Marge > 30% et modèle iconique). Le verdict principal n'est pas modifié ; le champ traverse tel quel jusqu'à Firestore (`repository.py` ne filtre pas les clés de `aiAnalysis`) et jusqu'au frontend (filtre "Pépites", compteur, badge secondaire dans `DealCard.jsx`).

### `backend/notifications.py` (`NotificationService`)
- **Déclenchement** : `NOTIFY_VERDICTS = {'PEPITE'}` par défaut, plus toute annonce avec `also_qualifies_pepite=true` (même si son verdict principal diffère).
- **Canaux** : ntfy.sh (optionnel, `NTFY_TOPIC`) et Email SMTP (optionnel, `SMTP_USER`/`SMTP_PASSWORD`).
- **Encodage des headers ntfy** : Les headers HTTP (`requests`) n'acceptent que du Latin-1. Le `Title` (qui peut contenir émojis/accents) est encodé en **RFC 2047** (`email.header.Header`, `maxlinelen=998` pour éviter le repliement multi-ligne — invalide sur un header HTTP brut), conformément à `docs.ntfy.sh/publish`.
- **Point d'attention critique** : `handle_deal_found()` (dans `bot.py`) appelle `notify_deal()` de façon synchrone et non protégée ; `run_scan()` n'a pas de `except` sur sa boucle des villes (seulement un `finally`). Une exception non gérée dans `notify_deal()` interromprait le scan des villes restantes du cycle en cours — c'est ce qui s'est produit avant le correctif du 2026-07-06 (`HIGH_PRIORITY_VERDICTS`/`profit` non définis).

### `backend/scraping/`
- **`FacebookScraper`** : Utilise Playwright pour naviguer sur Facebook Marketplace, scroller, et extraire les données brutes des annonces. 
    - **Détection des Baisses de Prix** : Avant analyse, si une annonce existe déjà en DB mais que son prix a baissé, elle est marquée comme une mise à jour. L'ancien prix est sauvegardé (`original_price`), la différence calculée (`price_drop_amount`), et l'annonce repasse dans le pipeline IA pour réévaluation (la marge évolue).
    - **Note d'architecture (Thread-Safety)** : L'instance `FacebookScraper` n'est plus globale au bot. Pour éviter les erreurs `greenlet.error` (Cannot switch to a different thread) de l'API synchrone de Playwright lors des commandes en arrière-plan (ex: `REFRESH`, `SCAN_URL`), un `temp_scraper` est instancié localement au sein de chaque thread worker et fermé immédiatement après usage.
    - **Logger par-utilisateur (2026-07-09)** : `FacebookScraper.__init__` reçoit désormais `logger=self.logger` (le logger `bot.{user_id[:8]}` raccordé au `FirestoreHandler`) depuis `bot.py`, propagé à `ListingParser.parse_listing_card()`/`parse_details_page()` et à `CityFinder.find_city_id_and_coords()` via `scraper.logger`. Avant ce correctif, `core.py`/`parser.py`/`city_finder.py` loguaient sur `logging.getLogger(__name__)` (loggers de module), jamais raccordés à Firestore — aucun log du scraper n'était visible dans le LogViewer de l'app, y compris les diagnostics de débogage. **Le même correctif a été étendu à `analyzer.py` (`DealAnalyzer(logger=...)`) et `notifications.py` (`NotificationService.notify_deal(..., logger=...)`)** — même piège, même solution (voir `CLAUDE.md` § Points d'Attention Critiques pour la règle générale à suivre pour tout nouveau module).
    - **Détection de fiche détail "dégradée" (2026-07-09)** : Facebook sert parfois une version limitée de la fiche détail à une session non authentifiée (titre/description disponibles via les balises `og:*`, mais prix et carrousel photo absents du DOM) — comportement intermittent, cause exacte non confirmée (piste : gating anti-bot lié à l'absence de session Facebook authentifiée, le scraper étant 100% anonyme). `ListingParser.parse_details_page()` détecte ce cas via "0 image extraite après filtrage" (signal non ambigu — contrairement à une détection basée sur l'absence de carrousel, qui donne un faux positif sur toute annonce à une seule photo légitime) et tente un reload unique avec ré-extraction complète (titre/prix/localisation incluses, pas seulement les images), en ne conservant le résultat du reload que s'il apporte strictement plus d'images. `bot.py::handle_deal_found()` ne stocke pas une annonce dont le scraping échoue malgré tout (0 image ET prix à 0$) — elle sera retraitée comme nouvelle à la prochaine session plutôt que de figer une fiche vide.
    - **Protection Anti-Bot (Stealth Mode)** : Pour éviter le bannissement ou les redirections vers /login, le scraper intègre désormais :
        - **Rotation d'IP (Proxies)** : Si la liste `PROXIES` dans `config.py` est remplie, chaque instance du scraper choisira aléatoirement un proxy, permettant une rotation des adresses IP à chaque nouvelle tâche de scraping.
        - **Randomisation** : Liste tournante de User-Agents modernes et viewports (résolutions d'écran) aléatoires à chaque démarrage.
        - **Flags de Furtivité** : Utilisation d'arguments Chromium spécifiques pour masquer le pilotage automatisé (`--disable-blink-features=AutomationControlled`).
        - **Détection Active** : Surveillance des redirections vers les pages de login ou Captcha, entraînant un arrêt propre de la session. Implémentée via `_is_valid_detail_page()`, appelée avant l'extraction des détails dans `scan_marketplace()` et `scan_specific_url()` : si la fiche détail n'a pas chargé correctement, l'annonce retombe sur l'image de la carte (recherche) plutôt que d'aspirer un contenu erroné.
    - **Extraction d'images filtrée (Anti-Suggestions)** : `ListingParser.parse_details_page()` (dans `parser.py`) exclut les vignettes appartenant au bloc "Suggestions" que Facebook affiche systématiquement sous la description d'une annonce (autres annonces : véhicules, meubles, etc.). Le filtre se base sur le lien ancêtre (`<a href="/marketplace/item/{AUTRE_ID}/...">`) plutôt que sur la taille de l'image, car ces vignettes ont la même taille que de vraies photos de produit. Ce bug touchait surtout les annonces ayant peu de vraies photos (le plafond de collecte de 10 images n'étant alors pas atteint par les vraies photos seules).

### `backend/resources/` (Nouveau)
- **`city_coordinates.json`:** Base de données locale des coordonnées des villes pour la cartographie.

### `backend/database.py` (`DatabaseService`)
- **Connexion Firebase :** Initialise à la fois **Firestore** et **Firebase Storage** via `firebase_admin.initialize_app(cred, {'storageBucket': ...})`.
- **`self.bucket`:** Objet bucket Storage passé au `FirestoreRepository` pour les opérations d'images.

### `backend/config/` (Nouveau)
- **`serviceAccountKey.json`:** Clé de service Firebase pour l'authentification du backend. (Non versionné)

### 🗄️ Firebase Storage
- **Upload** (`repository.upload_images_to_storage()`) : Télécharge les images depuis leurs URLs CDN Facebook et les stocke dans `deals/{deal_id}/{i}_{uuid}.jpg`. Retourne des URLs publiques pérennes.
- **Cycle de vie** (`repository.purge_rejected_images()`) : Supprime les images Storage des deals dont le verdict est dans les `rejection_verdicts` et dont le timestamp est > `IMAGE_RETENTION_REJECTED_DAYS` (défaut : 30j). Cible correctement `aiAnalysis.verdict` (et non `status`) pour couvrir les rejets modernes.
- **Script de migration** (`backend/scripts/migrate_images.py`) : Script pour migrer les annonces historiques. Teste la validité des URL Facebook, re-scrape via Playwright si expirées, puis uploade dans Firebase Storage. Intègre la **Rotation de Session** (redémarrage du navigateur toutes les 15 annonces) et le **Jitter** (délais aléatoires) pour contrer l'anti-botting de Facebook lors d'opérations massives.

## 2.1 🔄 Robustesse & Monitoring (Audit 2026-05-05)

### Watchdog — Redémarrage Automatique des Bots Crashés

`main.py` exécute une boucle watchdog qui vérifie tous les 30s si les threads des bots sont vivants.

**Améliorations (Audit 2026-05-05):**
- **Recréation du Logging** : Le `firestore_handler` est recréé à chaque redémarrage de thread car l'instance précédente est définitivement fermée lors du crash/arrêt du thread précédent.
- **Hygiène Multi-tenant** : Le watchdog supprime désormais les contextes de bots pour les utilisateurs retirés de Firestore (ou non présents dans `USER_IDS_TARGET`), évitant les fuites de ressources.
- **Isolation Absolue** : Chaque bot possède son propre logger Python (`bot.{user_id[:8]}`) et son propre `FirestoreHandler` pointant vers `artifacts/{app}/users/{user}/logs`.

**Mécanisme de redémarrage :**
```python
if not ctx["thread"].is_alive():
    # 1. Fermeture propre (si possible) et recréation du handler
    new_handler = setup_logging(db, app_id, user_id, offline_mode)
    # 2. Recréation de l'instance du bot et des events
    new_bot, new_stop, ... = _create_user_bot(db_service, user_id)
    # 3. Lancement du nouveau thread avec le nouveau handler
    new_t = threading.Thread(target=main_loop, args=(new_bot, new_handler, ...))
```

**Avantages:**
- Détecte les crashes silencieux (exceptions non-catchées dans la boucle principale).
- Isole les crashes : si le bot de l'utilisateur A crashe, B et C continuent.
- Recrée le bot avec un état vierge (botStatus = `idle`).

**Limitations:**
- Pas de backoff exponentiel. Un bot qui crashe à chaque redémarrage rédémarre en boucle toutes les 30s.
- Perte d'état de pause (si le bot était en pause 12h, il reprend en idle).

---

## 3. ⚛️ Frontend (React)

Le frontend est une Single Page Application (SPA) conçue pour être très réactive.

### `src/App.jsx`
- **Point d'entrée:** Structure l'application avec les fournisseurs de contexte.
- **`DealsProvider`:** Fournit les données et les actions relatives aux annonces.

### `src/hooks/useDealsManager.js`
- **Hook central:** C'est le cerveau du frontend pour le tri et l'affichage.
  1. **`onDealsUpdate()`:** S'abonne aux changements de la collection `guitar_deals` dans Firestore.
  2. **`setDeals()`:** Met à jour l'état local, ce qui provoque le re-rendu de l'interface.
  3. **Système de tri hiérarchique :** Gère les filtres dynamiques sur 4 niveaux. Utilise des **chemins complets (dot-notation)** pour les clés de comptage (`typeCounts`) et la résolution des taxonomies, évitant ainsi les collisions entre catégories homonymes (ex: "Solid Body" sous Guitare vs Basse).
  4. **`dealActions`:** Expose des fonctions (`handleRejectDeal`, `handleRetryAnalysis`) qui interagissent avec `firestoreService`.

### `src/services/firestoreService.js`
- **Couche d'abstraction:** Toutes les interactions avec Firestore sont ici.
- **`getRefs(userId)`:** Factory centralisée créant les références Firestore isolées par user. Valide `userId` avant création → `throw new Error(...)` si absent (fail fast).
- **`onDealsUpdate()`:** Implémente l'écouteur `onSnapshot` de Firestore.
- **Actions des Boutons (Refresh, Cleanup, etc.) :** Toutes les actions créent désormais un document dans la collection `commands` via `addCommand(type, payload)`.
- **Migration multi-user:** `migrateOldDataToNewUser(newUserId, userEmail)` → Email admin via `VITE_ADMIN_EMAIL` env var (sécurité). Flag `migrationDone` prévient les remigrés. Try/catch granulaire par étape.

### `src/components/BotControls.jsx`
- **Contrôle et Statut:** Regroupe l'indicateur de statut du bot (`idle`, `scanning`, `paused`, `stopped`) et les boutons de pilotage à distance (`STOP_BOT`, `STOP_SCAN`, `START_BOT`). Intégré dans le panneau latéral "Système".

### `src/components/DealCard.jsx`
- **Composant clé:** Affiche une seule annonce.
- **Props:** Reçoit un objet `deal` et des fonctions `on...` (ex: `onRetry`) depuis le composant parent.
- **Logique d'affichage:**
  - Affiche les informations de base (titre, prix).
  - Affiche les résultats de l'analyse IA (`deal.aiAnalysis`).
  - Contient un module financier interactif pour afficher les estimations de valeur, de coût et de marge.
  - Les boutons d'action (Rejeter, Réanalyser) appellent les fonctions passées en props, qui remontent jusqu'à `useDealsManager` puis `firestoreService`.

### `src/components/Dashboard.jsx`
- **Gestion de l'URL (`dealId`)**: Au chargement, le composant lit le paramètre `dealId` de l'URL. Si présent, il sélectionne l'annonce correspondante via `dealActions.handleSelectDeal` et force le `viewMode` à `'MAP'` pour afficher la modale de détail. L'URL est ensuite nettoyée pour éviter des ouvertures répétées.
- **Bouton de Partage**: Le bouton de partage écrit un snapshot de l'annonce dans la collection publique Firestore `shared_deals/{dealId}`, puis génère un lien `?shareId={dealId}`. Ce lien est accessible sans compte via `SharedDealPage.jsx`.

- **`src/components/HelpOverlay.jsx`**: Guide utilisateur interactif détaillant le fonctionnement de l'IA (Gemini), les scores, les verdicts et les notifications (Email/Ntfy). Accessible via le bouton d'aide dans la Navbar.

- **`src/components/SharedDealPage.jsx`**: Page publique rendue par `App.jsx` quand `?shareId=` est détecté dans l'URL, avant le mur d'auth. Affiche titre, prix, localisation, images, scores IA, analyse et lien FB. Lit depuis la collection Firestore publique `shared_deals/{shareId}`.

### `src/components/MapView.jsx`
- **Cartographie Google Maps :** Intègre### 1. Logique de Scraping et de Détection (`backend/scraping/`)

*   **Extraction :** Utilise Scrapy/Playwright pour cibler le Marketplace, contourner les protections, et charger les annonces dynamiquement (scroll down).
*   **Nettoyage initial :** Standardisation des ID, nettoyage des titres et descriptions (retrait des émojis inutiles, formatage des prix).
*   **Détection d'existence & Baisse de prix :** Avant analyse, un premier check compare l'ID avec la mémoire (session) et la base de données.
    *   Si l'annonce existe avec le même prix : Ignorée *(économie d'API)*.
    *   Si l'annonce existe mais avec un prix inférieur : Elle est traitée comme une *mise à jour* (`is_update = True`). Le nouveau prix écrase l'ancien, la différence (`price_drop_amount`) est calculée, et l'annonce repasse dans le pipeline d'IA pour réévaluer son potentiel (les marges évoluent).

### `src/components/Dashboard.jsx` (Tableau de Bord V2)
- **Interface Principale :** Regroupe la Navbar, le Tiroir de Filtres, et les différentes vues (Liste, Carte, Stats).
- **Overlay Mobile :** Implémentation d'un système d'overlay (`absolute inset-0`) pour l'annonce sélectionnée sur mobile, couvrant la carte au lieu de la compresser pour une lecture optimale.
- **Tableau de Bord de Statistiques (`StatsView.jsx`) :** Composant agrégeant les données de Firestore.
    - Calcule dynamiquement le Tunnel de Conversion (Funnel) et les KPIs financiers (Marge nette latente, Score moyen, Marge par pépite) sur l'inventaire en cours.
    - Utilise `recharts` pour visualiser un **Radar Chart** du profil moyen IA (5 scores) et un **Bar Chart** pour la distribution du Top 5 des Marques.
    - **Erreurs Portier corrigées (2026-07-11) :** Sous le Funnel — compte les annonces dont `initialModelUsed` ne compte qu'un maillon (arrêtées au Portier T1 seul) et dont la chaîne `aiAnalysis.model_used` **actuelle** en compte 2 ou plus (réanalysées avec succès jusqu'à l'Analyste ou l'Expert). Un signal direct du taux de faux positifs du Portier, sans dépendre du texte du verdict (`BAD_DEAL` étant ambigu — voir `initialVerdict`/`initialModelUsed` plus haut).

### `src/components/DealCard.jsx`
- **Composant de Production :** Version aboutie de la carte d'annonce avec design premium.
- **Barre d'Actions :** `renderActionButtons()` factorise les actions pour la Modale d'Analyse IA (`isModal=true`, seul point d'appel). Le footer de la carte (vue grille) a sa **propre copie indépendante non factorisée** du même bloc — dette technique existante, pas encore unifiée.
- **Partage Public :** `handleShare` écrit un snapshot dans `shared_deals/{dealId}` (Firestore public), puis génère `?shareId={dealId}`. Utilise `navigator.share` avec fallback clipboard. Le destinataire n'a pas besoin de compte.
- **Menu de Ré-analyse :** Dropdown dynamique (présent aux deux endroits ci-dessus) offrant le choix entre "Scan Standard", "Luthier Expert", et "Avec commentaire..." (2026-07-07) — ce dernier ouvre une modale dédiée pour saisir une correction/précision transmise en priorité à l'IA lors d'une réanalyse Expert (`user_comment`, voir `backend/analyzer.py`).

## 4. 🧠 Système de Prompts Dynamiques

Ce système permet de modifier le comportement de l'IA sans redéployer le code, grâce à une synchronisation via Firestore comme couche de configuration dynamique. L'analyse approfondie du code a révélé une architecture à deux vitesses, avec plusieurs couches de code actif et du code obsolète.

---

### 4.1 Inventaire des Fichiers Impliqués

| Fichier | Rôle | Statut |
|---|---|---|
| `prompts.json` | Source de vérité statique des données par défaut | ✅ Actif |
| `config.py` | Charge `prompts.json` et exporte les constantes `DEFAULT_*` | ✅ Actif |
| `backend/analyzer.py` | Consomme les prompts et appelle Gemini | ✅ Actif |
| `backend/services.py` | (`ConfigManager`) Lit la config Firestore et la snapshotte | ✅ Actif |
| `src/hooks/useBotConfig.js` | Charge les défauts, synchronise avec Firestore, expose l'état | ✅ Actif |
| `src/services/firestoreService.js` | Couche de persistence Firestore (`updateUserConfig`) | ✅ Actif |
| `src/components/ConfigPanel.jsx` | Éditeur de prompts UI (composant `PromptListEditor`) | ✅ Actif |

---

### 4.2 Flux de Données Actuel (Architecture Réelle)

```
prompts.json
  └─ config.py (au démarrage Python)
       ├─ DEFAULT_MAIN_PROMPT      ← prompts.json["main_analysis_prompt"]
       ├─ DEFAULT_GATEKEEPER_INSTRUCTION ← prompts.json["gatekeeper_verbosity_instruction"]
       ├─ DEFAULT_EXPERT_CONTEXT   ← prompts.json["expert_context_instruction"]
       └─ DEFAULT_TAXONOMY         ← prompts.json["taxonomy_master"]

Firestore users/{id} (analysisConfig)
  └─ ConfigManager.sync_with_firestore()
       └─ bot.config_manager.current_config_snapshot

backend/analyzer.py : analyze_deal(listing_data, firestore_config)
  ├─ config = firestore_config["analysisConfig"]
  ├─ Portier : config["mainAnalysisPrompt"] OU DEFAULT_MAIN_PROMPT
  │   + DEFAULT_TAXONOMY (toujours statique)
  │   + listing_data (titre, prix, description, localisation)
  │   + config["gatekeeperVerbosityInstruction"] OU DEFAULT_GATEKEEPER_INSTRUCTION
  └─ Expert : config["expertContextInstruction"] OU DEFAULT_EXPERT_CONTEXT
      + config["mainAnalysisPrompt"] OU DEFAULT_MAIN_PROMPT
      + DEFAULT_TAXONOMY
      + listing_data
```

**Côté Frontend :**
```
prompts.json (import statique Vite)
  └─ useBotConfig.js
       ├─ DEFAULT_MAIN_PROMPT, DEFAULT_GATEKEEPER, DEFAULT_EXPERT (valeurs initiales)
       └─ onBotConfigUpdate() → Firestore snapshot
            └─ analysisConfig (setState) → ConfigPanel.jsx
                 └─ PromptListEditor (éditeur ligne par ligne)
                      └─ onBlur → saveConfig() → updateUserConfig() → Firestore
```

---

### 4.3 Prompts Modifiables par l'Utilisateur

L'utilisateur peut modifier les 3 prompts suivants via le **ConfigPanel** (onglet "Intelligence Artificielle") :

| Clé Firestore | Description | Utilisé par |
|---|---|---|
| `analysisConfig.gatekeeperModel` | Modèle utilisé pour le filtrage rapide (Tier 1) | Portier |
| `analysisConfig.mainModel` | Modèle utilisé pour la structuration et les scores (Tier 2) | Analyste |
| `analysisConfig.expertModel` | Modèle utilisé pour l'analyse approfondie (Tier 3) | Expert Pro |
| `analysisConfig.mainAnalysisPrompt` | Prompt principal complet (persona + verdicts + format JSON) — **Array de strings**. | Portier + Expert |
| `analysisConfig.gatekeeperVerbosityInstruction` | Instruction du Portier (filtre initial, liste des catégories acceptées) — **Array de strings** | Portier uniquement |
| `analysisConfig.analystVerbosityInstruction` | Instruction de l'Analyste (format puce compact + 5 scores) — **Array de strings** | Analyste uniquement |
| `analysisConfig.expertProContextInstruction` | Contexte injecté en tête du prompt de l'Expert (contient `{status}` et `{reasoning}`) — **Array de strings** | Expert Pro uniquement |
| `analysisConfig.rejectionVerdicts` | Liste stricte des verdicts provoquant un arrêt immédiat de l'analyse | Portier uniquement |

> [!NOTE]
> Toutes les instructions de verbosité sont stockées en **`array of strings`** (une chaîne par phrase) pour permettre une édition ligne par ligne dans le `ConfigPanel`. Le backend (`analyzer.py`) les joint par `\n` avant de les envoyer à Gemini.

Les modifications sont **sauvegardées automatiquement au `onBlur`** de chaque champ, sans bouton de validation explicite.

---

### 4.4 Fallback et Robustesse

Le système dispose d'un mécanisme de fallback à deux niveaux :
1.  **Frontend :** Si Firestore ne contient pas de config, `useBotConfig.js` initialise l'état avec les valeurs lues depuis `prompts.json` directement (import Vite statique).
2.  **Backend :** `analyzer.py` utilise `config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT)`. Si la clé est absente de Firestore, les constantes chargées depuis `prompts.json` au démarrage servent de fallback.

---

### 4.5 Dette Technique Restante (Architecture)

-  **Taxonomie non éditable** : `DEFAULT_TAXONOMY` est chargée depuis `prompts.json` au démarrage de Python et est toujours **injectée en dur** dans `analyzer.py`. Elle n'est pas exposée dans l'interface de configuration et ne peut pas être modifiée via Firestore.
-  **Terminologie financière** : Le système migre vers des termes génériques (`ancillary_value` au lieu de `estimated_case_value`) pour supporter les amplis (footswitches, haut-parleurs) et les accessoires. Les anciens noms de champs restent supportés pour la compatibilité UI.

---

### 4.6 Avantages & Risques

- **(+) Flexibilité :** Modification du comportement de l'IA (et ajout d'exemples Few-Shot) sans redéploiement du backend.
- **(+) Robustesse :** Double fallback (Frontend statique + Backend statique) garantit que l'IA ne reste jamais sans prompt.
- **(+) Éditeur Ligne par Ligne :** Le composant `PromptListEditor` permet une édition intuitive.
- **(-) Risque de Casse :** L'utilisateur peut supprimer les instructions de format JSON critiques dans `mainAnalysisPrompt`, rendant les réponses de l'IA non parsables.
- **(-) Taxonomie non éditable :** La taxonomie (liste des types d'objets : guitares, amplis, étuis) est statique et non modifiable via l'interface.
