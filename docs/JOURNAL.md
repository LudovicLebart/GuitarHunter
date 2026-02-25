# Journal de Bord - Guitar Hunter AI

[2026-02-24] [PRO] Action : Parallélisation des commandes manuelles longues → Résultat : Résolution du délai d'exécution des commandes manuelles (RESCAN ALL, SCAN_URL). Ces commandes longues étaient exécutées de manière synchrone dans la boucle principale (`main.py`). Si un scan planifié de 10 minutes était en cours (`scheduler.run_pending()`), le `REFRESH` s'accumulait et démarrait tardivement à la fin de celui-ci (créant une impression de blocage). Correction : enveloppement des traitements longs dans un `threading.Thread` asynchrone pour une exécution immédiate sans bloquer la boucle d'événements principale de Firestore.

[2026-02-24] [PRO] Action : Création d'un point central de mise à jour `set_status` (avec `threading.Lock()`) activé → Résultat : Résolution du bug "En attente" pendant le scan. Le statut `botStatus` repassait à `idle` prématurément quand des threads parallèles (comme le nettoyage en arrière-plan) se terminaient pendant qu'un scan principal tournait. Création d'un point central de mise à jour `set_status` dans `GuitarHunterBot` avec `threading.Lock()` et un suivi des tâches actives par nom (`_active_tasks`). Le statut `idle` n'est confirmé sur Firestore que si l'ensemble des processus sont terminés, avec préservation de la priorité du statut `scanning` sur `cleaning` pour l'interface UI.

[2026-02-24] [PRO] Action : Ajout d'un sondage Firestore pendant les pauses et réécriture de `delete_all_logs` → Résultat : Réparation de deux bugs. (Bug 1) Réveil du bot en pause : La boucle d'attente dans `main.py` ne sondait pas Firestore, rendant le bot sourd à toute commande (REFRESH, SCAN_URL, etc.) sauf START_BOT. Correction : ajout d'un sondage Firestore toutes les 5s avec `bot.sync_and_apply_config()`. Toute commande actionnable interrompt maintenant la pause et est traitée immédiatement après le réveil. (Bug 2) Suppression des logs : Réécriture de `delete_all_logs` dans `repository.py` pour utiliser `list()` afin de forcer la consommation du stream Firestore avant chaque batch, ajout d'un garde-fou `max_iterations` et de logs de diagnostic améliorés.

[2026-02-24] [FLASH] Action : Identification d'un bug de réveil du bot → Résultat : Ajout au `TODO.md` : le bot en pause (`paused`) ignore la commande `REFRESH` (Rescan All) mais réagit au `SCAN_URL`.

[2026-02-24] [PRO] Session 27 : Robustesse de la détection d'indisponibilité du scraper (`check_listing_availability`). Passage d'une vérification textuelle stricte à une analyse Regex (insensible à la casse, mots entiers `\b`) incluant le français et l'anglais ("vendu", "sold", "expired"). Ajout de l'inspection des attributs ARIA et vérification stricte de la visibilité CSS (`display: none`, `opacity: 0`) vis `window.getComputedStyle` pour éliminer les faux positifs (éléments cachés ou mots partiels comme "revendu").

[2026-02-24] [FLASH] Session 26 (Bug Report) : Identification d'un problème de pérennité des images. Les URLs Facebook CDN expirent (paramètre `oe` dans l'URL). Les annonces valides perdent leur visibilité visuelle après quelques jours. Ajout au `TODO.md`.

[2026-02-24] [PRO] Session 26 : Amélioration du Pilotage du Bot (Commandes Avancées & UI). (Action 1) Ajout de la commande `STOP_SCAN` avec `scan_stop_event` indépendant pour interrompre un scraping sans tuer le bot. (Action 2) Refonte sémantique de `STOP_BOT` : le bot entre dans une boucle de pause de 12h (interruptible) au lieu de s'éteindre totalement. (Action 3) Ajout de `START_BOT` pour réveiller le bot instantanément de sa pause. (Action 4) Extraction et refonte de l'interface des contrôles : création du composant `<BotControls />` hybride avec indicateur de statut dynamique intégré dans le panneau latéral "Système".

[2026-02-24] [FLASH] Session 25 : Correction "Mode Hors Ligne" du Bot. Automatisation du déploiement des fichiers ignorés par Git via GitHub Secrets (`DOT_ENV` et `FIREBASE_SERVICE_ACCOUNT_KEY`). Mise à jour de `deploy.yml` pour recréer dynamiquement `.env` à la racine et `serviceAccountKey.json` dans `backend/config/` sur le serveur.

[2026-02-24] [FLASH] Session 24 : Correction du flux de déploiement GitHub Actions (`deploy.yml`). (Action 1) Correction de la casse de la branche `dev` (était `Dev`). (Action 2) Remplacement de la réinitialisation forcée sur `master` par une logique dynamique utilisant `${{ github.ref_name }}`. (Action 3) Ajout de logs détaillés et d'une gestion d'erreur robuste pour le redémarrage du service `guitare-hunter`. (Action 4) Audit complet de la documentation (`docs/`).

