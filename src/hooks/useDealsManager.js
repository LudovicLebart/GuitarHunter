import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  onDealsIndexUpdate,
  fetchDealsByIds,
  rejectDeal,
  deleteDeal,
  retryDealAnalysis,
  forceExpertAnalysis,
  toggleDealFavorite
} from '../services/firestoreService';
import promptsData from '../../prompts.json';
import { NEW_VERDICTS, LEGACY_VERDICTS, ARCHIVE_GROUP, computeInterestScore } from '../constants';

const ALL_VERDICTS = { ...NEW_VERDICTS, ...LEGACY_VERDICTS };
const MASTER_TAXONOMY = promptsData.taxonomy_master || {};

// Helper pour normaliser les chaînes pour la comparaison (minuscules, sans espaces, SANS ACCENTS)
const normalize = (str) => {
  if (!str) return '';
  return str
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "") // Enlève les accents
    .toLowerCase()
    .replace(/[^a-z0-9]/g, ''); // Ne garde que alphanumérique
};

// Recherche floue : retourne le path dont la CLÉ TEXTUELLE est la plus longue (donc la plus
// spécifique) parmi toutes les clés de taxonomie contenues dans la string. Les clés trop courtes
// (< FUZZY_MIN_KEY_LENGTH, ex: "sg", "aer") sont exclues de cette recherche par sous-chaîne : comme
// normalize() supprime les espaces, un texte comme "cordes guitare" devient "cordesguitare" et
// contiendrait accidentellement "sg" à la jonction des deux mots. Ces clés courtes ne doivent être
// résolues que par correspondance EXACTE (déjà tentée avant cet appel), jamais en sous-chaîne floue.
// Idem pour la branche "etui_housse" : ses leafs ("Guitare Electrique", "Guitare Acoustique", "Basse")
// reprennent tels quels les mots des types d'instruments qu'ils contiennent, donc entrent quasi
// systématiquement en collision avec le texte décrivant une vraie guitare. Ses valeurs sont un
// ensemble fixe et restreint que l'IA cible déjà en correspondance exacte — la recherche floue n'y
// apporte rien et n'y introduit que du risque.
// Enfin, les clés de profondeur 1 (ex: "guitare" seul) sont exclues : ce sont les noms de branches
// racines, présents dans la quasi-totalité des textes du domaine, donc sans pouvoir discriminant —
// et un match sur la branche racine seule n'apporte rien ici, puisque tout chemin plus profond qui
// matche déjà satisfait le préfixe "guitare." attendu par un filtre sur la catégorie racine.
const FUZZY_MIN_KEY_LENGTH = 5;
const FUZZY_EXCLUDED_BRANCHES = ['etui_housse'];
const findPathFuzzy = (normalizedSearchStr, taxonomyPaths) => {
  let bestKey = null;
  let bestPath = null;
  for (const [key, path] of Object.entries(taxonomyPaths)) {
    if (key.length < FUZZY_MIN_KEY_LENGTH) continue;
    if (path.length < 2) continue;
    if (FUZZY_EXCLUDED_BRANCHES.includes(path[0])) continue;
    if (normalizedSearchStr.includes(key)) {
      if (!bestKey || key.length > bestKey.length) {
        bestKey = key;
        bestPath = path;
      }
    }
  }
  return bestPath;
};

