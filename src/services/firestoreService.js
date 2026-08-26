import {
  doc, setDoc, deleteField, onSnapshot, getDoc, getDocs,
  collection, updateDoc, addDoc, deleteDoc, getFirestore, writeBatch,
  query, orderBy, limit, where, documentId, serverTimestamp, arrayUnion, arrayRemove
} from 'firebase/firestore';
import { db } from './firebase';

const APP_ID = import.meta.env.VITE_APP_ID_TARGET;

// --- Helper: Unflatten dot notation to nested objects ---
const unflatten = (data) => {
  if (Object(data) !== data || Array.isArray(data)) return data;
  const result = {};
  for (const p in data) {
    let cur = result, prop = "", parts = p.split(".");
    for (let i = 0; i < parts.length; i++) {
      let idx = !isNaN(parseInt(parts[i]));
      cur = cur[prop] || (cur[prop] = (idx ? [] : {}));
      prop = parts[i];
    }
    cur[prop] = data[p];
  }
  return result[""] || result;
};

// --- Annonces partagées publiquement (sans auth) ---

export const createSharedDeal = async (deal) => {
  const ref = doc(db, 'shared_deals', deal.id);
  const ai = deal.aiAnalysis || {};
  
  const scores = {
    price_score: ai.price_score ?? null,
    condition_score: ai.condition_score ?? null,
    rareness_score: ai.rareness_score ?? null,
    demand_score: ai.demand_score ?? null,
    margin_score: ai.margin_score ?? null,
  };

  await setDoc(ref, {
    title: deal.title || null,
    price: deal.price || null,
    location: deal.location || null,
    link: deal.link || null,
    description: deal.description || null,
    storageImageUrls: deal.storageImageUrls || [],
    imageUrls: deal.imageUrls || [],
    verdict: ai.verdict || deal.verdict || null,
    scores: scores,
    analysis: ai.reasoning || ai.analysis || deal.analysis || null,
    tier3_summary: deal.tier3_summary || null,
    sharedAt: new Date().toISOString(),
  });
};

export const getSharedDeal = async (dealId) => {
  const ref = doc(db, 'shared_deals', dealId);
  const snap = await getDoc(ref);
  return snap.exists() ? snap.data() : null;
};

// Catalogue de villes partagé (indépendant du userId)
const getSharedCitiesRef = () => {
  if (!APP_ID) throw new Error('firestoreService: APP_ID manquant.');
  return collection(db, 'artifacts', APP_ID, 'cities');
};

// --- Factory : crée les références Firestore pour un userId donné ---
const getRefs = (userId) => {
  if (!APP_ID || !userId) {
    throw new Error(`firestoreService: APP_ID ou userId manquant. APP_ID=${APP_ID}, userId=${userId}`);
  }
  const userDocRef = doc(db, 'artifacts', APP_ID, 'users', userId);
  return {
    userDocRef,
    dealsCollectionRef: collection(db, 'artifacts', APP_ID, 'users', userId, 'guitar_deals'),
    // Préférences de villes par user : docId = Facebook city ID, contient isScannable
    userCitiesPrefsRef: collection(db, 'artifacts', APP_ID, 'users', userId, 'cities'),
    commandsCollectionRef: collection(db, 'artifacts', APP_ID, 'users', userId, 'commands'),
  };
};

// --- Bot Configuration ---

export const updateUserConfig = async (newConfig, userId) => {
  try {
    const { userDocRef } = getRefs(userId);
    const hasDotNotation = Object.keys(newConfig).some(k => k.includes('.'));
    if (hasDotNotation) {
      await updateDoc(userDocRef, newConfig);
    } else {
      const expandedConfig = unflatten(newConfig);
      await setDoc(userDocRef, expandedConfig, { merge: true });
    }
    console.log("Config saved successfully.");
  } catch (error) {
    console.error("Error updating user config:", error);
    throw new Error("Erreur de sauvegarde de la configuration.");
  }
};

export const onBotConfigUpdate = (onUpdate, onError, userId) => {
  const { userDocRef } = getRefs(userId);
  return onSnapshot(userDocRef, (docSnap) => {
    if (docSnap.exists()) {
      onUpdate(docSnap.data());
    } else {
      console.warn("User document not found in Firestore.");
      onError({ message: "Dossier Python introuvable" });
    }
  }, (error) => {
    console.error("Error listening to bot config:", error);
    onError(error);
  });
};

// --- Commands ---

