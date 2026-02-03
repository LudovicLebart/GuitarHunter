import { useState, useEffect, useCallback } from 'react';
import { collection, onSnapshot, doc, updateDoc } from 'firebase/firestore';
import { db } from '../services/firebase';

const PYTHON_USER_ID = "00737242777130596039";
const APP_ID = "c_5d118e719dbddbfc_index.html-217";

export const useDeals = (user, setError) => {
  const [deals, setDeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dbStatus, setDbStatus] = useState({ status: 'pending', msg: 'En attente' });

  useEffect(() => {
    if (!user) return;
    const collectionRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'guitar_deals');
    const unsubscribe = onSnapshot(collectionRef, (snapshot) => {
      const dealsData = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      dealsData.sort((a, b) => (b.timestamp?.seconds || 0) - (a.timestamp?.seconds || 0));
      setDeals(dealsData);
      setLoading(false);
      setDbStatus({ status: 'success', msg: `${snapshot.size} annonces` });
    }, (err) => {
      setError(err.message);
      setLoading(false);
      setDbStatus({ status: 'error', msg: err.message });
    });
    return () => unsubscribe();
  }, [user, setError]);

  const handleRejectDeal = useCallback(async (dealId) => {
    try {
      const dealDocRef = doc(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'guitar_deals', dealId);
      await updateDoc(dealDocRef, {
        status: 'rejected',
        'aiAnalysis.verdict': 'REJECTED'
      });
    } catch (e) {
      setError("Erreur lors du rejet de l'annonce.");
    }
  }, [setError]);

  const handleRetryAnalysis = useCallback(async (dealId) => {
    try {
      const dealDocRef = doc(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'guitar_deals', dealId);
      await updateDoc(dealDocRef, {
        status: 'retry_analysis',
        'aiAnalysis.verdict': 'DEFAULT',
        'aiAnalysis.reasoning': 'Analyse relancée...'
      });
    } catch (e) {
      setError("Erreur lors de la demande de ré-analyse.");
    }
  }, [setError]);

  const handleToggleFavorite = useCallback(async (dealId, currentStatus) => {
    try {
      const dealDocRef = doc(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'guitar_deals', dealId);
      await updateDoc(dealDocRef, {
        isFavorite: !currentStatus
      });
    } catch (e) {
      setError("Erreur lors de la mise à jour des favoris.");
    }
  }, [setError]);

  return {
    deals,
    loading,
    dbStatus,
    handleRejectDeal,
    handleRetryAnalysis,
    handleToggleFavorite
  };
};
