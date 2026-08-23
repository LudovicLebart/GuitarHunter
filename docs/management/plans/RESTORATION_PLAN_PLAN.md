# 🚦 AIGUILLAGE ET PLAN D'ACTION

- **Périmètre :** une fois une annonce marquée "Achetée", permettre de construire et faire évoluer dans le temps, via la conversation existante avec Gemini, un **plan de restauration structuré** (checklist d'étapes de réparation/finition avant revente), avec un chiffrage par étape (estimé et réel) et un impact sur la marge de revente projetée.
- **Modèle Requis :** PRO (nouveau modèle de données Firestore, nouveau hook + composant, extension du chat existant, function calling Gemini au Lot B).
- **Le Plan :** livré en **2 lots séquencés avec validation intermédiaire obligatoire** (même convention que Galerie/Requalification).

---

## Contexte

Le chat "Discuter avec Gemini" existe déjà par annonce (`DealChatPanel.jsx`/`useDealChat.js`/`geminiChatService.js`, Firebase AI Logic 100% client-side, historique persisté `guitar_deals/{dealId}/chat/{msgId}`). Une fonctionnalité "Acheté" existe aussi déjà (`deal.isPurchased`/`purchasePrice`/`purchasedAt`). Il n'existe en revanche aucune notion de plan de restauration : ni champ Firestore dédié, ni UI, ni précédent de liste structurée éditable (le seul précédent de "champ dédié qui prime sur l'IA" est `manualClassification`, mais c'est une valeur unique, pas une checklist).

**Décisions produit déjà validées avec l'utilisateur** (AskUserQuestion) :
1. Évolution du plan via le chat en mode **proposition + validation** (carte Appliquer/Ignorer), jamais d'écriture silencieuse.
2. **Panneau/onglet dédié** dans la modale d'analyse, pas seulement des bulles de chat.
3. Réservé aux annonces **`isPurchased === true`**.
4. Chaque étape porte un **coût optionnel**, agrégé en un impact sur la marge.

**Deux revues critiques indépendantes effectuées avant tout code**, sur le même principe que la revue ayant déjà façonné le plan Galerie/Requalification :
- **Revue de fiabilité (Opus)** : 18 problèmes concrets trouvés sur le brouillon initial (races d'ids périmés, tours Gemini à texte vide, écritures `undefined` sur Firestore, ambiguïté de la formule de marge, etc.) — tous corrigés ci-dessous.
- **Revue produit/workflow (Fable)**, demandée explicitement par l'utilisateur en complément — pas une chasse aux bugs mais "qu'est-ce qui rendrait ce workflow réellement utile pour quelqu'un debout devant sa guitare". 6 propositions, toutes retenues avec la répartition de lot que la revue elle-même recommande :
  - **Lot A** : statut `waiting` dans l'enum, `actualCost`/`completedAt` par étape, bouton "Demander conseil" (pont panneau → chat).
  - **Lot B** : contexte du plan injecté enrichi (statuts/coûts/totaux, pas juste des libellés), bouton "Faire le point", prompt "Préparer l'annonce de revente".
  - **Question ouverte tranchée avec l'utilisateur** : la marge doit s'ancrer sur `resale_potential` (valeur *après* restauration, déjà produite par le pipeline IA — `prompts.json`) plutôt que sur `estimated_value` (valeur *en l'état actuel*), qui sous-estimait structurellement la marge en soustrayant les coûts de travaux d'une valeur d'avant-travaux.

---

## LOT A — Modèle de données + panneau manuel

### Modèle de données
Nouvelle **sous-collection** `guitar_deals/{dealId}/restorationPlan/{itemId}` (jamais un champ sur le document `deal`, ni dans `aiAnalysis` — les deux chemins d'écriture backend qui remplacent des documents/champs entiers, `.set(data)` sans merge sur le deal complet et `.update()` qui remplace tout `aiAnalysis`, ne touchent jamais une sous-collection : rien ne peut donc écraser silencieusement le plan de restauration) :
- `label` (string, obligatoire)
- `category` (enum fermé : `structurel`/`cosmetique`/`electronique`/`quincaillerie`/`reglage`/`autre` — même convention que `finish_application`/`finish_texture`)
- `status` (enum fermé, **figé avant toute première écriture** — l'élargir après coup obligerait à faire cohabiter la validation Lot B avec des données déjà persistées sur l'ancien enum) : `pending` / `waiting` / `in_progress` / `done` / `skipped`. `waiting` couvre l'état réel le plus fréquent d'une restauration multi-semaines — pièce commandée, rendez-vous luthier pris, colle qui sèche — distinct de `pending` (rien d'engagé) et `in_progress` (rien de faisable aujourd'hui). Le motif d'attente (chez qui, depuis quand) va dans `notes`, pas de champ dédié.
- `estimatedCost` (number, **omis** si absent — jamais `undefined`, jamais 0 par défaut, qui fausserait le total)
- `actualCost` (number, optionnel, saisi quand le statut passe à `done` — le devis change une fois le luthier consulté, la pièce coûte rarement exactement le prix estimé ; sans coût réel la marge reste une fiction d'avant-travaux)
- `completedAt` : posé automatiquement (code dédié dans `updateRestorationItem`, pas un champ générique du formulaire) au moment où `status` passe à `done`, et effacé symétriquement dès que le statut en ressort — `updatedAt` seul ne suffit pas, une note éditée ensuite l'écraserait
- `notes` (string, optionnel)
- `source` (`'user'` pour l'ajout manuel — `'ai'` pour une étape appliquée depuis une proposition Lot B)
- `createdAt` : **`new Date()`, pas `serverTimestamp()`** — le chat utilise déjà ce choix précisément parce que `orderBy('createdAt')` + `serverTimestamp()` non résolu localement (compensation de latence) ferait apparaître un item tout juste ajouté au mauvais endroit puis sauter une fois le serveur confirmé. `updatedAt` peut rester `serverTimestamp()` (rien ne trie dessus).
- `proposedByMessageId` (optionnel, Lot B) : id du message de chat à l'origine de l'étape, quand `source: 'ai'`.
- **Note pour un futur lot, à consigner mais pas à construire maintenant** : le jour où une photo par étape sera voulue, la bonne implémentation est un simple champ `photoUrls` référençant des URLs déjà dans `storageImageUrls` (le chemin photo → Storage → galerie existe déjà en entier via le chat) — pas un nouveau pipeline d'upload à rebâtir.

**Totaux, sémantique figée** :
- `totalEstimatedCost` = somme des `estimatedCost` de tous les items **sauf `skipped`**.
- `remainingCost` = somme des `estimatedCost` des items `pending` + `waiting` + `in_progress` (tout ce qui n'est ni `done` ni `skipped`).
- `spentCost` ("dépensé à date") = somme, pour les items `done`, de `actualCost ?? estimatedCost`.
- `deleteItem` (suppression définitive) et passage en statut `skipped` sont deux gestes distincts dans l'UI — l'un retire l'item, l'autre le garde visible mais hors chiffrage actif.

**Aucune règle Firestore à ajouter** : `artifacts/{appId}/users/{userId}/{document=**}` (`firebase/firestore.rules`) couvre déjà toute sous-collection sous un deal, exactement comme `chat` aujourd'hui.

**Aucun changement `deals_index`/`useDealsManager.js`** dans ce lot — le différer est réellement gratuit (pas juste reporté) : le jour où un filtre/stat sur l'état de restauration est voulu, une clé indexée dotted-path pourra s'ajouter sans migration, sur le même modèle que `manualClassification`/`mc`. Un tableau de bord multi-restaurations (toutes les annonces en cours de restauration) n'est pas construit dans ce lot non plus — le filtre `PURCHASED` déjà existant (`Dashboard.jsx`) suffit à les retrouver.

**Limites connues, assumées et documentées, pas de correctif prévu** :
- La sous-collection ne suit pas le cycle de vie du deal : `deleteDeal` ne supprime que le document parent, et une annonce supprimée puis re-scannée sous le même ID Facebook ressuscite l'ancien plan (même limite déjà vraie pour `chat`, mais rendue plus visible ici par les montants en jeu).
- Aucune migration multi-compte (`migrateOldDataToNewUser` ne copie que les documents deal, pas les sous-collections) — même limite que le chat.
- Le backend (ré-analyse, `analyze_single_deal`) ne voit jamais le plan de restauration — aucun impact sur le pipeline IA existant.
- Pas de réordonnancement des étapes ; pas de photo par étape (voir note ci-dessus pour le chemin d'implémentation futur).

### Service (`src/services/firestoreService.js`)
- `getRestorationPlanCollectionRef(dealId, userId)` (privée, miroir de `getDealChatCollectionRef`).
- `onRestorationPlanUpdate(dealId, onUpdate, onError, userId)` : `onSnapshot` trié `orderBy('createdAt', 'asc')`, miroir exact de `onDealChatUpdate`.
- `addRestorationItem(dealId, userId, { label, category, estimatedCost, notes, source, proposedByMessageId })` : `addDoc`, retourne l'id créé (nécessaire au Lot B pour rattacher `itemId` au marquage Appliquer/Ignorer).
- `updateRestorationItem(dealId, userId, itemId, patch)` : `updateDoc` **champ par champ** sur ce qui a changé uniquement (jamais l'objet entier depuis l'état du formulaire).
- `deleteRestorationItem(dealId, userId, itemId)`.

### Hook (`src/hooks/useRestorationPlan.js`)
- Monté **dans `DealAnalysisModal.jsx`** (pas dans le panneau lui-même) — divergence assumée par rapport à `useDealChat` (qui vit dans `DealChatPanel.jsx` car rien d'autre n'a besoin des messages) : la puce de résumé a besoin du plan même quand le panneau est fermé, et le Lot B en a besoin dans `sendMessage`.
- Actif uniquement si `deal?.id && user && deal.isPurchased`.
- Retourne `{ items, loading, error, addItem, updateItem, deleteItem, totals }`.

### UI (`src/components/DealCard/RestorationPlanPanel.jsx`)
- Header avec bouton retour (miroir du header de `DealChatPanel.jsx`).
- Barre de résumé : étapes terminées, coût total estimé, dépensé à date, reste à payer, et **"Marge nette projetée après restauration"** = `(resale_potential ?? estimated_value) − (purchasePrice ?? price) − totalEstimatedCost`, formule affichée en clair.
- Liste des items, formulaire d'ajout manuel, édition en mode formulaire local (jamais de champ contrôlé en continu depuis le snapshot — évite le vol de curseur).
- Bouton **"Demander conseil"** par étape → bascule sur la vue chat avec un brouillon pré-rempli.

### Point d'entrée (`DealAnalysisModal.jsx`)
- **Pas de 5ᵉ bouton dans la rangée d'actions** du header (viendrait recréer l'encombrement tout juste corrigé). À la place : puce cliquable "Restauration X/Y" ajoutée au bloc "Achetée" déjà affiché conditionnellement dans la rangée financière.
- `showChat` (booléen) généralisé en `activeView` (`'analysis' | 'chat' | 'restoration'`).
- Vues alternatives gardées montées (`hidden`) pour préserver le brouillon de chat en jonglant entre les vues — mais le chat n'est monté (listener Firestore + session Gemini ouverts) qu'à sa première ouverture, jamais dès l'ouverture de la modale.
- `activeView` retombe sur `'analysis'` si "Acheté" est décoché pendant que le panneau de restauration est ouvert.

---

## LOT B — Propositions IA via function calling

**Simplifié par rapport au brouillon initial, sur recommandation explicite de la revue de fiabilité** : uniquement `propose_restoration_step` (ajout d'une nouvelle étape). La fonction de mise à jour d'un item existant par `item_id` est **retirée du périmètre** (id périmés jamais nettoyables une fois rejoués dans l'historique, risque d'écraser une édition manuelle faite entre-temps dans le panneau) — l'utilisateur modifie/supprime toujours lui-même dans le panneau.

Points de fiabilité :
- `tools` gaté sur `deal.isPurchased`, session rebâtie si ce statut change en cours de conversation (`dealRef` toujours à jour lu par le listener Firestore, pas le `deal` fermé dans l'effet).
- Jamais de tour function-call sans texte persisté : `functionCalls()` lu avant `.text()`, une `functionResponse` factice renvoyée dans la même session pour obtenir un vrai texte de suite.
- Une `functionResponse` par `functionCall` du tour (l'API l'exige), même au-delà de 5 appels — seul l'**affichage** des propositions est plafonné à 5, jamais la réponse à l'API.
- État Appliquer/Ignorer persisté sur le message (`restorationProposalStates`, dot-notation).
- Repli sans `tools` si le modèle configuré ne supporte pas le function calling (le rejet arrive à l'envoi, pas à la construction du modèle).
- Validation stricte avant affichage (pas seulement avant application) : catégorie/coût/libellé.

Enrichissements produit (revue Fable) :
- Contexte du plan (statuts/coûts/totaux) injecté à chaque tour tant que le plan n'est pas vide, pas seulement au premier message.
- Bouton "Faire le point" et prompt "Préparer l'annonce de revente" — prompts prédéfinis envoyés comme un message normal, aucune infra function-calling supplémentaire.

---

## Vérification

**Lot A** (testable sans aucun accès Gemini) :
1. `npm run build` après chaque étape.
2. Marquer une annonce "Achetée" → puce "Restauration" → panneau s'ouvre.
3. Ajouter/modifier/supprimer une étape, cycler les statuts → totaux et marge se recalculent correctement, `completedAt` posé/effacé au bon moment.
4. "Demander conseil" → bascule en chat avec brouillon pré-rempli.
5. Décocher "Acheté" pendant que le panneau est ouvert → retour automatique sur l'analyse, pas d'écran vide.
6. Annonce non achetée : aucune trace de la fonctionnalité.

**Lot B** (non testable en conditions réelles depuis cet environnement — pas d'accès Gemini/Firebase) :
1. Défaut concret argumenté dans le chat → carte de proposition, jamais d'écriture silencieuse.
2. Conversation banale → aucune proposition spontanée.
3. Appliquer/Ignorer → effet durable, persisté, pas de doublon après reload.
4. "Faire le point"/"Préparer l'annonce" → réponse cohérente, pas perdue si un envoi était déjà en cours.
5. Bascule Acheté/non-Acheté en cours de conversation → tools réapparaissent/disparaissent au message suivant.
6. Modèle sans support function calling → repli sans `tools`, chat toujours utilisable.

---

## Statut

✅ **Lot A et Lot B implémentés, poussés sur `dev` et validés en conditions réelles par l'utilisateur** (2026-08-22). Revue de fiabilité (Opus) et revue produit/workflow (Fable) effectuées avant code ; 2 passes `/code-review` locales après implémentation ont trouvé 9 bugs, tous corrigés (voir `JOURNAL.md`).

✅ **Extension (2026-08-22, demande utilisateur après validation)** : réorganisation des étapes par glisser-déposer (`@dnd-kit`, champ `order` avec rattrapage silencieux) + photos par étape (`photoUrls`, upload direct ou sélection dans la galerie existante) + visionneuse plein écran partagée avec la galerie principale (`ImageLightbox`, extrait de `ImageGallery.jsx`) + swipe tactile. **Non testé en conditions réelles**, notamment le comportement tactile (drag-and-drop, swipe) sur un vrai appareil mobile — à valider par l'utilisateur.
