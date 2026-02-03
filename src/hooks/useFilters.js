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
    return ['ALL', ...(Array.isArray(node) ? node : Object.keys(node))];
  }, [level1Filter]);
  const level3Options = useMemo(() => {
    if (level2Filter === 'ALL' || level1Filter === 'ALL') return ['ALL'];
    const node1 = GUITAR_TAXONOMY[level1Filter];
    if (!node1 || Array.isArray(node1)) return ['ALL'];
    const node2 = node1[level2Filter];
    if (!node2) return ['ALL'];
    return ['ALL', ...(Array.isArray(node2) ? node2 : Object.keys(node2))];
  }, [level1Filter, level2Filter]);

  // Reset sub-filters
  useEffect(() => { setLevel2Filter('ALL'); setLevel3Filter('ALL'); }, [level1Filter]);
  useEffect(() => { setLevel3Filter('ALL'); }, [level2Filter]);

  // Filtered Deals
  const filteredDeals = useMemo(() => {
    return deals.filter(deal => {
      const analysis = deal.aiAnalysis || {};
      const verdict = analysis.verdict || 'PENDING';
      const status = deal.status;
      const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || !analysis.reasoning;

      if (filterType === 'ERROR') return isError && status !== 'rejected';
      if (filterType === 'REJECTED') return status === 'rejected';
      if (filterType === 'FAVORITES') return deal.isFavorite;
      if (status === 'rejected') return false;
      if (filterType !== 'ALL' && isError) return false;

      const matchesType = filterType === 'ALL' || verdict === filterType;
      const matchesSearch = deal.title?.toLowerCase().includes(searchQuery.toLowerCase());
      
      let matchesClassification = true;
      if (level1Filter !== 'ALL') {
        const path = taxonomyPaths[analysis.classification];
        if (!path) matchesClassification = false;
        else {
          if (path[0] !== level1Filter) matchesClassification = false;
          if (matchesClassification && level2Filter !== 'ALL' && (path.length < 2 || path[1] !== level2Filter)) matchesClassification = false;
          if (matchesClassification && level3Filter !== 'ALL' && (path.length < 3 || path[2] !== level3Filter)) matchesClassification = false;
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
  };
};