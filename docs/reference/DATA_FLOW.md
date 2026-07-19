# Flux de Données - Guitar Hunter

Ce document décrit l'architecture événementielle et le cycle de vie des données entre le Frontend (React/JS) et le Backend (Python) via Firebase Firestore.

## 1. Déclenchement de l'action depuis le Frontend
L'utilisateur interagit avec l'interface (ex: bouton "Refresh", ajout de ville, analyse forcée).
- **Service impliqué** : `src/services/firestoreService.js`
- **Méthode** : `addCommand(type, payload)` ou modification directe de la config utilisateur via `updateUserConfig`.
- **Exemple** : Un clic sur "Add City" (bouton "+" du champ de recherche principal) appelle `requestAddCity(cityName)`. Le backend utilise ensuite Playwright pour chercher cette ville sur Facebook Marketplace et extraire son ID interne et ses coordonnées mondiales.
- **Scan Manuel** : Le bouton "Lancer le scan" dans le `ConfigPanel` crée une commande `MANUAL_SCAN` qui force le bot à démarrer un cycle de scan complet des villes actives sans attendre le prochain intervalle.

- **Onboarding** : Lors d'un `signUp`, `signIn` ou au chargement d'une session existante dans `src/hooks/useAuth.js`, la fonction centralisée `ensureUserDoc` crée ou met à jour le document utilisateur dans `artifacts/{APP_ID}/users/{USER_ID}`. En cas d'erreur de permission Firestore, un signal visuel (`warning`) est envoyé au frontend. Ce document sert de signal au backend pour démarrer un bot dédié.

## 2. Structure de la commande (Collection `commands`)
Les actions asynchrones sont stockées dans la sous-collection `commands` pour être traitées par le bot.
- **Chemin** : `artifacts/{APP_ID}/users/{USER_ID}/commands/{COMMAND_ID}`
- **Structure type** :
  ```json
  {
    "type": "REFRESH" | "ADD_CITY" | "ANALYZE_DEAL" | "CLEAR_LOGS" | "STOP_BOT" | "STOP_SCAN" | "START_BOT",
    "payload": "Données spécifiques (ex: nom de ville, ID de l'annonce, null pour les arrêts)",
    "status": "pending",
    "createdAt": "Timestamp"
  }
  ```

