# Architecture Technique - Guitar Hunter AI

Ce document détaille le fonctionnement interne du projet.

## 1. 🔄 Firestore : Le Cœur du Système (Event Bus)

Le projet utilise une architecture où **Firestore n'est pas seulement une base de données, mais un bus d'événements et de commandes**.

⚠️ **IMPORTANT : Structure Imbriquée (Multi-tenant)**
Toutes les données sont isolées par application et par utilisateur. Le chemin de base pour toutes les collections est :
`artifacts/{APP_ID}/users/{USER_ID}/...`

- **`guitar_deals` (Collection):** (Chemin: `.../guitar_deals`). Contient toutes les annonces. Le frontend écoute cette collection en temps réel. Les annonces peuvent avoir plusieurs statuts : `analyzed` (par défaut), `rejected` (masqué totalement), ou `sold` (**Soft Delete** - masqué du flux principal mais conservé en base).
- **`commands` (Collection):** (Chemin: `.../commands`). Le frontend écrit des documents ici pour demander toutes les actions au backend (ex: `ANALYZE_DEAL`, `REFRESH`, `CLEANUP`, `STOP_BOT`). Le backend écoute cette collection, traite la commande de manière unifiée, puis la marque comme complétée. **(Architecture Actuelle)**
  - **`STOP_BOT` :** Commande spéciale qui lève un `threading.Event` dans `main.py` pour provoquer un arrêt propre de la boucle principale. Le bot met son statut à `stopped` avant de quitter.
- **`users/{userID}` (Document):** (Chemin: `artifacts/{APP_ID}/users/{USER_ID}`). Contient la configuration du bot. Les anciens déclencheurs par champs de timestamp (`forceRefresh`, etc.) ont été migrés vers la collection `commands` (Session 17).

## 2. 🐍 Backend (Python)

Le backend est un "worker" persistant qui tourne en boucle.

### `main.py`
- **Point d'entrée:** Initialise le `GuitarHunterBot`.
- **Boucle principale:**
  1. Vérifie les commandes dans Firestore (`sync_and_apply_config`).
  2. Exécute les tâches planifiées (scan, nettoyage) via `TaskScheduler`.
  3. Gère un `command_handlers` pour router les commandes Firestore vers les bonnes méthodes du bot.

### `backend/bot.py` (`GuitarHunterBot`)
- **Classe centrale:** Orchestre toutes les opérations du backend.
- **`run_scan()`:** Déclenche le scraping des villes configurées.
- **`handle_deal_found()`:** Callback appelé par le scraper pour chaque annonce trouvée. C'est ici que l'appel à l'analyseur est fait.
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
- **`FacebookScraper`:** Utilise Playwright pour naviguer sur Facebook Marketplace, scroller, et extraire les données brutes des annonces.

### `backend/resources/` (Nouveau)
- **`city_coordinates.json`:** Base de données locale des coordonnées des villes pour la cartographie.

### `backend/config/` (Nouveau)
- **`serviceAccountKey.json`:** Clé de service Firebase pour l'authentification du backend. (Non versionné)

## 3. ⚛️ Frontend (React)

Le frontend est une Single Page Application (SPA) conçue pour être très réactive.

### `src/App.jsx`
- **Point d'entrée:** Structure l'application avec les fournisseurs de contexte.
- **`DealsProvider`:** Fournit les données et les actions relatives aux annonces.

### `src/hooks/useDealsManager.js`
- **Hook central:** C'est le cerveau du frontend.
  1. **`onDealsUpdate()`:** S'abonne aux changements de la collection `guitar_deals` dans Firestore.
  2. **`setDeals()`:** Met à jour l'état local, ce qui provoque le re-rendu de l'interface.
  3. **`dealActions`:** Expose des fonctions (`handleRejectDeal`, `handleRetryAnalysis`) qui, lorsqu'elles sont appelées, interagissent avec `firestoreService`.

### `src/services/firestoreService.js`
- **Couche d'abstraction:** Toutes les interactions avec Firestore sont ici.
- **`onDealsUpdate()`:** Implémente l'écouteur `onSnapshot` de Firestore.
- **`onDealsUpdate()`:** Implémente l'écouteur `onSnapshot` de Firestore.
- **Actions des Boutons (Refresh, Cleanup, etc.) :** Toutes les actions créent désormais un document dans la collection `commands` via `addCommand(type, payload)`.

### `src/components/DealCard.jsx`
- **Composant clé:** Affiche une seule annonce.
- **Props:** Reçoit un objet `deal` et des fonctions `on...` (ex: `onRetry`) depuis le composant parent.
- **Logique d'affichage:**
  - Affiche les informations de base (titre, prix).
  - Affiche les résultats de l'analyse IA (`deal.aiAnalysis`).
  - Contient un module financier interactif pour afficher les estimations de valeur, de coût et de marge.
  - Les boutons d'action (Rejeter, Réanalyser) appellent les fonctions passées en props, qui remontent jusqu'à `useDealsManager` puis `firestoreService`.

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
| `analysisConfig.mainAnalysisPrompt` | Prompt principal complet (persona + verdicts + format JSON) — **Array de strings** | Portier + Expert |
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
