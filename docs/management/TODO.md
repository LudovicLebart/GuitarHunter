# Liste des Tâches - Guitar Hunter AI

Ce document sert à suivre les tâches à accomplir, les bugs à corriger et les améliorations prévues.

**Consigne pour l'Assistant AI :**
- Consultez ce fichier au début de chaque session.
- Ajoutez-y les nouvelles tâches définies lors des discussions avec l'utilisateur.
- Marquez les tâches comme `[x]` une fois qu'elles sont terminées et validées.
- Déplacez les tâches terminées dans la section "Terminé" si la liste devient trop longue.

---

## 🔐 Sécurité & Robustesse Multi-Utilisateur (Validé 2026-03-29)

### Phase 1 — Sécurité ✅

- [x] **Task 1.1 : Firestore Rules** *(2026-03-29)*
    - `firebase/firestore.rules` : `allow read, write: if true` → règles strictes `request.auth.uid == userId`
    - Document parent explicite : `match /artifacts/{appId}/users/{userId}`
    - Sous-collections couvertes : `match /artifacts/{appId}/users/{userId}/{document=**}`

- [x] **Task 1.2 : Inscription et Reset déverrouillés** *(Restaurés 2026-05-05)*
    - `useAuth.js` : `signUp` et `resetPassword` restaurés
    - `LoginPage.jsx` : Modes Login/Signup/Reset restaurés avec UI V2

- [x] **Task 1.3 : Guard `getRefs()`** *(2026-03-29)*
    - `firestoreService.js:26` : `console.warn` → `throw new Error(...)` si `userId` manquant

- [x] **Task 1.4 : Migration nettoyée** *(2026-03-29)*
    - Email admin : `ludovic.lebart@gmail.com` → `VITE_ADMIN_EMAIL` env var
    - Flag `migrationDone` : prévient les remigrés
    - Try/catch granulaire par étape (config/villes/annonces)

### Phase 2 — Robustesse ✅

- [x] **Task 2.1 : Try/except bots** *(2026-03-29)*
    - `main.py:224-247` : Création bot dans try/except. Échec isolé par user.

- [x] **Task 2.2 : Watchdog threads** *(2026-03-29)*
    - `main.py:255-284` : Boucle surveillance 30s. Redémarre threads morts.
    - Détection : `t.is_alive()`. Isolation : each user thread indépendant.

- [x] **Task 2.3 : Sémaphore Playwright** *(2026-03-29)*
    - `main.py:15` : `playwright_semaphore = threading.Semaphore(MAX_CONCURRENT_BROWSERS)`
    - `bot.py:38` : `self._browser_semaphore` reçu en param
    - `bot.py` : Chaque `FacebookScraper` → `acquire()`/`release()` (run_scan, scan_specific_url, cleanup, add_city_auto)
    - `.env` : `MAX_CONCURRENT_BROWSERS=3` (défaut)

- [x] **Task 2.4 : Lock `in_flight_command_ids`** *(2026-03-29)*
    - `main.py:60` : `in_flight_lock = threading.Lock()`
    - `main.py:95-99` : `with in_flight_lock: ...add(...)`
    - Finale : `discard()` au lieu de `remove()`

- [x] **Task 2.5 : `session_processed_ids` isolé** *(2026-03-29)*
    - `bot.py:35,72-77` : `@property` sur `threading.local()`
    - `bot.py:255` : `.clear()` au démarrage de scan

- [x] **Task 2.6 : Logger par user** *(2026-03-29)*
    - `bot.py:32` : `self.logger = logging.getLogger(f"bot.{user_id[:8]}")`
    - Tous les `logger.xxx(` remplacés par `self.logger.xxx(` dans bot.py

- [x] **Task 2.7 : Isolation du Logging (FirestoreHandler)** *(2026-05-05)*
    - `backend/logging_config.py` : `setup_logging` n'écrase plus le root logger.
    - Chaque bot possède son propre handler vers sa collection `logs` dédiée.
    - Support du redémarrage propre via nettoyage des handlers dans `setup_logging`.


