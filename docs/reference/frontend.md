# Frontend — application web React (référence)

> Vérifié le 2026-11-06 contre le commit `48d8784` : `index.html`, `main.jsx`, `src/` (75 fichiers `.js`/`.jsx`, environ 760 Ko), `package.json`, `storage.rules`. Relues en détail : `App.jsx`, les quatre contextes, `useAuth.js`, `apiService.js` (client REST/WebSocket, index des annonces), `firebase.js`, `storageService.js`, `indexCache.js`, `indexDelta.js`, le début de `useDealsManager.js` et de `useDealChat.js`, `useBotConfig.js`, `useFicheRoute.js`. Les gros composants d'affichage (`StatsView`, `DealCard/*`, `Dashboard`, `ConfigPanel`, `MapView`, `HelpOverlay`) ont été **parcourus par recherche ciblée, pas relus ligne à ligne**. L'inventaire mécanique (exports, importeurs, tests) a été relevé par un agent Haiku (voir `revue/2026-frontend.md`). Les routes appelées sont décrites dans `api.md`.

## Rôle

Application d'une seule page (React 18, Vite 5, Tailwind 3, Recharts, `@dnd-kit` pour le glisser-déposer, `react-markdown` pour les fiches) publiée sur GitHub Pages (`https://LudovicLebart.github.io/GuitarHunter/`). Elle liste et filtre les annonces, affiche leur analyse, pilote le bot (commandes, réglages), tient le plan de restauration et converse avec un modèle sur une annonce. Elle n'accède plus à Firestore.

