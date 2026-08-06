# Liste des Tâches - Guitar Hunter AI

Ce document sert à suivre les tâches à accomplir, les bugs à corriger et les améliorations prévues.

**Consigne pour l'Assistant AI :**
- Consultez ce fichier au début de chaque session.
- Ajoutez-y les nouvelles tâches définies lors des discussions avec l'utilisateur.
- Marquez les tâches comme `[x]` une fois qu'elles sont terminées et validées, puis déplacez-les vers [`TODO_ARCHIVE.md`](TODO_ARCHIVE.md) lors du prochain nettoyage plutôt que de les laisser s'accumuler ici.

> 📦 Tâches déjà terminées (historique complet, contexte technique conservé) : [`docs/management/TODO_ARCHIVE.md`](TODO_ARCHIVE.md)

---

## 🔍 Extension LeBonCoin (Exploration — 2026-07-21)

*Calibration/validation de l'approche Playwright "douce" face à DataDome terminée et validée en conditions réelles — voir l'archive pour le détail. Reste à faire :*

- [ ] **Reste à faire : décider de l'intégration réelle** (cadence, volume cible ~50-100/jour) — pas encore commencée, scripts actuels = calibration/test uniquement, aucune écriture Firestore. Voir les 2 points ci-dessous, à traiter avant/pendant cette intégration.

- [ ] **Dette technique : base commune scraper LeBonCoin/Facebook (mesures anti-bot)** *(Ajouté 2026-07-22, revue de code)*
    - *Détails :* `backend/scraping_leboncoin/core.py` (`LeboncoinScraper`) duplique actuellement des éléments déjà présents dans `backend/scraping/core.py` (`FacebookScraper`) : listes UA/viewports, flags de lancement stealth, cycle de vie de session (`start_session`/`close_session`/`_ensure_session`). Accepté pour l'instant (deux sites, deux stratégies d'extraction différentes — JSON structuré vs sélecteurs CSS), mais deviendra un vrai risque de dérive dès qu'on appliquera des règles anti-détection **communes** aux deux scrapers (cadence non-uniforme, plages horaires humaines — voir point suivant) : un correctif appliqué à un seul des deux modules ne se propage pas automatiquement à l'autre.
    - *Piste* : extraire une classe de base commune (session Playwright, stealth, human-pause/jitter) que les deux scrapers spécialisent, plutôt que deux implémentations parallèles à maintenir en synchronisation manuelle.

