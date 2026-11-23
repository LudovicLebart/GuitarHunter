# Constats de revue — section 7 : frontend

Relevés le 2026-11-06 pendant la passe « deepdocument » (commit `48d8784`). Rien n'a été corrigé. Format : voir [README](README.md). Limite : les gros composants d'affichage n'ont pas été relus ligne à ligne ; les constats ci-dessous viennent des fichiers lus en entier et de recherches ciblées dans tout `src/`.

### R-7-1 — `useAuth()` est instancié dans neuf endroits : neuf abonnements, neuf `POST /users/me` par ouverture
- Où : `src/hooks/useAuth.js` (hook à état local), appelé directement par `App.jsx:18`, `Navbar.jsx:28`, `ConfigPanel.jsx:448`, `StatsView.jsx:89`, `LogViewer.jsx:8`, `DealAnalysisModal.jsx:51`, `DealChatPanel.jsx:272`, `DealsContext.jsx:9`, et `AuthContext.jsx:7` ; seul `LoginPage` passe par `useAuthContext`.
- Catégorie : performance / simplification · Gravité : moyenne
- Constat : chaque instance s'abonne à `onAuthStateChanged`, lit les claims et appelle `ensureUser()` (`POST /users/me`). À chaque chargement de page, l'API reçoit donc au moins neuf appels identiques et le serveur de test comme celui de production résolvent neuf fois le même jeton. Les états d'authentification des instances peuvent aussi différer momentanément.
- Piste : n'utiliser que `useAuthContext` ; appeler `ensureUser` une seule fois dans le fournisseur.