## Démarrage et navigation
- Point d'entrée : `index.html` → `/main.jsx` → `src/App.jsx`.
- **Pas de routeur.** Trois mécanismes : `?shareId=<id>` (page publique d'une annonce partagée, rendue **avant** toute authentification) ; `#fiches` et `#fiche/<slug>` (page des fiches, après connexion, chargée à la demande ; `useFicheRoute` écoute `hashchange`) ; sinon le `Dashboard`.
- Dans le `Dashboard`, un état `viewMode` choisit la vue : `LIST` (cartes), `MAP` (carte), `STATS` (statistiques et explorateur de corrélations).
- Arborescence des fournisseurs : `AuthProvider` → `BotConfigProvider` → `DealsProvider` → `CitiesProvider` → `AppContent` (écran de chargement, `LoginPage` si non connecté, bandeau d'erreur global).

## Organisation du code (`src/`)

| Dossier | Contenu |
|---|---|
| `services/` | `apiService.js` (client de l'API : `apiFetch` avec jeton, délai de 20 s, WebSocket reconnectables, flux SSE), `firebase.js` (Auth, Storage, App Check, Firebase AI Logic), `storageService.js` (envoi de photos), `geminiChatService.js` (contexte, outils et validation du chat ; nom hérité, sert aussi à Claude), `claudeChatService.js` (adaptateur vers `POST /deals/{id}/chat/claude`) |
| `context/` | `AuthContext`, `BotConfigContext`, `DealsContext`, `CitiesContext` : exposent les hooks du même nom |
| `hooks/` | `useAuth`, `useBotConfig` (configuration, commandes du bot), `useDealsManager` (index, filtres, tri, sélection, actions), `useDealChat` (chat par annonce), `useRestorationPlan`, `useCities`, `useCitySuggestions` (Photon/OpenStreetMap), `useFichesCatalog`, `useFicheRoute` |
| `components/` | `Dashboard`, `Navbar`, `LoginPage`, `ConfigPanel`, `StatsView`, `DealsExplorer`, `MapView`, `FilterDrawer`, `LogViewer`, `AdminDashboard`, `FichesPage`, `SharedDealPage`, `HelpOverlay`, `TaxonomyTreePicker`, `ImageGallery`, `SimpleMarkdown`… ; `DealCard/` : carte, actions, modale d'analyse, panneau de chat, panneau du plan de restauration, éditeur de classification |
| `utils/` | fonctions pures (testées avec `node --test`) : cache et fusion de l'index (`indexCache`, `indexDelta`, `indexColumnar`, `retryBackoff`), `taxonomy` et `cities` (miroirs de `backend/taxonomy.py` et `backend/cities.py`), `fiches`, `fichesLookup`, `claudeChat`, `claudeSession`, `chatReply`, `dealContext`, `geo` |
| `constants.js`, `constants/restorationPlan.js` | verdicts (`NEW_VERDICTS`, `LEGACY_VERDICTS`, `ARCHIVE_GROUP`), catégories et statuts du plan |

## Authentification (`useAuth`, `firebase.js`)
Firebase Auth (e-mail et mot de passe : connexion, **inscription**, réinitialisation). À chaque changement d'état : lecture du claim `admin` (protection d'affichage seulement, la vraie est côté API), puis `POST /users/me` (`ensureUser`) pour que le bot découvre le compte. La déconnexion vide le cache IndexedDB de l'index. Firebase fournit aussi **Storage** (photos), **App Check** (reCAPTCHA Enterprise, activé seulement si `VITE_RECAPTCHA_SITE_KEY` est défini) et **Firebase AI Logic** (Gemini appelé directement depuis le navigateur).

## Chargement et mise à jour de la liste (`apiService.js::onDealsIndexUpdate`)
1. Affichage provisoire depuis **IndexedDB** (`indexCache.js`, base `guitarhunter-cache`, valable 7 jours, propre à l'utilisateur et à la forme des objets, empreinte de `dealFromRow`).
2. Première lecture **complète** : `GET /deals/index?format=columnar` (ETag : un 304 est rejoué par le navigateur). Décodage colonnaire puis `dealFromRow`.
3. WebSocket `/ws/deals` : chaque `{id}` reçu est regroupé pendant 300 ms puis lu avec `?ids=` (**lecture incrémentale**, 50 ids au plus) et fusionné ; `{"type":"bulk"}`, reconnexion, retour au premier plan après plus de 30 s d'absence, échec, ou plus de 50 ids → relecture complète. Relecture complète de sécurité toutes les **10 minutes** (page visible) car les suppressions et les frais de restauration ne notifient pas.
4. Une lecture à la fois, une seule en attente ; échec : nouvelle tentative avec attente croissante (jusqu'à 10 échecs consécutifs, pas de relance sur une erreur 4xx hors 408 et 429, premier échec silencieux).
5. Les documents complets (images, raisonnement) sont chargés à la demande par `POST /deals/by-ids` pour les annonces visibles (`useDealsManager`, 30 cartes puis 50 par défilement).

Les filtres, le tri et la recherche texte se font **côté navigateur** sur l'index complet en mémoire ; la recherche texte normalise sans accents ni ponctuation. Les préférences de filtres sont sauvegardées dans la configuration utilisateur (`uiFilters`).

## Chat d'annonce (`useDealChat`, `geminiChatService`, `claudeChatService`)
- Modèle par défaut : `claude-sonnet-5-5` (`DEFAULT_CHAT_MODEL`, réglage `analysisConfig.chatModel`) ; un nom `claude-*` passe par l'API (SSE), sinon Gemini est appelé directement depuis le navigateur par Firebase AI Logic.
- L'historique est lu et écrit par l'API (`/deals/{id}/chat`) et rafraîchi par WebSocket. Le contexte de l'annonce (texte, photos, plan de restauration, fiches utiles) n'est joint que tant que l'historique rejouable ne le contient pas déjà (`historyHasDealContext`).
- Outils déclarés côté navigateur, exécutés par lui : proposition d'étape de restauration (`validateRestorationStepProposal`, `fiche_slug` seulement parmi les fiches fournies au modèle), réorganisation, rappel d'une photo élidée, requalification de l'annonce (`validateDealRequalificationProposal`) ; consultation d'Opus (`consultOpus`).
- Photos de l'annonce remplacées à l'écriture par des références courtes et stables (hachage du chemin) pour ne pas dépasser la taille des messages ; élision des anciennes photos à la relecture de l'historique.
- Chaque tour Gemini poste son usage à `POST /usage` ; les tours Claude sont enregistrés par le serveur.
- Les fiches techniques utiles sont cherchées par `POST /deals/{id}/fiches/search` avec un délai maximal de 2,5 s et un disjoncteur (`fichesLookup`) : le chat répond même si la recherche est lente.

## Photos et fiches
Envoi de photos directement vers **Firebase Storage** (`deals/{dealId}/chat_*` ou `restoration_*`, JPEG, `getDownloadURL`), puis l'URL est enregistrée par l'API (galerie de l'annonce, étape du plan). Fiches : catalogue gardé 5 minutes en mémoire et rattaché à l'utilisateur (`useFichesCatalog`), page `FichesPage` (Markdown, table des matières, panneau d'historique replié), liens depuis les étapes du plan.

## Villes
`useCities` lit `GET /cities` et suit le WebSocket `/ws/cities`. L'ajout d'une ville passe par la commande `ADD_CITY` (le bot interroge Facebook). Suggestions de saisie : **Photon** (`photon.komoot.io`, OpenStreetMap), appelé depuis le navigateur — le texte tapé part vers ce service tiers.

## Configuration et commandes (`useBotConfig`)
Lit la configuration (`GET /users/me/config`, WebSocket `/ws/users/me/config`) et l'écrit par `PATCH` (clés en notation pointée dépliées). Réglages exposés par `ConfigPanel` : `scanConfig` (requête, prix, nombre d'annonces, fréquence, rayon, sources Facebook et Kijiji), modèles (`gatekeeperModel`, `mainModel`, `expertModel`, `chatModel`), `mainAnalysisPrompt`, `gatekeeperVerbosityInstruction`, `rejectionVerdicts`, mots-clés d'exclusion (`ConfigPanel`) ; la Recherche Active (`activeSearchFamilies`) se règle dans le `FilterDrawer`. Commandes envoyées (les onze types du bot, un `addCommand` chacun) : `REFRESH`, `CLEANUP`, `REANALYZE_ALL`, `REEVALUATE_NOT_PROMOTED`, `SCAN_URL`, `ADD_CITY`, `ANALYZE_DEAL`, `CLEAR_LOGS`, `STOP_BOT`, `START_BOT`, `STOP_SCAN`. `prompts.json` est **importé dans le bundle** pour fournir les valeurs par défaut.

## Administration
`AdminDashboard` (visible si le claim `admin` est présent) : liste des utilisateurs, pause, fréquence, suppression, coût du chat (`/admin/*`).

## Variables d'environnement du build
`VITE_API_BASE_URL` (défaut `http://localhost:8000`), `VITE_FIREBASE_*` (clé, domaine, projet, bucket, expéditeur, application, mesure), `VITE_RECAPTCHA_SITE_KEY` (facultative). Le déploiement écrit `.env` depuis le secret `DOT_ENV` avant `npm run build` (voir section 9).

## Pièges et invariants
- `useAuth()` est un **hook à état local, pas un singleton** : il est appelé directement dans plusieurs composants (constat R-7-1).
- Les identifiants du dossier de l'annonce côté Storage sont ceux de l'annonce Facebook, communs à tous les utilisateurs.
- Le cache IndexedDB n'est qu'un affichage provisoire : la première lecture réseau est toujours complète.
- Les fonctions de `apiService.js` gardent des signatures héritées de Firestore (paramètres `_chunkId`, `_userId` inutilisés) pour ne pas toucher aux appelants.
- Tout ajout d'une dépendance aux données de taxonomie ou de villes doit rester aligné avec les miroirs Python (`parity.test.js`).

## Tests
`npm test` (`node --test`) : 11 fichiers de test dans `src/utils/` (cache, delta, colonnaire, relance, chat, fiches, parité Python↔JavaScript…). Aucun test de composant ni de hook. Mesuré le 2026-11-06 : les 11 fichiers de `src/` passent (67 tests). `npm run lint` est **inutilisable** : ESLint 8 ne trouve aucun fichier de configuration (ni `.eslintrc*`, ni `eslint.config.*`, ni clé `eslintConfig`), donc la commande échoue avant d'analyser quoi que ce soit (constat R-7-10).
