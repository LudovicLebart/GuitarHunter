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

// --- Factory : crée les références Firestore pour un userId donné ---
const getRefs = (userId) => {
  if (!APP_ID || !userId) {
    console.warn("firestoreService: APP_ID ou userId manquant.", { APP_ID, userId });
  }
  const userDocRef = doc(db, 'artifacts', APP_ID, 'users', userId);
  return {
    userDocRef,
    dealsCollectionRef: collection(db, 'artifacts', APP_ID, 'users', userId, 'guitar_deals'),
    citiesCollectionRef: collection(db, 'artifacts', APP_ID, 'users', userId, 'cities'),
    commandsCollectionRef: collection(db, 'artifacts', APP_ID, 'users', userId, 'commands'),
    userDocRef,
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

export const onCitiesUpdate = (onUpdate, onError, userId) => {
  const { citiesCollectionRef } = getRefs(userId);
  return onSnapshot(citiesCollectionRef, (snapshot) => {
    const citiesData = snapshot.docs.map(d => ({ docId: d.id, ...d.data() }));
    citiesData.sort((a, b) => a.name.localeCompare(b.name));
    onUpdate(citiesData);
  }, (error) => {
    console.error("Error listening to cities:", error);
    onError(error);
  });
};

export const requestAddCity = (cityName, userId) => addCommand('ADD_CITY', cityName, userId);

export const deleteCity = async (docId, userId) => {
  try {
    const { citiesCollectionRef } = getRefs(userId);
    await deleteDoc(doc(citiesCollectionRef, docId));
  } catch (error) {
    console.error(`Error deleting city ${docId}:`, error);
    throw new Error("Erreur lors de la suppression de la ville.");
  }
};

export const toggleCityScannable = async (docId, currentStatus, userId) => {
  try {
    const { citiesCollectionRef } = getRefs(userId);
    await updateDoc(doc(citiesCollectionRef, docId), { isScannable: !currentStatus });
  } catch (error) {
    console.error(`Error toggling scannable for city ${docId}:`, error);
    throw new Error("Erreur lors de la mise à jour de la ville.");
  }
};

// --- Migration Automatique V2 ---
export const migrateOldDataToNewUser = async (newUserId, userEmail) => {
  const OLD_USER_ID = import.meta.env.VITE_USER_ID_TARGET;
  
  if (userEmail !== 'ludovic.lebart@gmail.com') {
    return false; // Pas de migration pour les nouveaux utilisateurs réguliers
  }

  if (!OLD_USER_ID || OLD_USER_ID === newUserId) return false;

  console.log(`Vérification de migration : Ancien ID (${OLD_USER_ID}) vers Nouveau UID (${newUserId}) pour ${userEmail}...`);

  const {
    userDocRef: newConfigRef,
    dealsCollectionRef: newDealsRef,
    citiesCollectionRef: newCitiesRef
  } = getRefs(newUserId);

  const {
    userDocRef: oldConfigRef,
    dealsCollectionRef: oldDealsRef,
    citiesCollectionRef: oldCitiesRef
  } = getRefs(OLD_USER_ID);

  // 1. Check if new user already has a config document
  const newConfigSnap = await getDoc(newConfigRef);
  if (newConfigSnap.exists()) {
    console.log("Migration ignorée : L'utilisateur a déjà des données.");
    return false;
  }

  console.log(`Lancement de la migration pour l'UID ${newUserId}...`);

  try {
    // 2. Copy Config
    const oldConfigSnap = await getDoc(oldConfigRef);
    if (oldConfigSnap.exists()) {
      await setDoc(newConfigRef, oldConfigSnap.data());
    }

    // 3. Copy Cities
    const oldCitiesSnap = await getDocs(oldCitiesRef);
    const cityPromises = oldCitiesSnap.docs.map(cityDoc => 
      setDoc(doc(newCitiesRef, cityDoc.id), cityDoc.data())
    );
    await Promise.all(cityPromises);

    // 4. Copy Deals (Batch is recommended for many deals, but standard write is okay for now)
    const oldDealsSnap = await getDocs(oldDealsRef);
    const dealPromises = oldDealsSnap.docs.map(dealDoc => 
      setDoc(doc(newDealsRef, dealDoc.id), dealDoc.data())
    );
    await Promise.all(dealPromises);

    console.log(`✅ Migration de ${OLD_USER_ID} vers ${newUserId} terminée avec succès !`);
    return true;
  } catch (error) {
    console.error("❌ Erreur pendant la migration des données :", error);
    return false;
  }
};
