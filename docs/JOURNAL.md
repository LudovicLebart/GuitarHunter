# Journal de Bord - Guitar Hunter AI

[2026-03-05] [PRO] Action : Implémentation complète de la sélection 3-Tiers et correction Gemini 2.5 Pro → Résultat : (1) Correction du bug où l'Expert Pro était écrasé vers Flash à cause d'une omission dans l'UI. (2) Ajout du modèle `gemini-2.5-pro` à la liste des modèles disponibles dans l'interface. (3) Ajout d'un 3ème menu déroulant dans le `ConfigPanel` pour configurer le modèle de l'Analyste (Tier 2 - `mainModel`) de manière indépendante du Portier (Tier 1) et de l'Expert (Tier 3). (4) Mise à jour du hook `useBotConfig.js` pour gérer les 3 modèles avec les bonnes valeurs par défaut du backend.

[2026-02-28] [PRO] Action : Implémentation de la redirection par `dealId` et amélioration du partage → Résultat : (1) Le composant `Dashboard.jsx` lit désormais le paramètre `dealId` de l'URL au chargement, sélectionne l'annonce correspondante et force l'affichage en mode "Carte" (`MapView`). (2) Le bouton de partage dans `DealCard.jsx` génère un lien vers l'application avec le `dealId` de l'annonce, permettant un partage direct et une ouverture de la modale de détail. (3) La logique de sélection de l'annonce depuis l'URL a été déplacée de `useDealsManager.js` vers `Dashboard.jsx` pour une meilleure gestion de l'état de l'interface.


[2024-07-30] [PRO] Action : Implémentation d'une stratégie de rotation d'IP (Proxies) → Résultat : (1) Ajout d'une liste `PROXIES` dans `config.py` pour centraliser la configuration. (2) Modification de `FacebookScraper` (`backend/scraping/core.py`) pour sélectionner aléatoirement un proxy de la liste à chaque instanciation d'un navigateur Playwright. (3) La rotation est effective car le bot instancie un scraper temporaire pour chaque tâche, garantissant une nouvelle IP pour chaque scan de ville ou action manuelle.