[2026-02-24] [FLASH] Session 23 : Correction du rejet systématique des étuis/housses par le Portier et le Coupe-Circuit. (Action 1) Mise à jour de `prompts.json` : retrait de la condition d'exclusion sur les "accessoires bas de gamme (gigbag fin seul)" dans `main_analysis_prompt` — Les amplis, étuis et housses (même simples) sont maintenant tous acceptés. Mise à jour de `gatekeeper_verbosity_instruction` : retrait du rejet des "accessoires nuls", ajout explicite des guitares, amplis, étuis et housses comme objets acceptés. (Action 2) Standardisation des 3 instructions de verbosité (`gatekeeper`, `analyst`, `expert_pro`) de `string` → `array of strings` pour la compatibilité avec l'éditeur ligne-par-ligne du ConfigPanel. Mise à jour de `backend/analyzer.py` : ajout de `join("\n")` si l'instruction reçue est une liste.

[2026-02-24] [PRO] Session 22 : Résolution du conflit de casse Git (`Dev` vs `dev`) empêchant le déploiement sur `gh-pages`. Suppression de la branche `Dev` distante, nettoyage des références locales, et succès de `npm run deploy`. Exécution du workflow `/git-push-dev-master` pour synchroniser et achever la session.

[2026-02-24] [FLASH] Session 21 (suite) : Correctif TypeError prix int → cast `str()` dans `analyzer.py` avant `extract_price_from_text`. Création de `backend/scripts/migrate_firestore_prompts.py` (audit racine + injection clés Tier2/3 + nettoyage obsolètes, mode `--dry-run`). Ajout commande `STOP_BOT` : handler `threading.Event` dans `main.py`, `triggerStopBot()` dans `firestoreService.js`, bouton Power dans `LogViewer.jsx`.

[2026-02-24] [FLASH] Session 21 : Implémentation du Funnel 3-Tiers + Refacto DRY → `analyzer.py` restructuré avec `_call_gemini_json` (mutualisation des appels API), prompt de base construit une seule fois. Cascade T1 (Flash-Lite) → T2 (Flash, format compact + 5 scores) → Carrefour Logique → T3 (Pro, conditionnel). Seuils ajoutés dans `config.py`. Nouvelles instructions `analyst_verbosity_instruction` et `expert_pro_context_instruction` ajoutées dans `prompts.json` et init Firestore (`bot.py`). 4 rondes de vérification, 4 bugs corrigés. Push `dev`.

[2026-02-23] [FLASH] Réflexion Statistiques → Conceptualisation des KPIs basés sur les scores du Tier 2/3 et archivage dans `docs/STATS_REFLEXION.md`.

[2026-02-23] [FLASH] Action : Conception de l'entonnoir d'analyse à 3 niveaux et création de `docs/FUNNEL_PLAN.md` → Résultat : Stratégie validée pour réduire les coûts (Tier 2 compact) tout en augmentant la profondeur (Tier 3 Expert Pro conditionnel). Introduction de 5 scores numériques et d'une logique de déclenchement "Jackpot" (Marge + Défi).
[2026-02-23] [FLASH] Action : Création de `backend/scripts/fetch_deal.py` → Résultat : Outil fonctionnel pour inspecter les annonces réelles dans la structure Firestore imbriquée (`artifacts/{app}/users/{user}/...`).
[2026-02-23] [FLASH] Action : Mise à jour de `docs/ARCHITECTURE.md` → Résultat : Documentation de la structure multi-tenant de la base de données.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` → Résultat : Assainissement du titre de la notification (suppression des sauts de ligne `\n`) pour éviter des erreurs HTTP `Invalid header value` lors de l'envoi à `ntfy.sh`.
[2026-02-22] [PRO] Action : Modification de `src/App.jsx` → Résultat : Le lecteur récupère désormais l'ID d'annonce via le lien `deals` complet (et plus `filteredDeals`), évitant que la carte ne s'ouvre pas si l'annonce est archivée/filtrée.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` → Résultat : Le lien cliquable des notifications `ntfy` renvoie désormais vers la carte du deal sur le frontend (`?dealId=...`) au lieu de l'annonce Facebook FB.
[2026-02-23] [FLASH] Action : Audit final et synchronisation des branches → Résultat : Documentation (Journal, Todo, Architecture, Data Flow) auditée et synchronisée. Fusion de la branche `dev` vers `master` et push remote.

Ce journal suit les changements majeurs, les décisions d'architecture et les nouvelles fonctionnalités.

---

---

### **Date: 23/02/2026** (Session 19)

**Auteur:** Assistant AI

**Type:** Optimisation IA (Entonnoir v2)

#### 📝 Description des Changements
- **Raffinage des déclencheurs Tier 3 (Expert Pro) :**
    - Couplage intelligent du prix et du score : le passage à l'Expert Pro pour les objets > 1000$ ne se fait que si le `deal_score` est >= 4 (évite d'analyser en profondeur des objets chers mais inintéressants).
    - Durcissement des contrôles d'authenticité : déclenchement systématique de l'Expert si `authenticity_score` <= 7.
    - Ajout d'un déclencheur spécifique pour les verdicts `COLLECTION`.
- **Mise à jour de `docs/FUNNEL_PLAN.md` :** Documentation complète de la logique de cascade.

