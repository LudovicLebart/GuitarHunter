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

- **`guitar_deals` (Collection):** (Chemin: `.../guitar_deals`). Contient les documents complets de toutes les annonces (avec images, descriptions et analyses IA détaillées). Le frontend ne charge plus cette collection en temps réel pour des raisons de coût, mais l'interroge sélectivement (Lazy Loading) par paquets de 30 uniquement pour les annonces affichées à l'écran.
- **`deals_index` (Collection sharded):** (Chemin: `.../deals_index/{chunk_0..19}`). Contient l'index global allégé des annonces (métadonnées de filtrage/compteurs — voir liste complète des champs dans `DATA_FLOW.md` § 5, dont `b`/`mn`/`co` brand/model_name/color depuis 2026-07-31), réparti de manière homogène sur 20 documents via un hachage MD5. Le frontend s'y abonne en temps réel au démarrage (20 lectures Firestore au lieu de 2748) pour calculer tous les compteurs, filtrer et trier en local.
- **`commands` (Collection):** (Chemin: `.../commands`). Le frontend écrit des documents ici pour demander toutes les actions au backend (ex: `ANALYZE_DEAL`, `REFRESH`, `CLEANUP`, `STOP_BOT`, `STOP_SCAN`, `START_BOT`). Le backend écoute cette collection, traite la commande de manière unifiée, puis la marque comme complétée.
  - **`STOP_BOT` :** Commande qui déclenche un état de "Sommeil" (pause de 12h interruptible) dans `main.py`. Utilise `stop_event` pour interrompre le travail en cours et change le statut du bot en `paused`. Le bot ne s'éteint plus totalement mais attend un réveil ou l'expiration du délai.
  - **`STOP_SCAN` :** Interrompt uniquement le cycle de scraping Playwright en cours via un `scan_stop_event` dédié. Le bot reste actif et prêt pour d'autres commandes (ex: Refresh, Reanalyse).
  - **`START_BOT` :** Réveil immédiat. Interrompt la boucle de pause via `start_event`. Note : toute autre commande actionnable (`REFRESH`, `SCAN_URL`, `CLEANUP`, `CLEAR_LOGS`, etc.) reçue pendant la pause réveille également le bot automatiquement (sondage Firestore toutes les 5s) et est exécutée immédiatement après le réveil.
  - **`MANUAL_SCAN` :** Déclenche un cycle de scan immédiat (`run_scan`) sans attendre le prochain intervalle du scheduler. Accessible via le bouton "Lancer le scan" dans le panneau de configuration.
