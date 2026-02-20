import { doc, setDoc, deleteField, onSnapshot, collection, updateDoc, addDoc, deleteDoc } from 'firebase/firestore';
import { db } from './firebase';

const PYTHON_USER_ID = process.env.USER_ID_TARGET;
const APP_ID = process.env.APP_ID_TARGET;

const userDocRef = doc(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID);
const dealsCollectionRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'guitar_deals');
const citiesCollectionRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'cities');
const commandsCollectionRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'commands');

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

// --- Bot Configuration ---

export const updateUserConfig = async (newConfig) => {
  try {
    console.log("Saving user config to Firestore:", newConfig);

    // CORRECTION BUG : setDoc + merge:true ne merge qu'au niveau RACINE du document.
    // Si on passe { analysisConfig: { mainAnalysisPrompt: [...] } }, il REMPLACE
    // l'intégralité du sous-objet analysisConfig, effaçant gatekeeperModel, expertModel, etc.
    //
    // Solution : détecter la notation par points (ex: 'analysisConfig.mainAnalysisPrompt').
    //   - Dot-notation → updateDoc : écriture chirurgicale, ne touche pas les champs frères.
    //   - Objet complet (Reset) → setDoc + merge : remplace les champs racine voulus.
    const hasDotNotation = Object.keys(newConfig).some(k => k.includes('.'));

    if (hasDotNotation) {
      // Écriture ciblée d'un seul champ imbriqué (ex: saveConfig depuis ConfigPanel)
      await updateDoc(userDocRef, newConfig);
    } else {
      // Écriture complète d'un objet de config (ex: handleResetDefaults)
      const expandedConfig = unflatten(newConfig);
      await setDoc(userDocRef, expandedConfig, { merge: true });
    }

    console.log("Config saved successfully.");
  } catch (error) {
    console.error("Error updating user config:", error);
    throw new Error("Erreur de sauvegarde de la configuration.");
  }
};

export const triggerManualRefresh = () => {
  return updateUserConfig({ forceRefresh: Date.now(), scanError: deleteField() });
};

export const triggerManualCleanup = () => {
  return updateUserConfig({ forceCleanup: Date.now() });
};

export const triggerRelaunchAll = () => {
  return updateUserConfig({ forceReanalyzeAll: Date.now() });
};

export const triggerScanSpecificUrl = (url) => {
  return updateUserConfig({ scanSpecificUrl: url });
};

export const resetBotConfigToDefaults = (defaults) => {
  return updateUserConfig(defaults);
};

export const onBotConfigUpdate = (onUpdate, onError) => {
  console.log("Setting up onSnapshot for bot config...");
  return onSnapshot(userDocRef, (docSnap) => {
    if (docSnap.exists()) {
      const data = docSnap.data();
      console.log("🔥 Firestore Update Received (Bot Config):", data);
      onUpdate(data);
    } else {
      console.warn("User document not found in Firestore.");
      onError({ message: "Dossier Python introuvable" });
    }
  }, (error) => {
    console.error("Error listening to bot config:", error);
    onError(error);
  });
};

// --- Deals ---

const getDealDocRef = (dealId) => doc(dealsCollectionRef, dealId);

export const onDealsUpdate = (onUpdate, onError) => {
  return onSnapshot(dealsCollectionRef, (snapshot) => {
    const dealsData = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
    dealsData.sort((a, b) => (b.timestamp?.seconds || 0) - (a.timestamp?.seconds || 0));
    onUpdate(dealsData, snapshot.size);
  }, (error) => {
    console.error("Error listening to deals:", error);
    onError(error);
  });
};

export const rejectDeal = async (dealId) => {
  try {
    await updateDoc(getDealDocRef(dealId), {
      status: 'rejected',
      'aiAnalysis.verdict': 'REJECTED'
    });
  } catch (error) {
    console.error(`Error rejecting deal ${dealId}:`, error);
    throw new Error("Erreur lors du rejet de l'annonce.");
  }
};

export const deleteDeal = async (dealId) => {
  try {
    await deleteDoc(getDealDocRef(dealId));
  } catch (error) {
    console.error(`Error deleting deal ${dealId}:`, error);
    throw new Error("Erreur lors de la suppression de l'annonce.");
  }
};

export const retryDealAnalysis = (dealId) => {
  const payload = { dealId: dealId, forceExpert: false };
  return addCommand('ANALYZE_DEAL', payload);
};

export const forceExpertAnalysis = (dealId) => {
  const payload = { dealId: dealId, forceExpert: true };
  return addCommand('ANALYZE_DEAL', payload);
};

export const toggleDealFavorite = async (dealId, currentStatus) => {
  try {
    await updateDoc(getDealDocRef(dealId), {
      isFavorite: !currentStatus
    });
  } catch (error) {
    console.error(`Error toggling favorite for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour des favoris.");
  }
};

// --- Cities ---

export const onCitiesUpdate = (onUpdate, onError) => {
  return onSnapshot(citiesCollectionRef, (snapshot) => {
    const citiesData = snapshot.docs.map(doc => ({
      docId: doc.id,
      ...doc.data()
    }));
    citiesData.sort((a, b) => a.name.localeCompare(b.name));
    onUpdate(citiesData);
  }, (error) => {
    console.error("Error listening to cities:", error);
    onError(error);
  });
};

export const requestAddCity = (cityName) => {
  return addCommand('ADD_CITY', cityName);
};

export const deleteCity = async (docId) => {
  try {
    await deleteDoc(doc(citiesCollectionRef, docId));
  } catch (error) {
    console.error(`Error deleting city ${docId}:`, error);
    throw new Error("Erreur lors de la suppression de la ville.");
  }
};

export const toggleCityScannable = async (docId, currentStatus) => {
  try {
    await updateDoc(doc(citiesCollectionRef, docId), {
      isScannable: !currentStatus
    });
  } catch (error) {
    console.error(`Error toggling scannable for city ${docId}:`, error);
    throw new Error("Erreur lors de la mise à jour de la ville.");
  }
};

// --- Commands ---

export const addCommand = async (type, payload) => {
  try {
    const docRef = await addDoc(commandsCollectionRef, {
      type: type,
      payload: payload,
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

export const onCommandUpdate = (commandId, callback) => {
  const commandDocRef = doc(commandsCollectionRef, commandId);
  return onSnapshot(commandDocRef, (docSnap) => {
    if (docSnap.exists()) {
      callback(docSnap.data());
    }
  }, (error) => {
    console.error(`Error listening to command ${commandId}:`, error);
  });
};

export const requestClearLogs = () => {
  return addCommand('CLEAR_LOGS', null);
};