#### 🤔 Raisonnement
L'objectif est d'économiser les appels au modèle Pro (plus coûteux) en s'assurant qu'il n'intervient que sur des annonces ayant un réel potentiel ou présentant un risque technique/historique nécessitant une haute précision.

---

### **Date: 23/02/2026** (Session 18)

**Auteur:** Assistant AI

**Type:** Optimisation IA (Scores & Pédagogie)

#### 📝 Description des Changements
- **Enrichissement du Tier 2 (Analyste) :**
    - Introduction d'un système de notation sur 10 pour 5 indices : `deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, et `restoration_interest_score`.
    - Ajout du `restoration_interest_score` : Ce score évalue la valeur "pédagogique" ou le défi technique d'un projet de lutherie, permettant d'identifier des "Pépites de restauration" même si la marge financière pure est moindre.
- **Logique "Jackpot" :** Création d'un déclencheur Expert Pro si `deal_score` >= 6 ET `restoration_interest_score` >= 7.

#### 🤔 Raisonnement
Le projet "Guitar Hunter" n'est pas qu'une question de profit immédiat, c'est aussi un projet luthier-centric. Valoriser l'intérêt technique des réparations permet de ne pas rater des instruments rares ou complexes qui enrichissent l'expertise du Maître Luthier.

---

### **Date: 23/02/2026** (Session 17)

**Auteur:** Assistant AI

**Type:** Refonte Système (Commandes & Base de données)

#### 📝 Description des Changements
- **Migration des "Legacy Commands" vers la collection `commands` :**
    - Modification du Frontend (`src/services/firestoreService.js`) pour que les actions manuelles (Refresh, Cleanup, Reanalyze All, Scan URL) créent des documents dans la collection `commands` au lieu de modifier des champs d'horodatage sur la racine du document utilisateur.
    - Simplification du Backend (`backend/services.py` & `backend/bot.py`) : Le `ConfigManager` a été épuré de toute la logique complexe de vérification d'horodatage. La boucle principale (`main.py`) gère désormais de manière unifiée toutes les commandes entrantes (avec statut `pending`, `completed`, `failed`).
    - Nettoyage du Backend (`backend/repository.py`) : L'ancienne méthode `consume_command` qui supprimait les champs du document utilisateur a été supprimée suite à la nouvelle architecture.

#### 🤔 Raisonnement
Cette unification de l'architecture autour de la collection `commands` facilite grandement la traçabilité. Auparavant, le bot devait surveiller 4 champs (`forceRefresh`, `forceCleanup`, `forceReanalyzeAll`, `scanSpecificUrl`) greffés sur le document utilisateur. Maintenant, chaque commande, quelle que soit sa nature, suit un flux de vie identique (création → attente → traitement → terminé/erreur), ce qui rend le système beaucoup plus robuste et prévisible.

---

### **Date: 23/02/2026** (Session 16)

**Auteur:** Assistant AI

**Type:** Refonte Système (Scraping & Frontend)

#### 📝 Description des Changements
- **Robustesse du Scraper Playwright :**
    - Modification de `check_listing_availability` dans `backend/scraping/core.py` pour utiliser l'évaluation JavaScript native du DOM (`page.evaluate`). La détection des marqueurs "Vendu", "Sold" ou "plus disponible" ne repose plus sur des cibles CSS volatiles, mais scanne les textes rendus et visibles du `div[role="main"]`.
    - Timeout de navigation augmenté à 30 secondes pour compenser la lenteur applicative de Facebook sans déclencher de "faux positifs" de suppressions.
- **Sauvegarde de l'Historique (Soft Delete) :**
    - La fonction de nettoyage `cleanup_sold_listings` bascule exclusivement sur le taggage Firestore avec `status: 'sold'`, abandonnant le comportement `Hard Delete` non-désiré.
- **Transparence de l'UI Frontend (`DealCard.jsx` & Filtrage) :**
    - L'état `sold` réduit désormais l'opacité visuelle de l'annonce et applique un badge contextuel bloquant.
    - Correction du "Fantôme d'Analyse" : Les annonces liquidées avant qu'une IA ne rende un verdict (`DEFAULT`) ne tentent plus d'afficher "Analyse en cours..." mais explicitement "Non Analysé (Vendu)".
    - Correction du badge Compteur (`SOLD`) dans la barre de filtre pour comptabiliser les annonces vendues sans qu'elles ne soient exclues prématurément par l'absence d'une classe d'instruments.

#### 🤔 Raisonnement
Le cycle complet de vie d'une annonce doit garantir zéro perte de données. Les annonces vendues constituent une mine d'or pour évaluer le "Velocity Pricing" d'un luthier ou d'un revendeur. En préservant ces documents Firestore de façon élégante, l'application mûrit vers une plateforme d'analyse de marché long terme, et non plus un simple scanner éphémère.

---

### **Date: 22/02/2026** (Session 15 - Soir)

**Auteur:** Assistant AI

**Type:** Amélioration de l'Architecture & Résolution de Dette Technique

