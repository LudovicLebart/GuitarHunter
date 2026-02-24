# Journal de Bord - Guitar Hunter AI

[2026-02-23] [FLASH] Réflexion Statistiques → Conceptualisation des KPIs basés sur les scores du Tier 2/3 et archivage dans `docs/STATS_REFLEXION.md`.

[2026-02-23] [FLASH] Action : Conception de l'entonnoir d'analyse à 3 niveaux et création de `docs/FUNNEL_PLAN.md` → Résultat : Stratégie validée pour réduire les coûts (Tier 2 compact) tout en augmentant la profondeur (Tier 3 Expert Pro conditionnel). Introduction de 5 scores numériques et d'une logique de déclenchement "Jackpot" (Marge + Défi).
[2026-02-23] [FLASH] Action : Création de `backend/scripts/fetch_deal.py` → Résultat : Outil fonctionnel pour inspecter les annonces réelles dans la structure Firestore imbriquée (`artifacts/{app}/users/{user}/...`).
[2026-02-23] [FLASH] Action : Mise à jour de `docs/ARCHITECTURE.md` → Résultat : Documentation de la structure multi-tenant de la base de données.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` → Résultat : Assainissement du titre de la notification (suppression des sauts de ligne `\n`) pour éviter des erreurs HTTP `Invalid header value` lors de l'envoi à `ntfy.sh`.
[2026-02-22] [PRO] Action : Modification de `src/App.jsx` → Résultat : Le lecteur récupère désormais l'ID d'annonce via le lien `deals` complet (et plus `filteredDeals`), évitant que la carte ne s'ouvre pas si l'annonce est archivée/filtrée.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` → Résultat : Le lien cliquable des notifications `ntfy` renvoie désormais vers la carte du deal sur le frontend (`?dealId=...`) au lieu de l'annonce Facebook FB.

Ce journal suit les changements majeurs, les décisions d'architecture et les nouvelles fonctionnalités.

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

### **Date: 24/05/2024** (Session 9)

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

### **Date: 24/05/2024** (Session 8)

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

### **Date: 24/05/2024** (Session 6)

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

### **Date: 24/05/2024** (Session 5)

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

### **Date: 24/05/2024** (Session 4)

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

### **Date: 24/05/2024** (Session 3)

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

### **Date: 24/05/2024** (Session 2)

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

### **Date: 24/05/2024** (Session 1)

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