### Code Review — 3 Rondes ✅

- Ronde 1 (Exactitude) : ✅ Valide. 1 bug Firestore rules → document parent ajouté.
- Ronde 2 (Cohérence) : ✅ Valide. Chaîne useAuth-AuthContext-LoginPage OK.
- Ronde 3 (Edge Cases) : ✅ Acceptables. Watchdog sans backoff = backlog.

### Backlog — Phase 3 (Architecture)

- [x] **Architecture : Découplage Frontend/Backend (Onboarding dynamique)** *(2026-05-05)*
    - *Détails :* Le backend scanne désormais Firestore pour découvrir les nouveaux utilisateurs.
    - *Correctif (Audit 2026-05-05) :* Ajout de l'initialisation auto du doc user lors du `signUp` et au chargement de session (`useAuth.js`) pour garantir la détection immédiate par le backend.
    - [x] *Correctif (Audit 2026-05-05) :* Watchdog fiabilisé pour recréer le log handler lors des redémarrages de threads.
    - [x] *Correctif (Audit 2026-05-05) :* Tooltip d'erreur sur le statut "Auth" pour un diagnostic rapide.
    - [x] *Correctif (Review 2026-05-06) :* Centralisation `ensureUserDoc` dans `useAuth.js` pour éviter la duplication.
    - [x] *Correctif (Review 2026-05-06) :* Propagation des erreurs Firestore Auth vers le statut UI.
    - [x] *Correctif (Review 2026-05-06) :* Sécurisation des sessions Playwright (`page.close()` safe).
    - *Impact :* Plus besoin de modifier le `.env` pour chaque nouvel utilisateur. Robustesse accrue face aux erreurs de permissions.


---

## 🏙️ Villes & Geocodage (2026-04-08)

- [x] **Bug : Backend scannait 0 villes après migration UID** *(Corrigé 2026-04-08)*
    - `repository.py:get_cities()` : fallback ancienne architecture si catalogue partagé vide
    - `migrate_cities_to_shared_catalog.py` : params `--source-user-id` / `--target-user-id`, gestion docId=facebook_city_id, copie fidèle isScannable
    - Migration exécutée : 20 villes → catalogue partagé, prefs `isScannable=True` pour wbPlgZgk...

- [x] **Bug : Backend rejette 20 villes (données incomplètes = lat/lon manquantes)** *(Corrigé 2026-04-08)*
    - `bot.py:add_city_auto()` : utilise Nominatim (OSM) pour coords, pas CityFinder. Enrichit villes existantes sans coords via merge upsert.
    - `utils.py:city_name_variants()` : essaie "McMasterville", "St-Jean", sans accents... pour maximiser succès geocodage.
    - `enrich_cities_coords.py` : script one-shot Nominatim pour les 20 villes manquantes.
    - Résultat : toutes les villes maintenant scannables (coords disponibles).

---

## 🚨 Priorité Haute (Bugs & Correctifs)

- [x] **Bug : Les guitares vendues ne sont plus détectées (Multi-utilisateur)** *(Corrigé 2026-04-10)*
    - *Détails :* Le service de nettoyage (`cleanup_sold_listings`) a été fiabilisé.
    - *Solution :* Migration vers une méthode `mark_deal_as_sold` dans le repository.
    - *Amélioration réalisée :* Ajout automatique d'un champ `soldAt` (date de détection de la vente) permettant des statistiques de "vitesse de vente".


- [x] **Bug : Collision des compteurs de taxonomie (Noms identiques)** *(Corrigé Session 37)*
    - Utilisation de chemins hiérarchiques complets (`dot-notation`) comme clés de comptage.
    - Mise à jour de `useDealsManager.js` et `FilterDrawer.jsx` pour gérer la récursion par path.