#### 📝 Description des Changements
- **Externalisation des verdicts de rejet (Coupe-circuit) :**
    - La liste des verdicts provoquant l'arrêt immédiat de l'analyse (`BAD_DEAL`, `REJECTED_ITEM`...) a été retirée du code Python (`backend/analyzer.py`).
    - Elle est désormais stockée dans `prompts.json` par défaut et gérée dynamiquement via Firestore (`analysisConfig.rejectionVerdicts`).
    - Ajout d'une interface d'édition (liste de textes) dans `ConfigPanel.jsx` (section "Intelligence Artificielle").

#### 🤔 Raisonnement
Cette modification résout une dette technique identifiée. Auparavant, si la taxonomie des verdicts venait à évoluer, le backend devait être recompilé. Maintenant, l'utilisateur a un contrôle total sur les conditions de "coupe-circuit" directement depuis l'interface web, rendant le système de filtrage (Portier) 100% piloté par les données.

---

### **Date: 22/02/2026** (Session 15 - Après-midi)

**Auteur:** Assistant AI

**Type:** Nettoyage & Organisation du Projet

#### 📝 Description des Changements
- **Dépollution de la racine :** Suppression des scripts de diagnostic et de setup obsolètes (`diagnose_firestore.py`, `populate_cities.py`, `test_notification.py`, `verify_setup.py`) et de l'ancien journal (`implementation_journal.md`).
- **Restructuration des fichiers de configuration :**
    - Création de `backend/resources/` et déplacement de `city_coordinates.json`.
    - Création de `firebase/` et déplacement de `firestore.rules`.
    - Création de `backend/config/` et déplacement de `serviceAccountKey.json`.
- **Mise à jour des références :** Correction des chemins d'accès dans `config.py` (backend), `src/components/MapView.jsx` (frontend) et `tests/check_baseline.py`.

#### 🤔 Raisonnement
Une racine propre facilite la navigation dans le projet et sépare clairement les fichiers de configuration, les ressources de données et le code source. La mise à jour des imports garantit que les deux environnements (Python et React) continuent de fonctionner sans interruption.

---

### **Date: 22/02/2026** (Session 15 - Matin)

**Auteur:** Assistant AI

**Type:** Analyse Technique & Audit de Données

#### 📝 Description des Changements
- **Audit de la base de données (Le mystère des annonces invisibles) :**
    - **Problème :** L'utilisateur a remarqué un écart de ~300 annonces entre le total Firestore (486) et les annonces visibles (84 + 91).
    - **Investigation :** Création de scripts d'audit (`inspect_db_stats.py`, `inspect_rejection_reasons.py`) pour analyser les documents `status: 'rejected'`.
    - **Découverte :** 287 annonces portent le verdict `REJECTED` (ancienne nomenclature v1). 20 proviennent du pré-filtre Javascript, le reste (267) provient des modèles Gemini (anciennes analyses).
    - **Cause de l'invisibilité :** Le frontend (`matchesVerdictFilter`) masque totalement les documents ayant un statut global `rejected`. Dans la nomenclature v2, le "bruit" est classé `REJECTED_ITEM` avec un statut global `analyzed`, ce qui les rend comptabilisables dans l'UI alors que la v1 les annihilait visuellement.
- **Analyse du système de nettoyage (Sold Listings) :**
    - Documentation du fonctionnement de `cleanup_sold_listings`. Identification de la fragilité de la détection (basée sur du texte strict) et du risque de perte d'historique dû au "Hard Delete".

#### 🤔 Raisonnement
Il est crucial de conserver l'historique des ventes pour de futures statistiques (Price History / Velocity). Le passage au "Soft Delete" est validé comme prochaine étape majeure.

---

### **Date: 20/02/2026** (Session 14 - Suite 2)

**Auteur:** Assistant AI

**Type:** Correction de Bug (Frontend / Firestore)

#### 📝 Description des Changements
- **Fix Bug #3 — Le bouton "Reset" corrompait Firestore :**
    - **Problème :** Bien que la sauvegarde champ par champ ait été corrigée hier (utilisation de la notation par point `updateDoc` avec `analysisConfig.mainAnalysisPrompt`), la fonction `handleResetDefaults` envoyait encore l'objet imbriqué entier `{ analysisConfig: { ... } }`. Cela entraînait un fallback de `firestoreService` sur l'ancienne méthode `setDoc` qui écrasait silencieusement la racine du document.
    - **Solution :** Refonte de `handleResetDefaults` dans `useBotConfig.js` pour construire un objet plat utilisant la notation par point avant de l'envoyer à `updateUserConfig`. La réinitialisation utilise désormais la même méthode d'écriture chirurgicale que les sauvegardes manuelles.

#### 🤔 Raisonnement
Cette asymétrie entre la sauvegarde ligne-par-ligne et la réinitialisation globale était un reste de l'ancienne architecture. Maintenant, toutes les opérations de mise à jour utilisent systématiquement la notation par point de Firestore pour garantir l'intégrité des autres données du document.

---

### **Date: 20/02/2026** (Session 14 - Suite)

**Auteur:** Assistant AI

**Type:** Nettoyage de Dette Technique

