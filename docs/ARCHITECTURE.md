# Architecture Technique - Guitar Hunter AI

Ce document détaille le fonctionnement interne du projet.

## 1. 🔄 Firestore : Le Cœur du Système (Event Bus)

Le projet utilise une architecture où **Firestore n'est pas seulement une base de données, mais un bus d'événements et de commandes**.

⚠️ **IMPORTANT : Structure Imbriquée (Multi-tenant)**
Toutes les données sont isolées par application et par utilisateur. Le chemin de base pour toutes les collections est :
`artifacts/{APP_ID}/users/{USER_ID}/...`

- **`guitar_deals` (Collection):** (Chemin: `.../guitar_deals`). Contient toutes les annonces. Le frontend écoute cette collection en temps réel. Les annonces peuvent avoir plusieurs statuts : `analyzed` (par défaut), `rejected` (masqué totalement), ou `sold` (**Soft Delete** - masqué du flux principal mais conservé en base).
- **`commands` (Collection):** (Chemin: `.../commands`). Le frontend écrit des documents ici pour demander toutes les actions au backend (ex: `ANALYZE_DEAL`, `REFRESH`, `CLEANUP`, `STOP_BOT`, `STOP_SCAN`, `START_BOT`). Le backend écoute cette collection, traite la commande de manière unifiée, puis la marque comme complétée.
  - **`STOP_BOT` :** Commande qui déclenche un état de "Sommeil" (pause de 12h interruptible) dans `main.py`. Utilise `stop_event` pour interrompre le travail en cours et change le statut du bot en `paused`. Le bot ne s'éteint plus totalement mais attend un réveil ou l'expiration du délai.
  - **`STOP_SCAN` :** Interrompt uniquement le cycle de scraping Playwright en cours via un `scan_stop_event` dédié. Le bot reste actif et prêt pour d'autres commandes (ex: Refresh, Reanalyse).
  - **`START_BOT` :** Réveil immédiat. Interrompt la boucle de pause via `start_event`. Note : toute autre commande actionnable (`REFRESH`, `SCAN_URL`, `CLEANUP`, `CLEAR_LOGS`, etc.) reçue pendant la pause réveille également le bot automatiquement (sondage Firestore toutes les 5s) et est exécutée immédiatement après le réveil.
- **`users/{userID}` (Document):** (Chemin: `artifacts/{APP_ID}/users/{USER_ID}`). Contient la configuration et le statut dynamique du bot (`botStatus`: `idle`, `scanning`, `paused`, `stopped`).

## 2. 🐍 Backend (Python)

Le backend est un "worker" persistant qui tourne en boucle.

### `main.py`
- **Point d'entrée:** Initialise le `GuitarHunterBot` et le `DatabaseService` (Firestore + Firebase Storage).
- **Boucle principale:**
  1. Vérifie les commandes dans Firestore (`sync_and_apply_config`).
  2. Exécute les tâches planifiées (scan, nettoyage) via `TaskScheduler`.
  3. Gère un `command_handlers` pour router les commandes Firestore vers les bonnes méthodes du bot.
- **`run.bat`:** Script de lancement à la racine du projet. Utilise toujours le venv Python (`\venv\Scripts\python.exe`) et force l'encodage UTF-8 (`PYTHONUTF8=1`). Commandes : `run.bat` (bot), `run.bat migrate` (migration dry-run), `run.bat migrate --real` (migration réelle).

### `backend/bot.py` (`GuitarHunterBot`)
- **Classe centrale:** Orchestre toutes les opérations du backend.
- **Gestionnaire d'état robuste:** Utilise un accès concurrent sécurisé via `threading.Lock()` et `set_status()` pour gérer l'étiquetage du `botStatus` en fonction des threads actifs (ex: `_active_tasks`), empêchant les processus asynchrones d'écraser prématurément des états prioritaires comme `scanning`.
- **`run_scan()`:** Déclenche le scraping des villes configurées. Régulé par le `scheduler`.
- **`handle_deal_found()`:** Callback appelé par le scraper pour chaque annonce trouvée. Orchestre : (1) upload des images vers Firebase Storage (`repo.upload_images_to_storage()`), (2) injection de `storageImageUrls` dans les données, (3) appel à l'analyseur IA, (4) sauvegarde dans Firestore.
- **`analyze_single_deal(payload)`:** Méthode spécifique pour traiter une commande de réanalyse (`ANALYZE_DEAL`). Elle récupère l'annonce et appelle `analyzer.analyze_deal`.
- **`sync_and_apply_config()`:** Lit la configuration depuis Firestore et applique les changements (fréquence, etc.).