[2024-07-30] [FLASH] Action : Analyse du diagnostic de détection du scraper par Facebook → Résultat : Le diagnostic est validé. Le projet a déjà implémenté la plupart des contre-mesures (session persistante, randomisation User-Agent/Viewport, jitter, intégration du téléchargement d'images, flags Playwright furtifs) documentées dans les Sessions 35 et 29. Une stratégie de rotation d'IP reste une amélioration potentielle.

[2026-02-27] [FLASH] Action : Optimisation Mobile du LogViewer → Résultat : Forçage de l'affichage en plein écran (`inset-0`, `rounded-none`) sur les petits écrans pour éviter la perte de visibilité de la console. Le comportement flottant est conservé pour les écrans larges (`sm:`).

[2026-02-27] [FLASH] Action : Correction de la lisibilité de la console (LogViewer) et du ConfigPanel → Résultat : Passage d'un fond semi-transparent (`bg-slate-900/95`) à un fond totalement opaque (`bg-slate-950`). Suppression du `backdrop-blur` qui causait des interférences visuelles lors de la superposition sur des images ou des cartes.

[2026-02-27] [FLASH] Action : Correction du blocage du scroll sur mobile → Résultat : Suppression des contraintes `min-height: 100%` et `overflow-x: hidden` sur les éléments racines dans `index.css`, `App.jsx` et `Dashboard.jsx`. Le défilement vertical natif et le geste de rafraîchissement ("pull-to-refresh") sont désormais fonctionnels sur mobile.

[2026-02-26] [FLASH] Action : Restauration du Bouton de Partage → Résultat : Ajout de l'icône `Share2` et de la fonction `handleShare` dans `DealCard.jsx`. Le bouton supporte désormais le partage natif (API `navigator.share`) et la copie automatique dans le presse-papier avec confirmation visuelle ("Lien copié !") en cas de fallback.

[2026-02-26] [FLASH] Action : Correction Critique du Scroll → Résultat : Restauration du défilement vertical en supprimant `overflow: hidden` de `index.css`. Ajout de `overflow-x-hidden` sur le `body` et le `Dashboard` pour empêcher les décalages horizontaux tout en conservant une expérience fluide sur PC et Mobile.

[2026-02-26] [FLASH] Action : Extraction de la Date de Mise en Ligne → Résultat : Implémentation du sélecteur `abbr[aria-label]` dans `ListingParser` pour capturer l'âge de l'annonce. Le champ `published_at_raw` est désormais propagé dans `listing_data` et stocké dans Firestore.

[2026-02-26] [FLASH] Action : Raffinement des Prompts pour les Lots (Bundles) → Résultat : Mise à jour de `prompts.json` (directives Portier et Prompt Principal). L'IA autorise désormais explicitement les instruments vendus avec des accessoires mineurs (micros, câbles, supports). Le verdict `REJECTED_ITEM` est désormais restreint aux annonces vendant *uniquement* des accessoires non autorisés.

[2026-02-26] [PRO] Action : Finalisation du Dashboard (Radar & Marques) & Ajout de Champs IA → Résultat : (1) Intégration de la librairie `recharts` dans le frontend. (2) Remplacement des placeholders dans `MockupStatsView.jsx` par un **Radar Chart** affichant le profil moyen des 5 scores Gemini et un **Bar Chart** pour la distribution du Top 5 des marques. Les données sont calculées dynamiquement depuis l'inventaire filtré. (3) Backend : Ajout des clés `brand`, `model_name`, `production_year`, et `country_of_origin` au dictionnaire JSON attendu dans `main_analysis_prompt` (`prompts.json`), enrichissant considérablement la granularité future de l'analyse IA.

[2026-02-26] [PRO] Action : Audit approfondi des Statistiques et du Tunnel de Conversion → Résultat : Vérification du code de `MockupStatsView.jsx`. (1) Le **Tunnel de Conversion** à 3 niveaux est déjà fonctionnel et alimenté par les données réelles de Firestore. (2) Les **KPIs Financiers** (Marge latente, ROI, Score moyen) sont calculés dynamiquement. (3) Identification des manques : le Radar Chart (nécessite Recharts) et la distribution par Marque (nécessite extraction `brand` backend) restent à implémenter. Mise à jour de la `TODO.md` pour refléter cet état d'avancement supérieur aux attentes.

[2026-02-26] [PRO] Action : Implémentation d'une Protection Anti-Botting (Stealth) Globale → Résultat : Correction du blocage par Facebook lors du rescraping massif. (1) **Randomisation** : Injection de User-Agents tournants et de Viewports aléatoires dans `FacebookScraper` (`core.py`). (2) **Furtivité Playwright** : Ajout de flags spécifiques (`AutomationControlled`, `infobars`) pour masquer l'automatisation. (3) **Détection de Blocage** : Interruption propre en cas de redirection vers `/login` ou CAPTCHA. (4) **Rotation & Jitter** : Le script `migrate_images.py` redémarre maintenant le navigateur toutes les 15 requêtes et utilise des délais aléatoires (jitter) pour simuler un comportement humain. Test `--dry-run` validé avec succès.

[2026-02-26] [PRO] Action : Raffinement des Interactions Cartographiques (Tooltip & Pins) → Résultat : Ajout d'InfoWindows enrichies au survol (PC) et au clic (Mobile) sur les marqueurs Google Maps. Les bulles incluent désormais une miniature, le titre, le score IA et la valeur estimée dans un design Dark Theme. Le marqueur sélectionné est désormais visuellement identifié par une taille supérieure.

[2026-02-26] [PRO] Action : Optimisation de l'Expérience Mobile (Overlay & Navigation) → Résultat : (1) Correction de l'affichage de l'annonce sur mobile : elle s'affiche désormais en "Full-Screen Overlay" par-dessus la carte au lieu de la compresser, garantissant une lisibilité maximale. (2) Inversion de la logique de clic sur mobile : le premier clic sur un pin ouvre l'InfoWindow, le clic sur la bulle ouvre l'annonce complète.

[2026-02-26] [PRO] Action : Amélioration UX de la DealCard et de la Modale IA → Résultat : (1) Le bouton de ré-analyse est devenu un menu déroulant dynamique offrant les options "Scan Standard" et "Luthier Expert", géré par `useState` pour supporter le survol (PC) et le clic (Mobile). (2) Factorisation de la barre d'actions complète (Favori, Scan, Rejeter, Suppression, Facebook) pour l'injecter directement dans l'en-tête de la Modale d'Expertise IA, offrant une parité fonctionnelle totale entre les vues.

[2026-02-26] [PRO] Action : Correction UI Mobile du Menu des Verdicts (Mockup V2) → Résultat : Le composant `VerdictDropdown` s'écrasait et coupait le texte sélectionné sur les petits écrans. Application de `whitespace-nowrap` sur le bouton principal et définition d'une largeur fixe (`w-56`) avec `truncate` sur les options du menu déroulant dans `MockupDashboard.jsx` pour garantir un affichage propre sur une seule ligne.

[2026-02-26] [PRO] Action : Correction du Responsive Design et Résolution de la "Double Navbar" Mobile (Mockup V2) → Résultat : Le rendu mobile souffrait d'un overflow horizontal causé par la Navbar V1 qui restait active en arrière-plan avec une largeur minimale incompressible. (1) Désactivation conditionnelle de la Navbar V1 dans `App.jsx` lorsque le Mockup V2 est ouvert, éliminant la "bande blanche" sur mobile. (2) Refonte du container de recherche/filtres dans `MockupDashboard` en utilisant un layout `grid-cols-1 md:flex` pour forcer un empilement vertical propre des éléments (Recherche, Favoris, Vues, Bouton X) sur petits écrans. (3) Application de `whitespace-nowrap` sur l'indicateur de statut du bot dans `MockupNavbar` pour empêcher le texte de se casser sur deux lignes, et ajustement global des marges internes (padding) pour maximiser l'espace utile sur smartphone.

[2026-02-26] [PRO] Action : Résolution de l'erreur Greenlet (Cannot switch to a different thread) sur le backend → Résultat : L'implémentation de tâches de scraping en arrière-plan (ex: REFRESH, SCAN_URL) générait des crashs asynchrones car l'instance Playwright globale (`self.scraper`) du thread principal ne pouvait pas être partagée avec les threads secondaires. La solution a été de retirer le contexte Playwright global dans le bot (`bot.py`) et la boucle principale (`main.py`). Désormais, chaque action appelant le Scraper (comme `run_scan`, `scan_specific_url` ou `cleanup_sold_listings`) instancie son propre scraper temporaire (`temp_scraper = FacebookScraper()`) localement et le libère `finally: temp_scraper.close_session()`. Cette architecture garantit l'isolation absolue des navigateurs Chromium par thread.

[2026-02-25] [PRO] Action : Raffinement final de l'UI V2 (Modale IA, Barre de Filtres, Map Centering, Raccourci Favoris) → Résultat : (1) Restauration de la section "Analyse Détaillée" dans la Modale IA : Le Markdown complet (`aiAnalysis.analysis`) s'affiche maintenant correctement avec saut de ligne grâce à `whitespace-pre-wrap` au lieu de l'ancien `aiAnalysis.reasoning` tronqué. (2) Rapatriement du statut "Favoris" dans la V2 avec un double accès : option intégrée au sommet de `VerdictDropdown` + création d'un bouton fixe "Cœur" adjacent pour un accès ultra-rapide en un clic. (3) Dynamisme de la Carte : Intégration de la logique `fitBounds` dans `MapView.jsx` pour que la Google Map se centre et zoome automatiquement sur les annonces visibles selon les filtres actifs, avec une sécurité anti-zoom extrême pour les annonces solitaires.

[2026-02-25] [PRO] Action : Finalisation de l'UI/UX du Mockup V2 (Responsive, Modale IA, Barre de Filtres) → Résultat : (1) Modale IA Plein Écran : Le bloc d'expertise IA collapsible a été remplacé par une modale "glassmorphism" (`z-[100]`) permettant une lecture très confortable sur Desktop sans déformer la DealCard. (2) Nettoyage Dashboard : Le compteur de résultats et le bouton "Effacer tous les filtres" (maintenant stylisé en bouton carré dynamique rouge) ont été consolidés à l'intérieur de la barre de filtres principale. (3) Hauteur des cartes : Réduction de la hauteur des images de `400px` à `280px` pour afficher la carte entière sur les écrans de PC portables sans scroller. (4) Correction Navbar Mobile : Résolution du débordement horizontal (`overflow-x-hidden`) en contraignant la largeur de la toolbar.
[2026-02-25] [FLASH] Action : Intégration de la galerie ImageGallery et données réelles dans le Mockup V2 → Résultat : Remplacement du défilement horizontal basique par le composant robuste ImageGallery. Support natif du plein écran, des flèches de navigation et de l'affichage vertical intégral (object-contain). Extraction de véritables URLs Facebook depuis Firestore pour un rendu réaliste.

[2026-02-25] [PRO] Action : Finalisation Responsive et Logique Taxonomique Mockup V2 → Résultat : (1) Correction Mobile : Le status interactif du bot reste toujours visible sur `MockupNavbar` (points info annexes masqués), et ajout d'un bouton "Fermer" sur les DealCards en vue carte sur petit écran pour éviter les blocages. (2) Comptage Taxonomie : Mise à jour de `buildDealCounts` pour que chaque item `FAKE_DEALS` itère sur son chemin entier de `classification` (`ex: electrique.ampli.combo`) pour remplir parfaitement l'arbre à 4 niveaux. (3) UX : Retrait des choix multiples "Toutes" redondants dans les sous-niveaux de filtres. (4) Alignement du Dropdown de filtres sur les "Nouveaux Verdicts" V2 via `ALL_FILTERS_CONFIG`.

[2026-02-25] [PRO] Action : Raffinement UX approfondi du Mockup V2 → Résultat : (1) Tiroir de filtres : Transformation de `MockupFilterDrawer` en un accordéon imbriqué en cascade à 4 niveaux avec badges dynamiques de comptage d'annonces. (2) Barre d'actions (`MockupDashboard`) : Remplacement du défilement horizontal des verdicts par un composant `VerdictDropdown` compact. (3) Recherche : Ajout du filtrage interactif (text/location) avec bouton de réinitialisation interne. (4) Carte : Implémentation du mode "Split-Screen" (`MockupMapView`) et du bouton toggle Liste/Carte. (5) Contrôles UI (`MockupNavbar`) : Intégration de la véritable logique `BotControls` interactive au survol, et ajout des boutons d'actions manuelles (Vérification et Rescan) à la racine de la Toolbar. Le prototype Mockup V2 est achevé et valide toutes les recommandations heuristiques UX de l'analyse précédente.

[2026-02-25] [PRO] Action : Implémentation du filtre Drawer en cascade à 4 niveaux → Résultat : `MockupFilterDrawer.jsx` entièrement réécrit avec un arbre de taxonomie `TAXONOMY_TREE` à 4 niveaux de profondeur. Comportement : tous les groupes sont repliés par défaut (accordéon). Chaque niveau s'affiche et s'ouvre automatiquement dès qu'un choix est fait au niveau parent (Niveau 1 : Type d'instrument, Niveau 2 : Sous-catégorie contextuelle, Niveau 3 : Modèle/Type, Niveau 4 : Marque/Détail). La sélection d'un niveau parent réinitialise automatiquement tous les niveaux enfants. Le titre du groupe indique le contexte (ex : "Sous-catégorie · Électrique"). Les clés de filtres dans `MockupDashboard.jsx` ont été mises à jour (`level1/level2/level3/level4`). "Verdict IA" retiré du Drawer (couvert par les onglets rapides en haut de la grille).