#### 📝 Description des Changements
- **Suppression du code mort :** Le fichier `backend/prompt_manager.py`, qui contenait l'ancienne architecture de prompts à 5 blocs inutilisée, a été retiré du projet (via `git rm`).
- **Nettoyage des configurations obsolètes :** Les anciennes clés (`persona`, `verdict_rules`, `system_structure`, etc.) ont été supprimées de `prompts.json` et de `config.py` pour alléger le code et éviter toute confusion future.

#### 🤔 Raisonnement
Le projet évolue avec succès vers un système d'analyse IA en cascade et paramétrable. Supprimer le code inactif (le vieux `PromptManager` monolithique) et nettoyer les résidus dans les configurations garantit que l'architecture reste claire et facile à comprendre pour les futures itérations.

---

### **Date: 20/02/2026** (Session 14)

**Auteur:** Assistant AI

**Type:** Audit Complet du Projet (Full Stack)

#### 📝 Description des Changements

1.  **Analyse globale des flux de données et de l'architecture :**
    - Réalisation d'un audit de bas en haut (Scrapers -> Core Logic -> IA -> Base de données -> Frontend).
    - Mise à jour de `docs/TODO.md` avec de nouvelles priorités de pointe (dette technique cachée).
    - Mise à jour de `docs/ARCHITECTURE.md` pour refléter la situation réelle des flux de commandes.

2.  **Identifications Clés (Dette Technique ajoutée au TODO) :**
    - **Architecture de Commandes Hybride :** Le backend écoute à la fois des champs horodatés sur `users/{id}` (legacy) et des documents dans la collection `commands` (nouveau). Cela crée une complexité inutile.
    - **Logique de Rejet Hardcodée :** Le composant `DealAnalyzer` filtre les annonces en lisant en dur une liste de "verdicts de rejet" (`BAD_DEAL`, `REJECTED_ITEM`, etc.). Si la taxonomie en frontend/prompts évolue, le backend devient aveugle sans mise à jour du code source.
    - **Fragilité du Scraper :** La détection d'une annonce vendue sur Playwright se fie à une expression exacte ("Cette annonce n’est plus disponible"), ce qui est très cassable.

#### 🤔 Raisonnement

- Il est vital de de temps à autre "dézoomer" de la résolution de bugs isolés pour analyser les tendances de l'architecture. Ces découvertes empêchent qu'un simple changement de configuration (ex: renommage d'un statut dans l'UI) ne fasse tomber tout le backend silencieusement.

---
### **Date: 20/02/2026** (Session 13)

**Auteur:** Assistant AI

**Type:** Amélioration de la Configuration / Préparation au Déploiement

#### 📝 Description des Changements

1.  **Uniformisation de la gestion des IDs dans le Frontend :**
    - **Problème :** Les constantes `PYTHON_USER_ID` et `APP_ID` étaient codées en dur dans `src/services/firestoreService.js`, créant une redondance avec les variables d'environnement déjà présentes dans `.env` et configurées dans `vite.config.js`.
    - **Solution :** Remplacement des valeurs en dur par `process.env.USER_ID_TARGET` et `process.env.APP_ID_TARGET`.
    - **Bénéfice :** La configuration est désormais centralisée dans le fichier `.env`, facilitant le déploiement et la maintenance.

#### 🤔 Raisonnement

- Le passage aux variables d'environnement est une bonne pratique indispensable avant un déploiement, assurant que le code reste agnostique de l'environnement et que les identifiants clés peuvent être gérés de manière sécurisée et centralisée.

---

### **Date: 20/02/2026** (Session 12)

**Auteur:** Assistant AI

**Type:** Correction de Bugs (Priorité Haute)

#### 📝 Description des Changements

1.  **Fix Bug #1 — Classifications "Autre" (Frontend + Backend) :**
    - **Problème :** L'IA inventait des libellés libres (ex: "Fender Stratocaster") qui ne correspondaient pas exactement aux clés de la taxonomie (ex: "Stratocaster"). La fonction `normalize` ne permettait pas de trouver ces classifications.
    - **Solution :**
        - Rendu l'instruction de classification plus stricte dans `prompts.json` (demande la valeur exacte d'une feuille de la taxonomie).
        - Ajout d'une fonction `findPathFuzzy` dans `useDealsManager.js` pour tolérer les variations (recherche par sous-chaîne normalisée).

2.  **Fix Bug #2 — Compteurs de filtres incorrects (Frontend) :**
    - **Problème :** La boucle de comptage dans `useDealsManager.js` n'incrémentait que les 3 premiers niveaux (`path[0]`, `path[1]`, `path[2]`). Sur une taxonomie à 4 niveaux, la feuille finale n'était jamais comptée, affichant des badges erronés.
    - **Solution :** Remplacement des affectations dures par une boucle `path.forEach(segment => ...)` pour incrémenter dynamiquement tous les niveaux du chemin de la taxonomie.

#### 🤔 Raisonnement

- Ces deux bugs impactaient fortement l'expérience utilisateur (mauvais comptage, difficulté à filtrer les guitares). En durcissant le backend (prompt) tout en assouplissant le frontend (fuzzy match), on maximise les chances que la classification fonctionne même sur les anciennes annonces.

---

### **Date: 20/02/2026** (Session 11)

**Auteur:** Assistant AI