- **`users/{userID}` (Document):** (Chemin: `artifacts/{APP_ID}/users/{USER_ID}`). Contient la configuration et le statut dynamique du bot (`botStatus`: `idle`, `scanning`, `paused`, `stopped`).
  - **`uiFilters` (2026-07-15, format taxonomie changé le 2026-07-31) :** Filtres/tri de la vue Deals (`filterType`, `selectedTypePaths`, `conditionFilter`, `priceFilter`, `sortMode`), persistés par utilisateur pour survivre au rechargement/reconnexion. Écrit avec debounce (800ms) par `useBotConfig.js::saveUiFilters`, hydraté une seule fois au premier chargement par `useDealsManager.js` (les écritures suivantes du même client ne re-déclenchent pas l'hydratation). La recherche texte libre (`searchQuery`) n'est volontairement pas persistée. **`selectedTypePaths` (2026-07-31)** remplace l'ancien quadruplet `level1Filter`/`level2Filter`/`level3Filter`/`level4Filter` (un seul chemin de taxonomie en cascade) par un tableau de chemins de taxonomie (dot-notation) — permet de cocher plusieurs catégories simultanément, y compris dans des branches différentes (ex: "Parlor" + "Baby / Mini"). `useDealsManager.js` migre en douceur au premier chargement : si `uiFilters.selectedTypePaths` est absent mais qu'un ancien `level1Filter` existe, il reconstruit le chemin unique équivalent plutôt que de perdre le filtre déjà sauvegardé par l'utilisateur.


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
- **Transmission des secrets (2026-07-11)** : `DOT_ENV`/`FIREBASE_SERVICE_ACCOUNT_KEY` sont transmis via `env:`/le paramètre `envs:` de `appleboy/ssh-action`, jamais interpolés littéralement dans un script bash (`echo "${{ secrets.X }}"`) — un guillemet ou une parenthèse dans la valeur du secret casserait sinon la syntaxe du script généré et ferait échouer tout le déploiement (vécu en production : 2 échecs consécutifs des deux jobs en modifiant `DOT_ENV`). Écriture des fichiers via `printf '%s' "$VAR" >` plutôt que `echo`.
- **`force_orphan: true`** : `gh-pages` est republiée avec un commit unique à chaque déploiement CI (pas d'historique conservé). Nécessaire pour que le job ne dépende jamais de l'état précédent de la branche — un déploiement manuel (`npm run deploy`) intercalé entre deux runs CI causait sinon un rejet Git (`! [rejected] gh-pages -> gh-pages (fetch first)`), vécu le 2026-07-07.

### `backend/bot.py` (`GuitarHunterBot`)
- **Classe centrale:** Orchestre toutes les opérations du backend.
- **Multi-utilisateur:** Accepte `app_id`, `user_id`, `browser_semaphore` en paramètres. Logger isolé par user : `logging.getLogger(f"bot.{user_id[:8]}")`.
- **Gestionnaire d'état robuste:** Utilise un accès concurrent sécurisé via `threading.Lock()` et `set_status()` pour gérer l'étiquetage du `botStatus` en fonction des threads actifs (ex: `_active_tasks`), empêchant les processus asynchrones d'écraser prématurément des états prioritaires comme `scanning`.
- **Session isolée par thread:** `session_processed_ids` → `@property` sur `threading.local()`. Chaque thread (scan, refresh) a sa propre mémoire de session pour éviter les collisions.
- **Sémaphore Playwright:** Chaque instanciation de `FacebookScraper` acquiert/libère le sémaphore global. Limite `MAX_CONCURRENT_BROWSERS` navigateurs simultanés (défaut 3).
- **`run_scan()`:** Point d'entrée du cycle de scan planifié (régulé par le `scheduler`). Délègue tout le travail à **`_run_sources_in_parallel(scan_config, cities_to_scan)`** (2026-07-27) : lance `_run_facebook_scan()` si `scanConfig.facebook_enabled` (toggle "Source Facebook" dans `ConfigPanel`, **activé par défaut** — absent = `True`, pour ne pas désactiver silencieusement Facebook sur un compte existant créé avant ce réglage), et `_run_kijiji_scan()` si `scanConfig.kijiji_enabled` (toggle "Source Kijiji (bêta)") — chacun dans son propre thread (`threading.Thread`, daemon) si activé, rejoints (`join()`) avant que `run_scan()` ne considère le cycle terminé. Les deux sources sont désactivables indépendamment (2026-07-27, demande utilisateur — isoler un scan Kijiji seul, sans le bruit de Facebook dans les logs partagés, pour déboguer une absence de résultats Kijiji) ; si aucune des deux n'est activée, le cycle est ignoré avec un `warning` explicite plutôt qu'un scan silencieusement vide. Le cycle complet dure `max(durée Facebook, durée Kijiji)` au lieu de `Facebook + Kijiji` en séquentiel quand les deux tournent. Sûr à paralléliser : aucune des deux sources n'écrit le même document Firestore (IDs Kijiji préfixés `kijiji_`), `session_processed_ids` est isolé par thread (`threading.local()`), et `_browser_semaphore` (thread-safe) continue de plafonner le nombre réel de navigateurs Playwright ouverts simultanément, indépendamment du nombre de threads.
  - **`_run_facebook_scan(scan_config, cities_to_scan)`** : boucle par ville, scraper instancié localement par ville avec protection par sémaphore.
    - **Filtre STRICT multi-villes (mode `distance=0`)** : `scan_marketplace()` accepte déjà toute annonce dont la localisation correspond à **l'une des villes** de la liste autorisée (`is_city_allowed()`), pas seulement celle recherchée. `_run_facebook_scan()` applique ensuite une logique à 3 voies sur le résultat : ville recherchée → traitée normalement ; **autre ville autorisée de la liste** → traitée immédiatement (au lieu d'être jetée après avoir payé le coût de la fiche détail complète) ; hors liste → rejetée.
    - **Comptabilisation des échecs de cycle** : `scan_marketplace()` retourne un dict (`deals`, `anti_bot_blocked`, `rejected_out_of_list`, `total_cards_seen`) au lieu d'une simple liste. `handle_deal_found()` retourne un code de statut par annonce (`scrape_failed`, `sold_marker`, `already_rejected`, `duplicate_unchanged`, `duplicate_cross_platform`, `rejected_prefilter`, `out_of_budget`, `processed`). `_run_facebook_scan()` agrège le tout dans un résumé de cycle (`📊 Résumé du cycle Facebook : ...`) loggé en fin de scan.
  - **`_run_kijiji_scan(scan_config, cities_to_scan)`** (2026-07-27, intégré au pipeline) : boucle sur le même catalogue de villes que Facebook (`cities_to_scan`), via `KijijiScraper.scan_city()`, à qui sont désormais passés `min_price`/`max_price`/`lat`/`lng`/`radius_km` (2026-07-27, voir `scan_marketplace()`-like filtrage côté recherche plus bas). IDs préfixés `kijiji_` avant même le check de dédup (`should_skip_deal`). `locations.py::nearest_configured_city()` est appelé ici pour corriger `location` (imprécis côté Kijiji, voir section dédiée plus bas) en la rattachant à la ville configurée la plus proche par GPS ; une annonce hors rayon de toute ville configurée (si `distance` > 0) est rejetée. Résumé de cycle symétrique à Facebook (`📊 Résumé du cycle Kijiji : ...`).
  - **Logs tagués par source (2026-07-27)** : Facebook et Kijiji tournant en parallèle et écrivant dans le même logger (`self.logger`), leurs lignes s'entremêlent dans le LogViewer — `handle_deal_found()` préfixe donc chacun de ses logs par `[Facebook]`/`[Kijiji]` (paramètre `source`, défaut `"Facebook"` pour ne pas casser `scan_specific_url()`).
- **`handle_deal_found(listing_data, is_manual_scan=False, source="Facebook")`:** Callback appelé par le scraper (`scan_marketplace()`, `scan_city()` et `scan_specific_url()`) pour chaque annonce trouvée. Orchestre : (1) upload des images vers Firebase Storage (`repo.upload_images_to_storage()`), (2) injection de `storageImageUrls` dans les données, (3) appel à l'analyseur IA, (4) sauvegarde dans Firestore. Retourne un code de statut (voir ci-dessus) plutôt que `None`.
  - **Garde-fou scraping raté (2026-07-09)** : Si `imageUrls` est vide ET prix à 0$, la fonction retourne `"scrape_failed"` immédiatement — aucun appel IA, aucune écriture Firestore. L'annonce reste absente de la base et sera retraitée comme nouvelle à la prochaine session/scan plutôt que de figer une fiche vide comme "déjà traitée".
  - **Détection de doublon cross-plateforme (2026-07-27, localisation par GPS depuis le même jour)** : `_find_cross_platform_duplicate(listing_data, source)` compare l'annonce (prix normalisé + similarité de titre Jaccard, seuil `CROSS_PLATFORM_TITLE_SIMILARITY_THRESHOLD=0.6` + localisation compatible) contre `repo.get_deals_index_snapshot()` (fusion des 20 chunks de `deals_index`, sans lire les documents complets de `guitar_deals`), en ne comparant qu'aux annonces de **l'autre** source (préfixe `kijiji_` de l'ID) — un doublon même-source est déjà géré par ID exact via `should_skip_deal()`. Objectif : repérer une même annonce postée à la fois sur Facebook et Kijiji avant d'appeler l'IA dessus une seconde fois. Appelé en tout début de `handle_deal_found()` (avant tout appel Gemini), sauf pour un scan manuel (`is_manual_scan=True`, où l'utilisateur demande explicitement l'analyse de cette URL précise) — retourne `"duplicate_cross_platform"` sans écriture Firestore si trouvé.
    - **Localisation : distance GPS plutôt que nom de ville exact** — un faux négatif réel (même guitare postée sur les deux sites, jamais détectée) a révélé que la comparaison initiale par `ListingParser.normalize_city_name` échouait systématiquement pour un Kijiji scanné manuellement (`location.name` = grande sous-région type "Longueuil / South Shore", jamais corrigée par `nearest_configured_city()` avant ce même correctif, voir plus bas) contre le nom de ville précis affiché côté Facebook. Simplement retirer la ville comme critère a été écarté (risque de faux positif : titre générique type "guitare électrique" + prix identique par coïncidence, entre deux villes différentes). `latitude`/`longitude` (désormais dans l'index, `la`/`lo` — voir `DATA_FLOW.md` § 5) comparées par distance Haversine (`CROSS_PLATFORM_MAX_DISTANCE_KM=5`) quand disponibles des deux côtés — le `location.coordinates` Kijiji est précis même quand `location.name` ne l'est pas. Repli sur l'ancienne comparaison par nom de ville normalisé si les coordonnées manquent d'un côté (Facebook ne les extrait pas systématiquement).
    - **`bot.py::scan_specific_url()` (scan manuel Kijiji) corrige désormais aussi `location` via `nearest_configured_city()`** — jusque-là, seul le scan automatique (`_run_kijiji_scan()`) appliquait cette correction ; le scan manuel gardait la valeur brute Kijiji imprécise, ce qui alimentait aussi bien un mauvais affichage que l'échec de dédup ci-dessus (repli par nom de ville non plus totalement inopérant pour ce chemin).
  - **Pré-filtres avant analyse IA** : en plus de `_check_exclusion()` (mots-clés → `verdict: REJECTED`, stocké), un plafond de prix défensif compare le prix scrapé à `scanConfig.max_price` — filet de sécurité résiduel derrière le filtre de prix appliqué côté recherche (Facebook : `minPrice`/`maxPrice` dans l'URL + `_apply_filters()` ; Kijiji : `price=min__max` dans l'URL, voir plus bas), qui peut échouer silencieusement (ex: timeout sur un champ de saisie Facebook). **Depuis le 2026-07-27**, une annonce hors budget est **ignorée sans écriture Firestore** (`return "out_of_budget"`) plutôt que stockée avec un verdict `BAD_DEAL` — hors budget est traité comme hors périmètre de recherche, pas comme une "mauvaise annonce" à archiver ; comportement uniforme Facebook/Kijiji. `BAD_DEAL` reste un verdict IA légitime (voir `prompts.json`) quand l'*analyse* elle-même juge le prix excessif relativement à la valeur estimée — seul le raccourci de pré-filtre a été retiré.
- **`scan_specific_url(url)`** ("Scan d'URL Direct" / commande `SCAN_URL`) : dispatche vers `KijijiScraper` ou `FacebookScraper` selon le domaine de `url` (`"kijiji.ca" in url.lower()`) — **avant le 2026-07-27, `FacebookScraper` était utilisé sans condition**, y compris pour une URL kijiji.ca (signalé par l'utilisateur : échec silencieux car mauvais site/sélecteurs, notification générique "Impossible de récupérer les informations..." et systématiquement étiquetée "URL Facebook"). Pour une URL Kijiji : l'ID retourné par `KijijiScraper.scan_specific_url()` est préfixé `kijiji_` avant `handle_deal_found()` (même raison que `_run_kijiji_scan()` — éviter une collision avec un ID Facebook, deux espaces d'entiers distincts) et `source="Kijiji"` est propagé à `handle_deal_found()`/`NotificationService.notify_scan_url_finished()`.
- **`analyze_single_deal(payload)`:** Méthode spécifique pour traiter une commande de réanalyse (`ANALYZE_DEAL`). Elle récupère l'annonce et appelle `analyzer.analyze_deal`.
- **`sync_and_apply_config()`:** Lit la configuration depuis Firestore et applique les changements (fréquence, etc.).
- **`add_city_auto(city_name)`:** Pilote le scraper pour découvrir une nouvelle ville globalement. Utilise `FacebookScraper.get_city_id_and_coords` pour naviguer dans le sélecteur de lieu de Facebook et extraire l'ID numérique de la ville.

### `backend/analyzer.py` (`DealAnalyzer`)
- **Responsabilité unique:** Analyser une annonce en cascade.
- **SDK (2026-07-07)** : Utilise `google.generativeai`, dont le support est **officiellement terminé** (`FutureWarning` explicite au chargement du module). Remplacé par `google-genai`. Migration non faite — planifiée séparément.
- **`_call_gemini_json(model_name, content_parts, user_email=None)`:** Méthode utilitaire DRY. Centralise l'appel Gemini, le parsing JSON et la gestion d'erreur. Utilisée par les 3 Tiers. Détecte les erreurs "modèle introuvable" (404/not found/not supported) via `_is_model_unavailable_error()` et déclenche `NotificationService.notify_model_error()` (throttlé à 1×/24h/modèle via `self._model_error_last_notified`) — utile pour les modèles Preview qui peuvent être retirés avec 2 semaines de préavis (préavis envoyé par email Google directement, non interceptable par l'API). **(2026-07-09)** Normalise aussi tout résultat JSON de type liste (`[{...}]`, réponse Gemini occasionnelle) en `dict` avant de le retourner — évite un `TypeError` sur les 3 Tiers, qui font tous `result["clé"] = ...`/`.get(...)`.
- **`_construct_base_user_prompt()`:** Construit le prompt de base (taxonomie + détails + few-shot) **une seule fois** par analyse.
- **Identification durcie (marque/numéro de série, 2026-07-31)** : constat utilisateur — des photos montrant clairement la tête/logo ou une plaque de numéro de série étaient parfois totalement ignorées par le Portier (T1), menant à de grosses erreurs de filtrage en amont. `prompts.json::main_analysis_prompt` (section IDENTIFICATION) et `gatekeeper_verbosity_instruction` (T1, qui reçoit aussi les images — voir `analyze_deal()` ci-dessous) exigent désormais explicitement l'examen de toute photo de logo/plaque/étiquette avant de conclure, et font primer cette preuve visuelle sur le titre/texte de l'annonce en cas de contradiction. Nouveau champ `color` dans le schéma JSON attendu (couleur/finition visible sur les photos). Aucun changement côté `analyzer.py` — le prompt et les images étaient déjà transmis ensemble à chaque Tier, seul le texte d'instruction a été renforcé. **Limite connue** : les utilisateurs ayant déjà personnalisé leurs prompts via Firestore (`ConfigPanel`) ne reçoivent pas ce renforcement automatiquement — seul le fallback par défaut (`prompts.json`) est mis à jour.
- **`analyze_deal(listing_data, firestore_config, force_expert=False, user_comment=None, user_email=None)` — Cascade 3-Tiers :**
  1. **Tier 1 — Portier (`gemini-3.5-flash-lite`, 2026-07-31 — anciennement `gemini-2.5-flash-lite`, gemini-2.5-* retiré par Google en octobre 2026) :** Filtre rapide/peu coûteux. Rejette bruit et services. Produit un verdict statut simple (`PEPITE`, `BAD_DEAL`, etc.). Si rejet → fin immédiate.
  2. **Tier 2 — Analyste (`gemini-3.6-flash`, 2026-07-31 — anciennement `gemini-3.5-flash`) :** Si T1 passe, analyse structurée avec 5 scores numériques (`deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, `restoration_interest_score`). Format compacté (puces). Migration validée par benchmark (Artificial Analysis Intelligence Index : 50 pour 3.6 Flash = identique à 3.5 Flash, contre 36 pour Flash-Lite — écart de capacité T1/T2 préservé, particulièrement net en raisonnement visuel : 80,1% vs 48,3%).
  3. **Carrefour Logique :** Évalue les scores du T2 et le prix extrait via `ListingParser.extract_price_from_text`. Déclenche le T3 si :
     - Prix > 1000€ ET deal_score >= 4
     - deal_score >= 8
     - Combo : deal_score >= 6 ET restoration_interest_score >= 7
     - authenticity_score <= 7 (doute d'authenticité)
     - confidence < 0.75
     - verdict == 'COLLECTION'
     - `force_expert=True` (demande manuelle)
  4. **Tier 3 — Expert Pro (`gemini-3.1-pro-preview`, 2026-07-07) [Conditionnel] :** Analyse exhaustive avec rapport Markdown complet. Écrase le résultat du T2. En cas d'échec : fallback sur le T2. Modèle Preview choisi pour sa puissance malgré le risque de dépréciation (2 semaines de préavis) — voir alerte email ci-dessus.
  - Le champ `model_used` retrace le chemin complet (ex: `"gemini-3.5-flash-lite -> gemini-3.6-flash -> gemini-3.1-pro-preview"`).
  - **Fallbacks codés en dur mis à jour (2026-07-31)** : `analyze_deal()` utilisait encore `gemini-2.5-flash-lite`/`gemini-3.5-flash`/`gemini-2.5-pro` comme valeurs par défaut si `firestore_config` ne contient pas ces clés — le cas `expertModel` par défaut (`gemini-2.5-pro`) était particulièrement à risque : c'est exactement le piège déjà documenté ci-dessous (`GEMINI_MODELS["default_analyst"]` pas réellement câblé) et `gemini-2.5-pro` est retiré par Google en octobre 2026. Alignés sur `GEMINI_MODELS` (config.py) : `gemini-3.5-flash-lite`/`gemini-3.6-flash`/`gemini-3.1-pro-preview`.
  - Le champ `tier3_trigger` indique le motif de déclenchement du T3 (si applicable).
  - **`user_comment` (2026-07-07)** : Si fourni (réanalyse manuelle avec correction utilisateur, ex: "Tu as identifié une PRS mais c'est une GWD"), injecté en priorité dans `base_prompt` — visible par tous les tiers exécutés.
  - **Double appartenance "Pépite" (2026-07-06)** : Le champ `also_qualifies_pepite` (booléen, dans le JSON T2/T3) est positionné par l'IA elle-même quand le verdict principal (`FAST_FLIP`/`LUTHIER_PROJ`/`CASE_WIN`/`COLLECTION`) remplit *aussi* les critères Pépite (Marge > 100% et > 150$ OU Marge > 30% et modèle iconique). Le verdict principal n'est pas modifié ; le champ traverse tel quel jusqu'à Firestore (`repository.py` ne filtre pas les clés de `aiAnalysis`) et jusqu'au frontend (filtre "Pépites", compteur, badge secondaire dans `DealCard.jsx`).

### `backend/notifications.py` (`NotificationService`)
- **Déclenchement** : `NOTIFY_VERDICTS = {'PEPITE'}` par défaut, plus toute annonce avec `also_qualifies_pepite=true` (même si son verdict principal diffère).
- **Canaux** : ntfy.sh (optionnel, `NTFY_TOPIC`) et Email SMTP (optionnel, `SMTP_USER`/`SMTP_PASSWORD`).
- **Encodage des headers ntfy** : Les headers HTTP (`requests`) n'acceptent que du Latin-1. Le `Title` (qui peut contenir émojis/accents) est encodé en **RFC 2047** (`email.header.Header`, `maxlinelen=998` pour éviter le repliement multi-ligne — invalide sur un header HTTP brut), conformément à `docs.ntfy.sh/publish`.
- **Point d'attention critique** : `handle_deal_found()` (dans `bot.py`) appelle `notify_deal()` de façon synchrone et non protégée ; `run_scan()` n'a pas de `except` sur sa boucle des villes (seulement un `finally`). Une exception non gérée dans `notify_deal()` interromprait le scan des villes restantes du cycle en cours — c'est ce qui s'est produit avant le correctif du 2026-07-06 (`HIGH_PRIORITY_VERDICTS`/`profit` non définis).
- **`notify_scan_url_finished()` (2026-07-21)** : Message adapté au code de statut retourné par `handle_deal_found()` (`processed`, `duplicate_unchanged`, `duplicate_cross_platform`, `already_rejected`, `marked_sold`, `rejected_prefilter`, `scrape_failed`, `sold_marker`), capturé par `bot.py::scan_specific_url()`. Inclut un lien direct vers l'annonce dans Guitar Hunter (`?dealId={id}`, même schéma que `notify_deal()`) en plus du lien d'origine. **`source` (2026-07-27, défaut `"Facebook"`)** : étiquette correctement le message ("URL Facebook :"/"URL Kijiji :") — auparavant toujours "URL Facebook" même pour un scan Kijiji, symptôme du même bug que `scan_specific_url()` ci-dessus (dispatch absent).

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
    - **Défilement dynamique borné (2026-07-14)** : `scan_marketplace()` scrollait auparavant un nombre fixe de fois (`ScraperConfig.scroll_iterations=3`, codé en dur, non exposé côté Firestore/`ConfigPanel`) avant de lire les cartes d'annonces chargées dans le DOM — ce plafond était atteint bien avant `max_ads` (réglable par l'utilisateur, ex: 50), limitant mécaniquement le nombre d'annonces vues par ville sans que ce soit visible ni configurable. Remplacé par un scroll dynamique : la boucle s'arrête dès que le nombre de cartes chargées atteint `max_ads`, ou qu'il stagne sur 2 itérations consécutives (fin de liste), avec un plafond de sécurité `ScraperConfig.max_scroll_iterations` (défaut 20) pour éviter qu'un cycle de scan s'éternise sur une ville à fort volume ou en cas de comportement anti-bot inattendu.
    - **Timeout `networkidle` sur le filtre de prix (Fix 2026-07-21)** : `_apply_filters()` attendait `page.wait_for_load_state("networkidle", timeout=10000)` après validation du prix maximum — Facebook Marketplace (SPA à trafic de fond permanent) n'atteint quasiment jamais un vrai silence réseau, ce qui faisait expirer l'attente quasi systématiquement (`WARNING - Erreur filtre prix: Timeout 10000ms exceeded.`), gaspillant 10s par ville. Remplacé par `wait_for_load_state("domcontentloaded", ...)`, qui ne dépend pas de l'arrêt du trafic réseau.
    - **Bug prix max sans garde-fou (Fix 2026-07-27)** : `_apply_filters()` remplissait et soumettait le champ "Prix maximum" de Facebook même quand `max_price == 0` (pas de plafond configuré), contrairement au champ "Prix minimum" qui avait déjà `if min_price > 0:`. Un scan sans plafond de prix aurait donc pu appliquer un filtre Facebook `maxPrice=0` invalide. Restructuré : soumission (`Enter` + attente de rechargement) faite une seule fois à la fin, seulement si un des deux champs a effectivement été rempli.

### `backend/scraping/kijiji/` (Nouveau 2026-07-26, validé en live le 2026-07-27 — intégré au pipeline `bot.py` et validé de bout en bout le 2026-07-27)
- **`KijijiScraper`** (`core.py`) : Scraper Playwright pour Kijiji.ca, calqué sur `FacebookScraper` — même forme de `listing_data` en sortie (`title`/`price`/`description`/`imageUrl(s)`/`link`/`location`/`id`), plus `source: "kijiji"`. Fournit `scan_marketplace()` (via le champ de recherche du site — voir limitation ci-dessous), `scan_search_url(url, max_ads)` (scrape directement une URL de résultats déjà construite, **méthode recommandée**), `scan_city(city_name, category_id, query, ...)` (résout un point d'ancrage Kijiji non-nul — sous-zone propre ou repli sur la plus proche résolvable, voir plus bas — puis appelle `scan_search_url`), `scan_specific_url()` (test isolé d'une annonce) et `check_listing_availability()` (miroir Facebook, pour le nettoyage périodique).
    - **Extraction basée sur `__NEXT_DATA__`** (confirmé en test live du 2026-07-26/27) : kijiji.ca (Next.js/Apollo) intègre l'état SSR complet de chaque annonce dans `<script id="__NEXT_DATA__">` — title/description/price/imageUrls exacts, garanti présent (hydratation React), donc bien plus fiable que JSON-LD ou tout sélecteur CSS. Présent à la fois sur une fiche détail individuelle (`parser.py::parse_details_page()`, cascade `__NEXT_DATA__` → JSON-LD → repli DOM) et sur une page de RÉSULTATS de recherche (tous les `StandardListing` affichés y sont — `parser.py::extract_all_standard_listings()`), avec toutefois **une seule URL d'image en aperçu par annonce côté résultats** (`imageCount` indique le vrai total ; la fiche détail individuelle reste visitée pour la galerie complète).
    - **⚠️ `location.name` pas toujours la ville précise** : constaté en test live — pour une annonce en périphérie d'une recherche (ex: physiquement à Sainte-Julie, trouvée via une recherche centrée sur Longueuil), `location.name` a renvoyé "Longueuil / South Shore" (la région de recherche Kijiji élargie), pas la ville exacte affichée sur la page. `location.address` (ex: "Rue Charles-de Gaulle, Ste-Julie, J3E 2V5") contient la ville réelle dans son texte et serait une piste pour une extraction plus précise, non implémentée. **Mitigation en place (2026-07-27)** : `locations.py::nearest_configured_city(latitude, longitude, city_coordinates, max_radius_km=None)` déduit la ville configurée la plus proche par distance Haversine sur les coordonnées GPS de l'annonce (toujours présentes/fiables, contrairement au texte) — appelé depuis `bot.py::_run_kijiji_scan()` pour chaque annonce trouvée.
    - **`core.py::_scrape_results_page()`** : essaie `__NEXT_DATA__` en premier (`_scrape_from_next_data`, pas de scroll/sélecteur DOM nécessaire pour les métadonnées de carte — confirmé : les liens Kijiji sont des URLs absolues, `a[href*='/v-']`, pas `a[href^='/v-']`), repli sur l'ancien défilement + sélecteurs `data-testid` (`_scrape_from_dom`) si `__NEXT_DATA__` est absent. Un timeout de fiche détail sur une seule annonce (`goto()`, vécu sur une annonce de Toronto) ne fait plus échouer tout le scan — repli sur les infos de carte/recherche déjà connues (`_fallback_details()`).
    - **`page.goto(..., wait_until="domcontentloaded")` (Fix 2026-07-27)** : `scan_search_url()`, `_visit_detail_page()`, `scan_specific_url()` attendaient l'événement `"load"` (défaut Playwright) sur leur `page.goto()` initial — Kijiji charge en continu des pubs/trackers en arrière-plan (déjà connu, voir les `wait_for_load_state("networkidle", ...)` tolérants ailleurs dans ce module), donc `"load"` pouvait dépasser `timeout_navigation` (60s) même quand le contenu utile était déjà là. Vécu en production : `Page.goto: Timeout 60000ms exceeded` sur une recherche par ailleurs valide, faisant échouer tout le scan de la ville. Même correctif que Facebook (`_apply_filters()`, ci-dessous) : `__NEXT_DATA__` (SSR) est déjà dans le HTML initial dès `domcontentloaded`, pas besoin d'attendre le "load" complet — précédent déjà en place pour `check_listing_availability()` dans ce même fichier.
    - **`backend/scraping/kijiji/locations.py`** (résolution ville → ID de lieu) : Kijiji publie un arbre statique et complet de tous ses lieux, pour **tout le Canada**, en un seul appel HTTP (`https://www.kijiji.ca/j-locations.json`). L'hypothèse initiale que le paramètre `q=` filtrait par province (`q=Quebec` → Québec seulement) s'est révélée fausse en vérification (diagnostic comparatif `backend/scripts/diag_kijiji_locations_scope.py`, puis confirmation décisive : l'ID de Toronto est présent dans la réponse peu importe `q=`) — la réponse est toujours l'arbre complet. `backend/scripts/fetch_kijiji_locations.py` télécharge/aplatit cet arbre en lookup `{nom_normalisé: {id, slug}}` (variantes FR/EN via `ListingParser.normalize_city_name`) sauvegardé dans `backend/resources/kijiji_locations.json` — **~192 entrées, ce sont de larges sous-régions** (ex: "Longueuil / South Shore" couvre aussi Saint-Bruno, Sainte-Julie, etc.), pas une ville par entrée : la plupart des petites municipalités du catalogue n'ont aucun équivalent par nom. `locations.build_search_url(category_id, location_id, query, ...)` construit l'URL de résultats correspondante (ex: `/b-guitar/longueuil-rive-sud/guitare/k0c613l1700279` — `c613` = ID de catégorie global "Guitars", stable pour tout le site ; `l1700279` = ID de lieu pour Longueuil/South Shore).
        - **⚠️ `location_id=0` (Canada) confirmé cassé (2026-07-27)** : une première tentative (même journée) faisait ancrer `scan_city()` sur `location_id=0` pour toute ville sans sous-zone propre, en s'appuyant sur `address`/`ll`/`radius` pour le ciblage géographique — **validation live sur une vraie annonce (Brossard) a montré que Kijiji ignore silencieusement `address=`/`ll=`/`radius=` quand le lieu du chemin d'URL est `l0`**, peu importe le format de `address` (avec ou sans province, les deux testés). Le test initial "positif" sur Saint-Bruno-de-Montarville n'a donc probablement pas fonctionné grâce au ciblage explicite, mais par coïncidence (tri par défaut/IP de l'environnement de test, plausiblement déjà géolocalisé près de Montréal).
        - **Repli sur le point d'ancrage résolvable le plus proche (correctif, 2026-07-27)** : `scan_city()` essaie `resolve_location()` d'abord (sous-zone propre à la ville, cas exact) ; à défaut, `locations.py::nearest_resolvable_hub(latitude, longitude, resolvable_hubs)` trouve par distance Haversine le point d'ancrage **valide et résolvable** le plus proche parmi `resolvable_hubs` (précalculé une fois par instance via `build_resolvable_hubs(lookup, city_coordinates)` — le sous-ensemble de `backend/resources/city_coordinates.json`, ~839 municipalités québécoises, qui résolvent réellement vers un lieu Kijiji, ~24 sur 839). `address`/`ll`/`radius` restent portés par la ville réelle (Brossard), seul l'ID d'ancrage du chemin d'URL change (celui de Longueuil/South Shore, 1700279) — validé en live : identique à la sélection manuelle d'un utilisateur via l'UI Kijiji pour la même ville. `"richmond"` (QC, Estrie) exclu explicitement des candidats d'ancrage — collision confirmée : résout vers l'ID Kijiji de Richmond, BC, pas la municipalité québécoise homonyme (même famille de piège que documentée dans `resolve_location()` pour Waterloo/Abbotsford/Stoke/Oka, mais celle-ci vérifiée réelle contre les données live). Si aucun ancrage n'est trouvé (pas de lat/lng fournis, ou aucun candidat résolvable à proximité), la ville est ignorée (`[]`) plutôt que de lancer une recherche Canada entière non ciblée.
        - **Filtre prix/rayon/adresse côté recherche (2026-07-27, validé en live)** : `build_search_url()` accepte `min_price`/`max_price` (append `?price={min}__{max}`, un bord vide si non fourni) et `address`/`lat`/`lng`/`radius_km` (append `&address={ville}&ll={lat}%2C{lng}&radius={radius_km}`, les trois envoyés **ensemble uniquement** — aucune validation live que `ll`/`radius` suffisent sans `address`) — mêmes mécanismes que `minPrice`/`maxPrice` et la géolocalisation forcée côté Facebook, mais encodés directement dans l'URL plutôt que pilotés via un champ de formulaire, et **seulement valables avec un `location_id` non-nul** (voir ci-dessus). Validé en live (`test_kijiji_scraper.py --search-url` puis `--scan-city`) : `price=100__250` ne retourne que des annonces entre 100$ et 250$, `address=...&ll=...&radius=6` ne retourne que des annonces dans ce rayon autour de l'adresse donnée.
        - **`radius_km` : défaut à deux paliers + réglage par ville (2026-07-27)** : un seul rayon fixe pour toutes les villes serait soit trop petit pour une grande ville (Montréal), soit inutilement large (faux positifs — `radius` se comporte plutôt comme un rectangle qu'un cercle, constaté par l'utilisateur) pour une petite. `bot.py::_run_kijiji_scan()` ne calcule plus de plancher fixe : priorité `city_data['kijijiRadiusKm']` (réglage par ville, Firestore) > `scanConfig.distance` (réglage global explicite, si > 0, partagé avec Facebook) > `None` transmis à `scan_city()`, qui applique alors elle-même `KijijiScraper.DEFAULT_RADIUS_KM_RESOLVED` (15km, ville résolue directement — sa propre sous-zone Kijiji, en pratique une ville assez grande pour ça) ou `DEFAULT_RADIUS_KM_HUB_FALLBACK` (5km, ville via `nearest_resolvable_hub()` — petite municipalité satellite par construction). Proxy imparfait (aucune donnée de taille/population par ville disponible) mais gratuit. `kijijiRadiusKm` : nouveau champ optionnel sur les préférences user des villes (`users/{uid}/cities/{cityId}`, même doc qu'`isScannable`) — `firestoreService.js::setCityKijijiRadius()`/`useCities.js::handleSetCityKijijiRadius` côté écriture (champ "km" par ville dans `ConfigPanel.jsx::CityManagementSection`), `repository.py::get_cities()` le propage dans `cities_to_scan` côté lecture backend.
    - **`KijijiListingParser`** (`parser.py`) : extraction de l'ID (dernier segment numérique du chemin `/v-<catégorie>/<lieu>/<titre>/<id>` — pas le premier, un slug intermédiaire peut aussi être numérique). Réutilise `ListingParser.extract_price_from_text` (module Facebook) plutôt que de le dupliquer.
    - **`scan_marketplace()` limité** : le champ de recherche de la page d'accueil (`input#global-header-search-bar-input`, confirmé par diagnostic live) fonctionne, mais **aucun champ de lieu n'est visible sur la page d'accueil** — le filtre de lieu semble caché derrière une modale non identifiée, donc `location` (scan_config) risque d'être silencieusement ignoré. `scan_search_url`/`scan_city` contournent complètement ce problème (le lieu est déjà encodé dans l'URL) et sont recommandés à la place.
    - **Écarts assumés vs `FacebookScraper`** (pas des oublis) : pas de rotation de proxy. Le filtre par ville, contrairement à l'évaluation initiale du 2026-07-26, est désormais couvert par `locations.py` (pancanadien, une seule requête HTTP, pas de navigateur nécessaire — plus simple que l'équivalent Facebook `get_city_id_and_coords()`) ; le filtre géographique par rayon/prix, lui, est désormais couvert côté recherche (`ll=`/`radius=`/`price=` dans l'URL, voir plus haut) — ce n'est donc plus un écart avec Facebook depuis le 2026-07-27.
    - **⚠️ Pagination non gérée** : `__NEXT_DATA__`/le DOM ne reflètent que les annonces déjà rendues côté serveur pour une page de résultats — si Kijiji pagine ses résultats (au lieu d'un défilement infini, non confirmé), `max_ads` au-delà de ce total nécessiterait de naviguer vers les pages suivantes (non implémenté).
    - **Intégré au pipeline (`bot.py::_run_kijiji_scan()`, 2026-07-27)** : source activable/désactivable via `scanConfig.kijiji_enabled` (toggle "Source Kijiji (bêta)" dans `ConfigPanel`), tourne en parallèle de `_run_facebook_scan()` (voir `run_scan()` plus haut) sur le même catalogue de villes/filtres partagés (`max_ads`, `search_query`, `distance`) — pas de `scan_config` Kijiji séparé dans cette itération. Annonces fusionnées dans `guitar_deals` (même collection que Facebook), distinguées par leur ID préfixé `kijiji_` et par `deal.link` (contient `kijiji.ca`) côté frontend. Seule la catégorie 613 (Guitars) est mappée pour l'instant. Validé de bout en bout en conditions réelles (`backend/scraping/kijiji/`, 49 tests unitaires + `backend/scripts/test_kijiji_scraper.py` pour les tests live).

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
- **Script de migration** (`backend/scripts/migrate_images.py`) : Script pour migrer les annonces historiques. Teste la validité des URL Facebook, re-scrape via Playwright si expirées, puis uploade dans Firebase Storage. Intègre la **Rotation de Session** (redémarrage du navigateur toutes les 15 annonces) et le **Jitter** (délais aléatoires) pour contrer l'anti-botting de Facebook lors d'opérations massives. **Ne convient pas** pour rétro-remplir un nouveau champ sur des annonces déjà uploadées : sa condition de saut (`storageImageUrls` déjà présent) les écarte toutes — voir `backfill_gs_uris.py` ci-dessous pour ce cas.
- **Script de backfill léger** (`backend/scripts/backfill_gs_uris.py`, 2026-08-01) : rétro-remplit `storageImageGsUris` (voir § Chat Gemini) sur les annonces qui ont déjà `storageImageUrls` — sans re-télécharger quoi que ce soit, via `repository.py::list_deal_image_gs_uris(deal_id)` qui liste les blobs déjà présents dans Firebase Storage sous `deals/{deal_id}/` (même motif que `delete_deal_images()`). Beaucoup plus léger que `migrate_images.py` pour ce cas précis (pas de Playwright, pas de re-upload). Support `--dry-run`.

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
  1. **`onDealsIndexUpdate()` :** S'abonne aux 20 chunks de l'index dans Firestore. Reçoit et fusionne les métadonnées légères en mémoire.
  2. **Lazy Loading (`loadedDeals`) :** Gère un cache local réutilisable de documents d'annonces complets. Il détecte automatiquement les annonces visibles à l'écran (premières 30, 60, etc.) et télécharge les documents complets manquants à la volée.
  3. **Défilement Infini (`visibleCount`) :** Affiche les deals par paquets de 30 au démarrage, extensible automatiquement de 50 en 50 lorsque l'utilisateur scroll vers le bas de la liste (via `IntersectionObserver` raccordé à `loadMore`).
  4. **Filtres de type en multi-sélection (2026-07-31) :** `selectedTypePaths` (tableau de chemins de taxonomie en dot-notation, ex: `["guitare.acoustique_acier.formes_standard.Parlor", "guitare.acoustique_acier.specialites.Travel.Baby / Mini"]`) remplace l'ancien système à 4 niveaux en cascade (un seul chemin actif à la fois). `matchesTypeFilter()` fait correspondre un deal si son chemin de classification égale ou descend (préfixe) d'**au moins un** chemin sélectionné — un chemin intermédiaire coché (ex: "Travel") inclut donc toutes ses sous-catégories. `typeCounts` reste calculé par chemin complet (dot-notation), indépendamment de la sélection courante, pour afficher un compteur à côté de chaque case à cocher dans `FilterDrawer.jsx`. La recherche texte libre (`searchQuery`) matche aussi `brand`/`model_name`/`color` (pas seulement `title`), disponibles pour toutes les annonces via `deals_index` (voir `DATA_FLOW.md` § 5).
  5. **`dealActions`:** Expose des fonctions (`handleRejectDeal`, `handleRetryAnalysis`) qui interagissent avec `firestoreService` en transmettant le `chunkId` requis pour maintenir l'index synchronisé.
  6. **`sortMode` (2026-07-14) :** État `'date'` ou `'interest'`. En mode `'interest'`, il utilise la note d'intérêt précalculée et stockée dans l'index (`interestScore`) pour trier instantanément en local, avec repli sur `computeInterestScore` en fallback.

### `src/services/firestoreService.js`
- **Couche d'abstraction:** Toutes les interactions avec Firestore sont ici.
- **`getRefs(userId)`:** Factory centralisée créant les références Firestore isolées par user. Valide `userId` avant création → `throw new Error(...)` si absent (fail fast).
- **`onDealsIndexUpdate()` :** Écoute les 20 documents de la collection `deals_index` et fournit un dictionnaire fusionné des métadonnées de toutes les annonces.
- **`fetchDealsByIds(ids)` :** Charge les documents d'annonces complets par paquets de 30 maximum via une requête `where(documentId(), 'in', chunks)`.
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
- **`src/components/DealCard/DealAnalysisModal.jsx` — Fiche Technique (2026-07-31)** : bloc affichant marque, modèle, année, pays de fabrication et couleur (`deal.aiAnalysis.brand/model_name/production_year/country_of_origin/color`) — ces champs étaient déjà produits par l'IA mais jamais affichés dans l'UI. Un champ absent ou valant une variante de "Inconnue" est filtré silencieusement plutôt que d'afficher une ligne vide.
- **Chat Gemini intégré (`DealChatPanel.jsx`, `useDealChat.js`, `geminiChatService.js`, 2026-07-31)** : remplace l'itération précédente (copie presse-papier + hand-off vers `gemini.google.com`, abandonnée car incapable de transmettre les photos — voir historique dans `JOURNAL.md`). Conversation multi-tour construite avec **Firebase AI Logic** (SDK `firebase/ai`, `getAI()`/`getGenerativeModel()`/`startChat()`) appelé **directement depuis le frontend** — pas de backend Python impliqué, pas de latence de polling.
  - **Pourquoi client-side plutôt qu'une Cloud Function** : le backend Python existant est un *worker* qui poll Firestore toutes les quelques secondes (pensé pour des tâches lentes en arrière-plan), un mauvais fit pour un aller-retour conversationnel. Firebase AI Logic est le SDK officiel conçu pour "app + images sur Cloud Storage for Firebase + chat" — sécurité via **Firebase App Check** (reCAPTCHA Enterprise, `VITE_RECAPTCHA_SITE_KEY`) plutôt qu'une clé API à cacher côté serveur. **Étape manuelle requise, non faisable depuis un environnement automatisé** : activer Firebase AI Logic (Gemini Developer API) et enregistrer une clé reCAPTCHA Enterprise dans App Check, dans la console Firebase du projet.
  - **Jeton de debug App Check pour le dev local (2026-07-31)** : reCAPTCHA Enterprise valide un domaine de production, pas `localhost` — `firebase.js` pose `self.FIREBASE_APPCHECK_DEBUG_TOKEN = true` avant `initializeAppCheck()`, uniquement si `import.meta.env.DEV` (jamais actif en build de production). Le jeton généré au premier lancement local (affiché en console navigateur) doit être enregistré une fois dans la console Firebase (App Check > Apps > ⋮ > Manage debug tokens).
  - **Images en base64/`inlineData` (2026-08-01, corrigé)** : `gs://` direct **ne fonctionne pas** avec le backend réellement configuré (`GoogleAIBackend`, API Developer) — confirmé en test réel (erreur 400 "Referencing Google Cloud Storage files directly is not supported. Register them using FileService.RegisterFile first."). Ce mécanisme n'existe que côté **Vertex AI** (vérifié initialement, mais backend non retenu ici pour rester cohérent avec `GEMINI_API_KEY` côté Python — voir plus haut) ; le File API du Developer API n'est lui-même pas exposé par le SDK Firebase AI Logic. `geminiChatService.js::buildDealImageParts()` télécharge donc chaque image depuis son URL HTTPS publique (`storageImageUrls`) et l'encode en base64 (`inlineData`) côté navigateur avant de l'attacher au premier message. `backend/repository.py::upload_images_to_storage()` retourne toujours un tuple `(storageImageUrls, storageImageGsUris)` et `storageImageGsUris` reste écrit en base (`backfill_gs_uris.py`) — gardé pour une éventuelle migration future vers `VertexAIBackend`, mais **non utilisé** par le chat actuellement.
    - **Risque CORS non vérifié** : `fetch()` depuis le navigateur vers `storage.googleapis.com` peut être bloqué si le bucket Firebase Storage n'a pas de configuration CORS autorisant l'origine de l'app (contrairement à une balise `<img src>`, non soumise aux mêmes règles — c'est ainsi que les mêmes URLs s'affichent déjà sans problème ailleurs dans l'app). Si le chat ne reçoit toujours aucune photo après le correctif ci-dessus, vérifier la console réseau du navigateur pour une erreur CORS, et configurer `gsutil cors set` sur le bucket si besoin.
  - **Historique persisté** : `guitar_deals/{dealId}/chat/{msgId}` (écriture directe frontend → Firestore, déjà couvert par la règle générique `users/{userId}/{document=**}`, aucune règle Firestore à ajouter). Chaque message stocke `parts` (payload exact envoyé/reçu par l'API, y compris les pièces image du premier tour — rejoué tel quel dans `startChat({history})` pour reprendre une conversation après rechargement) et `displayText` (texte réellement affiché, sans le contexte injecté invisible à l'utilisateur).
  - **Modèle** : `analysisConfig.expertModel` (même modèle que le Tier 3 Expert Pro du pipeline d'analyse, pour une continuité de capacité entre analyse automatique et conversation).
  - **Caching** : évalué et écarté — le caching explicite (`CachedContent`) exige un minimum de ~32 768 tokens, très au-dessus du contexte d'une conversation sur une seule annonce (~1500-2500 tokens). Le caching implicite (automatique sur les modèles récents, sans code à écrire) s'applique naturellement grâce à `startChat()` qui garde les images/contexte en préfixe stable de l'historique.
  - **Dépendance** : `firebase` passé de `^10.8.0` à `^12.17.0` (le module `firebase/ai` n'existe qu'à partir de la v11) — surface utilisée par l'app (`firebase/app`, `firebase/auth`, `firebase/firestore`) inchangée, build vérifié, mais **non testé en conditions réelles** (pas de compte Firebase dans cet environnement) : à valider par l'utilisateur (login, chargement des annonces) avant fusion.
  - **Bouton "Discuter avec Gemini"** : retiré de la carte liste, disponible uniquement dans la modale d'analyse (`DealCardActions.jsx`, prop `onOpenChat`, gardée par `isModal`) — ouvre le panneau de chat à la place du contenu d'analyse habituel (bouton retour). Réduit le nombre de boutons sur la vue liste (voir `TODO.md`).

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
    - Utilise `recharts` pour visualiser un **Radar Chart** du profil moyen IA (5 scores) et deux **Bar Chart** pour la distribution du Top des Marques et des Couleurs/Finitions (`aiAnalysis.color`, nouveau 2026-07-31). Ces deux graphiques lisent `aiAnalysis.brand`/`aiAnalysis.color` sur `enrichedDeals` (fusion index + cache `loadedDeals`) — depuis que `brand`/`color` sont indexés (`deals_index`, voir `DATA_FLOW.md` § 5), ils sont représentatifs de **toutes** les annonces et pas seulement de celles déjà ouvertes par l'utilisateur.
    - **Erreurs Portier corrigées (2026-07-11) :** Sous le Funnel — compte les annonces dont `initialModelUsed` ne compte qu'un maillon (arrêtées au Portier T1 seul) et dont la chaîne `aiAnalysis.model_used` **actuelle** en compte 2 ou plus (réanalysées avec succès jusqu'à l'Analyste ou l'Expert). Un signal direct du taux de faux positifs du Portier, sans dépendre du texte du verdict (`BAD_DEAL` étant ambigu — voir `initialVerdict`/`initialModelUsed` plus haut).
    - **Volume de Scraping Quotidien (2026-07-21) :** `BarChart` regroupant `enrichedDeals` par jour (14 derniers jours) via `timestamp.seconds`, déjà présent sur 100% des annonces de l'index temps réel (`deals_index`) — pas seulement celles chargées en lazy loading. Aucune lecture Firestore additionnelle.

### `src/components/DealCard.jsx`
- **Composant de Production :** Version aboutie de la carte d'annonce avec design premium.
- **Barre d'Actions :** `renderActionButtons()` factorise les actions pour la Modale d'Analyse IA (`isModal=true`, seul point d'appel). Le footer de la carte (vue grille) a sa **propre copie indépendante non factorisée** du même bloc — dette technique existante, pas encore unifiée.
- **Partage Public :** `handleShare` écrit un snapshot dans `shared_deals/{dealId}` (Firestore public), puis génère `?shareId={dealId}`. Utilise `navigator.share` avec fallback clipboard. Le destinataire n'a pas besoin de compte.
- **Menu de Ré-analyse :** Dropdown dynamique (présent aux deux endroits ci-dessus) offrant le choix entre "Scan Standard", "Luthier Expert", et "Avec commentaire..." (2026-07-07) — ce dernier ouvre une modale dédiée pour saisir une correction/précision transmise en priorité à l'IA lors d'une réanalyse Expert (`user_comment`, voir `backend/analyzer.py`).
- **Badge Note d'Intérêt (2026-07-14) :** À côté du badge de verdict, affiche `computeInterestScore(aiAnalysis)` (`constants.js`, moyenne des 5 scores IA) sous forme "Note X.X/10" — absent si aucun score n'est disponible. Sert de repère visuel complémentaire au tri par intérêt (`useDealsManager.js::sortMode`).
- **Bouton "voir l'annonce d'origine" sensible à la source (`DealCardActions.jsx`, 2026-07-27) :** `deal.source` n'existant que pour Kijiji (jamais pour Facebook), la détection se fait via `deal.link.includes('kijiji.ca')` — même logique que le badge source à côté du titre (`DealCard/index.jsx::isKijiji`). Affiche un badge orange "K" + tooltip "Voir sur Kijiji" au lieu de l'icône Facebook bleue quand l'annonce vient de Kijiji.
- **Chat Gemini intégré (`DealCardActions.jsx` → `DealChatPanel.jsx`, 2026-07-31)** : voir la description complète (Firebase AI Logic, images `gs://`, historique Firestore) dans la section `DealCard/DealAnalysisModal.jsx — Fiche Technique` plus haut.

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
