import { useState, useMemo, useEffect } from 'react';
import promptsData from '../../prompts.json';

const GUITAR_TAXONOMY = promptsData.taxonomy_guitares || {};

export const useFilters = (deals) => {
  // Filter States
  const [filterType, setFilterType] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [level1Filter, setLevel1Filter] = useState('ALL');
  const [level2Filter, setLevel2Filter] = useState('ALL');
  const [level3Filter, setLevel3Filter] = useState('ALL');

  // Taxonomy Path Finder
  const taxonomyPaths = useMemo(() => {
    const paths = {};
    const traverse = (node, currentPath) => {
      if (Array.isArray(node)) {
        node.forEach(item => {
          paths[item] = [...currentPath, item];
        });
      } else if (typeof node === 'object' && node !== null) {
        Object.keys(node).forEach(key => {
          traverse(node[key], [...currentPath, key]);
        });
      }
    };
    traverse(GUITAR_TAXONOMY, []);
    return paths;
  }, []);

  // Filter Options
  const level1Options = useMemo(() => ['ALL', ...Object.keys(GUITAR_TAXONOMY)], []);
  
  const level2Options = useMemo(() => {
    if (level1Filter === 'ALL' || !GUITAR_TAXONOMY[level1Filter]) return ['ALL'];
    const node = GUITAR_TAXONOMY[level1Filter];
    // Si le noeud est un tableau (feuille directe), on retourne les éléments
    if (Array.isArray(node)) return ['ALL', ...node];
    // Sinon c'est un objet, on retourne ses clés
    return ['ALL', ...Object.keys(node)];
  }, [level1Filter]);

  const level3Options = useMemo(() => {
    if (level2Filter === 'ALL' || level1Filter === 'ALL') return ['ALL'];
    const node1 = GUITAR_TAXONOMY[level1Filter];
    
    // Si node1 est un tableau, il n'y a pas de niveau 3
    if (Array.isArray(node1)) return ['ALL'];
    
    const node2 = node1[level2Filter];
    if (!node2) return ['ALL'];
    
    // Si node2 est un tableau, ce sont les options finales
    if (Array.isArray(node2)) return ['ALL', ...node2];
    
    // Si c'est encore un objet (cas rare dans cette taxonomie mais possible), on prend les clés
    return ['ALL', ...Object.keys(node2)];
  }, [level1Filter, level2Filter]);

  // Reset sub-filters when parent changes
  useEffect(() => { setLevel2Filter('ALL'); setLevel3Filter('ALL'); }, [level1Filter]);
  useEffect(() => { setLevel3Filter('ALL'); }, [level2Filter]);

  // --- COUNTS CALCULATION ---
  const counts = useMemo(() => {
    const c = {
        ALL: 0,
        FAVORITES: 0,
        REJECTED: 0,
        ERROR: 0,
        // Taxonomy counts (Level 1 only for simplicity)
        ...Object.keys(GUITAR_TAXONOMY).reduce((acc, key) => ({ ...acc, [key]: 0 }), {})
    };

    deals.forEach(deal => {
        const analysis = deal.aiAnalysis || {};
        const verdict = analysis.verdict || 'PENDING';
        const status = deal.status;
        const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || !analysis.reasoning;
        const isRejected = status === 'rejected';

        // Global counts
        if (!isRejected) {
            c.ALL++;
            if (isError) {
                c.ERROR++;
            } else {
                // Compte dynamique par verdict (ex: PEPITE, GOOD_DEAL, etc.)
                c[verdict] = (c[verdict] || 0) + 1;
            }
        }
        
        if (deal.isFavorite) c.FAVORITES++;
        if (isRejected) c.REJECTED++;

        // Taxonomy counts (only for active deals)
        if (!isRejected && !isError) {
            const classification = analysis.classification;
            const path = taxonomyPaths[classification];
            if (path && path.length > 0) {
                const rootCategory = path[0];
                if (c.hasOwnProperty(rootCategory)) {
                    c[rootCategory]++;
                }
            }
        }
    });

    return c;
  }, [deals, taxonomyPaths]);

  // Filtered Deals
  const filteredDeals = useMemo(() => {
    return deals.filter(deal => {
      const analysis = deal.aiAnalysis || {};
      const verdict = analysis.verdict || 'PENDING';
      const status = deal.status;
      const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || !analysis.reasoning;

      // 1. Filtre par Type (Onglets)
      if (filterType === 'ERROR') return isError && status !== 'rejected';
      if (filterType === 'REJECTED') return status === 'rejected';
      if (filterType === 'FAVORITES') return deal.isFavorite;
      
      // Exclusion par défaut des rejetés et erreurs dans les autres vues
      if (status === 'rejected') return false;
      if (filterType !== 'ALL' && isError) return false;

      const matchesType = filterType === 'ALL' || verdict === filterType;
      
      // 2. Filtre par Recherche Texte
      const matchesSearch = deal.title?.toLowerCase().includes(searchQuery.toLowerCase());
      
      // 3. Filtre par Taxonomie (Cascading Selects)
      let matchesClassification = true;
      if (level1Filter !== 'ALL') {
        const classification = analysis.classification;
        const path = taxonomyPaths[classification];
        
        if (!path) {
            // Si la classification n'est pas dans la taxonomie connue, on exclut
            matchesClassification = false;
        } else {
          // Vérification Niveau 1
          if (path[0] !== level1Filter) matchesClassification = false;
          
          // Vérification Niveau 2
          if (matchesClassification && level2Filter !== 'ALL') {
             // Si le chemin est trop court, ça ne matche pas
             if (path.length < 2 || path[1] !== level2Filter) matchesClassification = false;
          }
          
          // Vérification Niveau 3
          if (matchesClassification && level3Filter !== 'ALL') {
             // Le niveau 3 doit correspondre exactement à la feuille ou au 3ème élément
             if (path.length < 3 || path[2] !== level3Filter) matchesClassification = false;
          }
        }
      }

      return matchesType && matchesSearch && matchesClassification;
    });
  }, [deals, filterType, searchQuery, level1Filter, level2Filter, level3Filter, taxonomyPaths]);

  return {
    filteredDeals,
    filterType, setFilterType,
    searchQuery, setSearchQuery,
    level1Filter, setLevel1Filter,
    level2Filter, setLevel2Filter,
    level3Filter, setLevel3Filter,
    level1Options,
    level2Options,
    level3Options,
    counts, // Export des compteurs
  };
};