- [x] **Bug : Liens d'images Facebook expirés ("URL signature expired")** *(Corrigé Session 29)*
    - Stockage pérenne via Firebase Storage. Upload systématique lors de chaque `handle_deal_found`.
    - Politique de cycle de vie : purge des images des deals rejetés après 30 jours (`IMAGE_RETENTION_REJECTED_DAYS`).
    - Script de migration one-shot : `backend/scripts/migrate_images.py`.

- [x] **Bug : Scans multiples concurrents (ouverture de plusieurs fenêtres Playwright)** *(Corrigé Session 42)*
    - *Détails :* La boucle principale de `main.py` relançait la même commande `REFRESH` plusieurs fois si elle restait `pending` dans Firestore, entraînant des scans concurrents et des erreurs.
    - *Solution :* Implémentation d'un verrou local (`in_flight_command_ids` set) dans `main.py` pour s'assurer qu'une commande n'est exécutée qu'une seule fois à la fois, même si elle est encore `pending` dans Firestore.

- [x] **Opération de maintenance : Nettoyage et rafraîchissement des images corrompues** *(Effectué Session 42)*
    - *Détails :* Suite au bug des scans multiples, des images incorrectes ont pu être associées à des annonces.
    - *Solution :* Création et exécution du script `backend/scripts/refresh_images.py`.
    - *Fiabilisation :* Le script a été optimisé pour utiliser une session de navigateur unique (anti-détection) et pour cibler uniquement les annonces créées après une date spécifique (`--since-date`) pour plus d'efficacité.

- [x] **Bug : Liens d'images Facebook expirés ("URL signature expired")** *(Corrigé Session 29)*
    - Frontend : fallback `storageImageUrls || imageUrls` dans `DealCard.jsx`.

- [x] **Bug : Interruption du Script de Rescraping d'Images par Facebook (Anti-botting)** *(Corrigé Session 35)*
    - *Détails :* Playwright est détecté par Facebook lors du rescraping massif des images. 
    - *Solution :* Implémentation de mesures **Stealth** (User-Agent/Viewport aléatoires, flags anti-detection), détection active de blocage, **Rotation de Session** (toutes les 15 requêtes) et **Jitter** aléatoire.

- [x] **Bug : Le bot en pause ne se réveille pas via "Rescan All"** *(Corrigé Session 28)*
    - Boucle de pause dans `main.py` sonde désormais Firestore toutes les 5s.
    - Toute commande d'action, et notamment les commandes manuelles asynchrones (REFRESH, SCAN_URL), interrompt la pause.

- [x] **Bug : "Delete All Logs" ne fonctionne pas** *(Corrigé Session 28)*
    - `delete_all_logs` dans `repository.py` réécrite avec `list()` pour forcer la consommation du stream Firestore.

- [x] **Bug : Statut "En attente" pendant le Scraping** *(Corrigé Session 28)*
    - Implémentation de `set_status()` avec `threading.Lock()` et `_active_tasks` dans `GuitarHunterBot` pour gérer les conflits de threads (ex: `run_scan` vs `cleanup_sold_listings`).

- [x] **Bug : Commandes manuelles (Rescan, URL) qui démarrent "tardivement"** *(Corrigé Session 28)*
    - Les commandes `REFRESH`, `REANALYZE_ALL` et `SCAN_URL` s'exécutent désormais dans des threads `daemon` séparés dans `main_loop` pour ne pas bloquer le séquenceur `scheduler.run_pending()`.

- [x] **Brancher la purge lifecycle au scheduler** *(Corrigé Session 29)*
    - `bot.purge_rejected_images()` ajouté comme `purge_func=` dans `TaskScheduler` (`services.py`). Job hebdomadaire déclenché automatiquement au démarrage du bot.

- [x] **Vérifier les règles Firebase Storage** *(Fait)*
    - *Détails :* Confirmer que les blobs uploadés via `blob.make_public()` sont bien accessibles publiquement. Vérifier dans la console Firebase → Storage → Rules que les lectures publiques sont autorisées.

- [x] **Lancer la migration réelle des images** *(Fait Session 29 — migrate --real)*

