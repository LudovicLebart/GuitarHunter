import { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  onDealsUpdate, 
  rejectDeal, 
  deleteDeal,
  retryDealAnalysis,
  forceExpertAnalysis,
  toggleDealFavorite 
} from '../services/firestoreService';
import promptsData from '../../prompts.json';
import { VERDICTS } from '../constants';

const GUITAR_TAXONOMY = promptsData.taxonomy_guitares || {};

export const useDealsManager = (user, setError) => {
  const [deals, setDeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dbStatus, setDbStatus] = useState({ status: 'pending', msg: 'En attente' });

  const [filterType, setFilterType] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [level1Filter, setLevel1Filter] = useState('ALL');
  const [level2Filter, setLevel2Filter] = useState('ALL');
  const [level3Filter, setLevel3Filter] = useState('ALL');

  useEffect(() => {
    if (!user) return;
    const unsubscribe = onDealsUpdate(
      (dealsData, count) => {
        setDeals(dealsData.map(d => ({ ...d })));
        setLoading(false);
        setDbStatus({ status: 'success', msg: `${count} annonces` });
      },
      (err) => {
        setError(err.message);
        setLoading(false);
        setDbStatus({ status: 'error', msg: err.message });
      }
    );
    return () => unsubscribe();
  }, [user, setError]);

  const handleRejectDeal = useCallback(async (dealId) => {
    try { await rejectDeal(dealId); } catch (e) { setError(e.message); }
  }, [setError]);

  const handleDeleteDeal = useCallback(async (dealId) => {
    if (window.confirm("Voulez-vous vraiment supprimer définitivement cette annonce ?")) {
      try { await deleteDeal(dealId); } catch (e) { setError(e.message); }
    }
  }, [setError]);

  const handleRetryAnalysis = useCallback(async (dealId) => {
    setDeals(prev => prev.map(d => d.id === dealId ? { ...d, status: 'analyzing', aiAnalysis: { ...d.aiAnalysis, reasoning: undefined, verdict: undefined } } : d));
    try { await retryDealAnalysis(dealId); } catch (e) { setError(e.message); }
  }, [setError]);

  const handleForceExpertAnalysis = useCallback(async (dealId) => {
    setDeals(prev => prev.map(d => d.id === dealId ? { ...d, status: 'analyzing_expert', aiAnalysis: { ...d.aiAnalysis, reasoning: undefined, verdict: undefined } } : d));
    try { await forceExpertAnalysis(dealId); } catch (e) { setError(e.message); }
  }, [setError]);

  const handleToggleFavorite = useCallback(async (dealId, currentStatus) => {
    try { await toggleDealFavorite(dealId, currentStatus); } catch (e) { setError(e.message); }
  }, [setError]);

  const taxonomyPaths = useMemo(() => {
    const paths = {};
    const traverse = (node, currentPath) => {
      if (Array.isArray(node)) {
        node.forEach(item => { paths[item] = [...currentPath, item]; });
      } else if (typeof node === 'object' && node !== null) {
        Object.keys(node).forEach(key => {
          const newPath = [...currentPath, key];
          paths[key] = newPath;
          traverse(node[key], newPath);
        });
      }
    };
    traverse(GUITAR_TAXONOMY, []);
    return paths;
  }, []);

  const level1Options = useMemo(() => ['ALL', ...Object.keys(GUITAR_TAXONOMY)], []);
  const level2Options = useMemo(() => {
    if (level1Filter === 'ALL' || !GUITAR_TAXONOMY[level1Filter]) return ['ALL'];
    const node = GUITAR_TAXONOMY[level1Filter];
    return ['ALL', ...(Array.isArray(node) ? node : Object.keys(node))];
  }, [level1Filter]);
  const level3Options = useMemo(() => {
    if (level2Filter === 'ALL' || level1Filter === 'ALL') return ['ALL'];
    const node1 = GUITAR_TAXONOMY[level1Filter];
    if (Array.isArray(node1)) return ['ALL'];
    const node2 = node1[level2Filter];
    if (!node2 || Array.isArray(node2)) return ['ALL'];
    return ['ALL', ...Object.keys(node2)];
  }, [level1Filter, level2Filter]);

  useEffect(() => { setLevel2Filter('ALL'); setLevel3Filter('ALL'); }, [level1Filter]);
  useEffect(() => { setLevel3Filter('ALL'); }, [level2Filter]);

  // --- CALCUL DES COMPTEURS POUR LES FILTRES DE TYPE ---
  // On calcule ces compteurs séparément pour qu'ils ne dépendent pas des filtres actifs
  const typeCounts = useMemo(() => {
    const c = {};
    deals.forEach(deal => {
        if (deal.status === 'rejected') return;
        const classification = deal.aiAnalysis?.classification;
        if (!classification) return;
        
        const path = taxonomyPaths[classification];
        if (path) {
            // Niveau 1
            if (path[0]) c[path[0]] = (c[path[0]] || 0) + 1;
            // Niveau 2
            if (path[1]) c[path[1]] = (c[path[1]] || 0) + 1;
            // Niveau 3
            if (path[2]) c[path[2]] = (c[path[2]] || 0) + 1;
        }
    });
    return c;
  }, [deals, taxonomyPaths]);

  const filteredDeals = useMemo(() => {
    return deals.filter(deal => {
      const analysis = deal.aiAnalysis || {};
      const verdict = analysis.verdict || 'PENDING';
      const status = deal.status;
      
      const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || (!analysis.reasoning && verdict !== 'PENDING');

      if (filterType === 'ERROR') return isError && status !== 'rejected';
      if (filterType === 'REJECTED') return status === 'rejected';
      if (filterType === 'FAVORITES') return deal.isFavorite;
      if (status === 'rejected') return false;
      if (filterType !== 'ALL' && isError) return false;

      const matchesType = filterType === 'ALL' || verdict === filterType;
      
      const matchesSearch = !searchQuery || deal.title?.toLowerCase().includes(searchQuery.toLowerCase());

      let matchesClassification = true;
      if (level1Filter !== 'ALL') {
        const path = taxonomyPaths[analysis.classification];
        if (!path || path[0] !== level1Filter) matchesClassification = false;
        if (matchesClassification && level2Filter !== 'ALL' && (path.length < 2 || path[1] !== level2Filter)) matchesClassification = false;
        if (matchesClassification && level3Filter !== 'ALL' && (path.length < 3 || path[2] !== level3Filter)) matchesClassification = false;
      }

      return matchesType && matchesSearch && matchesClassification;
    });
  }, [deals, filterType, searchQuery, level1Filter, level2Filter, level3Filter, taxonomyPaths]);
  
  const counts = useMemo(() => {
    const initialCounts = { ALL: 0, FAVORITES: 0, REJECTED: 0, ERROR: 0 };
    Object.keys(VERDICTS).forEach(key => {
      initialCounts[key] = 0;
    });

    deals.forEach(deal => {
        const verdict = deal.aiAnalysis?.verdict || 'PENDING';
        const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || (!deal.aiAnalysis.reasoning && verdict !== 'PENDING');
        
        if (deal.status !== 'rejected') {
            initialCounts.ALL++;
            if (isError) initialCounts.ERROR++;
            else if (initialCounts.hasOwnProperty(verdict)) {
                initialCounts[verdict]++;
            }
        }
        if (deal.isFavorite) initialCounts.FAVORITES++;
        if (deal.status === 'rejected') initialCounts.REJECTED++;
    });
    
    // On fusionne les compteurs de verdict avec les compteurs de type
    return { ...initialCounts, ...typeCounts };
  }, [deals, typeCounts]);

  return {
    deals,
    loading,
    dbStatus,
    filteredDeals,
    counts,
    filterProps: {
      filterType, setFilterType,
      searchQuery, setSearchQuery,
      level1Filter, setLevel1Filter,
      level2Filter, setLevel2Filter,
      level3Filter, setLevel3Filter,
      level1Options,
      level2Options,
      level3Options,
      counts,
    },
    dealActions: {
      handleRejectDeal,
      handleDeleteDeal,
      handleRetryAnalysis,
      handleForceExpertAnalysis,
      handleToggleFavorite
    }
  };
};