const addCommand = async (type, payload, userId) => {
  try {
    const { commandsCollectionRef } = getRefs(userId);
    const docRef = await addDoc(commandsCollectionRef, {
      type,
      payload,
      status: 'pending',
      createdAt: new Date()
    });
    console.log(`Command ${type} added with ID: ${docRef.id}.`);
    return docRef;
  } catch (error) {
    console.error(`Error adding command ${type}:`, error);
    throw new Error("Erreur lors de l'envoi de la commande.");
  }
};

export const triggerManualRefresh = (userId) => addCommand('REFRESH', null, userId);
export const triggerManualCleanup = (userId) => addCommand('CLEANUP', null, userId);
export const triggerRelaunchAll = (userId) => addCommand('REANALYZE_ALL', null, userId);
export const triggerScanSpecificUrl = (url, userId) => addCommand('SCAN_URL', url, userId);
export const resetBotConfigToDefaults = (defaults, userId) => updateUserConfig(defaults, userId);
export const triggerStopBot = (userId) => addCommand('STOP_BOT', null, userId);
export const triggerStopScan = (userId) => addCommand('STOP_SCAN', null, userId);
export const triggerStartBot = (userId) => addCommand('START_BOT', null, userId);
export const requestClearLogs = (userId) => addCommand('CLEAR_LOGS', null, userId);

export const onCommandUpdate = (commandId, callback, userId) => {
  const { commandsCollectionRef } = getRefs(userId);
  const commandDocRef = doc(commandsCollectionRef, commandId);
  return onSnapshot(commandDocRef, (docSnap) => {
    if (docSnap.exists()) callback(docSnap.data());
  }, (error) => {
    console.error(`Error listening to command ${commandId}:`, error);
  });
};

// --- Deals ---

export const onDealsIndexUpdate = (onUpdate, onError, userId) => {
  try {
    const { userDocRef } = getRefs(userId);
    const dealsIndexCollectionRef = collection(userDocRef, 'deals_index');
    
    return onSnapshot(dealsIndexCollectionRef, (snapshot) => {
      let mergedDeals = {};
      snapshot.docs.forEach(docSnap => {
        const data = docSnap.data();
        if (data && data.deals) {
          Object.assign(mergedDeals, data.deals);
        }
      });
      onUpdate(mergedDeals, Object.keys(mergedDeals).length);
    }, (error) => {
      console.error("Error listening to deals index:", error);
      onError(error);
    });
  } catch (error) {
    onError(error);
  }
};

export const fetchDealsByIds = async (ids, userId) => {
  if (!ids || ids.length === 0) return [];
  const { dealsCollectionRef } = getRefs(userId);
  
  // Split ids into chunks of 30 because Firestore 'in' query is limited to 30 keys
  const chunks = [];
  for (let i = 0; i < ids.length; i += 30) {
    chunks.push(ids.slice(i, i + 30));
  }
  
  try {
    const promises = chunks.map(chunk => {
      const q = query(dealsCollectionRef, where(documentId(), 'in', chunk));
      return getDocs(q);
    });
    
    const snapshots = await Promise.all(promises);
    const deals = [];
    snapshots.forEach(snapshot => {
      snapshot.docs.forEach(d => {
        deals.push({ id: d.id, ...d.data() });
      });
    });
    return deals;
  } catch (error) {
    console.error("Error fetching deals by IDs:", error);
    throw error;
  }
};

const getDealDocRef = (dealId, userId) => {
  const { dealsCollectionRef } = getRefs(userId);
  return doc(dealsCollectionRef, dealId);
};

export const rejectDeal = async (dealId, chunkId, userId) => {
  try {
    const { dealsCollectionRef, userDocRef } = getRefs(userId);
    await updateDoc(doc(dealsCollectionRef, dealId), {
      status: 'rejected',
      'aiAnalysis.verdict': 'REJECTED'
    });
    if (chunkId) {
      const indexDocRef = doc(userDocRef, 'deals_index', chunkId);
      await updateDoc(indexDocRef, {
        [`deals.${dealId}.s`]: 'rejected',
        [`deals.${dealId}.v`]: 'REJECTED'
      });
    }
  } catch (error) {
    console.error(`Error rejecting deal ${dealId}:`, error);
    throw new Error("Erreur lors du rejet de l'annonce.");
  }
};

export const deleteDeal = async (dealId, chunkId, userId) => {
  try {
    const { dealsCollectionRef, userDocRef } = getRefs(userId);
    await deleteDoc(doc(dealsCollectionRef, dealId));
    if (chunkId) {
      const indexDocRef = doc(userDocRef, 'deals_index', chunkId);
      await updateDoc(indexDocRef, {
        [`deals.${dealId}`]: deleteField()
      });
    }
  } catch (error) {
    console.error(`Error deleting deal ${dealId}:`, error);
    throw new Error("Erreur lors de la suppression de l'annonce.");
  }
};