[2026-02-25] [PRO] Action : Création du Mockup Complet UI V2 → Résultat : Prototype interactif Dark Mode complet accessible via le bouton "Mockup V2" dans la Navbar.
 Composants créés : `MockupDealCard.jsx` (image full-width, marge affichée, bloc IA collapsible, titres normalisés, hit-zones 44px), `MockupNavbar.jsx` (statuts système compacts, boutons Filtres et Paramètres, bouton quitter), `MockupFilterDrawer.jsx` (volet latéral coulissant avec 4 niveaux de filtres dynamiques et taxonomie en cascade — les sous-catégories s'adaptent automatiquement au type sélectionné, sans bouton Appliquer), `MockupDashboard.jsx` (assemblage complet : 8 fausses annonces, filtrage live via `useMemo`, onglets verdicts rapides, 3 sections Radar/Marché/Archives, bouton "Effacer les filtres"). Intégration du vrai `ConfigPanel` ouvert via le bouton ⚙️. Le `App.jsx` bascule entre l'interface réelle et le Mockup V2 via un `useState` sans modifier les données ni les hooks Firestore.

[2026-02-25] [PRO] Action : Extension de l'analyse UI/UX (Deep Heuristic Evaluation) → Résultat : Analyse des détails qualitatifs au-delà du simple layout.

[2026-02-25] [PRO] Action : Révision de l'analyse UI/UX suite aux retours utilisateurs → Résultat : Mise à jour de `docs/UI_UX_ANALYSIS.md` pour se concentrer sur les défauts structurels critiques : 1) Démantèlement du panneau latéral (Aside) qui gaspille 20% de la largeur. 2) Refonte des filtres horizontaux qui débordent en un "Drawer" latéral. 3) Correction de la DealCard Mobile pour forcer l'image en pleine largeur (`w-full`). 4) Nettoyage des boutons d'action (remplacement des textes par des icônes comme FB). Le `TODO.md` a été réécrit avec ces nouvelles priorités absolues.