### R-7-2 — Les réglages de l'Expert et de l'Analyste ne sont pas modifiables, et l'interface écrit une clé que le backend ne lit pas
- Où : `src/hooks/useBotConfig.js:30, 56, 109, 201, 219` (clé `expertContextInstruction`, lue dans `prompts.json` sous `expert_context_instruction`, qui n'existe pas) ; `backend/analyzer.py:773` et `backend/bot.py:194` (clé `expertProContextInstruction`, `prompts.json:348` `expert_pro_context_instruction`).
- Catégorie : bug / doc-code · Gravité : basse à moyenne
- Constat : (1) la valeur par défaut côté interface est une liste vide, (2) elle est enregistrée sous une clé morte, (3) « réinitialiser aux valeurs par défaut » écrit cette clé morte. L'instruction de l'Analyste (`analystVerbosityInstruction`) n'apparaît nulle part dans `src/`. `ConfigPanel` n'édite que `mainAnalysisPrompt`, `gatekeeperVerbosityInstruction`, `rejectionVerdicts` et les quatre modèles. La doc et `CLAUDE.md` laissent croire que tous les prompts se modifient dans l'application.
- Piste : aligner les noms de clés, ou retirer les champs inutiles ; préciser ce qui est éditable.

### R-7-3 — Fichier mort de 24 Ko
- Où : `src/components/MapView.orig.jsx` (aucune référence dans le dépôt).
- Catégorie : code-mort · Gravité : basse
- Piste : supprimer (l'historique Git le garde).

### R-7-4 — Les règles de Firebase Storage laissent n'importe quel compte déposer des images, sans quota
- Où : `storage.rules` (`allow create` pour tout utilisateur authentifié sur `deals/{dealId}/(chat|restoration)_*`, 5 Mo, images ; `allow read: if true`).
- Catégorie : sécurité / coût · Gravité : moyenne (avec l'inscription ouverte, voir R-6-1 et suivants)
- Constat : `dealId` n'est pas cloisonné par utilisateur (risque accepté dans le commentaire du fichier) ; rien ne limite le nombre de fichiers. Le stockage et le trafic sont facturés au projet. La lecture est publique pour tous les chemins de photos. Le commentaire du fichier décrit encore un modèle Firestore (« seul `storageImageUrls` de SON document… ») qui n'existe plus.
- Piste : quota par utilisateur (par exemple via une fonction), ou passage des dépôts par l'API.

### R-7-5 — Le chat Gemini du navigateur dépend d'App Check, facultatif
- Où : `src/services/firebase.js:22-42` (`VITE_RECAPTCHA_SITE_KEY` absente = App Check désactivé), `geminiChatService.js`.
- Catégorie : sécurité / coût · Gravité : moyenne (à confirmer : la clé est-elle dans le secret `DOT_ENV` de production ?)
- Constat : sans App Check, Firebase AI Logic peut être appelé avec la clé publique du site par un tiers, au quota du projet. Le chat sur Claude, lui, passe par le serveur.
- Piste : vérifier la présence de la clé dans le build de production ; sinon l'activer.

### R-7-6 — `npm test` exécute aussi les tests des paquets installés dans `venv/`
- Où : `package.json` (`"test": "node --test"`, sans dossier cible).
- Catégorie : test · Gravité : basse
- Constat (mesuré le 2026-11-06) : en local, la commande a traversé `venv\Lib\site-packages\playwright\…` : 68 « tests » dont 1 en échec (un fichier du pilote Playwright), en 48 s. En CI il n'y a pas de `venv`, donc le défaut ne s'y voit pas, mais le résultat local est rouge à tort.
- Piste : `node --test src/`.

### R-7-7 — Reliquats de Firestore dans l'API du client
- Où : `apiService.js` (paramètres `_chunkId` et `_userId` inutilisés dans `rejectDeal`, `deleteDeal`, `onDealsIndexUpdate`…, `unflatten` « copié de `firestoreService.js` », commentaires de tête) ; `storageService.js` et `useRestorationPlan.js` (commentaires sur des sous-collections Firestore).
- Catégorie : simplification / doc-code · Gravité : basse
- Piste : retirer les paramètres inutilisés et les commentaires périmés lors d'un prochain passage sur le fichier (52 Ko).

### R-7-8 — Données saisies envoyées à un service tiers, et URL par défaut locale
- Où : `useCitySuggestions.js` (chaque saisie de ville part vers `photon.komoot.io`, choix documenté dans le fichier) ; `apiService.js:66` (`VITE_API_BASE_URL` absente = `http://localhost:8000`).
- Catégorie : confidentialité / robustesse · Gravité : basse
- Constat : le premier point est un choix assumé, à garder en tête pour une politique de confidentialité. Le second fait échouer en silence un build sans variable (le navigateur bloque l'appel d'une page HTTPS vers du HTTP local).
- Piste : échouer à la construction si la variable manque.

### R-7-10 — `npm run lint` ne fonctionne pas : aucune configuration ESLint
- Où : `package.json` (`"lint": "eslint . --ext js,jsx --report-unused-disable-directives --max-warnings 0"`, plugins `react`, `react-hooks`, `react-refresh` installés), racine du dépôt (aucun `.eslintrc*`, `eslint.config.*`, ni clé `eslintConfig`).
- Catégorie : outillage · Gravité : basse à moyenne
- Constat (mesuré par l'agent d'inventaire, code de sortie 2, recoupé par `ls`) : ESLint 8.57 quitte avant toute analyse. Le lint n'a donc jamais protégé le code (variables inutilisées, règles des hooks React) ; le script et trois plugins sont des reliques. Le lint n'est pas dans le job `tests` de `deploy.yml` non plus.
- Piste : ajouter une configuration (règles recommandées + `react-hooks`) et corriger les avertissements existants avant de l'activer en CI.

### R-7-9 — Aucun test de composant ni de hook
- Où : 11 fichiers de test, tous dans `src/utils/`.
- Catégorie : test-manquant · Gravité : basse à moyenne
- Constat : `useDealChat` (72 Ko), `useDealsManager` (38 Ko), `StatsView` (53 Ko) et `apiService` (52 Ko) concentrent la logique et n'ont pas de test propre, sauf les utilitaires purs qu'ils appellent.
- Piste : extraire la logique en fonctions pures testables (déjà fait pour l'index et les fiches).
