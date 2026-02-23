# Architecture Technique - Guitar Hunter AI

Ce document détaille le fonctionnement interne du projet.

## 1. 🔄 Firestore : Le Cœur du Système (Event Bus)

Le projet utilise une architecture où **Firestore n'est pas seulement une base de données, mais un bus d'événements et de commandes**.

- **`guitar_deals` (Collection):** Contient toutes les annonces. Le frontend écoute cette collection en temps réel. Les annonces peuvent avoir plusieurs statuts : `analyzed` (par défaut), `rejected` (masqué totalement), ou `sold` (**Soft Delete** - masqué du flux principal mais conservé en base).
- **`commands` (Collection):** Le frontend écrit des documents ici pour demander des actions au backend (ex: `ANALYZE_DEAL`). Le backend écoute cette collection, traite la commande, puis la supprime ou la marque comme complétée. **(Nouvelle Architecture)**
- **`users/{userID}` (Document):** Contient la configuration du bot. De plus, sert historiquement de bus de commandes pour des actions comme `forceRefresh` ou `scanSpecificUrl` en modifiant des champs avec un timestamp. **(Architecture Legacy - Dette Technique)**

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
- **Responsabilité unique:** Analyser une annonce.
- **`analyze_deal(listing_data, force_expert=False)`:**
  - **Cascade d'analyse:**
    1. **Portier (Gatekeeper):** Un modèle Gemini rapide et peu coûteux est appelé en premier. Son rôle est de filtrer le bruit.
       - *Dette Technique :* La vérification du verdict (ex: `gatekeeper_status in ['BAD_DEAL', 'REJECTED_ITEM', ...]`) est actuellement codée en dur dans `analyzer.py`, rendant le backend fragile si la configuration des verdicts évolue.
    2. **Expert:** Si le portier valide l'annonce (ou si `force_expert=True`), un modèle plus puissant est appelé pour valider le verdict du Portier et fournir une analyse financière.
  - **Gestion des images:** Télécharge, optimise et envoie les images à Gemini Vision.
  - **Formatage:** Construit le prompt utilisateur et s'attend à recevoir une réponse JSON structurée.

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
- **`retryDealAnalysis(dealId)` / `forceExpertAnalysis(dealId)`:** Créent un nouveau document dans la collection `commands` (Nouvelle Architecture).
- **`triggerManualRefresh()` / `triggerManualCleanup()`:** Modifient les champs de timestamps sur le document `users/{id}` pour déclencher des actions backend (Architecture Legacy).

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
       └─ DEFAULT_TAXONOMY         ← prompts.json["taxonomy_guitares"]

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
| `analysisConfig.mainAnalysisPrompt` | Prompt principal complet (persona + verdicts + format JSON) | Portier + Expert |
| `analysisConfig.gatekeeperVerbosityInstruction` | Instruction de concision ajoutée à la fin du prompt du Portier | Portier uniquement |
| `analysisConfig.expertContextInstruction` | Contexte injecté en tête du prompt de l'Expert (contient `{status}` et `{reasoning}`) | Expert uniquement |
| `analysisConfig.rejectionVerdicts` | Liste stricte des verdicts provoquant un arrêt immédiat de l'analyse | Portier uniquement |

Les modifications sont **sauvegardées automatiquement au `onBlur`** de chaque champ, sans bouton de validation explicite.

---

### 4.4 Fallback et Robustesse

Le système dispose d'un mécanisme de fallback à deux niveaux :
1.  **Frontend :** Si Firestore ne contient pas de config, `useBotConfig.js` initialise l'état avec les valeurs lues depuis `prompts.json` directement (import Vite statique).
2.  **Backend :** `analyzer.py` utilise `config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT)`. Si la clé est absente de Firestore, les constantes chargées depuis `prompts.json` au démarrage servent de fallback.

---

### 4.5 Dette Technique Restante (Architecture)

-  **Taxonomie non éditable** : `DEFAULT_TAXONOMY` est chargée depuis `prompts.json` au démarrage de Python et est toujours **injectée en dur** dans `analyzer.py`. Elle n'est pas exposée dans l'interface de configuration et ne peut pas être modifiée via Firestore.

---

### 4.6 Avantages & Risques

- **(+) Flexibilité :** Modification du comportement de l'IA (et ajout d'exemples Few-Shot) sans redéploiement du backend.
- **(+) Robustesse :** Double fallback (Frontend statique + Backend statique) garantit que l'IA ne reste jamais sans prompt.
- **(+) Éditeur Ligne par Ligne :** Le composant `PromptListEditor` permet une édition intuitive.
- **(-) Risque de Casse :** L'utilisateur peut supprimer les instructions de format JSON critiques dans `mainAnalysisPrompt`, rendant les réponses de l'IA non parsables.
- **(-) Taxonomie non éditable :** La taxonomie (liste des types de guitares) est statique et non modifiable via l'interface.
