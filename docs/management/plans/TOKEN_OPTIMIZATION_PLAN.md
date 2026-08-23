# Plan — Optimisation IA : tokens, persona luthier, pages narratives

## Contexte

Déclenché par une demande de réduction de la consommation de tokens du chat Gemini (coût API). Un premier correctif ponctuel (consigne de concision) a été proposé, mais l'utilisateur a demandé une réflexion stratégique complète avant tout code, avec deux idées complémentaires en plus de l'optimisation pure :
- **Persona IA "luthier/vendeur référent"** dans le contexte restauration/préparation à la vente.
- **Pages narratives "histoire de la guitare"** (achat, étapes de restauration, erreurs/corrections, vente finale), à terme pour un usage interne ET public (extension du partage existant, `SharedDealPage.jsx`/`shared_deals`).

Deux revues indépendantes ont été menées avant tout plan détaillé :
- **Fable** (stratégie produit/séquencement) — a identifié le vrai poste de coût dominant : les photos jointes sont rejouées intégralement à l'API à **chaque tour** de conversation (`useDealChat.js::sanitizeHistory` rejoue les `parts` Firestore, `inlineData` compris).
- **Opus** (faisabilité technique, sur le mécanisme d'élision + rappel de photos) — a tranché une incertitude API centrale et trouvé plusieurs bugs réels, détaillés ci-dessous.

Trois plans séquencés en résultent, à validation séparée (convention du projet) : **Plan 1 (tokens) → Plan 2 (persona) → Plan 3 (histoire)**.

---

## Plan 1 — Réduction de la consommation de tokens (en cours)

### Verdict technique central (revue Opus, tranché par lecture du SDK `@firebase/ai` installé)

Envoyer dans un même appel `chat.sendMessage()` un tableau mêlant une part `functionResponse` et des parts `inlineData` (photos) est **impossible** : le SDK lève `AIError(INVALID_CONTENT)` avant tout appel réseau (`assignRoleToPartsAndValidateSendMessageRequest`), car il doit dériver un rôle unique par message et les deux types de part imposent des rôles différents (`function` vs `user`). **Piège** : cette erreur tombe dans le `catch` existant de `sendMessage()` et désactive silencieusement les tools pour toute la session (symptôme trompeur : "Gemini ne propose plus rien"), donc cette approche est écartée définitivement.

**Alternative retenue ("Alternative C")** : quand le modèle appelle une fonction de rappel photo, on **abandonne** la réponse en cours, on reconstruit une session fraîche depuis l'historique d'AVANT ce tour (`sanitizeHistory(messages)`), et on renvoie le même tour utilisateur augmenté des photos demandées comme un `Content` `role: user` normal. Réutilise exactement le mécanisme déjà en prod pour le repli "modèle sans support function calling" (`useDealChat.js:191-196`) — pas de nouveau pattern à inventer. Coût : 2 générations au lieu d'1 quand un rappel a lieu (jamais 3).

### Bugs réels trouvés en cours de revue (à corriger indépendamment de l'élision)

1. **`toolsUnsupportedRef` collant sur n'importe quelle erreur** (`useDealChat.js:186-199`) : une simple erreur réseau/503 pendant un tour désactive le function calling **définitivement** pour la session (jamais remis à `false`), sans signal. Aujourd'hui une dégradation discrète ; devient critique avec le rappel de photos (modèle rendu aveugle sur tout l'historique). À corriger : ne poser le flag que sur une erreur diagnostiquable comme "tools non supportés" ; sinon repli non collant (ce tour seulement).
2. **Limite Firestore 1 MiB par document, probablement déjà frôlée** : le premier message persiste `parts` avec toutes les photos de l'annonce en base64 (`useDealChat.js:174`) — 8-10 photos × 1024px/JPEG 80% ≈ 1,1 à 2,6 Mo, contre 1 048 576 octets de limite dure. **À vérifier en premier** (avant tout le reste) sur une vraie annonce à beaucoup de photos. Si confirmé : ne plus persister les `inlineData` des photos d'annonce dans le premier message (reconstructibles depuis `storageImageUrls`) — corrige le bug ET réduit le coût Firestore, s'articule avec le schéma de refs ci-dessous.

### Conception retenue pour l'élision + le rappel

- **Schéma de refs** (deux familles, préfixées pour ne jamais se confondre avec les refs du plan de restauration) :
  - Photo d'annonce : `d-<hash6>` — hash court (FNV-1a base36) du **pathname** de l'URL Storage, **jamais un index de position** dans `storageImageUrls` (ce tableau est réécrit intégralement côté backend — un index périmé résoudrait silencieusement vers la mauvaise photo, un hash périmé échoue proprement).
  - Photo jointe au chat : `c-<messageId6>-<partIndex>` — le `partIndex` reste stable car l'élision remplace **en place** (voir ci-dessous), jamais en retirant une part.
  - Un seul résolveur `buildPhotoRefIndex(deal, messages)` / `resolvePhotoRefs(refs, index)`, réutilisé à la fois pour poser les refs dans les placeholders d'élision et pour résoudre un appel du modèle — même discipline que `resolveRestorationReorderProposal`.
- **Élision non-mutante** : `sanitizeHistory` pousse `parts` par référence, réutilisés par `DealChatPanel`/`addPhotoToGallery` pour l'affichage et la galerie — une élision qui muterait en place casserait les vignettes existantes. La fonction d'élision doit produire des objets/tableaux neufs, et remplacer une part `inlineData` par une part `text` **au même index** (jamais retirer une part).
- **Budget en nombre d'images, pas en nombre de tours**, granularité tour entier : `MAX_HISTORY_IMAGES = 6`, on parcourt l'historique de la fin vers le début, on garde les tours-image jusqu'à épuisement du budget. Le tour courant n'est jamais élidé ; toujours garder au moins le tour-image le plus récent même s'il dépasse le budget seul.
- **Élision active seulement si le rappel est réellement disponible** (`elision ⇔ capacité de rappel`) — si le repli sans tools s'est déclenché, reconstruire l'historique SANS élision (coût repayé, mais le modèle n'est jamais aveugle).
- **Pas de liste globale de refs réinjectée à chaque tour** — chaque ref voyage dans le placeholder, à la place exacte de la photo élidée dans l'historique (~25 tokens au lieu de 500-1000), avec un rappel court de la règle dans l'addendum système.
- **Fonction `request_photo_review`** : `photo_refs: string[]`, `reason: string`. Plafonds : `MAX_RECALLED_PHOTOS_PER_TURN = 3` (tronqué au-delà, signalé dans le texte) ; `MAX_PHOTO_RECALL_ROUNDS_PER_TURN = 1` (cap dur anti-ping-pong — un 2e rappel dans le tour rejoué bascule sur un `functionResponse` d'erreur classique plutôt qu'un 2e rejeu, borne absolue à 2 générations) ; garde anti-appel redondant si toutes les refs demandées sont déjà dans le tour courant (pas de rejeu, notamment au premier message).
- **Refs hallucinés** : toutes invalides → pas de rejeu, `functionResponse` d'erreur explicite ; partiellement valides → rejeu avec les valides, manquantes signalées dans le texte du tour rejoué ; ref valide mais irrécupérable (fetch KO) → traitée comme manquante, jamais avalée silencieusement (le modèle doit savoir qu'il ne l'a pas eue).
- **Découplage de `isPurchased`** : `request_photo_review` doit être disponible pour TOUTE conversation (l'essentiel du gain d'élision est hors annonces achetées), donc `getDealChatModel` compose deux jeux de tools indépendants ; `chatToolsRef` cesse d'être un booléen et devient une signature (`'none' | 'photo' | 'photo+resto'`) comparée avant chaque envoi.
- **Rappel persisté** : un champ `photoRecall: { refs, missing }` sur le message model créé après un rejeu, pour que l'élision suivante distingue "jamais revue" de "déjà réexaminée au tour N" dans son placeholder — sinon le modèle peut redemander la même photo à chaque tour et annuler le gain. Bonus UI : puce "🔍 Photo réexaminée" sous la bulle concernée.
- **Photos d'annonce au premier message — différé en phase 2** : le plus gros gain restant (n'envoyer que 2-3 photos d'ouverture + refs pour le reste), mais aussi le changement le plus perceptible. À arbitrer avec des chiffres réels (voir instrumentation), pas à l'intuition — devient prioritaire si la limite Firestore du point 2 est confirmée.

### Lots

- **Lot A** *(trivial, prêt à coder)* : consigne de concision par défaut dans `SYSTEM_INSTRUCTION`, `generationConfig.maxOutputTokens` en filet de sécurité.
- **Lot B** *(diagnostic + correctifs indépendants)* : vérifier la taille réelle des documents de premier message sur une annonce à beaucoup de photos (limite Firestore 1 MiB) et corriger si confirmé ; corriger `toolsUnsupportedRef` collant ; instrumentation temporaire `result.response.usageMetadata` (log `promptTokenCount`/`cachedContentTokenCount`) pour mesurer le vrai gain avant/après plutôt que de le supposer (le caching implicite de Gemini sur les préfixes stables peut réduire le bénéfice réel de l'élision).
- **Lot C** : infrastructure de refs (`buildPhotoRefIndex`/`resolvePhotoRefs`) + élision non-mutante enrobant `sanitizeHistory` (fonction séparée, `sanitizeHistory` elle-même inchangée).
- **Lot D** : fonction `request_photo_review` (Alternative C : session fraîche rejouée), plafonds, gestion des refs hallucinés, découplage de `isPurchased`, persistance `photoRecall` + puce UI. **Lots C et D doivent sortir ensemble** (élision sans rappel = régression de capacité, rappel sans élision = rien à rappeler).
- **Lot E** *(différé, phase 2)* : chargement paresseux des photos d'annonce au premier message — uniquement après mesure des gains réels du Lot B/C/D et confirmation/infirmation de la limite Firestore.

---

## Plan 2 — Persona "luthier / vendeur référent" (backlog, après Plan 1)

Pas de nouvelle surface : étendre `RESTORATION_SYSTEM_INSTRUCTION_ADDENDUM` (déjà conditionné par `isPurchased` dans `getDealChatModel`) en un vrai bloc d'identité/posture — luthier-restaurateur expérimenté ET revendeur qui connaît le marché de l'occasion, pense marge/prix de revente en continu (`purchasePrice` + coûts du plan déjà dans le contexte). Proactivité par la posture (une suggestion courte en fin de réponse) et par extension du pattern de boutons de prompts prédéfinis déjà validé ("Faire le point"/"Préparer l'annonce de revente" → ajouter p. ex. "Conseil d'atelier sur l'étape en cours"), jamais par des tours spontanés (coût + contraire à la philosophie "jamais d'écriture silencieuse" du projet). Risque quasi nul sur l'existant (aucun changement de plomberie, les consignes tools sont conservées telles quelles dans le nouveau bloc).

## Plan 3 — Pages "histoire de la guitare" (backlog, après Plan 1 et 2)

Sous-collection `guitar_deals/{dealId}/story/{chapterId}` — le narratif est un **artefact dérivé et régénérable**, jamais la source de vérité (les faits restent dans `purchasePrice`/`purchasedAt`, les items du plan de restauration, le chat). Génération **incrémentale par chapitre** (jamais une régénération complète), déclenchement explicite (bouton "Ajouter un chapitre" dans le panneau restauration), modèle bas coût. Chapitre éditable par l'utilisateur — **un chapitre édité n'est jamais régénéré automatiquement** (décision validée avec l'utilisateur), même philosophie proposition/validation que le reste du projet. Publication = extension du snapshot `shared_deals` déjà existant (pas de système parallèle), avec un flag par chapitre pour distinguer journal privé / page de vente publique — point de design à retrancher en détail avec l'utilisateur avant de planifier ce lot. Prévu en 2-3 lots : (A) génération/édition privée, (B) publication dans `SharedDealPage.jsx`, (C, plus tard) chapitre "annonce de revente" branché sur le bouton existant.