### `backend/analyzer.py` (`DealAnalyzer`)
- **Responsabilité unique:** Analyser une annonce en cascade.
- **`_call_gemini_json(model_name, content_parts)`:** Méthode utilitaire DRY. Centralise l'appel Gemini, le parsing JSON et la gestion d'erreur. Utilisée par les 3 Tiers.
- **`_construct_base_user_prompt()`:** Construit le prompt de base (taxonomie + détails + few-shot) **une seule fois** par analyse.
- **`analyze_deal(listing_data, firestore_config, force_expert=False)` — Cascade 3-Tiers :**
  1. **Tier 1 — Portier (`gemini-2.5-flash-lite`) :** Filtre rapide/peu coûteux. Rejette bruit et services. Produit un verdict statut simple (`PEPITE`, `BAD_DEAL`, etc.). Si rejet → fin immédiate.
  2. **Tier 2 — Analyste (`gemini-2.5-flash`) :** Si T1 passe, analyse structurée avec 5 scores numériques (`deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, `restoration_interest_score`). Format compacté (puces).
  3. **Carrefour Logique :** Évalue les scores du T2 et le prix extrait via `ListingParser.extract_price_from_text`. Déclenche le T3 si :
     - Prix > 1000€ ET deal_score >= 4
     - deal_score >= 8
     - Combo : deal_score >= 6 ET restoration_interest_score >= 7
     - authenticity_score <= 7 (doute d'authenticité)
     - confidence < 0.75
     - verdict == 'COLLECTION'
     - `force_expert=True` (demande manuelle)
  4. **Tier 3 — Expert Pro (`gemini-2.5-pro`) [Conditionnel] :** Analyse exhaustive avec rapport Markdown complet. Écrase le résultat du T2. En cas d'échec : fallback sur le T2.
  - Le champ `model_used` retrace le chemin complet (ex: `"gemini-2.5-flash-lite -> gemini-2.5-flash -> gemini-2.5-pro"`).
  - Le champ `tier3_trigger` indique le motif de déclenchement du T3 (si applicable).

### `backend/scraping/`
- **`FacebookScraper`** : Utilise Playwright pour naviguer sur Facebook Marketplace, scroller, et extraire les données brutes des annonces. 
    - **Note d'architecture (Thread-Safety)** : L'instance `FacebookScraper` n'est plus globale au bot. Pour éviter les erreurs `greenlet.error` (Cannot switch to a different thread) de l'API synchrone de Playwright lors des commandes en arrière-plan (ex: `REFRESH`, `SCAN_URL`), un `temp_scraper` est instancié localement au sein de chaque thread worker et fermé immédiatement après usage.
    - **Protection Anti-Bot (Stealth Mode)** : Pour éviter le bannissement ou les redirections vers /login, le scraper intègre désormais :
        - **Randomisation** : Liste tournante de User-Agents modernes et viewports (résolutions d'écran) aléatoires à chaque démarrage.
        - **Flags de Furtivité** : Utilisation d'arguments Chromium spécifiques pour masquer le pilotage automatisé (`--disable-blink-features=AutomationControlled`).
        - **Détection Active** : Surveillance des redirections vers les pages de login ou Captcha, entraînant un arrêt propre de la session.

### `backend/resources/` (Nouveau)
- **`city_coordinates.json`:** Base de données locale des coordonnées des villes pour la cartographie.

### `backend/database.py` (`DatabaseService`)
- **Connexion Firebase :** Initialise à la fois **Firestore** et **Firebase Storage** via `firebase_admin.initialize_app(cred, {'storageBucket': ...})`.
- **`self.bucket`:** Objet bucket Storage passé au `FirestoreRepository` pour les opérations d'images.

### `backend/config/` (Nouveau)
- **`serviceAccountKey.json`:** Clé de service Firebase pour l'authentification du backend. (Non versionné)

### 🗄️ Firebase Storage
- **Upload** (`repository.upload_images_to_storage()`) : Télécharge les images depuis leurs URLs CDN Facebook et les stocke dans `deals/{deal_id}/{i}_{uuid}.jpg`. Retourne des URLs publiques pérennes.
- **Cycle de vie** (`repository.purge_rejected_images()`) : Supprime les images Storage des deals dont le verdict est dans les `rejection_verdicts` et dont le timestamp est &gt; `IMAGE_RETENTION_REJECTED_DAYS` (défaut : 30j). Cible correctement `aiAnalysis.verdict` (et non `status`) pour couvrir les rejets modernes.
- **Script de migration** (`backend/scripts/migrate_images.py`) : Script pour migrer les annonces historiques. Teste la validité des URL Facebook, re-scrape via Playwright si expirées, puis uploade dans Firebase Storage. Intègre la **Rotation de Session** (redémarrage du navigateur toutes les 15 annonces) et le **Jitter** (délais aléatoires) pour contrer l'anti-botting de Facebook lors d'opérations massives.

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
- **`onDealsUpdate()`:** Implémente l'écouteur `onSnapshot` de Firestore.
- **`onDealsUpdate()`:** Implémente l'écouteur `onSnapshot` de Firestore.
- **Actions des Boutons (Refresh, Cleanup, etc.) :** Toutes les actions créent désormais un document dans la collection `commands` via `addCommand(type, payload)`.

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

### `src/components/MapView.jsx`
- **Cartographie Google Maps :** Intègre la logique des marqueurs et des InfoWindows.
- **Interactions Enrichies :** Les marqueurs affichent des InfoWindows (tooltips) au survol (PC) ou au clic (Mobile). Ces bulles contiennent une miniature de l'annonce, le titre, le Score DEAL (IA) et la Valeur Estimée.
- **Logique de Navigation :** Sur mobile, le premier clic ouvre la bulle d'info. Le second clic sur la bulle ouvre l'annonce complète en bas d'écran (overlay).

### `src/components/Dashboard.jsx` (Tableau de Bord V2)
- **Interface Principale :** Regroupe la Navbar, le Tiroir de Filtres, et les différentes vues (Liste, Carte, Stats).
- **Overlay Mobile :** Implémentation d'un système d'overlay (`absolute inset-0`) pour l'annonce sélectionnée sur mobile, couvrant la carte au lieu de la compresser pour une lecture optimale.
- **Tableau de Bord de Statistiques (`StatsView.jsx`) :** Composant agrégeant les données de Firestore.
    - Calcule dynamiquement le Tunnel de Conversion (Funnel) et les KPIs financiers (Marge nette latente, Score moyen, Marge par pépite) sur l'inventaire en cours.
    - Utilise `recharts` pour visualiser un **Radar Chart** du profil moyen IA (5 scores) et un **Bar Chart** pour la distribution du Top 5 des Marques.

### `src/components/DealCard.jsx`
- **Composant de Production :** Version aboutie de la carte d'annonce avec design premium.
- **Barre d'Actions unifiée :** Les actions (Favori, Scan, Rejeter, Suppression, Partager, FB) sont factorisées dans une fonction `renderActionButtons` utilisée à la fois dans le footer de la carte et dans le header de la Modale d'Analyse IA.
- **Partage Intelligent :** Intègre l'API `navigator.share` avec fallback automatique vers la copie dans le presse-papier pour une flexibilité maximale (PC/Mobile).
- **Menu de Ré-analyse :** Dropdown dynamique offrant le choix entre "Scan Standard" et "Luthier Expert".

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
| `analysisConfig.mainAnalysisPrompt` | Prompt principal complet (persona + verdicts + format JSON) — **Array de strings**. *Note: Gère désormais les lots (instruments + accessoires) pour éviter les rejets abusifs.* | Portier + Expert |
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