[2026-02-25] [PRO] Action : Analyse approfondie de l'UI/UX et ajout de `docs/UI_UX_ANALYSIS.md` → Résultat : Validation de la structure d'interface actuelle (Dashboard SaaS, code couleur sémantique). Définition de 4 axes prioritaires documentés dans le TODO pour un design Premium : Dark Mode, Micro-interactions visuelles, Refonte par "Tiroir" de la taxonomie des filtres, Intégration d'un panneau de statistiques.

[2026-02-25] [PRO] Action : Implémentation du stockage pérenne des images via Firebase Storage → Résultat : Les URLs CDN de Facebook expirent après 1-3 jours, rendant les images des annonces archivées inaccessibles. (Action 1) Init du bucket Storage dans `backend/database.py` : passage du `storageBucket` à `firebase_admin.initialize_app()` et exposition de `self.bucket`. (Action 2) Ajout de `FIREBASE_STORAGE_BUCKET` et `IMAGE_RETENTION_REJECTED_DAYS` (30j) dans `config.py`. (Action 3) Le `FirestoreRepository` passe le bucket aux méthodes `upload_images_to_storage()` (upload + URL publique) et `purge_rejected_images()` (purge lifecycle). (Action 4) Le bot (`bot.py`) uploade systematiquement les images avant de sauvegarder chaque annonce et expose `purge_rejected_images()` pour le scheduler. (Action 5) Le frontend (`DealCard.jsx`) utilise `storageImageUrls || imageUrls` comme fallback. (Action 6) Création du script one-shot `backend/scripts/migrate_images.py` pour migrer les annonces existantes (test validité URL, re-scraping si expirée, upload Storage). (Action 7) Branchement de la purge lifecycle au `TaskScheduler` (`services.py`) via `purge_func=` — job hebdomadaire automatique. (Action 8) Correction du dry-run du script de migration : Playwright ne se lançait pas inutilement, seulement un HTTP HEAD pour tester la validité des URLs. (Action 9) Ajout de `run.bat` et du workflow `.agent/workflows/run-venv.md` pour forcer l'usage du venv.