- [x] **Feature : Extraire la Date de Mise en Ligne** *(Session 40)*
    - *Détails :* Extraction de la date relative (`abbr[aria-label]`) via le scraper pour enrichir les métadonnées de l'annonce.

- [x] **Bug : Images sans rapport (véhicules, bateaux...) associées à une annonce** *(Corrigé 2026-07-06)*
    - *Détails :* Le bloc "Suggestions" affiché par Facebook sous la description de chaque annonce était partiellement capturé par le filtre d'extraction d'images (basé uniquement sur la taille >300×300px), surtout pour les annonces ayant peu de vraies photos.
    - *Solution :* `parser.py::parse_details_page()` exclut désormais les images entourées d'un lien vers une autre annonce (`<a href="/marketplace/item/{AUTRE_ID}/...">`). Ajout d'un garde-fou `_is_valid_detail_page()` dans `core.py` pour les cas de redirection /login réelle.
    - *Vérifié :* Test réel sur une annonce publique — 19 images (16 suggestions) → 3 images (toutes réelles) après correctif.

- [ ] **Bug : Les notifications ntfy de "pépite" ne permettent pas d'ouvrir l'annonce**
    - *Détails :* Le lien dans la notification ntfy.sh renvoie à la page principale de l'application plutôt qu'à l'annonce spécifique. (Corrigé par l'implémentation du partage via `dealId` qui génère un lien direct vers l'annonce).

- [x] **Feature : Double appartenance "Pépite" pour les autres verdicts d'opportunité** *(Corrigé 2026-07-06)*
    - *Détails :* Un `LUTHIER_PROJ`/`FAST_FLIP`/`CASE_WIN`/`COLLECTION` qui remplit aussi les critères Pépite (marge) restait invisible du filtre/notifications "Pépites".
    - *Solution :* Nouveau champ IA `also_qualifies_pepite` (`prompts.json`), pris en compte dans le filtre et le compteur Pépites (`useDealsManager.js`), badge secondaire "Aussi Pépite" (`DealCard.jsx`), et déclenchement de la notification (`notifications.py`).
    - *Bug critique corrigé au passage* : `notify_deal()` plantait (`NameError` sur `HIGH_PRIORITY_VERDICTS`/`profit`) à chaque Pépite trouvée, interrompant le scan des villes restantes (pas de `except` sur la boucle dans `bot.py::run_scan`).
    - *Bug annexe corrigé* : `NtfyNotifier.send()` plantait silencieusement sur les émojis/accents du titre (headers HTTP Latin-1 uniquement) — corrigé via encodage RFC 2047.
- [x] **Bug : Les notifications ntfy de "pépite" ne permettent pas d'ouvrir l'annonce**
- [x] **Bug : Problème de déplacement sur la carte (MapView)** *(Corrigé 2026-05-06)*
    - *Détails :* Correction de l'interaction InfoWindow (gap mouseout) et restauration du bouton de fermeture.

- [ ] **Problème de la double connexion API (Feature future) :**
    - *Détails :* À lister si le besoin s'en fait sentir.

---

## 🧹 Maintenabilité & Dette Technique

- [x] **Implémenter une stratégie de rotation d'IP (proxies) pour le scraper**
    - *Détails :* Si les problèmes de détection par Facebook persistent, explorer l'intégration de proxies résidentiels ou d'une rotation d'IP pour le scraper Playwright afin d'améliorer la furtivité et la résilience.
- [ ] **Problème à documenter...**
    - *Détails :* ...

---

## 🎨 Interface Utilisateur (UI/UX) - Priorités Structurelles et Ergonomiques

- [x] **Prototype Mockup V2 (Phase d'Exploration Completée)**
    - *Détails :* Mockup complet avec Dark Mode, Map Split-Screen, et Filtres en cascade. Validé en Session 29-31.
    - [x] **Libérer l'Affichage Desktop (Démantèlement de l'Aside)** *(Ok en Mockup)*
    - [x] **Lisibilité Financière : Badge Marge sur vue liste** *(Ok en Mockup)*
    - [x] **Filtre Drawer : Cascade 4 niveaux** *(Ok en Mockup)*
    - [x] **Refonte du Mobile : Images Full-Width** *(Ok en Mockup)*