export const retryDealAnalysis = (dealId, userId, userComment = '') =>
  addCommand('ANALYZE_DEAL', { dealId, forceExpert: false, userComment }, userId);

export const forceExpertAnalysis = (dealId, userId, userComment = '') =>
  addCommand('ANALYZE_DEAL', { dealId, forceExpert: true, userComment }, userId);

export const toggleDealFavorite = async (dealId, currentStatus, chunkId, userId) => {
  try {
    const { dealsCollectionRef, userDocRef } = getRefs(userId);
    await updateDoc(doc(dealsCollectionRef, dealId), { isFavorite: !currentStatus });
    if (chunkId) {
      const indexDocRef = doc(userDocRef, 'deals_index', chunkId);
      await updateDoc(indexDocRef, {
        [`deals.${dealId}.f`]: !currentStatus
      });
    }
  } catch (error) {
    console.error(`Error toggling favorite for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour des favoris.");
  }
};

export const toggleDealPurchased = async (dealId, currentStatus, chunkId, userId, purchasePrice = null) => {
  try {
    const { dealsCollectionRef, userDocRef } = getRefs(userId);
    const newStatus = !currentStatus;
    await updateDoc(doc(dealsCollectionRef, dealId), newStatus
      ? { isPurchased: true, purchasedAt: serverTimestamp(), purchasePrice: purchasePrice ?? deleteField() }
      : { isPurchased: false, purchasedAt: deleteField(), purchasePrice: deleteField() }
    );
    if (chunkId) {
      const indexDocRef = doc(userDocRef, 'deals_index', chunkId);
      await updateDoc(indexDocRef, {
        [`deals.${dealId}.pu`]: newStatus
      });
    }
  } catch (error) {
    console.error(`Error toggling purchased for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour du statut d'achat.");
  }
};

/**
 * Correction manuelle de la classification d'une annonce (2026-08-16).
 *
 * Écrite dans un champ DÉDIÉ `manualClassification`, jamais dans `aiAnalysis.classification` :
 * une ré-analyse écrase intégralement `aiAnalysis`, la correction serait donc perdue au premier
 * "Ré-analyser" (même famille de piège que le bug `ArrayUnion` du 2026-08-12, qui détruisait
 * silencieusement `aiAnalysis`). Le champ dédié prime à l'affichage et au filtrage.
 *
 * L'index léger reçoit la valeur corrigée dans `c` (pour que filtres/compteurs/stats en tiennent
 * compte sans charger les documents complets) plus un marqueur `mc` qui signale l'origine manuelle.
 * `classificationPath` vaut null pour ANNULER la correction et revenir au verdict de l'IA.
 */
export const setDealClassification = async (dealId, chunkId, userId, classificationPath, aiClassification = null) => {
  try {
    const { dealsCollectionRef, userDocRef } = getRefs(userId);
    await updateDoc(doc(dealsCollectionRef, dealId), {
      manualClassification: classificationPath || deleteField()
    });
    if (chunkId) {
      const indexDocRef = doc(userDocRef, 'deals_index', chunkId);
      await updateDoc(indexDocRef, {
        // En annulation, l'index retombe sur la classification de l'IA (pas sur du vide).
        [`deals.${dealId}.c`]: classificationPath || aiClassification || deleteField(),
        [`deals.${dealId}.mc`]: classificationPath ? true : deleteField()
      });
    }
  } catch (error) {
    console.error(`Error setting classification for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la correction de la catégorie.");
  }
};

/**
 * Ajoute une photo (déjà uploadée vers Firebase Storage, voir storageService.js) à la galerie de
 * l'annonce — utilisée par le bouton "Ajouter à la galerie" du chat Gemini (2026-08-21, voir
 * useDealChat.js::addPhotoToGallery). `storageImageUrls` est un VRAI champ tableau, contrairement
 * à `aiAnalysis` (objet) sur lequel un `ArrayUnion` avait silencieusement corrompu les annonces
 * vendues le 2026-08-12 — `arrayUnion` est l'usage correct ici.
 */
export const addImageToDealGallery = async (dealId, url, userId) => {
  try {
    const { dealsCollectionRef } = getRefs(userId);
    await updateDoc(doc(dealsCollectionRef, dealId), {
      storageImageUrls: arrayUnion(url)
    });
  } catch (error) {
    console.error(`Error adding gallery image for deal ${dealId}:`, error);
    throw new Error("Erreur lors de l'ajout de la photo à la galerie.");
  }
};

// --- Chat IA (2026-07-31, Firebase AI Logic) ---
// Historique persisté par annonce : guitar_deals/{dealId}/chat/{msgId}, écrit directement
// depuis le frontend (le chat n'implique aucun aller-retour backend Python — voir
// docs/reference/ARCHITECTURE.md § Chat Gemini).

const getDealChatCollectionRef = (dealId, userId) => {
  const { dealsCollectionRef } = getRefs(userId);
  return collection(doc(dealsCollectionRef, dealId), 'chat');
};

export const onDealChatUpdate = (dealId, onUpdate, onError, userId) => {
  const chatQuery = query(getDealChatCollectionRef(dealId, userId), orderBy('createdAt', 'asc'));
  return onSnapshot(chatQuery, (snapshot) => {
    onUpdate(snapshot.docs.map(d => ({ id: d.id, ...d.data() })));
  }, (error) => {
    console.error(`Error listening to chat for deal ${dealId}:`, error);
    onError?.(error);
  });
};

// `parts` = payload complet envoyé/reçu de l'API Gemini (peut inclure le contexte injecté +
// les pièces image gs://, invisibles à l'utilisateur) ; `displayText` = ce qui est réellement
// affiché dans la bulle de chat (le texte tapé par l'utilisateur, ou la réponse du modèle).
// `attachedImagePartIndices` (optionnel, 2026-08-22, tableau — remplace l'ancien champ singulier
// `attachedImagePartIndex` conservé pour lecture rétrocompatible des messages déjà en base) =
// index dans `parts` des photos jointes par l'utilisateur depuis le chat (distinctes des photos de
// l'annonce déjà présentes dans `parts` sur le premier message) — référence les entrées existantes
// plutôt que de dupliquer leur base64, pour un affichage sans équivoque des miniatures dans la bulle.
// `restorationProposals` (optionnel, 2026-08-22, Lot B) : propositions d'ajout d'étape faites par
// l'IA via function calling sur ce tour — jamais les parts function-call/function-response brutes
// (jamais rejouées dans l'historique Gemini, voir useDealChat.js), juste la forme validée/normalisée
// affichée en carte sous la bulle. Retourne l'id du document créé (aucun appelant ne le capture
// aujourd'hui — `message.id` du listener Firestore suffit pour `proposedByMessageId`/le marquage
// Appliquer/Ignorer, une fois le message déjà visible côté client — gardé pour un futur usage).
export const addDealChatMessage = async (dealId, role, parts, displayText, userId, attachedImagePartIndices, restorationProposals, photoRecall, isError) => {
  try {
    const chatCollectionRef = getDealChatCollectionRef(dealId, userId);
    const payload = { role, parts, displayText, createdAt: new Date() };
    if (attachedImagePartIndices?.length) payload.attachedImagePartIndices = attachedImagePartIndices;
    if (restorationProposals?.length) payload.restorationProposals = restorationProposals;
    // `photoRecall` (2026-08-23, Plan 1 tokens, Lot D) : posé sur le message modèle quand ce tour a
    // nécessité un rappel de photo(s) élidée(s) — voir useDealChat.js::sendMessage. Purement
    // informatif (bascule d'affichage), aucune logique n'en dépend.
    if (photoRecall?.refs?.length) payload.photoRecall = photoRecall;
    // `isError` (2026-08-24) : marque structurellement un placeholder d'échec (plutôt que de
    // détecter le texte "⚠️ Erreur..." côté UI, fragile) — pilote l'affichage du bouton
    // "Réessayer" dans DealChatPanel.jsx::ChatBubble.
    if (isError) payload.isError = true;
    const docRef = await addDoc(chatCollectionRef, payload);
    return docRef.id;
  } catch (error) {
    console.error(`Error saving chat message for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la sauvegarde du message.");
  }
};

// Remplace en place le contenu d'un message de chat déjà persisté (2026-08-24, bouton
// "Réessayer") — utilisé pour transformer un placeholder d'erreur en vraie réponse (ou en un
// nouvel échec) SANS ajouter de document supplémentaire : `useDealChat.js::sanitizeHistory`
// exige une alternance stricte user/model, deux tours 'model' consécutifs casseraient tout envoi
// suivant sur cette conversation. `restorationProposals`/`photoRecall` sont explicitement remis à
// `null` quand absents (pas juste omis) pour effacer une éventuelle valeur laissée par une
// tentative précédente sur ce même document.
export const replaceDealChatMessage = async (dealId, messageId, { parts, displayText, restorationProposals, photoRecall, isError }, userId) => {
  try {
    const chatCollectionRef = getDealChatCollectionRef(dealId, userId);
    await updateDoc(doc(chatCollectionRef, messageId), {
      parts, displayText,
      restorationProposals: restorationProposals?.length ? restorationProposals : null,
      photoRecall: photoRecall?.refs?.length ? photoRecall : null,
      isError: !!isError,
    });
  } catch (error) {
    console.error(`Error replacing chat message ${messageId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour du message.");
  }
};

// Marque une photo jointe d'un message de chat comme "déjà ajoutée à la galerie" (2026-08-21,
// étendu 2026-08-22 pour plusieurs photos par message) — persisté sur le message lui-même plutôt
// qu'en état local, pour rester vrai après un reload ou depuis un autre client. `addedToGalleryUrls`
// est une map `{ "<partIndex>": url }` (clé Firestore forcément string) : chaque photo du message a
// son propre bouton "Ajouter à la galerie", indépendant des autres.
export const markChatMessageAddedToGallery = async (dealId, messageId, partIndex, url, userId) => {
  try {
    const chatCollectionRef = getDealChatCollectionRef(dealId, userId);
    await updateDoc(doc(chatCollectionRef, messageId), { [`addedToGalleryUrls.${partIndex}`]: url });
  } catch (error) {
    console.error(`Error marking chat message ${messageId} as added to gallery:`, error);
    throw new Error("Erreur lors de la mise à jour du message.");
  }
};

// Persiste l'état Appliquer/Ignorer d'une proposition d'étape de restauration (2026-08-22, Lot B)
// SUR LE MESSAGE, pas seulement en état React local — sinon un reload réactiverait un bouton déjà
// cliqué et permettrait de dupliquer l'étape. Même schéma dot-notation que `addedToGalleryUrls`.
// `itemId` (optionnel) référence l'étape créée dans restorationPlan quand status === 'applied'.
export const markChatMessageRestorationProposalStatus = async (dealId, messageId, proposalIndex, status, userId, itemId) => {
  try {
    const chatCollectionRef = getDealChatCollectionRef(dealId, userId);
    const value = itemId ? { status, itemId } : { status };
    await updateDoc(doc(chatCollectionRef, messageId), { [`restorationProposalStates.${proposalIndex}`]: value });
  } catch (error) {
    console.error(`Error marking restoration proposal ${proposalIndex} on message ${messageId}:`, error);
    throw new Error("Erreur lors de la mise à jour de la proposition.");
  }
};

// --- Plan de restauration (2026-08-22) ---
// Sous-collection dédiée guitar_deals/{dealId}/restorationPlan/{itemId}, jamais un champ sur le
// deal ni dans aiAnalysis : repository.py écrase le deal entier (.set sans merge) et tout
// aiAnalysis (.update) sur plusieurs chemins backend — une sous-collection n'est concernée par
// aucun des deux, donc rien ne peut écraser silencieusement le plan de restauration.

const getRestorationPlanCollectionRef = (dealId, userId) => {
  const { dealsCollectionRef } = getRefs(userId);
  return collection(doc(dealsCollectionRef, dealId), 'restorationPlan');
};

export const onRestorationPlanUpdate = (dealId, onUpdate, onError, userId) => {
  const planQuery = query(getRestorationPlanCollectionRef(dealId, userId), orderBy('createdAt', 'asc'));
  return onSnapshot(planQuery, (snapshot) => {
    onUpdate(snapshot.docs.map(d => ({ id: d.id, ...d.data() })));
  }, (error) => {
    console.error(`Error listening to restoration plan for deal ${dealId}:`, error);
    onError?.(error);
  });
};

// `createdAt: new Date()` (pas serverTimestamp()) — même choix que le chat (voir
// addDealChatMessage) : un serverTimestamp() non résolu localement lit `null` le temps de la
// confirmation serveur, ce qui ferait sauter l'item ajouté dans le tri `orderBy('createdAt')`.
// `source`/`proposedByMessageId` (optionnels, 2026-08-22, Lot B) : une étape appliquée depuis une
// proposition IA appelle cette même fonction avec `source: 'ai'` — un seul chemin d'écriture pour
// l'ajout manuel (panneau) et l'ajout proposé (chat), jamais deux logiques parallèles à maintenir.
// `order` (optionnel, calculé par l'appelant depuis la liste déjà en mémoire — voir
// useRestorationPlan.js::addItem et useDealChat.js::applyRestorationProposal) : sans lui, un
// ajout laissait l'item sans `order`, ce qui redéclenchait le rattrapage silencieux
// (backfillRestorationOrder) sur TOUT le plan à chaque ajout — effaçant de fait un ordre de
// glisser-déposer déjà mis en place par l'utilisateur (bug trouvé en revue, corrigé ici).
export const addRestorationItem = async (dealId, userId, { label, category, estimatedCost, notes, source = 'user', proposedByMessageId, order }) => {
  try {
    const planCollectionRef = getRestorationPlanCollectionRef(dealId, userId);
    const payload = { label, category, status: 'pending', source, createdAt: new Date() };
    if (estimatedCost != null) payload.estimatedCost = estimatedCost;
    if (notes) payload.notes = notes;
    if (proposedByMessageId) payload.proposedByMessageId = proposedByMessageId;
    if (order != null) payload.order = order;
    // Retourne l'id du document créé — nécessaire pour rattacher `itemId` au marquage
    // Appliquer/Ignorer de la proposition d'origine (voir useDealChat.js::applyRestorationProposal).
    const docRef = await addDoc(planCollectionRef, payload);
    return docRef.id;
  } catch (error) {
    console.error(`Error adding restoration item for deal ${dealId}:`, error);
    throw new Error("Erreur lors de l'ajout de l'étape de restauration.");
  }
};

// Mise à jour champ par champ uniquement (jamais l'objet entier depuis un formulaire) : une
// édition de note et une future proposition IA appliquée en parallèle ne doivent jamais pouvoir
// s'écraser l'une l'autre. `completedAt` posé automatiquement au passage à 'done' plutôt que de
// dépendre de `updatedAt`, qu'une note éditée ensuite écraserait — et effacé symétriquement dès
// que le statut change vers autre chose que 'done' (rouvrir une étape ne doit pas laisser une
// date de complétion périmée).
export const updateRestorationItem = async (dealId, userId, itemId, patch) => {
  try {
    const planCollectionRef = getRestorationPlanCollectionRef(dealId, userId);
    const payload = { ...patch, updatedAt: serverTimestamp() };
    if (patch.estimatedCost === null) payload.estimatedCost = deleteField();
    if (patch.actualCost === null) payload.actualCost = deleteField();
    if (patch.notes === null) payload.notes = deleteField();
    if (patch.status === 'done') {
      payload.completedAt = serverTimestamp();
    } else if (patch.status) {
      payload.completedAt = deleteField();
    }
    await updateDoc(doc(planCollectionRef, itemId), payload);
  } catch (error) {
    console.error(`Error updating restoration item ${itemId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour de l'étape de restauration.");
  }
};

export const deleteRestorationItem = async (dealId, userId, itemId) => {
  try {
    const planCollectionRef = getRestorationPlanCollectionRef(dealId, userId);
    await deleteDoc(doc(planCollectionRef, itemId));
  } catch (error) {
    console.error(`Error deleting restoration item ${itemId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la suppression de l'étape de restauration.");
  }
};

// Réordonnancement (glisser-déposer manuel, ou proposition IA appliquée depuis le chat, 2026-08-23) —
// `orderedItemIds` = ids dans le nouvel ordre voulu, un seul batch pour tous les items du plan.
export const reorderRestorationItems = async (dealId, userId, orderedItemIds) => {
  try {
    const planCollectionRef = getRestorationPlanCollectionRef(dealId, userId);
    const batch = writeBatch(db);
    orderedItemIds.forEach((itemId, index) => {
      batch.update(doc(planCollectionRef, itemId), { order: index, updatedAt: serverTimestamp() });
    });
    await batch.commit();
  } catch (error) {
    console.error(`Error reordering restoration items for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la réorganisation des étapes.");
  }
};

// Assigne un `order` (2026-08-22, réorganisation par glisser-déposer) à TOUS les items d'un coup,
// selon l'ordre `orderedItems` fourni (déjà trié par `createdAt`, l'ordre de la requête Firestore)
// — jamais de migration explicite : le premier client qui charge un plan sans `order` (ancien, ou
// tout juste créé) le rattrape ainsi pour tout le monde en un seul batch, pour ne jamais mélanger
// des items ordonnés et non-ordonnés dans la même liste. Silencieux (fire-and-forget côté appelant).
export const backfillRestorationOrder = async (dealId, userId, orderedItems) => {
  try {
    const planCollectionRef = getRestorationPlanCollectionRef(dealId, userId);
    const batch = writeBatch(db);
    orderedItems.forEach((item, index) => {
      batch.update(doc(planCollectionRef, item.id), { order: index });
    });
    await batch.commit();
  } catch (error) {
    console.error(`Error backfilling restoration order for deal ${dealId}:`, error);
  }
};

// Photos par étape (2026-08-22) — tableau réel, `arrayUnion`/`arrayRemove` comme `storageImageUrls`
// sur le deal (jamais un `ArrayUnion` posé sur un objet, voir l'incident du 2026-08-12 documenté
// ailleurs). Une URL peut venir d'un upload direct (`storageService.js::uploadRestorationPhotoToDealStorage`)
// ou d'une photo déjà existante dans la galerie de l'annonce (`deal.storageImageUrls`) — même champ,
// même fonction d'écriture dans les deux cas.
export const addRestorationItemPhoto = async (dealId, userId, itemId, url) => {
  try {
    const planCollectionRef = getRestorationPlanCollectionRef(dealId, userId);
    await updateDoc(doc(planCollectionRef, itemId), { photoUrls: arrayUnion(url) });
  } catch (error) {
    console.error(`Error adding photo to restoration item ${itemId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors de l'ajout de la photo à l'étape.");
  }
};

export const removeRestorationItemPhoto = async (dealId, userId, itemId, url) => {
  try {
    const planCollectionRef = getRestorationPlanCollectionRef(dealId, userId);
    await updateDoc(doc(planCollectionRef, itemId), { photoUrls: arrayRemove(url) });
  } catch (error) {
    console.error(`Error removing photo from restoration item ${itemId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors du retrait de la photo de l'étape.");
  }
};

// --- Cities ---

/**
 * Écoute le catalogue partagé + les préférences user en temps réel.
 * Fusionne les deux sources et retourne un tableau de villes enrichi :
 * { docId (= Facebook city ID), name, id, latitude, longitude, isScannable }
 * Les villes du catalogue sans préférence user ont isScannable = false.
 * Retourne une fonction de nettoyage qui désabonne les deux listeners.
 */
export const onCitiesUpdate = (onUpdate, onError, userId) => {
  const sharedCitiesRef = getSharedCitiesRef();
  const { userCitiesPrefsRef } = getRefs(userId);

  let catalogCache = {};
  let prefsCache = {};

  const merge = () => {
    if (Object.keys(catalogCache).length > 0) {
      // Nouvelle architecture : catalogue partagé + prefs user séparées
      const merged = Object.entries(catalogCache)
        .map(([cityId, cityData]) => ({
          docId: cityId,
          ...cityData,
          isScannable: prefsCache[cityId]?.isScannable ?? false,
        }))
        .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
      onUpdate(merged);
    } else {
      // Fallback ancienne architecture : données complètes dans users/{uid}/cities
      // (name, id, lat, lon, isScannable dans le même document)
      const merged = Object.entries(prefsCache)
        .filter(([, data]) => data.name && data.id)
        .map(([cityId, data]) => ({
          docId: cityId,
          ...data,
        }))
        .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
      onUpdate(merged);
    }
  };

  const unsubCatalog = onSnapshot(sharedCitiesRef, (snapshot) => {
    catalogCache = {};
    snapshot.docs.forEach(d => { catalogCache[d.id] = d.data(); });
    merge();
  }, (error) => { console.error("Error listening to shared cities:", error); onError(error); });

  const unsubPrefs = onSnapshot(userCitiesPrefsRef, (snapshot) => {
    prefsCache = {};
    snapshot.docs.forEach(d => { prefsCache[d.id] = d.data(); });
    merge();
  }, (error) => { console.error("Error listening to city prefs:", error); onError(error); });

  return () => { unsubCatalog(); unsubPrefs(); };
};

// `cityPayload` : chaîne simple (repli, ajout à l'aveugle) ou `{name, latitude, longitude,
// regionHint}` depuis une suggestion choisie explicitement par l'utilisateur — voir
// `useCitySuggestions.js` et `backend/bot.py::add_city_auto()`.
export const requestAddCity = (cityPayload, userId) => addCommand('ADD_CITY', cityPayload, userId);

/**
 * Supprime la préférence user pour cette ville (la retire de la liste active).
 * La ville reste dans le catalogue partagé.
 * docId = Facebook city ID
 */
export const deleteCity = async (docId, userId) => {
  try {
    const { userCitiesPrefsRef } = getRefs(userId);
    await deleteDoc(doc(userCitiesPrefsRef, docId));
  } catch (error) {
    console.error(`Error removing city pref ${docId}:`, error);
    throw new Error("Erreur lors de la suppression de la ville.");
  }
};

/**
 * Active ou désactive le scan d'une ville pour cet utilisateur.
 * docId = Facebook city ID
 */
export const toggleCityScannable = async (docId, currentStatus, userId) => {
  try {
    const { userCitiesPrefsRef } = getRefs(userId);
    await setDoc(doc(userCitiesPrefsRef, docId), { isScannable: !currentStatus }, { merge: true });
  } catch (error) {
    console.error(`Error toggling scannable for city ${docId}:`, error);
    throw new Error("Erreur lors de la mise à jour de la ville.");
  }
};

/**
 * Définit le rayon de recherche Kijiji (km) pour cette ville, pour cet utilisateur —
 * prime sur le défaut à deux paliers appliqué côté backend (voir bot.py::_run_kijiji_scan).
 * radiusKm null/0 efface le réglage (repli sur le défaut).
 * docId = Facebook city ID
 */
export const setCityKijijiRadius = async (docId, radiusKm, userId) => {
  try {
    const { userCitiesPrefsRef } = getRefs(userId);
    await setDoc(doc(userCitiesPrefsRef, docId), { kijijiRadiusKm: radiusKm || null }, { merge: true });
  } catch (error) {
    console.error(`Error setting Kijiji radius for city ${docId}:`, error);
    throw new Error("Erreur lors de la mise à jour du rayon Kijiji.");
  }
};

// --- Migration Automatique V2 ---
export const migrateOldDataToNewUser = async (newUserId, userEmail) => {
  const OLD_USER_ID = import.meta.env.VITE_USER_ID_TARGET;
  const ADMIN_EMAIL = import.meta.env.VITE_ADMIN_EMAIL;

  if (!ADMIN_EMAIL || userEmail !== ADMIN_EMAIL) {
    return false; // Pas de migration pour les utilisateurs non-admin
  }

  if (!OLD_USER_ID || OLD_USER_ID === newUserId) return false;

  const {
    userDocRef: newConfigRef,
    dealsCollectionRef: newDealsRef,
    userCitiesPrefsRef: newCitiesPrefsRef
  } = getRefs(newUserId);

  const {
    userDocRef: oldConfigRef,
    dealsCollectionRef: oldDealsRef,
    userCitiesPrefsRef: oldCitiesPrefsRef
  } = getRefs(OLD_USER_ID);

  const sharedCitiesRef = getSharedCitiesRef();

  // 1. Vérifier si la migration a déjà eu lieu
  const newConfigSnap = await getDoc(newConfigRef);
  if (newConfigSnap.exists() && newConfigSnap.data()?.migrationDone === true) {
    return false;
  }

  console.log(`Lancement de la migration pour l'UID ${newUserId}...`);

  // 2. Copie Config
  try {
    const oldConfigSnap = await getDoc(oldConfigRef);
    if (oldConfigSnap.exists()) {
      await setDoc(newConfigRef, { ...oldConfigSnap.data(), migrationDone: true });
    }
    console.log('Migration — config : ✅');
  } catch (error) {
    console.error('Migration — config : ❌', error);
    return false;
  }

  // 3. Migration des villes vers le catalogue partagé + prefs user
  try {
    const oldCitiesSnap = await getDocs(oldCitiesPrefsRef);
    await Promise.all(oldCitiesSnap.docs.map(async (cityDoc) => {
      const data = cityDoc.data();
      const facebookCityId = data.id ? String(data.id) : cityDoc.id;
      // Écrire dans le catalogue partagé (les métadonnées de la ville)
      const { isScannable, ...catalogData } = data;
      await setDoc(doc(sharedCitiesRef, facebookCityId), catalogData, { merge: true });
      // Écrire la pref isScannable pour le nouvel user
      await setDoc(doc(newCitiesPrefsRef, facebookCityId), { isScannable: isScannable ?? false }, { merge: true });
    }));
    console.log(`Migration — villes (${oldCitiesSnap.size}) vers catalogue partagé : ✅`);
  } catch (error) {
    console.error('Migration — villes : ❌', error);
  }

  // 4. Copie Deals
  try {
    const oldDealsSnap = await getDocs(oldDealsRef);
    await Promise.all(oldDealsSnap.docs.map(dealDoc =>
      setDoc(doc(newDealsRef, dealDoc.id), dealDoc.data())
    ));
    console.log(`Migration — annonces (${oldDealsSnap.size}) : ✅`);
  } catch (error) {
    console.error('Migration — annonces : ❌', error);
  }

  console.log(`✅ Migration de ${OLD_USER_ID} vers ${newUserId} terminée.`);
  return true;
};