[2026-02-24] [FLASH] Action : Ajout de la taxonomie aux annonces rejetées par le Portier → Résultat : Les annonces immédiatement rejetées (BAD_DEAL, REJECTED_ITEM) ne possédaient pas de champ `classification`, empêchant leur filtrage par type dans l'UI. (Action 1) Modification de `gatekeeper_verbosity_instruction` dans `prompts.json` pour exiger la classification dans le JSON de sortie du Portier (Tier 1). (Action 2) Mise à jour de `backend/analyzer.py` pour extraire cette classification et l'inclure dans le payload de retour lors du coupe-circuit. Ce correctif affine l'expérience utilisateur lors de l'exploration des archives rejetées.

[2026-02-24] [PRO] Action : Simplification de la taxonomie des accessoires et durcissement des rejets → Résultat : L'IA laissait passer les pédales et les supports de guitare en les amalgamant sous la clé racine `accessoire_etui`. (Action 1) Renommage de la clé racine de la taxonomie `accessoire_etui` en `etui_housse` et suppression du niveau imbriqué `protection` pour aplatir la structure. (Action 2) Modification stricte du prompt du Portier (Tier 1) et du prompt principal pour ordonner le rejet immédiat (`REJECTED_ITEM`) de tout accessoire n'étant pas un étui rigide ou une housse (ex: pédales, supports, ficelles, micros).

[2026-02-24] [PRO] Action : Correction de la profondeur de filtrage et de la justification des rejets (Frontend) → Résultat : (Bug 1) Le filtre de taxonomie (FilterBar) n'affichait que 3 niveaux, empêchant la sélection des feuilles (ex: `Parlor`) suite à l'ajout des catégories racines (`guitare`, `ampli`, etc.). Ajout d'un 4ème niveau `level4Filter` dans `useDealsManager.js` et `FilterBar.jsx` pour restaurer la granularité complète. (Bug 2) Les annonces rejetées par l'Intelligence Artificielle restaient affichées avec le statut trompeur "Analyse en cours...". Modification de `DealCard.jsx` pour afficher la justification réelle (`deal.aiAnalysis.reasoning`) ou une phrase de rejet par défaut.



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
    - **Cause de l'invisibilité :** Le frontend (`matchesVerdictFilter`) masque totalement les documents ayant un statut global `rejected`. Dans la nomenclature v2, le "bruit" est classé `REJECTED_ITEM` avec un statut global `analyzed`, ce qui les rend comptabilisable dans l'UI alors que la v1 les annihilait visuellement.
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
    - Mise à jour de `docs/ARCHITECTURE.MD` pour refléter la situation réelle des flux de commandes.

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