export const useDealsManager = (user, setError, uiFilters, saveUiFilters) => {
  const [dealsIndexMap, setDealsIndexMap] = useState({});
  const [loadedDeals, setLoadedDeals] = useState({});
  const [visibleCount, setVisibleCount] = useState(30);
  const [loading, setLoading] = useState(true);
  const [selectedDeal, setSelectedDeal] = useState(null);
  const [dbStatus, setDbStatus] = useState({ status: 'pending', msg: 'En attente' });
  // Ref pour tracker les IDs en cours de fetch et éviter les double-appels réseau au scroll rapide
  const fetchingIdsRef = useRef(new Set());

  const [filterType, setFilterType] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  // Chemins de taxonomie sélectionnés (multi-sélection, ex: ["guitare.acoustique_acier.formes_standard.Parlor",
  // "guitare.acoustique_acier.specialites.Travel.Baby / Mini"]) — un tableau vide = "Tous les types".
  // Un deal correspond si son chemin de classification égale ou descend (préfixe) d'AU MOINS un chemin sélectionné.
  const [selectedTypePaths, setSelectedTypePaths] = useState([]);
  const [conditionFilter, setConditionFilter] = useState('ALL');
  const [priceFilter, setPriceFilter] = useState('ALL');
  const [sortMode, setSortMode] = useState('date'); // 'date' | 'interest'

  // Reconstruction des deals légers à partir de l'index
  const deals = useMemo(() => {
    return Object.entries(dealsIndexMap).map(([id, entry]) => ({
      id,
      status: entry.s,
      location: entry.l,
      storageImageUrls: entry.i ? [entry.i] : [],
      initialModelUsed: entry.imu,
      aiAnalysis: {
        verdict: entry.v,
        classification: entry.c,
        condition_score: entry.cs,
        also_qualifies_pepite: entry.ap,
        deal_score: entry.is,
        estimated_value: entry.ev,
        model_used: entry.mu,
        estimated_gross_margin: entry.egm,
        brand: entry.b,
        model_name: entry.mn,
        color: entry.co
      },
      isFavorite: entry.f,
      timestamp: entry.t ? { seconds: entry.t } : null,
      publishTimestamp: entry.pt ? { seconds: entry.pt } : null,
      soldTimestamp: entry.st ? { seconds: entry.st } : null,
      price: entry.p,
      title: entry.title,
      chunkId: entry.h,
      interestScore: entry.is
    }));
  }, [dealsIndexMap]);

  // --- Persistance des filtres par utilisateur (Firestore, via useBotConfig) ---
  const hydratedFiltersRef = useRef(false);

  // Hydratation : au premier chargement de uiFilters depuis Firestore (objet non-null,
  // potentiellement {} si rien n'a jamais été sauvegardé), on applique les valeurs connues une
  // seule fois. Les rechargements suivants de uiFilters (ex: nos propres writes) sont ignorés.
  useEffect(() => {
    if (uiFilters == null || hydratedFiltersRef.current) return;
    hydratedFiltersRef.current = true;
    if (uiFilters.filterType) setFilterType(uiFilters.filterType);
    if (Array.isArray(uiFilters.selectedTypePaths)) {
      setSelectedTypePaths(uiFilters.selectedTypePaths);
    } else if (uiFilters.level1Filter && uiFilters.level1Filter !== 'ALL') {
      // Migration douce depuis l'ancien format (un seul chemin en cascade level1..4) :
      // reconstruit le chemin déjà sélectionné par l'utilisateur plutôt que de le perdre.
      if (uiFilters.level1Filter === 'OTHER') {
        setSelectedTypePaths(['OTHER']);
      } else {
        const legacyPath = [uiFilters.level1Filter, uiFilters.level2Filter, uiFilters.level3Filter, uiFilters.level4Filter]
          .filter(v => v && v !== 'ALL')
          .join('.');
        if (legacyPath) setSelectedTypePaths([legacyPath]);
      }
    }
    if (uiFilters.conditionFilter) setConditionFilter(uiFilters.conditionFilter);
    if (uiFilters.priceFilter) setPriceFilter(uiFilters.priceFilter);
    if (uiFilters.sortMode) setSortMode(uiFilters.sortMode);
  }, [uiFilters]);

  // Sauvegarde (debouncée dans saveUiFilters) à chaque changement de filtre, une fois hydraté —
  // pour ne pas écraser une valeur sauvegardée par la valeur par défaut avant son chargement.
  useEffect(() => {
    if (!hydratedFiltersRef.current || !saveUiFilters) return;
    saveUiFilters({
      filterType, selectedTypePaths,
      conditionFilter, priceFilter, sortMode
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType, selectedTypePaths, conditionFilter, priceFilter, sortMode]);

  // Reset visibleCount when filters change
  useEffect(() => {
    setVisibleCount(30);
  }, [filterType, selectedTypePaths, conditionFilter, priceFilter, searchQuery]);

  useEffect(() => {
    if (!user) return;
    const uid = user.uid;
    const unsubscribe = onDealsIndexUpdate(
      (indexMap, count) => {
        setDealsIndexMap(indexMap);
        setLoading(false);
        setDbStatus({ status: 'success', msg: `${count} annonces` });
      },
      (err) => {
        setError(err.message);
        setLoading(false);
        setDbStatus({ status: 'error', msg: err.message });
      },
      uid
    );
    return () => unsubscribe();
  }, [user, setError]);

  const handleRejectDeal = useCallback(async (dealId) => {
    if (!user) return;
    const chunkId = dealsIndexMap[dealId]?.h;
    try { await rejectDeal(dealId, chunkId, user.uid); } catch (e) { setError(e.message); }
  }, [user, dealsIndexMap, setError]);

  const handleDeleteDeal = useCallback(async (dealId) => {
    if (!user) return;
    if (window.confirm("Voulez-vous vraiment supprimer définitivement cette annonce ?")) {
      const chunkId = dealsIndexMap[dealId]?.h;
      try { await deleteDeal(dealId, chunkId, user.uid); } catch (e) { setError(e.message); }
    }
  }, [user, dealsIndexMap, setError]);

  const handleRetryAnalysis = useCallback(async (dealId, userComment = '') => {
    if (!user) return;
    setDealsIndexMap(prev => {
      const next = { ...prev };
      if (next[dealId]) {
        next[dealId] = { ...next[dealId], s: 'analyzing', v: undefined };
      }
      return next;
    });
    try { await retryDealAnalysis(dealId, user.uid, userComment); } catch (e) { setError(e.message); }
  }, [user, setError]);

  const handleForceExpertAnalysis = useCallback(async (dealId, userComment = '') => {
    if (!user) return;
    setDealsIndexMap(prev => {
      const next = { ...prev };
      if (next[dealId]) {
        next[dealId] = { ...next[dealId], s: 'analyzing_expert', v: undefined };
      }
      return next;
    });
    try { await forceExpertAnalysis(dealId, user.uid, userComment); } catch (e) { setError(e.message); }
  }, [user, setError]);

  const handleToggleFavorite = useCallback(async (dealId, currentStatus) => {
    if (!user) return;
    const chunkId = dealsIndexMap[dealId]?.h;
    try { await toggleDealFavorite(dealId, currentStatus, chunkId, user.uid); } catch (e) { setError(e.message); }
  }, [user, dealsIndexMap, setError]);

  // Construction de la map de chemins normalisés
  const { taxonomyFullPaths, taxonomyLeafPaths } = useMemo(() => {
    const fullPaths = {};
    const leafPaths = {};
    const traverse = (node, currentPath) => {
      if (Array.isArray(node)) {
        node.forEach(item => {
          const path = [...currentPath, item];
          const fullKey = normalize(path.join('.'));
          const leafKey = normalize(item);
          fullPaths[fullKey] = path;
          // Leaf only: prioritize the deeper node if there's a collision? 
          // For now, simple leaf mapping for fallback.
          leafPaths[leafKey] = path;
        });
      } else if (typeof node === 'object' && node !== null) {
        Object.keys(node).forEach(key => {
          const path = [...currentPath, key];
          const fullKey = normalize(path.join('.'));
          const leafKey = normalize(key);
          fullPaths[fullKey] = path;
          leafPaths[leafKey] = path;
          traverse(node[key], path);
        });
      }
    };
    traverse(MASTER_TAXONOMY, []);
    return { taxonomyFullPaths: fullPaths, taxonomyLeafPaths: leafPaths };
  }, []);

  // Multi-sélection : coche/décoche un chemin de taxonomie (ex: "guitare.acoustique_acier.formes_standard.Parlor").
  const toggleTypePath = useCallback((path) => {
    setSelectedTypePaths(prev => prev.includes(path) ? prev.filter(p => p !== path) : [...prev, path]);
  }, []);

  // --- LOGIQUE DE FILTRAGE ET COMPTAGE DYNAMIQUE ---

  // 1. Helper pour vérifier si un deal correspond au filtre de VERDICT
  const matchesVerdictFilter = useCallback((deal, currentFilterType) => {
    if (deal.status === 'rejected') return false;
    const analysis = deal.aiAnalysis || {};
    const verdict = analysis.verdict || 'PENDING';
    // Un verdict "connu" est soit PENDING, soit présent dans la taxonomie (NEW/LEGACY), soit
    // dans ARCHIVE_GROUP (ex: 'SOLD' legacy). Tout le reste (ex: 'ERROR_GATEKEEPER' renvoyé par
    // le backend en cas de double échec Tier1+Tier2) est traité comme une erreur, même avec un
    // reasoning non vide, pour ne pas polluer la vue "Toutes" avec un badge par défaut trompeur.
    const knownVerdict = verdict === 'PENDING' || !!ALL_VERDICTS[verdict] || ARCHIVE_GROUP.includes(verdict);
    const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || !knownVerdict;

    if (currentFilterType === 'ERROR') return isError;
    if (currentFilterType === 'REJECTED') return false;
    if (currentFilterType === 'SOLD') return deal.status === 'sold';

    // Si l'annonce est vendue et qu'on n'est pas dans le filtre SOLD, on cache (sauf favoris)
    if (deal.status === 'sold' && currentFilterType !== 'FAVORITES') return false;

    // Favoris : on montre le favori sauf s'il est tombé dans le bruit (erreur d'analyse, ou
    // verdict archivé autre que BAD_DEAL — "trop cher" reste un favori légitime, le reste non).
    if (currentFilterType === 'FAVORITES') {
      if (isError) return false;
      if (ARCHIVE_GROUP.includes(verdict) && verdict !== 'BAD_DEAL') return false;
      return deal.isFavorite;
    }

    // Si on demande explicitement un verdict (ex: REJECTED_ITEM), on le montre
    if (currentFilterType === verdict) return true;

    // Double appartenance : une annonce FAST_FLIP/LUTHIER_PROJ/CASE_WIN/COLLECTION qui
    // remplit aussi les critères Pépite doit apparaître dans le filtre Pépites également.
    if (currentFilterType === 'PEPITE' && analysis.also_qualifies_pepite) return true;

    // Si le filtre est ALL (ou un filtre implicite via les types), on applique le nettoyage
    if (currentFilterType === 'ALL') {
      if (isError) return false;
      // EXCLUSION DU BRUIT : Si le verdict est dans le groupe ARCHIVE, on le cache de la vue ALL
      if (ARCHIVE_GROUP.includes(verdict)) return false;
      return true;
    }

    return false;
  }, []);

  // 2. Helper pour vérifier si un deal correspond aux filtres de TYPE (multi-sélection)
  const matchesTypeFilter = useCallback((deal, typePaths, search) => {
    if (deal.status === 'rejected') return false;
    // Note: Pour le type filter, on ne bloque pas 'sold' ici car matchesVerdictFilter s'en charge.

    // Recherche textuelle (titre + marque/modèle/couleur identifiés par l'IA)
    const analysis = deal.aiAnalysis || {};
    if (search) {
      const needle = search.toLowerCase();
      const haystack = [deal.title, analysis.brand, analysis.model_name, analysis.color]
        .filter(Boolean).join(' ').toLowerCase();
      if (!haystack.includes(needle)) return false;
    }

    if (!typePaths || typePaths.length === 0) return true; // Aucune sélection = Tous les types

    // Classification
    const classification = analysis.classification;
    if (!classification) return typePaths.includes('OTHER');

    const normalizedClass = normalize(classification);
    // 1. Try exact full path lookup
    let path = taxonomyFullPaths[normalizedClass];
    // 2. Fallback to leaf lookup
    if (!path) path = taxonomyLeafPaths[normalizedClass];
    // 3. Last resort fuzzy search
    if (!path) path = findPathFuzzy(normalizedClass, taxonomyLeafPaths);
    if (!path) return typePaths.includes('OTHER');

    // Un deal correspond si son chemin égale ou descend (préfixe) d'AU MOINS un des chemins
    // sélectionnés — permet de cocher "Parlor" ET "Baby / Mini" simultanément même si ces deux
    // catégories se trouvent dans des branches différentes de la taxonomie.
    const fullPathStr = path.join('.');
    return typePaths.some(selected =>
      selected === fullPathStr || fullPathStr.startsWith(`${selected}.`)
    );
  }, [taxonomyFullPaths, taxonomyLeafPaths]);

  // 2.5 Helper pour vérifier si un deal correspond aux filtres de PRIX et CONDITION
  const matchesConditionAndPrice = useCallback((deal, condition, priceFilter) => {
    // === CONDITION ===
    if (condition !== 'ALL') {
      const conditionScore = deal.aiAnalysis?.condition_score;
      if (conditionScore == null) return false; // Si pas de score, on exclut

      if (condition === 'excellent' && conditionScore < 8) return false;
      if (condition === 'good' && conditionScore < 5) return false;
      if (condition === 'project' && conditionScore >= 5) return false;
    }

    // === PRICE ===
    if (priceFilter !== 'ALL') {
      const price = deal.price;
      if (price == null) return false; // Si pas de prix, on exclut

      if (priceFilter === 'under100' && price >= 100) return false;
      if (priceFilter === '100-300' && (price < 100 || price > 300)) return false;
      if (priceFilter === '300-600' && (price < 300 || price > 600)) return false;
      if (priceFilter === 'over600' && price <= 600) return false;
    }

    return true;
  }, []);

  // 3. Calcul des compteurs de TYPE (Basé sur les deals filtrés par VERDICT, CONDITION et PRICE)
  const typeCounts = useMemo(() => {
    const c = { OTHER: 0, all: 0 };
    deals.forEach(deal => {
      if (!matchesVerdictFilter(deal, filterType)) return;
      if (!matchesConditionAndPrice(deal, conditionFilter, priceFilter)) return;

      c.all++;

      const classification = deal.aiAnalysis?.classification;
      if (!classification) {
        c.OTHER++;
        return;
      }

      const normalizedClass = normalize(classification);
      let path = taxonomyFullPaths[normalizedClass] || taxonomyLeafPaths[normalizedClass];
      if (!path) path = findPathFuzzy(normalizedClass, taxonomyLeafPaths);

      if (path) {
        let currentPath = "";
        path.forEach(segment => {
          currentPath = currentPath ? `${currentPath}.${segment}` : segment;
          c[currentPath] = (c[currentPath] || 0) + 1;
        });
      } else {
        c.OTHER++;
      }
    });
    return c;
  }, [deals, filterType, conditionFilter, priceFilter, matchesVerdictFilter, matchesConditionAndPrice, taxonomyFullPaths, taxonomyLeafPaths]);

  // 4. Calcul des compteurs de VERDICT (Basé sur les deals filtrés par TYPE, CONDITION et PRICE)
  const verdictCounts = useMemo(() => {
    const c = { ALL: 0, FAVORITES: 0, REJECTED: 0, ERROR: 0, SOLD: 0 };
    // Initialiser tous les compteurs de verdicts possibles
    Object.keys(ALL_VERDICTS).forEach(key => c[key] = 0);

    deals.forEach(deal => {
      // Cas spécial : REJECTED compte tous les rejetés
      if (deal.status === 'rejected') {
        c.REJECTED++;
        return;
      }

      // Cas spécial : SOLD compte TOUTES les annonces vendues, indépendamment des autres filtres
      if (deal.status === 'sold') {
        c.SOLD++;
        if (deal.isFavorite) c.FAVORITES++; // Compter aussi dans les favoris si applicable
        return; // On sort pour ne pas les compter dans "ALL" ni dans les autres catégories de base
      }

      // On n'inclut que les deals qui passent les filtres de type, condition et prix actuels
      if (!matchesTypeFilter(deal, selectedTypePaths, searchQuery)) return;
      if (!matchesConditionAndPrice(deal, conditionFilter, priceFilter)) return;

      const verdict = deal.aiAnalysis?.verdict || 'PENDING';
      const knownVerdict = verdict === 'PENDING' || !!ALL_VERDICTS[verdict] || ARCHIVE_GROUP.includes(verdict);
      const isError = !deal.aiAnalysis || verdict === 'DEFAULT' || verdict === 'ERROR' || !knownVerdict;

      if (isError) {
        c.ERROR++;
      } else {
        // Le compteur ALL ne doit compter que ce qui est visible dans ALL (donc pas le bruit)
        if (!ARCHIVE_GROUP.includes(verdict)) {
          c.ALL++;
        }

        if (c.hasOwnProperty(verdict)) {
          c[verdict]++;
        }

        // Double appartenance : compte aussi dans PEPITE sans dupliquer le total ALL.
        if (verdict !== 'PEPITE' && deal.aiAnalysis?.also_qualifies_pepite) {
          c.PEPITE++;
        }
      }
      // Cohérent avec matchesVerdictFilter('FAVORITES') : on ne compte pas le bruit archivé
      // (sauf BAD_DEAL) ni les erreurs, même si l'annonce est marquée favorite.
      const favoriteNoise = isError || (ARCHIVE_GROUP.includes(verdict) && verdict !== 'BAD_DEAL');
      if (deal.isFavorite && !favoriteNoise) c.FAVORITES++;
    });
    return c;
  }, [deals, selectedTypePaths, conditionFilter, priceFilter, searchQuery, matchesTypeFilter, matchesConditionAndPrice]);

  // 5. Liste finale filtrée (Intersection de tous les filtres)
  const filteredDeals = useMemo(() => {
    const result = deals.filter(deal => {
      if (filterType === 'REJECTED') return deal.status === 'rejected';
      if (filterType === 'SOLD') return deal.status === 'sold';


      // Pour les autres filtres, on combine verdict, type, condition et prix
      const verdictMatch = matchesVerdictFilter(deal, filterType);
      const typeMatch = matchesTypeFilter(deal, selectedTypePaths, searchQuery);
      const condPriceMatch = matchesConditionAndPrice(deal, conditionFilter, priceFilter);

      return verdictMatch && typeMatch && condPriceMatch;
    });

    if (sortMode === 'interest') {
      return [...result].sort((a, b) => {
        const scoreA = a.interestScore ?? computeInterestScore(a.aiAnalysis);
        const scoreB = b.interestScore ?? computeInterestScore(b.aiAnalysis);
        if (scoreA == null && scoreB == null) return 0;
        if (scoreA == null) return 1;
        if (scoreB == null) return -1;
        if (scoreB === scoreA) {
          const timeA = a.timestamp?.seconds || 0;
          const timeB = b.timestamp?.seconds || 0;
          return timeB - timeA;
        }
        return scoreB - scoreA;
      });
    }

    if (sortMode === 'publish_date') {
      return [...result].sort((a, b) => {
        const timeA = a.publishTimestamp?.seconds || 0;
        const timeB = b.publishTimestamp?.seconds || 0;
        if (timeA === timeB) {
          return (b.timestamp?.seconds || 0) - (a.timestamp?.seconds || 0); // Fallback à la date d'analyse
        }
        return timeB - timeA;
      });
    }

    if (sortMode === 'sold_date') {
      return [...result].sort((a, b) => {
        const timeA = a.soldTimestamp?.seconds || 0;
        const timeB = b.soldTimestamp?.seconds || 0;
        if (timeA === timeB) {
          return (b.timestamp?.seconds || 0) - (a.timestamp?.seconds || 0);
        }
        return timeB - timeA;
      });
    }

    // Default: Sort by date descending (analysis date)
    return [...result].sort((a, b) => {
      const timeA = a.timestamp?.seconds || 0;
      const timeB = b.timestamp?.seconds || 0;
      return timeB - timeA;
    });
  }, [deals, filterType, selectedTypePaths, conditionFilter, priceFilter, searchQuery, sortMode, matchesVerdictFilter, matchesTypeFilter, matchesConditionAndPrice]);

  const visibleDeals = useMemo(() => {
    return filteredDeals.slice(0, visibleCount);
  }, [filteredDeals, visibleCount]);

  // Effect pour charger les deals visibles manquants
  useEffect(() => {
    if (!user || visibleDeals.length === 0) return;
    const uid = user.uid;
    const missingIds = visibleDeals
      .map(d => d.id)
      .filter(id => !loadedDeals[id] && !fetchingIdsRef.current.has(id));

    if (missingIds.length === 0) return;

    // Marquer les IDs comme "en cours de fetch" pour bloquer les double-appels
    missingIds.forEach(id => fetchingIdsRef.current.add(id));

    let isSubscribed = true;
    fetchDealsByIds(missingIds, uid).then(fetched => {
      if (!isSubscribed) return;
      setLoadedDeals(prev => {
        const next = { ...prev };
        fetched.forEach(deal => {
          next[deal.id] = deal;
        });
        return next;
      });
    }).catch(err => {
      if (isSubscribed) setError(err.message);
    }).finally(() => {
      // Libérer les IDs qu'on soit en succès ou erreur
      missingIds.forEach(id => fetchingIdsRef.current.delete(id));
    });

    return () => { isSubscribed = false; };
  }, [visibleDeals, loadedDeals, user, setError]);

  // Effect pour charger selectedDeal s'il a été ouvert depuis l'URL et n'est pas dans le cache
  useEffect(() => {
    if (!user || !selectedDeal) return;
    const dealId = selectedDeal.id;
    if (loadedDeals[dealId]) return;

    let isSubscribed = true;
    fetchDealsByIds([dealId], user.uid).then(fetched => {
      if (!isSubscribed) return;
      if (fetched.length > 0) {
        setLoadedDeals(prev => ({ ...prev, [dealId]: fetched[0] }));
      }
    }).catch(err => {
      if (isSubscribed) setError(err.message);
    });

    return () => { isSubscribed = false; };
  }, [selectedDeal, loadedDeals, user, setError]);

  const finalSelectedDeal = useMemo(() => {
    if (!selectedDeal) return null;
    const full = loadedDeals[selectedDeal.id];
    return full ? { ...selectedDeal, ...full } : { ...selectedDeal, isLoading: true };
  }, [selectedDeal, loadedDeals]);

  // Fusionner les données légères et les données complètes pour la partie visible
  const finalFilteredDeals = useMemo(() => {
    return visibleDeals.map(deal => {
      const full = loadedDeals[deal.id];
      return full ? { ...deal, ...full } : { ...deal, isLoading: true };
    });
  }, [visibleDeals, loadedDeals]);

  const hasMore = visibleCount < filteredDeals.length;
  const loadMore = useCallback(() => {
    setVisibleCount(prev => prev + 50);
  }, []);

  const counts = useMemo(() => ({ ...verdictCounts, ...typeCounts }), [verdictCounts, typeCounts]);

  return {
    deals,
    loading,
    dbStatus,
    loadedDeals,
    selectedDeal: finalSelectedDeal,
    setSelectedDeal,
    filteredDeals: finalFilteredDeals,
    totalFilteredDeals: filteredDeals,
    hasMore,
    loadMore,
    counts,
    filterProps: {
      filterType, setFilterType,
      searchQuery, setSearchQuery,
      selectedTypePaths, setSelectedTypePaths, toggleTypePath,
      conditionFilter, setConditionFilter,
      priceFilter, setPriceFilter,
      sortMode, setSortMode,
      counts,
    },
    dealActions: {
      handleRejectDeal,
      handleDeleteDeal,
      handleRetryAnalysis,
      handleForceExpertAnalysis,
      handleToggleFavorite,
      handleSelectDeal: setSelectedDeal 
    }
  };
};