- [x] **Réalisme des Images et Galerie (Mockup)** *(Ok en Mockup)*
- [x] **Dark Scrollbar pour les Filtres (Mockup)**
    - *Détails :* Terminé et appliqué aux blocs d'analyses IA et volets latéraux.

- [x] **🚀 Activation V2 — Mockup → Production Ready** *(Complété Session 36)*
    - *Détails :* La V2 est désormais l'interface par défaut. Les composants "Mockup" ont été renommés en noms standards (`Dashboard`, `DealCard`, `Navbar`, `FilterDrawer`, `StatsView`). Les anciens fichiers V1 (`FilterBar`, `SectionGroup`, `DealModal`, `BotControls`, `DebugStatus`) ont été supprimés. `App.jsx` a été simplifié pour monter directement le `Dashboard`.
- [x] **Bug Mockup V2 : Filtres inopérants** *(Câblé en Session 32)*
- [x] **Refonte UI Mobile : Corrections majeures** *(Complété Session 34)*
    - *Détails :* L'interface mobile présente de nombreux problèmes et doit être corrigée en priorité.
    - [x] Correction du bouton "Statut" (Menu des Verdicts) qui s'écrasait et coupait le texte.
    - [x] Affichage de l'annonce en "Overlay" (plein écran) sur mobile.
    - [x] Inversion de l'ouverture (1er clic = Tooltip, 2ème clic = Overlay).
- [x] **Bug : Débordement horizontal en mode mobile** *(Corrigé 2026-07-06)*
    - *Détails :* Aucune contention `overflow-x` dans l'app ; la page se dimensionnait sur l'élément le plus large (dropdown à largeur ambiguë, menus `absolute` sans limite de largeur) plutôt que sur l'écran. La barre "Recherche & Actions" était aussi trop étroite en mobile pour contenir la croix "Effacer les filtres".
    - *Solution :* `overflow-x: hidden` global (`index.css`), largeur explicite sur le dropdown Statut, empilement des groupes de boutons sous 640px, `max-w-[calc(100vw-2rem)]` sur les menus flottants.
    - *À confirmer par l'utilisateur* : rendu du Dashboard authentifié sur mobile réel (non vérifiable en session, mur d'authentification).
- [x] **Système de Thème (Dark Mode) global** *(Intégré dans le Mockup)*
- [/] **Dashboard Analytics & Statistiques** *(Moteur de calcul intégré — `MockupStatsView.jsx`)*
    - *Détails :* Le "moteur" de stats est fonctionnel au sein du composant, utilisant les données réelles de Firestore.
- [x] **Créer un Panneau de Statistiques (Dashboard Analytics)**
    - [x] Afficher les KPIs financiers (Marges, Scores, Volumes).
    - [x] Implémenter le Tunnel de Conversion (Funnel) 3-Tiers.
    - [x] Implémenter le Radar Chart des 5 scores Gemini (recharts).
    - [x] Distribution par Marque (fallback textuel en attendant extraction `brand` backend).
- [x] **Revoir l'affichage du bloc de prix / Actions** *(Complété Session 34)*
    - *Détails :* Intégration de la barre d'actions complète dans la modale IA et parité avec la DealCard. Option de scan Standard/Expert.
- [ ] **Ajouter un bouton de sauvegarde explicite pour les prompts**
    - *Détails :* Actuellement, chaque `onBlur` sur un champ du `PromptListEditor` déclenche une sauvegarde immédiate dans Firestore. Envisager un bouton "Sauvegarder" avec confirmation pour éviter les sauvegardes accidentelles.