**Type:** Correction de Bug Critique (Frontend / Firestore)

#### 📝 Description des Changements

1.  **Correction du bug de corruption silencieuse de `analysisConfig` dans Firestore :**
    - **Problème :** La fonction `updateUserConfig` dans `firestoreService.js` utilisait systématiquement `setDoc` avec `merge: true`. Ce comportement merge uniquement au niveau racine du document Firestore. Passer un objet `{ analysisConfig: { mainAnalysisPrompt: [...] } }` **remplaçait intégralement** le sous-objet `analysisConfig`, effaçant silencieusement `gatekeeperModel`, `expertModel`, `gatekeeperVerbosityInstruction` et `expertContextInstruction`.
    - **Impact :** Chaque `onBlur` sur un `PromptListEditor` corrompait Firestore. La corruption causait également une race condition qui annulait le Reset.
    - **Solution :** `updateUserConfig` détecte maintenant si les clés passées contiennent une notation par points (ex: `'analysisConfig.mainAnalysisPrompt'`) :
        - **Dot-notation** → `updateDoc` : écriture chirurgicale sur le champ exact, sans toucher les champs frères.
        - **Objet complet** (ex: Reset) → `setDoc` + `merge: true` : comportement inchangé pour les resets complets.
    - **Fichiers modifiés :** `src/services/firestoreService.js`

#### 🤔 Raisonnement

- `updateDoc` de Firestore accepte nativement la notation par points pour cibler des sous-champs précis. C'est l'outil prévu pour ce cas d'usage. Le code utilisait déjà `unflatten` pour "deviner" l'intention, mais ce n'est pas suffisant car `setDoc + merge` ne merge pas en profondeur.

---

### **Date: 20/02/2026** (Session 10)

**Auteur:** Assistant AI

**Type:** Audit de Documentation & Analyse Approfondie

#### 📝 Description des Changements

1.  **Audit complet du système de prompts :**
    - Analyse exhaustive de tous les fichiers impliqués dans le pipeline de prompts, du backend (`config.py`, `analyzer.py`, `services.py`) au frontend (`useBotConfig.js`, `firestoreService.js`, `ConfigPanel.jsx`).
    - Identification et documentation du code mort : la classe `PromptManager` dans `backend/prompt_manager.py` est un orphelin non instancié, vestige d'une ancienne architecture "5 blocs". Les clés `persona`, `verdict_rules`, `reasoning_instruction`, `user_prompt`, `system_structure` dans `prompts.json` et leurs constantes associées dans `config.py` sont obsolètes.
    - Validation du format de `prompts.json` : syntaxiquement valide.

2.  **Mise à jour de `docs/ARCHITECTURE.md` (Section 4 — Système de Prompts) :**
    - Remplacement de la description générale par une analyse technique détaillée avec inventaire des fichiers, diagrammes de flux de données réels (Backend + Frontend), tableau des prompts modifiables par l'utilisateur, documentation du mécanisme de fallback, et inventaire de la dette technique.

#### 🤔 Raisonnement

- La documentation précédente donnait une vue d'ensemble correcte mais imprécise. L'ajout du tableau de fichiers avec leur statut (actif/orphelin) et des diagrammes de flux en texte brut offre une référence fiable pour les futurs développements, notamment pour le nettoyage du code mort.

---

### **Date: 23/02/2026** (Session 9)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Ajustement de la largeur de l'image sur mobile:**
    - **Problème:** La largeur de l'image sur mobile (`w-32`) était trop étroite.
    - **Solution:** La largeur du conteneur de l'image est passée à `w-1/2` (50% de la largeur de la carte), offrant un meilleur équilibre visuel avec le bloc de prix qui occupe les 50% restants.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Cet ajustement répond à la demande de donner plus d'importance à l'image sur mobile, tout en conservant une disposition en deux colonnes compacte.

---

### **Date: 23/02/2026** (Session 8)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Refonte de la structure de la `DealCard` (Mobile First):**
    - **Problème:** La disposition précédente ne satisfaisait pas les besoins spécifiques de l'affichage mobile (image complète, compacité) et desktop (hiérarchie claire).
    - **Solution:** Une approche "Mobile First" avec deux structures distinctes a été implémentée :
        - **Mobile (`md:hidden`):** Un en-tête compact affiche l'image (largeur fixe `w-32`) et le bloc de prix côte à côte. Le titre et les détails suivent en dessous.
        - **Desktop (`hidden md:block`):** La disposition classique en deux colonnes est conservée, avec l'image "sticky" à gauche. Dans la colonne de droite, le bloc de prix est positionné au-dessus du titre pour une meilleure hiérarchie.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

2.  **Création du composant `PriceDisplay`:**
    - **Action:** La logique d'affichage du prix et du menu déroulant financier a été extraite dans un sous-composant `PriceDisplay`. Cela permet de l'utiliser à deux endroits différents dans le code (header mobile et colonne desktop) sans dupliquer la logique complexe.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

3.  **Retour à l'affichage complet des images:**
    - **Action:** Annulation du changement `object-cover` dans `ImageGallery.jsx`. Les images sont de nouveau affichées en entier (`object-contain`) pour ne perdre aucun détail de l'instrument.