## 3. Interception et traitement par le Backend Python
Le script `main.py` surveille Firestore et délègue les tâches à `backend/bot.py`.
- **Mécanisme d'écoute** : Boucle principale dans `main.py` qui appelle `bot.sync_and_apply_config()`. Le script scanne également la collection `users` toutes les 30s pour découvrir de nouveaux utilisateurs et démarrer leurs bots respectifs.
- **Dispatching** : `command_handlers` dans `main.py` associe le `type` de commande à une méthode de `GuitarHunterBot`.
- **Exécution Asynchrone** : Les commandes longues (ex: `REFRESH`, `REANALYZE_ALL`, `SCAN_URL`) sont lancées dans des threads `daemon` séparés (`threading.Thread`) pour ne pas bloquer les autres opérations ni le séquenceur principal (`scheduler`). Chaque exécution asynchrone appelant le scraper initialise son propre navigateur localement pour éviter les plantages `greenlet.error` de conflit de threads (Playwright n'étant pas thread-safe si instancié globalement). **Nouveau** : Ces instances utilisent des techniques de **Stealth/Anti-Bot** (User-Agent aléatoire, Viewport varié, flags Playwright).
- **Exécution Synchrone** : Les commandes immédiates ou vitales (ex: `STOP_BOT`, `CLEAR_LOGS`) sont exécutées directement dans la boucle.
- **Traitement** : Le bot exécute l'action (scan Facebook, appel API Gemini, nettoyage), puis :
  - Marque la commande comme complétée : `bot.repo.mark_command_completed(command_id)`.
  - Met à jour son statut de façon concurrente via une méthode verrouillée : `bot.set_status('scanning' | 'idle' | 'paused' | 'stopped', task_name='...')`, garantissant l'intégrité de l'affichage UI même avec de multiples threads actifs.

## 4. Structure des résultats (Collection `guitar_deals`)
*Note : Malgré le nom historique `guitar_deals`, cette collection stocke désormais tous les types d'équipements (Guitares, Amplis, Étuis).*
Lorsqu'une annonce est trouvée et analysée, elle est enregistrée dans Firestore.
- **Chemin** : `artifacts/{APP_ID}/users/{USER_ID}/guitar_deals/{DEAL_ID}`
- **Étapes de création** :
  1. `bot.handle_deal_found(listing_data)` — **(2026-07-09)** si `imageUrls` est vide ET prix à 0$ (scraping manifestement raté), la fonction s'arrête ici : rien n'est écrit dans `guitar_deals`, l'annonce sera retraitée comme nouvelle à la prochaine session.
  2. Pré-filtres : mot-clé d'exclusion (`verdict: REJECTED` → `status: rejected`) ou prix > `scanConfig.max_price` (**2026-07-09**, `verdict: BAD_DEAL` → `status` reste `analyzed`, catégorie "Trop Cher" masquée par défaut côté frontend mais pas un vrai rejet).
  3. `repo.upload_images_to_storage(image_urls, deal_id)` → retourne `storageImageUrls` (URLs Firebase pérennes).
  4. `analyzer.analyze_deal(listing_data)` -> Génère un verdict (Good Deal, Rejected, etc.).
  5. `repo.create_new_deal(...)` ou `repo.update_deal_analysis(...)` avec `storageImageUrls` injecté. **(2026-07-11)** `create_new_deal()` snapshotte en plus `initialVerdict`/`initialModelUsed` (verdict et chaîne `model_used` du tout premier passage) — ces champs ne sont plus jamais réécrits par une réanalyse ultérieure, contrairement à `aiAnalysis`.
- **Format de donnée type** :
  ```json
  {
    "title": "String",
    "price": "Number",
    "original_price": "Number (Optionnel, si baisse de prix)",
    "price_drop_amount": "Number (Optionnel, si baisse de prix)",
    "status": "analyzed" | "rejected" | "sold",
    "initialVerdict": "Verdict du tout premier passage IA (figé, jamais réécrit)",
    "initialModelUsed": "Chain of models du tout premier passage (ex: flash-lite seul si arrêté au Portier) - absent sur les annonces créées avant 2026-07-11",
    "imageUrls": ["URL CDN Facebook (temporaire)"],
    "storageImageUrls": ["URL Firebase Storage (pérenne)"],
    "aiAnalysis": { 
       "verdict": "PEPITE" | "FAST_FLIP" | "BAD_DEAL" | "REJECTED_ITEM" | ...,
       "classification": "Valeur hiérarchique (dot-notation, ex: guitare.electrique.solid_body)",
       "brand": "Marque (ex: Fender)",
       "model_name": "Modèle exact (ex: Stratocaster)",
       "production_year": "Année/Décennie",
       "country_of_origin": "Pays de fabrication",
       "reasoning": "Markdown text",
       "deal_score": 0-10,
       "authenticity_score": 0-10,
       "condition_score": 0-10,
       "liquidity_score": 0-10,
       "restoration_interest_score": 0-10,
       "model_used": "Chain of models used (ex: flash-lite -> flash -> pro)",
       "tier3_trigger": "Reason why Expert Pro was called (optional)"
    },
    "link": "URL",
    "published_at_raw": "il y a X semaines (extraite par le scraper)",
    "soldAt": "Timestamp (Optionnel, présent uniquement si status=sold)",
    "timestamp": "ServerTimestamp"
  }
  ```

## 5. Rôle de l'Index et Sharding (Collection `deals_index`)
Pour contourner la limite de taille et les coûts de lecture Firestore, le système maintient un index allégé des annonces.
- **Chemin** : `artifacts/{APP_ID}/users/{USER_ID}/deals_index/{CHUNK_ID}` (de `chunk_0` à `chunk_19`).
- **Principe** : Les annonces sont distribuées sur 20 chunks via un hachage MD5 déterministe sur le `deal_id`.
- **Maintenance (Backend)** : À chaque création/modification/suppression/vente, le backend met à jour la clé correspondante dans le chunk d'index via dot-notation (ex: `deals.deal_123.s = "sold"`), sans aucune lecture Firestore supplémentaire.
- **Propriétés indexées** : `s` (statut), `v` (verdict), `f` (isFavorite), `t` (timestamp), `p` (prix), `c` (classification), `cs` (condition_score), `ap` (also_qualifies_pepite), `title` (titre) et `is` (interest_score).

## 6. Mise à jour automatique et Lazy Loading du Frontend
Le Frontend utilise les capacités temps-réel de l'index et charge les détails à la demande.
- **Abonnements temps réel** :
  - `onDealsIndexUpdate` : Écoute les 20 documents de `deals_index`. Fusionne localement les dictionnaires de métadonnées de toutes les annonces en un unique tableau léger en mémoire au démarrage (seulement 20 lectures Firestore au lieu de 2748+).
  - `onBotConfigUpdate` : Écoute les changements du document utilisateur (statut du bot, erreurs, config globale).
  - `onCitiesUpdate` : Écoute la liste des villes.
- **Lazy Loading des documents complets** :
  - Le hook `useDealsManager.js` filtre et trie localement les annonces légères à partir de l'index en mémoire.
  - Il identifie la tranche visible à l'écran (premières 30 annonces au départ, puis étendues de 50 en 50 automatiquement par défilement infini).
  - Un `IntersectionObserver` dans `Dashboard.jsx` surveille un trigger invisible en bas de liste et appelle `loadMore` dès qu'on s'en approche à moins de 300px.
  - Il déclenche `fetchDealsByIds(missingIds)` pour charger en une seule fois les documents complets (images, description, analyse IA reasoning) associés uniquement aux annonces visibles.
  - Les cartes d'annonces affichent un squelette animé (skeleton loader) durant la brève phase de chargement des détails complets (~150ms).
  - Si l'utilisateur clique sur un marqueur de carte ou ouvre un lien direct `?dealId=`, le document complet est également téléchargé à la volée s'il n'est pas déjà présent dans le cache React local.

## 6. Flux d'Interactions UI (Exemple : Cartographie)
1. **Survol/Clic Marqueur** → `MapView` déclenche l'affichage de l'InfoWindow locale (Data issues du `deal` associé).
2. **Clic InfoWindow** → `MapView` appelle `onSelectDeal(deal)`.
3. **Changement d'état** → `Dashboard` reçoit le nouveau `selectedDeal` et déclenche l'affichage (Overlay sur Mobile, Sidebar sur Desktop).
4. **Redirection par URL (`dealId`)** → Si l'URL contient un paramètre `dealId` (ex: `?dealId=123`), le `Dashboard` détecte ce paramètre au chargement, sélectionne l'annonce correspondante et ouvre la modale de détail, en forçant le mode d'affichage "Carte". L'URL est ensuite nettoyée.
5. **Partage d'Annonce (public)** → Le bouton de partage dans `DealCard.jsx` écrit un snapshot de l'annonce dans la collection Firestore publique `shared_deals/{dealId}`, puis génère un lien `?shareId={dealId}`. Lorsque ce lien est ouvert, `App.jsx` détecte `?shareId=` avant le mur d'auth et rend `SharedDealPage.jsx` directement, sans exiger de compte. La collection `shared_deals` est lisible publiquement (`allow read: if true` dans les règles Firestore).
## 7. Flux de Logs (Observabilité)
Le système de logging est désormais isolé par utilisateur pour garantir l'étanchéité des données en mode multi-tenant.
- **Backend** : `backend/logging_config.py` configure un logger nommé `bot.{user_id[:8]}` pour chaque bot.
- **Transmission** : Le `FirestoreHandler` capture les logs émis par ce logger et les envoie par lots (batches) vers la sous-collection `logs` de l'utilisateur.
- **Modules `backend/scraping/*`, `analyzer.py`, `notifications.py` (2026-07-09)** : Tous reçoivent désormais ce même logger par-utilisateur (injecté depuis `bot.py` via un paramètre `logger`, propagé jusqu'aux fonctions/méthodes utilitaires — ex: `FacebookScraper(..., logger=self.logger)`, `DealAnalyzer(logger=self.logger)`, `NotificationService.notify_deal(..., logger=self.logger)`). Avant ce correctif (appliqué module par module au fil de l'investigation), chacun loguait sur `logging.getLogger(__name__)` (logger de module, jamais raccordé au `FirestoreHandler`) — rien de ce qui s'y passait n'était visible dans le LogViewer. **Règle pour tout nouveau module** : accepter un paramètre `logger` optionnel (repli sur le logger de module) plutôt que de logger directement sur un logger de module — sinon ses logs resteront invisibles pour l'utilisateur.
- **Chemin Firestore** : `artifacts/{APP_ID}/users/{USER_ID}/logs/{LOG_ID}`
- **Frontend** : Le composant `LogViewer.jsx` s'abonne à cette collection en temps réel pour afficher la console de débogage spécifique à l'utilisateur connecté.
- **Ordre d'affichage non garanti** : `FirestoreHandler` bufferise les logs et les envoie par lots toutes les 3s (thread séparé). Des logs émis à quelques centaines de ms d'écart (ex: juste avant/après un appel synchrone à `handle_deal_found`) peuvent recevoir un `timestamp` serveur identique ou très proche et s'afficher dans un ordre différent de leur ordre d'émission réel dans le code — ne pas déduire l'ordre d'exécution depuis l'ordre d'affichage du LogViewer sans vérifier le code source.
- **Nettoyage** : La commande `CLEAR_LOGS` permet à l'utilisateur de vider sa collection de logs sans affecter les autres utilisateurs.