- [ ] **Cadence de scan calquée sur un rythme humain (pas d'activité nocturne)** *(Ajouté 2026-07-22)*
    - *Détails :* Un bot qui scanne à un rythme uniforme 24h/24 (y compris la nuit, ex: 3h du matin) est lui-même un signal comportemental détectable dans la durée — un humain ne consulte pas les petites annonces en pleine nuit. Point soulevé par l'utilisateur, pas encore pris en compte.
    - *Piste* : lors de l'intégration réelle (bot.py/scheduling), prévoir une plage horaire d'activité réaliste (ex: pas de scan ou volume fortement réduit entre ~00h-7h), idéalement avec une légère variation aléatoire des bornes plutôt qu'un couperet fixe (qui serait lui-même un pattern détectable).
    - *Portée* : concerne potentiellement les deux scrapers — Facebook tourne déjà 24h/24 via `TaskScheduler` à cadence fixe en minutes (`schedule.every(X).minutes`), sans notion de plage horaire. À évaluer si ça vaut la peine de l'appliquer aussi côté Facebook, ou seulement pour LeBonCoin où le risque de détection est plus aigu (DataDome vs protections plus légères de Facebook) — décision produit à trancher avec l'utilisateur.

---

## 🛒 Multi-plateforme — Scraper Kijiji

*Scraper autonome intégré au pipeline et validé de bout en bout (2026-07-27) — voir l'archive pour le détail. Reste à faire :*

- [ ] **Mapping de catégories** : seule la catégorie 613 (Guitars) est connue/utilisée pour l'instant ; ajouter les ID pertinents (amplis, étuis...) si besoin.
- [ ] **Pagination non gérée** : `__NEXT_DATA__` ne reflète que les annonces déjà rendues côté serveur pour une page de résultats — si Kijiji pagine (plutôt qu'un défilement infini), `max_ads` au-delà de ce total nécessitera de naviguer vers les pages suivantes (non implémenté).
- [ ] **Écarts assumés vs `FacebookScraper`** : pas de rotation de proxy (le filtre par ville est couvert par `locations.py`, le filtre géo/prix par `build_search_url()`).

---

## 🚨 Priorité Haute (Bugs & Correctifs)

- [ ] **Bug : Scraping échoue à détecter les annonces vendues (label "VENDU" dans le titre ou annonce inexistante)** *(Ajouté 2026-07-19)*
    - *Symptôme signalé :* Le scraper détecte régulièrement des annonces dont le titre contient le mot "VENDU" (ajouté manuellement par le vendeur), ou des annonces que Facebook retourne encore dans les résultats de listing même si la fiche détail n'existe plus ou redirige. Ces annonces passent le pipeline IA et génèrent des faux positifs.
    - *Causes probables :*
        1. Le portier (`gemini-2.5-flash-lite`) n'est pas instruit de rejeter les annonces dont le titre ou la description contient explicitement "VENDU", "SOLD", "vendu!", etc.
        2. `check_listing_availability` vérifie la redirection 404 mais pas le cas "page existe, mais titre contient VENDU" (vendeur qui ne supprime pas l'annonce).
    - *Pistes de correction :*
        1. ✅ **Filtre pré-IA (implémenté 2026-07-19)** : `handle_deal_found()` (`backend/bot.py`) — vérification de `SOLD_MARKERS` (`vendu`, `sold`, `deal closed`…) dans le titre et les 200 premiers chars de description. Rejet avant `session_processed_ids.add()` (pas marqué "traité") pour permettre re-détection si le vendeur corrige son titre. Log visible dans LogViewer.
        2. [ ] **Filtre scraper** : dans `check_listing_availability()` (`backend/scraping/core.py`), ajouter une vérification du titre récupéré — si le titre de la fiche détail contient "VENDU", traiter comme vendu.
        3. ✅ **Prompt Tier 1 (implémenté 2026-08-06)** : `gatekeeper_verbosity_instruction` (`prompts.json`) instruit désormais explicitement le Portier de rejeter (`REJECTED_ITEM`) toute annonce dont le titre/description signale une vente déjà conclue — couvre notamment les scans manuels, qui contournent le filtre pré-IA (piste 1). Non testé en conditions réelles depuis l'environnement de dev (pas d'accès Gemini/Facebook/Kijiji) — à valider par l'utilisateur.
    - *Priorité :* Moyenne — génère du bruit et des lectures Firestore inutiles mais pas de bug critique. Reste ouvert : piste 2 seule.

- [ ] **Investiguer : session Facebook non authentifiée → Facebook gate parfois le prix/les photos**
    - *Détails :* Le scraper est 100% anonyme (aucun `storage_state`/cookies persistants nulle part dans le backend, vérifié). Comportement intermittent observé sur `SCAN_URL` — la fiche détail se charge sans carrousel photo ni prix visible, alors que le titre/description restent disponibles (voir `TODO_ARCHIVE.md` pour l'historique du bug "Fiche détail Facebook dégradée").
    - *Options à trancher avec l'utilisateur :* (a) accepter la limitation — les annonces concernées ne sont simplement plus stockées (garde-fou "scraping raté" déjà en place) ; (b) implémenter une session Facebook authentifiée (identifiants d'un compte dédié, risque de bannissement selon les CGU Facebook, gestion sécurisée des secrets, renouvellement de session).

- [ ] **Fix : `GEMINI_MODELS["default_analyst"]` (`config.py`) n'est pas réellement câblé**
    - *Détails :* Découvert le 2026-07-09 en corrigeant le fix `gemini-2.5-flash`. `bot.py::_init_firestore_structure()` n'initialise que `gatekeeperModel`/`expertModel` dans le document Firestore d'un nouvel utilisateur, jamais `mainModel` — `GEMINI_MODELS["default_analyst"]` est donc mort de fait. Le vrai défaut utilisé en pratique est le fallback codé en dur dans `analyzer.py::analyze_deal()` (`config.get('mainModel', '...')`), qui doit être maintenu manuellement en synchronisation avec `config.py`.
    - *Solution à trancher :* soit initialiser `mainModel` dans `_init_firestore_structure()` (cohérent avec `gatekeeperModel`/`expertModel`), soit supprimer `default_analyst` de `config.py` si on préfère garder un seul point de vérité (le fallback dans `analyzer.py`).

- [ ] **Fix : Ordre d'affichage du LogViewer non garanti (batching Firestore)**
    - *Détails :* Découvert le 2026-07-09 en diagnostiquant le bug de fiche détail dégradée — `FirestoreHandler` bufferise les logs et les envoie par lots toutes les 3s ; des logs émis à quelques centaines de ms d'écart peuvent recevoir un `timestamp` serveur identique/très proche, et s'afficher dans le LogViewer dans un ordre différent de leur émission réelle (observé concrètement : un log de `handle_deal_found` affiché avant un log qui le précède pourtant dans le code).
    - *Solution possible :* ajouter un champ de séquence monotone (ex: compteur incrémental côté `FirestoreHandler`, ou timestamp local haute résolution) pour un tri stable côté `LogViewer.jsx`, en complément du `timestamp` serveur.

- [ ] **Problème de la double connexion API (Feature future) :**
    - *Détails :* À lister si le besoin s'en fait sentir.

---

## 🧹 Maintenabilité & Dette Technique

- [ ] **Migrer `backend/analyzer.py` du SDK `google.generativeai` vers `google-genai`**
    - *Détails :* Découvert le 2026-07-07 — `google.generativeai` émet désormais un `FutureWarning` explicite indiquant que son support est totalement terminé. Toujours fonctionnel pour l'instant, mais refactor à planifier (signatures d'API différentes entre les deux SDK).

- [ ] **Architecture : Pool d'annonces commun entre utilisateurs (dédoublonnage par ID Facebook)**
    - *Détails :* Chaque utilisateur possède sa propre sous-collection isolée `users/{uid}/guitar_deals` (architecture multi-tenant, `ARCHITECTURE.md §1`). Quand plusieurs utilisateurs scannent des zones géographiques qui se recoupent, la **même annonce Facebook** (même ID) est scrapée et analysée par l'IA (3 appels Gemini) séparément pour chacun — un pur gaspillage, puisque le contenu de l'annonce est identique.
    - *Preuve concrète* : `backend/scripts/analyze_funnel_by_user.py` a mis en évidence des annonces identiques (ex: "Guitare Oscar Smith", "Guitare acoustique Madera") analysées 3 fois pour 3 utilisateurs différents (`GEMINI_PROMPT_CACHING_PLAN.md §8.2`).
    - *Piste* : passer à un **pool d'annonces partagé** (collection globale indexée par ID Facebook, analysée IA une seule fois), avec une couche de **filtrage/affichage par utilisateur** (ville, prix, mots-clés propres à chaque config) qui ne montre que les annonces pertinentes pour ses propres critères de recherche — sans dupliquer ni le scraping ni l'analyse IA.
    - *Impact estimé* : réduction directe et significative des appels Gemini (donc du coût), plus large que le gain du caching de contexte (`GEMINI_PROMPT_CACHING_PLAN.md`) puisqu'elle élimine l'appel plutôt que de le rendre moins cher. À chiffrer/planifier séparément (refactor architecture significatif : migration des données existantes, règles Firestore, `firestoreService.js`, `bot.py`).

- [ ] **Problème à documenter...**
    - *Détails :* ...

---

## 🎨 Interface Utilisateur (UI/UX)

- [ ] **Ajouter un bouton de sauvegarde explicite pour les prompts**
    - *Détails :* Actuellement, chaque `onBlur` sur un champ du `PromptListEditor` déclenche une sauvegarde immédiate dans Firestore. Envisager un bouton "Sauvegarder" avec confirmation pour éviter les sauvegardes accidentelles.

- [ ] **Migration catalogue partagé** *(Dette technique)*
    - *Détails :* Le serveur déployé utilise l'ancienne architecture (villes dans `users/{uid}/cities` avec métadonnées complètes). Le catalogue partagé `artifacts/{APP_ID}/cities` est vide. Un fallback a été ajouté côté frontend, mais la migration vers la nouvelle architecture reste à faire pour le déploiement de la nouvelle version backend.

- [ ] **Améliorer la recherche globale (Modèle, Lieu, etc.)**
    - *Détails :* Permettre à la barre de recherche de filtrer également selon la taxonomie. Envisager une autocomplétion intelligente qui propose des catégories (ex: Guitares, Amplis) en plus des termes libres.
    - *Progrès (2026-07-31)* : la recherche texte libre matche désormais aussi `brand`/`model_name`/`color` (en plus du `title`), sur toutes les annonces via l'index (`deals_index`). Reste à faire : matcher la taxonomie elle-même et l'autocomplétion de catégories.

- [/] **Dashboard Analytics & Statistiques** *(Moteur de calcul intégré, en cours)*
    - *Détails :* Le "moteur" de stats est fonctionnel au sein du composant, utilisant les données réelles de Firestore.

- [/] **Trop de boutons d'action sur la DealCard** *(Ajouté 2026-07-31, retour utilisateur après test du bouton "Discuter sur Gemini")*
    - *Détails :* La barre d'actions (`DealCardActions.jsx`) accumulait Favori, Ré-analyser (menu), Rejeter, Supprimer, Partager, Discuter sur Gemini, Voir l'annonce d'origine — jugée surchargée. Décision produit non tranchée à l'origine : l'utilisateur voulait réfléchir à un autre emplacement (ex: menu secondaire, uniquement dans la modale et pas la carte liste, regroupement des actions secondaires derrière un menu "···").
    - *Progrès (2026-07-31, chat Gemini intégré)* : le bouton "Discuter avec Gemini" a été retiré de la carte liste (visible uniquement dans la modale, `isModal` + `onOpenChat`) — un bouton en moins sur la vue liste. Reste ouvert : la barre d'actions de la modale elle-même (7 boutons) n'a pas été réorganisée/regroupée.

### 🪟 Modale d'Analyse IA

- [ ] **Bouton "Discuter sur Gemini"** *(Branche `feature/discuter-gemini`, 2026-07-31, en attente de validation utilisateur avant fusion)*
    - *Détails :* Alternative à un chat IA intégré (jugée trop lourde — nouveau backend, nouvelle collection Firestore) : copie un prompt (annonce + analyse IA) dans le presse-papier et ouvre `gemini.google.com/app?q=...` dans un nouvel onglet pour que l'utilisateur poursuive la conversation avec Gemini directement.
    - *Non validé* : impossible de vérifier depuis l'environnement de dev si `?q=` préremplit réellement le champ de saisie Gemini (Playwright bloqué par le proxy du sandbox). Le presse-papier reste un repli garanti dans tous les cas. À tester par l'utilisateur, puis fusionner dans `dev` si ok.

---

## 🧠 Système de Prompts & IA

### 🔴 Fiabilité de l'Éditeur de Prompts

- [ ] **Ajouter une validation des prompts avant sauvegarde**
    - *Détails :* L'éditeur ne vérifie pas si l'utilisateur a cassé la structure JSON attendue dans `mainAnalysisPrompt`. Implémenter une détection de la présence du bloc `### FORMAT DE RÉPONSE JSON STRICT` et afficher un avertissement si absent.
- [ ] **Ajouter un bouton "Réinitialiser cette section" par prompt**
    - *Détails :* Permettre de revenir aux valeurs par défaut de `prompts.json` individuellement.

### 🟡 Architecture des Prompts

- [ ] **Découper `mainAnalysisPrompt` en sections éditables indépendantes**
    - *Détails :* Le prompt principal est actuellement un bloc monolithique. Le structurer en sous-sections indépendantes dans Firestore et dans l'UI : `Persona & Objectifs`, `Règles de Verdicts`, `Format JSON`. Permet une édition chirurgicale sans risque de tout casser.

- [ ] **Rendre la Taxonomie modifiable via l'interface**
    - *Détails :* Stocker `taxonomy_master` dans Firestore et l'injecter dynamiquement dans `analyzer.py`. Exposed dans le `ConfigPanel` avec un éditeur JSON dédié.

---

## 📊 Statistiques & Dashboard

- [/] **Mettre en place le moteur de statistiques (Impact Tier 3)**
    - *Plan de travail :* [`docs/explanation/STATS_REFLEXION.md`](../explanation/STATS_REFLEXION.md)
    - *Objectif :* Exploiter les 5 scores et le funnel pour générer des KPIs financiers (ROI, Marges) et qualitatifs (Profil de marché, Vitesse de rotation).
    - [x] **Statistiques croisées (2026-08-06)** : `StatsView.jsx` — Sweet Spot (score IA moyen par tranche de prix), Marge moyenne par catégorie de taxonomie, Véracité IA (score des annonces vendues vs ensemble du marché), Comparaison Facebook vs Kijiji, Géographie des opportunités par ville. Basé uniquement sur l'index léger déjà chargé (`deals_index`), sans lecture Firestore supplémentaire. Détail dans `STATS_REFLEXION.md`.
    - [ ] **Reste à faire** : "Cold Deals" (annonces anciennes en apparence bonnes mais invendables), `discount_index`, badges "Certifié Expert" sur les KPIs basés sur une analyse Tier 3.
