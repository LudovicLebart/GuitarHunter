import {
  doc, setDoc, deleteField, onSnapshot, getDoc, getDocs,
  collection, updateDoc, addDoc, deleteDoc, getFirestore
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
  await setDoc(ref, {
    title: deal.title || null,
    price: deal.price || null,
    location: deal.location || null,
    link: deal.link || null,
    description: deal.description || null,
    storageImageUrls: deal.storageImageUrls || [],
    imageUrls: deal.imageUrls || [],
    verdict: deal.verdict || null,
    scores: deal.scores || null,
    analysis: deal.analysis || null,
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

export const onDealsUpdate = (onUpdate, onError, userId) => {
  const { dealsCollectionRef } = getRefs(userId);
  return onSnapshot(dealsCollectionRef, (snapshot) => {
    const dealsData = snapshot.docs.map(d => ({ id: d.id, ...d.data() }));
    dealsData.sort((a, b) => (b.timestamp?.seconds || 0) - (a.timestamp?.seconds || 0));
    onUpdate(dealsData, snapshot.size);
  }, (error) => {
    console.error("Error listening to deals:", error);
    onError(error);
  });
};

const getDealDocRef = (dealId, userId) => {
  const { dealsCollectionRef } = getRefs(userId);
  return doc(dealsCollectionRef, dealId);
};

export const rejectDeal = async (dealId, userId) => {
  try {
    await updateDoc(getDealDocRef(dealId, userId), {
      status: 'rejected',
      'aiAnalysis.verdict': 'REJECTED'
    });
  } catch (error) {
    console.error(`Error rejecting deal ${dealId}:`, error);
    throw new Error("Erreur lors du rejet de l'annonce.");
  }
};

export const deleteDeal = async (dealId, userId) => {
  try {
    await deleteDoc(getDealDocRef(dealId, userId));
  } catch (error) {
    console.error(`Error deleting deal ${dealId}:`, error);
    throw new Error("Erreur lors de la suppression de l'annonce.");
  }
};

export const retryDealAnalysis = (dealId, userId) =>
  addCommand('ANALYZE_DEAL', { dealId, forceExpert: false }, userId);

export const forceExpertAnalysis = (dealId, userId) =>
  addCommand('ANALYZE_DEAL', { dealId, forceExpert: true }, userId);

export const toggleDealFavorite = async (dealId, currentStatus, userId) => {
  try {
    await updateDoc(getDealDocRef(dealId, userId), { isFavorite: !currentStatus });
  } catch (error) {
    console.error(`Error toggling favorite for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour des favoris.");
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

export const requestAddCity = (cityName, userId) => addCommand('ADD_CITY', cityName, userId);

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