- [x] **Redessiner le Panneau de Paramètres (ConfigPanel)** *(Complété Session 38 & 41)*
    - *Détails :* Aligner l'esthétique du panneau de configuration sur la V2. Correction de la lisibilité de la console par l'ajout d'un fond 100% opaque.
    - *Détails :* Aligner l'esthétique du panneau de configuration (prompts, villes, etc.) sur la nouvelle charte graphique V2 (Dark Mode, Slate/Blue palette, coins arrondis, typographie).

- [x] **Autocomplétion dans le formulaire d'ajout de ville** *(2026-04-07)*
    - *Détails :* Suggestions filtrées depuis le catalogue existant dès 2 caractères tapés. Clic = activation directe si ville non-active.

- [ ] **Migration catalogue partagé** *(Dette technique)*
    - *Détails :* Le serveur déployé utilise l'ancienne architecture (villes dans `users/{uid}/cities` avec métadonnées complètes). Le catalogue partagé `artifacts/{APP_ID}/cities` est vide. Un fallback a été ajouté côté frontend, mais la migration vers la nouvelle architecture reste à faire pour le déploiement de la nouvelle version backend.

- [ ] **Améliorer la recherche globale (Modèle, Lieu, etc.)**
    - *Détails :* Permettre à la barre de recherche de filtrer également selon la taxonomie. Envisager une autocomplétion intelligente qui propose des catégories (ex: Guitares, Amplis) en plus des termes libres.

### 🪟 Modale d'Analyse IA (Mockup V2)

- [x] **Ajouter un bouton Favoris dans la modale** *(Session 33)*
    - *Détails :* L'utilisateur peut désormais marquer une annonce en favori directement depuis la vue détaillée (modale) de la carte.

---

### 🗺️ Cartographie (Mockup V2)

- [x] **Améliorer l'interaction avec les Pins** *(Complété Session 34)*
    - *Détails :* InfoWindows enrichies (Dark Theme), miniatures, score IA. Gestion différencée Hover (PC) / Click (Mobile).

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

- [ ] **Mettre en place le moteur de statistiques (Impact Tier 3)**
    - *Plan de travail :* [`docs/explanation/STATS_REFLEXION.md`](../explanation/STATS_REFLEXION.md)
    - *Objectif :* Exploiter les 5 scores et le funnel pour générer des KPIs financiers (ROI, Marges) et qualitatifs (Profil de marché, Vitesse de rotation).

- [x] **Feature : Détection des Baisses de Prix** *(Session 05/03/2026)*
    - *Détails :* Le bot compare le prix actuel avec le prix en DB. Si inférieur, il met à jour le document, calcule `price_drop_amount` et force une réanalyse IA.
    - *Frontend :* Affichage d'un badge vert émeraude "Baisse -XX$" sur la DealCard.

- [x] **Feature : Pipeline IA 3-Tiers configurable** *(Session 05/03/2026)*
    - *Détails :* Ajout d'un modèle intermédiaire "Analyste" (Tier 2) entre le Portier et l'Expert Pro.
    - *Frontend :* Le `ConfigPanel` permet désormais de choisir les 3 modèles indépendamment. Correction du bug écrasant l'Expert Pro vers Flash.

---

## ✅ Terminé

- [x] **Feature : Notifications Email par utilisateur (SMTP Gmail)** *(2026-04-10)*
    - *Backend* : Refonte de `notifications.py` (Ntfy + Email).
    - *Intégration* : `bot.py` récupère l'email Firebase Auth et le transmet à `notify_deal`.
    - *Configuration* : Support SMTP (Gmail TLS) via `.env`.

