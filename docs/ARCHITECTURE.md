# Architecture Technique - Guitar Hunter AI

Ce document détaille le fonctionnement interne du projet.

## 1. 🔄 Firestore : Le Cœur du Système (Event Bus)

Le projet utilise une architecture où **Firestore n'est pas seulement une base de données, mais un bus d'événements et de commandes**.

- **`guitar_deals` (Collection):** Contient toutes les annonces. Le frontend écoute cette collection en temps réel.
- **`commands` (Collection):** Le frontend écrit des documents ici pour demander des actions au backend (ex: `ANALYZE_DEAL`). Le backend écoute cette collection, traite la commande, puis la supprime ou la marque comme complétée.
- **`users/{userID}` (Document):** Contient la configuration du bot (fréquence de scan, prompts, etc.). Le backend et le frontend lisent et écrivent ici pour se synchroniser.

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
    1. **Portier (Gatekeeper):** Un modèle Gemini rapide et peu coûteux est appelé en premier. **IMPORTANT :** Il reçoit le même prompt complet que l'Expert (taxonomie, critères) car il doit effectuer une analyse visuelle fine pour détecter les contrefaçons (ex: Chibson) et filtrer le bruit. Son rôle est de trancher rapidement mais intelligemment.
    2. **Expert:** Si le portier valide l'annonce (ou si `force_expert=True`), un modèle plus puissant est appelé pour valider le verdict du Portier et fournir une analyse financière détaillée (estimation de valeur, coût de réparation, marge, etc.).
  - **Gestion des images:** Télécharge, optimise et envoie les images à Gemini Vision.
  - **Formatage:** Construit le prompt utilisateur et s'attend à recevoir une réponse JSON structurée.

### `backend/scraping/`
- **`FacebookScraper`:** Utilise Playwright pour naviguer sur Facebook Marketplace, scroller, et extraire les données brutes des annonces.

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
- **`retryDealAnalysis(dealId)` / `forceExpertAnalysis(dealId)`:** N'appellent pas une API HTTP. À la place, elles **créent un nouveau document** dans la collection `commands` de Firestore. Le backend, qui écoute cette collection, se chargera du reste.

### `src/components/DealCard.jsx`
- **Composant clé:** Affiche une seule annonce.
- **Props:** Reçoit un objet `deal` et des fonctions `on...` (ex: `onRetry`) depuis le composant parent.
- **Logique d'affichage:**
  - Affiche les informations de base (titre, prix).
  - Affiche les résultats de l'analyse IA (`deal.aiAnalysis`).
  - Contient un module financier interactif pour afficher les estimations de valeur, de coût et de marge.
  - Les boutons d'action (Rejeter, Réanalyser) appellent les fonctions passées en props, qui remontent jusqu'à `useDealsManager` puis `firestoreService`.

## 4. 🧠 Système de Prompts Dynamiques

Le système permet de modifier le comportement de l'IA sans redéployer le code, grâce à une synchronisation via Firestore.

### Sources de Données
1.  **`prompts.json` (Statique):** Contient les prompts par défaut, la taxonomie des guitares et les instructions de formatage. C'est la configuration "usine".
2.  **Firestore `users/{userID}` (Dynamique):** Contient les surcharges de configuration définies par l'utilisateur via l'interface.

### Flux de Modification
1.  **Édition:** L'utilisateur modifie les prompts dans le `ConfigPanel` du frontend.
2.  **Sauvegarde:** Les modifications sont envoyées à Firestore (`updateUserConfig`).
3.  **Consommation:**
    - Le backend récupère la configuration Firestore avant chaque analyse.
    - Il fusionne les valeurs dynamiques avec les valeurs par défaut (si nécessaire).
    - Il construit le prompt final en assemblant : `Main Prompt` + `Taxonomie` + `Données Annonce` + `Instructions Spécifiques` (Portier ou Expert).

### Structure du Prompt Assemblé
Le prompt envoyé à Gemini est construit dynamiquement dans `backend/analyzer.py` :
```python
[Main Analysis Prompt (Configurable)]
+
### TAXONOMIE DE RÉFÉRENCE
[JSON Taxonomie (Statique pour l'instant)]
+
Détails de l'annonce :
- Titre : ...
- Prix : ...
...
+
[Instruction Spécifique (Portier ou Expert)]
```

### Avantages & Inconvénients
- **(+) Flexibilité:** Permet d'itérer rapidement sur le "Prompt Engineering".
- **(+) Robustesse:** Fallback automatique sur `prompts.json` si Firestore est vide.
- **(-) Risque:** L'utilisateur peut casser l'IA en supprimant des instructions de formatage JSON critiques.
- **(-) Taxonomie:** La taxonomie est actuellement statique dans le code backend et ne peut pas être modifiée via l'interface.