#### ✅ Objectif : Passer d'un système "Tout-Guitare"- [x] Bugfix: Taxonomy Count Collision (hierarchical paths).
  - [x] Round 1: Code Audit (Path normalization & aggregation).
  - [x] Round 2: Data Mapping Verification (Multi-parent nodes).
  - [x] Round 3: UI/Filter Interaction Sync.
- **Nouveaux Produits** : Intégration des `amplificateurs` (Lampes, Transistors, Modélisation) et des `accessoires_etuis` (Rigides, Housses souples).
- **Persona Luthier** : Mise à jour des prompts pour évaluer les amplis (état des lampes, transformateurs) et valoriser l'apport financier des housses/étuis pour le flipping.
- **Synchronisation Full-Stack** : Mise à jour de `config.py` et `useDealsManager.js` pour supporter dynamiquement la nouvelle structure.

#### 🤔 Raisonnement

- L'expansion permet de capturer des opportunités de "Fast Flip" (ex: Boss Katana) et de maximiser la valeur des packs guitare+étui.
- Le maintien du persona **Maître Luthier** assure une analyse technique rigoureuse, même sur des objets non-luthier classiques comme les amplis numériques.

---

[2026-02-26] [FLASH] Action effectuée → Migration complète vers l'UI V2, suppression de l'obsolescence V1 et validation du build de production.

### Session 36 : Activation Définitive de la V2 & Nettoyage V1

#### ✅ Objectif : Remplacer l'ancienne UI par la nouvelle interface SaaS V2.

- **Standardisation des Composants** : Renommage massif des composants `Mockup*` en noms de production (`Dashboard`, `Navbar`, `DealCard`, `FilterDrawer`, `StatsView`).
- **Simplification de `App.jsx`** : Suppression de toute la logique de bascule V1/V2. L'application monte désormais directement le `Dashboard` V2.
- **Suppression de la Dette Technique** : Élimination des fichiers V1 obsolètes (`FilterBar.jsx`, `SectionGroup.jsx`, `DealModal.jsx`, `BotControls.jsx`, `DebugStatus.jsx`).
- **Validation** : Build Vite (`npm run build`) validé avec succès (0 erreur d'import).

#### 🤔 Raisonnement

- La V2 est jugée supérieure en termes d'ergonomie (Filtres en tiroir, Stats intégrées, Map Split-screen) et d'esthétique (Dark Mode).
- Supprimer les fichiers obsolètes évite toute confusion future et allège le bundle final.
- La transition "Production Ready" marque la fin de la phase de prototypage de la nouvelle interface.

---

[2026-02-26] [FLASH] Action effectuée → Polissage UI : Verrouillage du scroll global et correction du clipping dans la Navbar.

### Session 39 : Polissage de l'Expérience Utilisateur

#### ✅ Objectif : Supprimer les artefacts visuels résiduels pour une expérience "Produit" parfaite.

- **Désactivation du Scroll Corps** : Ajout de `overflow: hidden` sur `html, body, #root` dans `index.css` pour forcer l'utilisation des conteneurs internes et supprimer la barre de défilement du navigateur.
- **Correction du Menu Statut** : Retrait de `overflow-x-hidden` sur la `Navbar` pour permettre au menu de survol (status controls) de s'afficher sans être tronqué.
- **Z-Index & Layers** : Vérification de la superposition des éléments interactifs pour un rendu "floating" optimal.

#### 🤔 Raisonnement

- Le Dashboard V2 est conçu pour être une interface fixe (SPA). La présence d'une scrollbar native sur le côté droit nuisait à l'aspect premium et cassait l'alignement visuel.
- La Navbar doit être capable de déborder (overflow visible) pour ses menus contextuels, tout en restant `sticky`.

---

[2026-02-26] [FLASH] Action effectuée → Bugfix ConfigPanel : Suppression d'un double `return` et de blocs syntaxiques redondants bloquant le build Vite.

### Session 40 : Correction Syntaxique Critique

- **Correction `ExclusionKeywordsSection`** : Suppression du code dupliqué par erreur lors du précédent push. Le composant `ConfigPanel.jsx` est désormais syntaxiquement correct.
- **Vérification** : Le build Vite ne doit plus lever l'erreur `The character "}" is not valid inside a JSX element`.

---
