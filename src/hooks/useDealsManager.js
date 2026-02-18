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
import { NEW_VERDICTS, LEGACY_VERDICTS } from '../constants';

const ALL_VERDICTS = { ...NEW_VERDICTS, ...LEGACY_VERDICTS };
const GUITAR_TAXONOMY = promptsData.taxonomy_guitares || {};

// Helper pour normaliser les chaînes pour la comparaison (minuscules, sans espaces, SANS ACCENTS)
const normalize = (str) => {
  if (!str) return '';
  return str
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "") // Enlève les accents
    .toLowerCase()
    .replace(/[^a-z0-9]/g, ''); // Ne garde que alphanumérique
};

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

  // Construction de la map de chemins normalisés
  const taxonomyPaths = useMemo(() => {
    const paths = {};
    const traverse = (node, currentPath) => {
      if (Array.isArray(node)) {
        node.forEach(item => { 
            paths[normalize(item)] = [...currentPath, item]; 
        });
      } else if (typeof node === 'object' && node !== null) {
        Object.keys(node).forEach(key => {
          const newPath = [...currentPath, key];
          paths[normalize(key)] = newPath;
          traverse(node[key], newPath);
        });
      }
    };
    traverse(GUITAR_TAXONOMY, []);
    return paths;
  }, []);

  const level1Options = useMemo(() => ['ALL', ...Object.keys(GUITAR_TAXONOMY), 'OTHER'], []);
  
  const level2Options = useMemo(() => {
    if (level1Filter === 'ALL' || level1Filter === 'OTHER' || !GUITAR_TAXONOMY[level1Filter]) return ['ALL'];
    const node = GUITAR_TAXONOMY[level1Filter];
    return ['ALL', ...(Array.isArray(node) ? node : Object.keys(node))];
  }, [level1Filter]);
  
  const level3Options = useMemo(() => {
    if (level2Filter === 'ALL' || level1Filter === 'ALL' || level1Filter === 'OTHER') return ['ALL'];
    const node1 = GUITAR_TAXONOMY[level1Filter];
    if (Array.isArray(node1)) return ['ALL'];
    const node2 = node1[level2Filter];
    if (!node2 || Array.isArray(node2)) return ['ALL'];
    return ['ALL', ...Object.keys(node2)];
  }, [level1Filter, level2Filter]);

  useEffect(() => { setLevel2Filter('ALL'); setLevel3Filter('ALL'); }, [level1Filter]);
  useEffect(() => { setLevel3Filter('ALL'); }, [level2Filter]);

  // --- LOGIQUE DE FILTRAGE ET COMPTAGE DYNAMIQUE ---

  // 1. Helper pour vérifier si un deal correspond au filtre de VERDICT
  const matchesVerdictFilter = useCallback((deal, currentFilterType) => {
      if (deal.status === 'rejected') return false;
      const analysis = deal.aiAnalysis || {};
      const verdict = analysis.verdict || 'PENDING';
      const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || (!analysis.reasoning && verdict !== 'PENDING');

      if (currentFilterType === 'ERROR') return isError;
      if (currentFilterType === 'REJECTED') return false; // Les rejetés sont gérés à part
      if (currentFilterType === 'FAVORITES') return deal.isFavorite;
      if (currentFilterType !== 'ALL' && isError) return false;
      
      // Si le filtre est ALL, on accepte tout sauf les erreurs (sauf si on veut voir les erreurs dans ALL ?)
      // Généralement ALL montre tout ce qui est valide.
      if (currentFilterType === 'ALL') return !isError;

      return verdict === currentFilterType;
  }, []);

  // 2. Helper pour vérifier si un deal correspond aux filtres de TYPE
  const matchesTypeFilter = useCallback((deal, l1, l2, l3, search) => {
      if (deal.status === 'rejected') return false;
      
      // Recherche textuelle
      if (search && !deal.title?.toLowerCase().includes(search.toLowerCase())) return false;

      // Classification
      const analysis = deal.aiAnalysis || {};
      const classification = analysis.classification;
      const path = classification ? taxonomyPaths[normalize(classification)] : null;

      if (l1 !== 'ALL') {
        if (l1 === 'OTHER') {
            if (path) return false; // Si c'est classé, ce n'est pas OTHER
        } else {
            if (!path || path[0] !== l1) return false;
            if (l2 !== 'ALL' && (path.length < 2 || path[1] !== l2)) return false;
            if (l3 !== 'ALL' && (path.length < 3 || path[2] !== l3)) return false;
        }
      }
      return true;
  }, [taxonomyPaths]);

  // 3. Calcul des compteurs de TYPE (Basé sur les deals filtrés par VERDICT)
  const typeCounts = useMemo(() => {
    const c = { OTHER: 0 };
    deals.forEach(deal => {
        // On n'inclut que les deals qui passent le filtre de verdict actuel
        if (!matchesVerdictFilter(deal, filterType)) return;

        const classification = deal.aiAnalysis?.classification;
        if (!classification) {
            c.OTHER++;
            return;
        }
        
        const path = taxonomyPaths[normalize(classification)];
        if (path) {
            if (path[0]) c[path[0]] = (c[path[0]] || 0) + 1;
            if (path[1]) c[path[1]] = (c[path[1]] || 0) + 1;
            if (path[2]) c[path[2]] = (c[path[2]] || 0) + 1;
        } else {
            c.OTHER++;
        }
    });
    return c;
  }, [deals, filterType, matchesVerdictFilter, taxonomyPaths]);

  // 4. Calcul des compteurs de VERDICT (Basé sur les deals filtrés par TYPE)
  const verdictCounts = useMemo(() => {
    const c = { ALL: 0, FAVORITES: 0, REJECTED: 0, ERROR: 0 };
    // Initialiser tous les compteurs de verdicts possibles
    Object.keys(ALL_VERDICTS).forEach(key => c[key] = 0);

    deals.forEach(deal => {
        // Cas spécial : REJECTED compte tous les rejetés
        if (deal.status === 'rejected') {
            c.REJECTED++;
            return;
        }

        // On n'inclut que les deals qui passent les filtres de type actuels
        if (!matchesTypeFilter(deal, level1Filter, level2Filter, level3Filter, searchQuery)) return;

        const verdict = deal.aiAnalysis?.verdict || 'PENDING';
        const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || (!deal.aiAnalysis.reasoning && verdict !== 'PENDING');
        
        if (isError) {
            c.ERROR++;
        } else {
            c.ALL++; // ALL compte tous les verdicts valides
            if (c.hasOwnProperty(verdict)) {
                c[verdict]++;
            }
        }
        if (deal.isFavorite) c.FAVORITES++;
    });
    return c;
  }, [deals, level1Filter, level2Filter, level3Filter, searchQuery, matchesTypeFilter]);

  // 5. Liste finale filtrée (Intersection des deux filtres)
  const filteredDeals = useMemo(() => {
    return deals.filter(deal => {
        if (filterType === 'REJECTED') return deal.status === 'rejected';
        
        // Pour les autres filtres, on combine verdict et type
        const verdictMatch = matchesVerdictFilter(deal, filterType);
        const typeMatch = matchesTypeFilter(deal, level1Filter, level2Filter, level3Filter, searchQuery);
        
        return verdictMatch && typeMatch;
    });
  }, [deals, filterType, level1Filter, level2Filter, level3Filter, searchQuery, matchesVerdictFilter, matchesTypeFilter]);
  
  const counts = useMemo(() => ({ ...verdictCounts, ...typeCounts }), [verdictCounts, typeCounts]);

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
