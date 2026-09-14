# Plan d'Implémentation : Galerie via Chat Gemini + Requalification d'Annonce

**Objectif :** étendre le chat "Discuter avec Gemini" existant sur une annonce avec deux capacités : (1) ajouter une photo envoyée dans le chat à la galerie de l'annonce, (2) permettre à Gemini de proposer une requalification (verdict, scores, specs) suite à la conversation, avec validation utilisateur avant application.

**Modèle IA Recommandé pour l'exécution :** PRO (refactoring multi-fichiers frontend, nouvelle logique Storage côté client + function calling Gemini).

**Livraison : deux lots séquencés**, avec validation utilisateur entre les deux (Lot 1 galerie d'abord, Lot 2 requalification ensuite) — pas un bloc monolithique.

---

## 0. Contexte

Le chat existe déjà (`DealChatPanel.jsx` / `useDealChat.js` / `geminiChatService.js`), 100% client-side via Firebase AI Logic (`firebase/ai`), persistance dans `guitar_deals/{dealId}/chat/{msgId}`. Il permet déjà de joindre une photo au message, mais celle-ci n'est envoyée qu'en base64 inline à Gemini — jamais uploadée ni ajoutée à `storageImageUrls` (le champ lu par la galerie). Aucun mécanisme n'existe pour que Gemini modifie le contenu d'une annonce depuis le chat.

## 1. Revue critique (confrontation Opus) — pourquoi l'architecture de la requalification a changé

Une première version du plan prévoyait un champ dédié `chatRequalification` + mirroring dans l'index léger (`deals_index/{chunk}.deals.{dealId}.cq.*`) + un helper `getEffectiveAnalysis(deal)` câblé sur ~7 sites de lecture. Une revue contradictoire (modèle Opus, avant tout code) a trouvé plusieurs problèmes bloquants :

- **`StatsView.jsx`** (lignes ~103-109) fusionne aussi `loadedDeals` sur le doc complet — la 1ère version du plan le déclarait à tort "sans changement nécessaire" ; en pratique la requalification aurait été écrasée dès qu'une annonce est ouverte (bug intermittent, dépendant du cache de session).
- **`interestScore`** (pastille de score, tri "par intérêt") est précalculé côté backend (`entry.is`) et prime toujours sur l'`aiAnalysis` fusionné (opérateur `??` dans `useDealsManager.js`) — jamais recalculé après requalification, donc deux scores différents affichés pour la même annonce au même endroit.
- **Aucune validation de plage/énumération** n'était prévue avant "Appliquer" : un verdict halluciné par Gemini (le prompt backend contient lui-même un exemple `"verdict": "VALUE"`, hors énumération) aurait fait basculer l'annonce dans l'onglet "Erreurs", sans aucun moyen de revenir en arrière.
- Le correctif envisagé pour l'alias `analysis || reasoning` (dupliquer `reasoning` vers `chatRequalification.analysis`) était une erreur : `analysis` (rapport Tier 3 complet) et `reasoning` (résumé court) sont deux champs distincts, pas un alias — l'appliquer aurait écrasé le rapport d'expertise complet par une phrase de chat.

**Décision retenue :** au lieu de ce sous-système parallèle, le bouton "Appliquer" (Lot 2) déclenche `retryDealAnalysis(dealId, userId, userComment)` — chemin **déjà existant et en production** (`analyzer.py::analyze_deal(..., user_comment=...)` injecte le commentaire dans le prompt de ré-analyse). Conséquence : zéro nouveau champ Firestore, zéro clé d'index, zéro site de lecture à corriger ; la canonicalisation/validation de la taxonomie reste gérée côté backend (`_canonicalize_classification`). Contrepartie assumée : l'application n'est plus littérale (le backend peut interpréter différemment la correction) et devient asynchrone (dépend du bot actif).

Points de la revue qui restent applicables quelle que soit l'architecture, donc conservés :
- `getDownloadURL()` obligatoire après upload Storage — jamais reconstruire une URL `storage.googleapis.com` à la main (l'ACL `publicRead` posée par `make_public()` côté backend n'existe pas sur un upload SDK Web).
- Règles Storage restrictives (pas `write: if auth != null` — le chemin `deals/{dealId}/...` n'est pas cloisonné par utilisateur, `dealId` étant l'ID de l'annonce marketplace, potentiellement partagé entre utilisateurs qui scannent la même annonce).
- Garde anti-double-clic sur "Ajouter à la galerie".
- Fermeture propre du tour de function calling (Lot 2) — ne jamais persister une part texte vide dans l'historique rejoué.
- Consigne système explicite limitant l'appel de la fonction Gemini aux cas de désaccord factuel réel + fallback si le modèle configuré ne supporte pas le function calling.

---

## 2. Lot 1 — Galerie (photo du chat → galerie de l'annonce)

### Upload Storage côté client (nouveau — aucun précédent dans `src/`)
- `src/services/firebase.js` : exporter `storage` (`getStorage(app)`).
- Nouveau `src/services/storageService.js` : `base64ToBlob(data, mimeType)`, `uploadChatPhotoToDealStorage(dealId, blob, mimeType)` → upload vers `deals/{dealId}/chat_{timestamp}_{uuid8}.jpg`, retourne l'URL via `getDownloadURL(ref)`.
- `storage.rules` : remplacer le `deny` global par une règle scoping `deals/{dealId}/{fileName}` — lecture publique, **création** authentifiée uniquement (`fileName.matches('chat_.*')`, taille < 5 Mo, `contentType` image), `update`/`delete` interdits côté client. Déploiement requis (`firebase deploy --only storage`) après validation. Aucune règle Firestore à modifier.

### UI
- `DealChatPanel.jsx` (`ChatBubble`) : bouton "Ajouter à la galerie" sur les bulles avec `attachedImage` uniquement. États idle → upload (bouton désactivé) → "Ajoutée ✓" (persisté via `addedToGalleryUrl` sur le message).
- `useDealChat.js` : `addPhotoToGallery(message)` orchestrant upload + `addImageToDealGallery` (nouveau, `arrayUnion` sur `storageImageUrls`) + `markChatMessageAddedToGallery`.
- `useDealsManager.js` : `handleGalleryImageAdded(dealId, url)` (patch optimiste de `loadedDeals`, même pattern que `handleSetClassification`), threadé `Dashboard.jsx` → `DealCard` → `DealAnalysisModal` → `DealChatPanel`.

### Limite connue (documentée, pas corrigée dans ce lot)
`analyze_single_deal` (backend) construit `listing_data` à partir des `imageUrls` Facebook d'origine, jamais de `storageImageUrls` — une photo ajoutée via le chat n'est donc jamais vue par une ré-analyse ultérieure (elle reste dans la galerie et la conversation, mais pas dans le contexte d'analyse backend).

---

## 3. Lot 2 — Requalification via chat (après validation du Lot 1)

### Function calling Gemini
- `geminiChatService.js` : fonction `propose_deal_requalification` (Schema `firebase/ai`) — champs : `verdict, deal_score, authenticity_score, condition_score, liquidity_score, restoration_interest_score, brand, model_name, production_year, country_of_origin, color, finish_application, finish_texture, neck_scale_length` + `justification` (texte, sert uniquement à construire le commentaire envoyé au backend). Exclus : `classification` (géré par `manualClassification`), `reasoning`/`analysis` (rapport Tier 3, jamais touché depuis le chat), `model_used`, `tier3_trigger`, `estimated_value`, `estimated_gross_margin`, `summary`.
- `tools: [...]` sur `getGenerativeModel(...)`, avec fallback sans `tools` si le modèle configuré ne le supporte pas (pas de régression du chat existant).
- `SYSTEM_INSTRUCTION` : n'appeler la fonction qu'en cas de désaccord factuel réel, jamais spontanément.

### Fermeture propre du tour de function call
`useDealChat.js` : sur détection d'un `functionCall`, renvoyer un `functionResponse` factice dans la même session pour obtenir un vrai texte de Gemini avant de persister (jamais de part texte vide dans l'historique Firestore rejoué — risque de rejet définitif de la conversation par l'API sinon).

### Carte de proposition et application
- Nouveau `RequalificationProposalCard.jsx` : avant/après (uniquement les champs qui diffèrent) + justification, boutons Appliquer/Annuler.
- **Appliquer** : formatte la proposition en texte français et appelle `retryDealAnalysis(dealId, userId, texte)` (fonction existante) — action asynchrone, pas une écriture directe.
- **Annuler** : marque le message `proposedRequalificationStatus: 'dismissed'`, aucun impact sur l'annonce.
- Après application, résumé du changement préfixé au prochain message utilisateur (pas un tour orphelin, supprimé sinon par `sanitizeHistory`), pour que Gemini ne re-propose pas la même correction plus tard dans le fil.

---

## 4. Vérification

**Lot 1 :** déploiement des règles Storage avant test ; upload → apparition immédiate dans la galerie puis après reload ; double-clic → une seule image ; URL accessible sans 403 y compris sur `SharedDealPage` déconnecté ; upload > 5 Mo ou non-image rejeté par les règles.

**Lot 2 :** proposition cohérente sur désaccord factuel argumenté ; pas de proposition sur conversation banale ; Annuler sans effet sur l'annonce ; Appliquer déclenche bien une commande `ANALYZE_DEAL` avec le bon commentaire et le résultat final reflète la correction demandée ; réponse function-call pure (sans texte) ne produit pas de bulle vide ; fallback correct si le modèle ne supporte pas `tools`.

---

## Statut

📋 Plan validé par l'utilisateur (revu et corrigé après confrontation Opus) — 2026-08-21.
✅ Lot 1 (galerie) codé le 2026-08-21, validé en conditions réelles.
✅ Lot 2 (requalification) codé le 2026-08-27, validé en conditions réelles le 2026-08-27 — voir JOURNAL.md.
🔁 Mécanisme d'application revu le 2026-08-27 (2e confrontation Opus, suite au retour utilisateur "ça a pris du temps" + correction non suivie du premier coup) : "Appliquer" ne déclenche plus `retryDealAnalysis` (§3 ci-dessus, devenu obsolète) mais patche directement `aiAnalysis` — voir JOURNAL.md et `docs/reference/ARCHITECTURE.md`.
