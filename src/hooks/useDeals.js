import { useState, useEffect, useCallback } from 'react';
import { 
  onDealsUpdate, 
  rejectDeal, 
  deleteDeal,
  retryDealAnalysis,
  forceExpertAnalysis,
  toggleDealFavorite 
} from '../services/firestoreService';

export const useDeals = (user, setError) => {
  const [deals, setDeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dbStatus, setDbStatus] = useState({ status: 'pending', msg: 'En attente' });

  useEffect(() => {
    if (!user) return;

    const handleUpdate = (dealsData, count) => {
      // Force la création de nouveaux objets pour garantir le re-rendering des composants mémoïsés
      const newDeals = dealsData.map(d => ({ ...d }));
      setDeals(newDeals);
      setLoading(false);
      setDbStatus({ status: 'success', msg: `${count} annonces` });
    };

    const handleError = (err) => {
      setError(err.message);
      setLoading(false);
      setDbStatus({ status: 'error', msg: err.message });
    };

    const unsubscribe = onDealsUpdate(handleUpdate, handleError);
    return () => unsubscribe();
  }, [user, setError]);

  const handleRejectDeal = useCallback(async (dealId) => {
    try {
      await rejectDeal(dealId);
    } catch (e) {
      setError(e.message);
    }
  }, [setError]);

  const handleDeleteDeal = useCallback(async (dealId) => {
    if (window.confirm("Voulez-vous vraiment supprimer définitivement cette annonce ?")) {
      try {
        await deleteDeal(dealId);
      } catch (e) {
        setError(e.message);
      }
    }
  }, [setError]);

  const handleRetryAnalysis = useCallback(async (dealId) => {
    try {
      await retryDealAnalysis(dealId);
    } catch (e) {
      setError(e.message);
    }
  }, [setError]);

  const handleForceExpertAnalysis = useCallback(async (dealId) => {
    try {
      await forceExpertAnalysis(dealId);
    } catch (e) {
      setError(e.message);
    }
  }, [setError]);

  const handleToggleFavorite = useCallback(async (dealId, currentStatus) => {
    try {
      await toggleDealFavorite(dealId, currentStatus);
    } catch (e) {
      setError(e.message);
    }
  }, [setError]);

  return {
    deals,
    loading,
    dbStatus,
    handleRejectDeal,
    handleDeleteDeal,
    handleRetryAnalysis,
    handleForceExpertAnalysis,
    handleToggleFavorite
  };
};