- [x] **Feature : Système Multi-Utilisateurs & Migration V2** *(Session 2026-03-21)*
    - *Backend* : `USER_IDS_TARGET` dans `.env` (liste d'UIDs). Un thread par utilisateur dans `main.py`. `bot.py` paramétrable.
    - *Frontend* : Firebase Auth email/password (`useAuth.js`). `LoginPage.jsx` (Login/Register). `firestoreService.js` dynamisé (`getRefs(userId)`).
    - *Migration* : Script automatisé pour rapatrier l'ancienne DB vers le nouveau UID Firebase de l'administrateur.


- [x] Raffinement UI V2 : Modale IA plein écran, MapView auto-centrée, Raccourci Favoris.
- [x] Implémentation du Mockup V2 avec refonte UX totale (Filtres, Stats Dropdown, Navbar, Maps).
- [x] Session 29 : Stockage pérenne des images via Firebase Storage (Backend & UI implémenté).
- [x] Session 29 : Purge automatique hebdomadaire des images rejetées (TaskScheduler).
- [x] Correction: Simplification de la taxonomie (etui_housse) et rejet strict des autres accessoires (ex: pédales, stands).
- [x] Correction: Ajout du 4ème niveau de tri dans FilterBar et affichage des rejets (Session 28).
- [x] Expansion du Scope (Étape 1) : Taxonomie Master (Guitares, Amplis, Étuis).
- [x] Création de la structure de documentation (`docs/`).
- [x] Mise en place du `AI_BRIEFING.md`.
- [x] Refonte responsive de la `DealCard` (Mobile First).
- [x] Analyse approfondie du système de prompts dynamiques (Session 10).
- [x] Nettoyage et restructuration de la racine du projet (Session 15).
- [x] Externalisation des verdicts de rejet (Session 15).
- [x] Refonte du système de nettoyage des annonces vendues (Soft Delete) (Session 16).
- [x] Implémentation du Funnel 3-Tiers (Optimisation Expert Pro) (Session 21).
- [x] "Delete All Logs" : Correction IDs codés en dur (Session 21).
- [x] "Stop Bot" : Injection de `threading.Event` pour arrêt immédiat (Session 21/26).
- [x] Création d'un outil de migration et audit Firestore (Session 21).
- [x] Résolution du conflit de casse Git (`Dev` vs `dev`) (Session 22).
- [x] Correction du rejet systématique des étuis/housses (Session 23).
- [x] Standardisation des instructions de verbosité en format `array of strings` (Session 23).
- [x] Déploiement : Correction du redémarrage automatique et gestion des branches (Session 24).
- [x] Correction "Mode Hors Ligne" : Automatisation via GitHub Secrets (.env & Firebase Key) (Session 25).
- [x] Amélioration du Pilotage : Commandes `STOP_SCAN`, `START_BOT` et Pause 12h (Session 26).
- [x] Refonte UI : Composant `<BotControls />` et indicateur de statut dynamique (Session 26).
- [x] Session 27 : Fiabilisation (Regex PRO) de la détection de disponibilité du Scraper.
- [x] Correction Critique : Scroll bloqué sur la page principale (V2) sur mobile. Suppression des contraintes CSS restrictives.
- [x] Restauration du Bouton de Partage (V2) avec support native share & clipboard.
- [x] **Feature : Documentation Utilisateur Interactive (Help Overlay)** *(2026-05-05)*
    - Intégration d'un bouton d'aide dans la Navbar.
    - Création d'un overlay interactif documentant les scores IA, les verdicts, les commandes bot et les notifications email.
- [x] **Correctifs Visibilité & Globalisation** *(2026-05-06)*
    - [x] Amélioration visuelle du bouton d'aide (label "Aide" et contraste).
    - [x] Ajout d'un bandeau d'erreur dans le Dashboard pour le feedback utilisateur.
    - [x] Assouplissement du géocodage dans le backend (désormais **Totalement Global**, supporte n'importe quelle ville via scraping ID FB + Nominatim mondial).
    - [x] Ajout de texte d'aide dans le panneau de gestion des villes.
    - [x] **Refonte Help Overlay** : Guide technique en 4 étapes, isolation de l'expertise IA, précision sur le Rayon 0.
    - [x] **UX City Management** : Ajout direct via champ de recherche, suppression du formulaire `showAddForm`.
    - [x] **Robustesse CityFinder** : Support multi-langue, capture d'alias d'URL, injection `Control+A` pour nettoyage.
    - [x] **Scan Manuel** : Bouton "Lancer le scan" intégré au panneau de config.