#### 🤔 Raisonnement

- Cette solution hybride offre le meilleur des deux mondes : une expérience mobile optimisée pour la densité d'information et une expérience desktop riche et structurée. L'extraction du composant `PriceDisplay` maintient le code propre et maintenable malgré la duplication structurelle.

---

### **Date: 23/02/2026** (Session 6)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Uniformisation de l'affichage du bloc prix:**
    - **Problème:** Le bloc de prix pouvait encore dépasser de la carte sur certains écrans d'ordinateur lorsque le titre était long et que l'affichage était en mode "ligne" (côte à côte).
    - **Solution:** L'affichage a été uniformisé pour être identique sur mobile et desktop. Le bloc de prix est désormais **toujours** positionné en dessous du titre et aligné à gauche. Cela garantit qu'il dispose toujours de toute la largeur nécessaire et élimine tout risque de dépassement.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- La cohérence de l'interface est primordiale. En adoptant une disposition verticale unique, on simplifie la maintenance et on s'assure que le contenu critique (le prix et les détails financiers) est toujours lisible, quelle que soit la contrainte d'espace horizontal.

---

### **Date: 23/02/2026** (Session 5)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Ajustement de la taille du bouton de prix:**
    - **Problème:** Le bouton de prix, bien que fonctionnel, pouvait être rendu plus compact pour un meilleur équilibre visuel.
    - **Solution:** Plusieurs micro-ajustements ont été effectués : réduction du `padding`, de la taille de la police, de la taille de l'icône, de l'espacement interne et du rayon de la bordure.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Ce changement est un raffinement stylistique visant à perfectionner l'équilibre et l'harmonie des composants de l'interface.

---

### **Date: 23/02/2026** (Session 4)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Fusion du Bouton de Prix et du Toggle d'Expansion:**
    - **Problème:** Le bouton affichant le prix et le bouton pour déplier les détails financiers étaient deux éléments séparés, ce qui était moins intuitif et prenait plus de place.
    - **Solution:** Les deux éléments ont été fusionnés en un seul composant interactif. Le bouton de prix contient maintenant le montant et l'icône "chevron". L'ensemble du bloc est cliquable pour afficher/masquer les détails financiers.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Cette modification améliore l'expérience utilisateur en créant un point d'interaction unique et clair, ce qui est un standard de design d'interface.
- Elle permet également un gain d'espace marginal mais appréciable sur les petits écrans.

---

### **Date: 24/02/2026** (Session 4)

**Auteur:** Assistant AI

**Type:** Correction de bugs (Priorité Haute)

#### 📝 Description des Changements

1.  **Correction de la commande `STOP_BOT` (Backend):**
    - **Problème:** La commande `STOP_BOT` via l'interface UI (ou Firestore) passait le statut du bot à `stopped` mais le programme Python continuait son scan ou nettoyage en cours (boucles synchrones Playwright/Firebase longues).
    - **Solution:** J'ai passé l'instance `threading.Event()` (`stop_event`) depuis `main.py` jusque dans `GuitarHunterBot` (`bot.py`) et `FacebookScraper` (`core.py`). Des vérifications `if self.stop_event.is_set(): return/break` ont été ajoutées dans les points stratégiques des boucles de défilement (`page.mouse.wheel`), d'analyse d'annonces, de nettoyage des vendues (`cleanup_sold_listings`) et des réanalyses en attente.
    - **Fichiers modifiés:** `main.py`, `backend/bot.py`, `backend/scraping/core.py`.

2.  **Correction de la suppression des logs côté client (Frontend):**
    - **Problème:** Le bouton "Vider la base de données" du `LogViewer.jsx` ne produisait aucun effet. Les logs écoutés correspondaient à un "userIdTarget" et un "appId" codés en dur (`00737242777130596039`, `c_5d118e71...`). 
    - **Solution:** Standardisation via des variables d'environnement. Ajout de `VITE_APP_ID_TARGET` et `VITE_USER_ID_TARGET` dans `.env` côté React, de façon à ce que le `LogViewer` se base dynamiquement sur la même configuration ciblée que le Backend Python et Firebase.
    - **Fichiers modifiés:** `src/components/LogViewer.jsx`, `.env`.

#### 🤔 Raisonnement

- **Stop Bot réactif :** Pour que "l'arrêt d'urgence" fonctionne, il fallait sortir le code d'une simple vérification entre deux cycles du scheduler (ancienne méthode) et propager un kill-switch asynchrone jusque dans les boucles de scraping internes. L'objet `threading.Event()` est parfait pour ça, agissant comme un drapeau partagé et thread-safe.
- **Dette Technique (Logs) :** Le code frontend pour les logs était resté sur un ancien jet de POC où je développais avec mes propres IDs personnels (Session 1 à 5). La standardisation avec `.env` aligne le `LogViewer` sur le reste de l'application.

---

