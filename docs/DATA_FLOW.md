# Flux de Données - Guitar Hunter

Ce document décrit l'architecture événementielle et le cycle de vie des données entre le Frontend (React/JS) et le Backend (Python) via Firebase Firestore.

## 1. Déclenchement de l'action depuis le Frontend
L'utilisateur interagit avec l'interface (ex: bouton "Refresh", ajout de ville, analyse forcée).
- **Service impliqué** : `src/services/firestoreService.js`
- **Méthode** : `addCommand(type, payload)` ou modification directe de la config utilisateur via `updateUserConfig`.
- **Exemple** : Un clic sur "Add City" appelle `requestAddCity(cityName)`.

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
- **Mécanisme d'écoute** : Boucle principale dans `main.py` qui appelle `bot.sync_and_apply_config()`.
- **Dispatching** : `command_handlers` dans `main.py` associe le `type` de commande à une méthode de `GuitarHunterBot`.
- **Exécution Asynchrone** : Les commandes longues (ex: `REFRESH`, `REANALYZE_ALL`, `SCAN_URL`) sont lancées dans des threads `daemon` séparés (`threading.Thread`) pour ne pas bloquer les autres opérations ni le séquenceur principal (`scheduler`). Chaque exécution asynchrone appelant le scraper initialise son propre navigateur localement pour éviter les plantages `greenlet.error` de conflit de threads (Playwright n'étant pas thread-safe si instancié globalement).
- **Exécution Synchrone** : Les commandes immédiates ou vitales (ex: `STOP_BOT`, `CLEAR_LOGS`) sont exécutées directement dans la boucle.
- **Traitement** : Le bot exécute l'action (scan Facebook, appel API Gemini, nettoyage), puis :
  - Marque la commande comme complétée : `bot.repo.mark_command_completed(command_id)`.
  - Met à jour son statut de façon concurrente via une méthode verrouillée : `bot.set_status('scanning' | 'idle' | 'paused' | 'stopped', task_name='...')`, garantissant l'intégrité de l'affichage UI même avec de multiples threads actifs.

## 4. Structure des résultats (Collection `guitar_deals`)
*Note : Malgré le nom historique `guitar_deals`, cette collection stocke désormais tous les types d'équipements (Guitares, Amplis, Étuis).*
Lorsqu'une annonce est trouvée et analysée, elle est enregistrée dans Firestore.
- **Chemin** : `artifacts/{APP_ID}/users/{USER_ID}/guitar_deals/{DEAL_ID}`
- **Étapes de création** :
  1. `bot.handle_deal_found(listing_data)`
  2. `repo.upload_images_to_storage(image_urls, deal_id)` → retourne `storageImageUrls` (URLs Firebase pérennes).
  3. `analyzer.analyze_deal(listing_data)` -> Génère un verdict (Good Deal, Rejected, etc.).
  4. `repo.create_new_deal(...)` ou `repo.update_deal_analysis(...)` avec `storageImageUrls` injecté.
- **Format de donnée type** :
  ```json
  {
    "title": "String",
    "price": "Number",
    "status": "analyzed" | "rejected" | "sold",
    "imageUrls": ["URL CDN Facebook (temporaire)"],
    "storageImageUrls": ["URL Firebase Storage (pérenne)"],
    "aiAnalysis": { 
       "verdict": "PEPITE" | "FAST_FLIP" | "BAD_DEAL" | "REJECTED_ITEM" | ...,
       "classification": "Valeur de taxonomy_master (ex: guitare.acoustique.folk)",
       "reasoning": "Markdown text",
       "deal_score": 0-10,
       "authenticity_score": 0-10,
       "condition_score": 0-10,
       "liquidity_score": 0-10,
       "restoration_interest_score": 0-10,
       "model_used": "Chain of models used",
       "tier3_trigger": "Reason why Expert Pro was called (optional)"
    },
    "link": "URL",
    "timestamp": "ServerTimestamp"
  }
  ```

## 5. Mise à jour automatique du Frontend (Listen UI)
Le Frontend utilise les capacités temps-réel de Firestore pour refléter les changements sans rechargement.
- **Mécanisme** : `onSnapshot` de Firebase.
- **Abonnements** :
  - `onDealsUpdate` : Écoute les changements dans `guitar_deals` pour mettre à jour la liste des annonces.
  - `onBotConfigUpdate` : Écoute les changements du document utilisateur (statut du bot, erreurs, config globale).
  - `onCitiesUpdate` : Écoute la liste des villes.
- **Résultat** : L'UI React réagit instantanément dès que Python écrit dans Firestore.

## 6. Flux d'Interactions UI (Exemple : Cartographie)
1. **Survol/Clic Marqueur** → `MapView` déclenche l'affichage de l'InfoWindow locale (Data issues du `deal` associé).
2. **Clic InfoWindow** → `MapView` appelle `onSelectDeal(deal)`.
3. **Changement d'état** → `MockupDashboard` reçoit le nouveau `selectedDeal` et déclenche l'affichage (Overlay sur Mobile, Sidebar sur Desktop).
