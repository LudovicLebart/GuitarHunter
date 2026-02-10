import { doc, setDoc, deleteField, onSnapshot, collection, updateDoc, addDoc, deleteDoc } from 'firebase/firestore';
import { db } from './firebase';

const PYTHON_USER_ID = "00737242777130596039";
const APP_ID = "c_5d118e719dbddbfc_index.html-217";

const userDocRef = doc(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID);
const dealsCollectionRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'guitar_deals');
const citiesCollectionRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'cities');
const commandsCollectionRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'commands');

// --- Bot Configuration ---

export const updateUserConfig = async (newConfig) => {
  try {
    await setDoc(userDocRef, newConfig, { merge: true });
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
  return onSnapshot(userDocRef, (docSnap) => {
    if (docSnap.exists()) {
      onUpdate(docSnap.data());
    } else {
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

export const retryDealAnalysis = async (dealId) => {
  try {
    await updateDoc(getDealDocRef(dealId), {
      status: 'retry_analysis',
      'aiAnalysis.verdict': 'DEFAULT',
      'aiAnalysis.reasoning': 'Analyse standard relancée...'
    });
  } catch (error) {
    console.error(`Error retrying analysis for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la demande de ré-analyse.");
  }
};

export const forceExpertAnalysis = async (dealId) => {
  try {
    await updateDoc(getDealDocRef(dealId), {
      status: 'retry_analysis_expert',
      'aiAnalysis.verdict': 'DEFAULT',
      'aiAnalysis.reasoning': 'Analyse expert demandée...'
    });
  } catch (error) {
    console.error(`Error forcing expert analysis for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la demande d'analyse expert.");
  }
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
        // CORRECTION ICI : On sépare docId (ID Firestore) et id (ID Facebook)
        const citiesData = snapshot.docs.map(doc => ({
            docId: doc.id, // L'ID unique du document Firestore
            ...doc.data()  // Les données (qui contiennent le champ 'id' = ID Facebook)
        }));
        // Tri alphabétique par défaut
        citiesData.sort((a, b) => a.name.localeCompare(b.name));
        onUpdate(citiesData);
    }, (error) => {
        console.error("Error listening to cities:", error);
        onError(error);
    });
};

export const addCity = async (cityName, cityId) => {
    console.log(`Attempting to add city: ${cityName} with ID: ${cityId}`);
    try {
        await addDoc(citiesCollectionRef, {
            name: cityName,
            id: cityId,
            isScannable: false, // Par défaut non scannable
            createdAt: new Date()
        });
        console.log("City added successfully");
    } catch (error) {
        console.error("Error adding city (FULL DETAILS):", error);
        throw new Error(`Erreur lors de l'ajout de la ville: ${error.message}`);
    }
};

export const deleteCity = async (docId) => {
    try {
        // On utilise docId ici
        await deleteDoc(doc(citiesCollectionRef, docId));
    } catch (error) {
        console.error(`Error deleting city ${docId}:`, error);
        throw new Error("Erreur lors de la suppression de la ville.");
    }
};

export const toggleCityScannable = async (docId, currentStatus) => {
    try {
        // On utilise docId ici
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
        await addDoc(commandsCollectionRef, {
            type: type,
            payload: payload,
            status: 'pending',
            createdAt: new Date()
        });
        console.log(`Command ${type} added successfully.`);
    } catch (error) {
        console.error(`Error adding command ${type}:`, error);
        throw new Error("Erreur lors de l'envoi de la commande.");
    }
};