### **Date: 23/02/2026** (Session 3)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Refonte du Menu de Réanalyse:**
    - **Problème:** Le menu de réanalyse (Standard/Expert) était "détaché" de la carte lors du défilement (scroll) car il utilisait un `Portal`. De plus, il était trop volumineux avec du texte inutile.
    - **Solution:**
        - **Ancrage:** Le menu est maintenant rendu directement dans le DOM de la carte, positionné en absolu par rapport au bouton de réanalyse. Il suit donc parfaitement le défilelement de la page.
        - **Design Compact:** Le texte a été supprimé au profit d'icônes (`RefreshCw` et `BrainCircuit`) avec des info-bulles (`title`). Le menu est beaucoup plus discret et s'intègre mieux à l'interface.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- L'utilisation de `Portal` pour des menus contextuels liés à des éléments scrollables est souvent problématique sans une gestion complexe de la position. L'ancrage direct via CSS (`position: absolute`) est une solution plus robuste et plus simple ici.
- La réduction de la taille du menu améliore l'expérience utilisateur, en particulier sur mobile où l'espace est limité.

---

### **Date: 23/02/2026** (Session 2)

**Auteur:** Assistant AI

**Type:** Amélioration du Design Responsive (UI/UX)

#### 📝 Description des Changements

1.  **Amélioration de l'affichage de la `DealCard` sur mobile:**
    - **Problème:** Sur les écrans de petite taille, le bloc contenant les informations financières (`Prix`, `Valeur Estimée`, etc.) ne passait pas à la ligne et débordait de la carte, rendant l'interface inutilisable.
    - **Solution:** La structure de l'en-tête de la carte a été rendue "responsive" :
        - Sur les écrans `md` et plus, le titre et le bloc financier sont côte à côte.
        - Sur les petits écrans (mobile), le bloc financier passe automatiquement sous le titre, utilisant toute la largeur disponible et évitant tout dépassement.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

2.  **Simplification de l'affichage du prix:**
    - **Problème:** Pour gagner de la place sur mobile, l'affichage du prix pouvait être plus compact.
    - **Solution:**
        - La mention "Prix Demandé" a été supprimée.
        - La taille de la police du prix a été réduite (`text-xl` au lieu de `text-2xl`).
        - Le padding du conteneur du prix a été ajusté.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Ces changements sont cruciaux pour l'utilisabilité de l'application sur des appareils mobiles. Ils suivent les principes du "responsive design" en adaptant la disposition du contenu à la taille de l'écran.
- La simplification du prix contribue à une interface plus épurée et directe.

---

### **Date: 23/02/2026** (Session 1)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX) & Correction de bug

#### 📝 Description des Changements

1.  **Refonte du Module Financier sur la `DealCard`:**
    - **Problème:** Les indicateurs financiers clés (`estimated_value`, `net_guitar_cost`, etc.) étaient cachés sous des conditions trop restrictives (ex: uniquement si la marge était positive ou si l'annonce n'était pas rejetée).
    - **Solution:** Un nouveau module financier a été implémenté :
        - **Toujours visible:** Le prix demandé, la valeur estimée et le potentiel de revente sont maintenant toujours visibles si les données existent, même pour les annonces rejetées.
        - **Détails sur demande:** Un menu déroulant (toggle) a été ajouté pour afficher les détails techniques comme le **Coût Net** et la **Marge Brute**.
        - **Code couleur:** La marge brute est maintenant colorée (vert si positive, rouge si négative) pour une identification rapide de la rentabilité.
    - **Fichier modifié:** `src/components/DealCard.jsx`

2.  **Correction du Bug de Réanalyse "Expert":**
    - **Problème:** Lors d'un clic sur le bouton de réanalyse "Expert", l'indicateur de chargement (spinner) ne s'activait pas car le statut `analyzing_expert` n'était pas correctement géré par le frontend.
    - **Solution:** Le statut `analyzing_expert` a été ajouté aux listes de vérification `isAnalyzing` et `getModelName` dans la `DealCard`.
    - **Fichier modifié:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- La refonte du module financier a pour but de fournir à l'utilisateur un contexte complet sur **pourquoi** une annonce est jugée bonne ou mauvaise, même après qu'elle ait été rejetée.
- La correction du bug de réanalyse améliore le retour visuel pour l'utilisateur, confirmant que son action a bien été prise en compte.

---

### Session 20 : Expansion du Scope - Étape 1 (Amps & Étuis)

#### ✅ Objectif : Passer d'un système "Tout-Guitare" à un système Multi-Catégorie Luthier-Centric.

- **Refonte de la Taxonomie** : Migration de `taxonomy_guitares` vers `taxonomy_master`.
- **Nouveaux Produits** : Intégration des `amplificateurs` (Lampes, Transistors, Modélisation) et des `accessoires_etuis` (Rigides, Housses souples).
- **Persona Luthier** : Mise à jour des prompts pour évaluer les amplis (état des lampes, transformateurs) et valoriser l'apport financier des housses/étuis pour le flipping.
- **Synchronisation Full-Stack** : Mise à jour de `config.py` et `useDealsManager.js` pour supporter dynamiquement la nouvelle structure.

#### 🤔 Raisonnement

- L'expansion permet de capturer des opportunités de "Fast Flip" (ex: Boss Katana) et de maximiser la valeur des packs guitare+étui.
- Le maintien du persona **Maître Luthier** assure une analyse technique rigoureuse, même sur des objets non-luthier classiques comme les amplis numériques.

---
