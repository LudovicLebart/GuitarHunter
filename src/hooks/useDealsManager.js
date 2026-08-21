import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  onDealsIndexUpdate,
  fetchDealsByIds,
  rejectDeal,
  deleteDeal,
  retryDealAnalysis,
  forceExpertAnalysis,
  toggleDealFavorite,
  setDealClassification
} from '../services/firestoreService';
import { NEW_VERDICTS, LEGACY_VERDICTS, ARCHIVE_GROUP, computeInterestScore } from '../constants';
// Résolution/index de la taxonomie : source unique partagée avec DealCard et l'autocomplétion.
import { TAXONOMY_NODES, resolveClassification } from '../utils/taxonomy';

const ALL_VERDICTS = { ...NEW_VERDICTS, ...LEGACY_VERDICTS };

// Un chemin de taxonomie est ancêtre d'un autre s'il en est un préfixe strict (segment par segment).
const isAncestorPath = (a, b) => b.startsWith(`${a}.`);

// Helper pour normaliser les chaînes pour la comparaison (minuscules, sans espaces, SANS ACCENTS)
const normalize = (str) => {
  if (!str) return '';
  return str
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "") // Enlève les accents
    .toLowerCase()
    .replace(/[^a-z0-9]/g, ''); // Ne garde que alphanumérique
};

// Normalisation "souple" pour la RECHERCHE TEXTE LIBRE : minuscules, sans accents, ponctuation et
// underscores convertis en espaces — mais les séparations de mots sont CONSERVÉES, contrairement à
// normalize() ci-dessus qui les supprime.
// C'est la différence critique : normalize() est fait pour comparer des identifiants de taxonomie
// entre eux (où l'espacement ne doit pas compter), alors qu'ici on compare une saisie utilisateur à
// du texte libre. Supprimer les espaces des deux côtés recréerait exactement le faux positif déjà
// corrigé sur la recherche floue (`utils/taxonomy.js`) : "cordes guitare" -> "cordesguitare"
// contient "sg".
const normalizeLoose = (str) => {
  if (!str) return '';
  return str
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
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
  const [finishApplicationFilter, setFinishApplicationFilter] = useState('ALL');
  const [finishTextureFilter, setFinishTextureFilter] = useState('ALL');
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
        // Scores individuels (2026-08-06) : auparavant absents de l'index léger, "deal_score" était
        // substitué par la moyenne des 5 scores ("is") — imprécis pour toute annonce non chargée en
        // entier. Désormais indexés individuellement (voir repository.py::_update_deal_index), donc
        // toujours corrects même sans charger le document complet.
        deal_score: entry.ds,
        authenticity_score: entry.as,
        liquidity_score: entry.ls,
        restoration_interest_score: entry.rs,
        estimated_value: entry.ev,
        model_used: entry.mu,
        estimated_gross_margin: entry.egm,
        brand: entry.b,
        model_name: entry.mn,
        color: entry.co,
        finish_application: entry.fa,
        finish_texture: entry.ft
      },
      // `mc` marque une classification corrigée à la main : `c` porte alors la valeur corrigée.
      manualClassification: entry.mc ? entry.c : undefined,
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
      // Purge défensive d'une sélection sauvegardée avant le fix anti-chaîne (chemins
      // ancêtre+descendant coexistant) : ne garde que les chemins les plus spécifiques,
      // en retirant tout chemin qui a un DESCENDANT aussi présent dans la sélection (donc
      // moins spécifique que ce descendant, qui doit primer).
      const saved = uiFilters.selectedTypePaths;
      setSelectedTypePaths(saved.filter(p => !saved.some(o => o !== p && isAncestorPath(p, o))));
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
    if (uiFilters.finishApplicationFilter) setFinishApplicationFilter(uiFilters.finishApplicationFilter);
    if (uiFilters.finishTextureFilter) setFinishTextureFilter(uiFilters.finishTextureFilter);
    if (uiFilters.sortMode) setSortMode(uiFilters.sortMode);
  }, [uiFilters]);

  // Sauvegarde (debouncée dans saveUiFilters) à chaque changement de filtre, une fois hydraté —
  // pour ne pas écraser une valeur sauvegardée par la valeur par défaut avant son chargement.
  useEffect(() => {
    if (!hydratedFiltersRef.current || !saveUiFilters) return;
    saveUiFilters({
      filterType, selectedTypePaths,
      conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter, sortMode
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType, selectedTypePaths, conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter, sortMode]);

  // Reset visibleCount when filters change
  useEffect(() => {
    setVisibleCount(30);
  }, [filterType, selectedTypePaths, conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter, searchQuery]);

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

  // Correction manuelle de la catégorie (null = annuler et revenir à la classification de l'IA).
  const handleSetClassification = useCallback(async (dealId, classificationPath) => {
    if (!user) return;
    const entry = dealsIndexMap[dealId];
    try {
      // En annulation, l'index doit retomber sur la classification d'origine de l'IA — or `c`
      // porte la valeur corrigée quand `mc` est posé. On la relit donc sur le document complet
      // (toujours chargé : la correction se fait depuis la modale d'analyse).
      const aiClassification = loadedDeals[dealId]?.aiAnalysis?.classification
        ?? (entry?.mc ? null : entry?.c);
      await setDealClassification(dealId, entry?.h, user.uid, classificationPath, aiClassification);
      // `loadedDeals` est un cache écrit une seule fois, et il PRIME sur l'index dans la fusion
      // ({ ...deal, ...full }) : sans invalidation, une 2e correction ou un retour à la catégorie
      // de l'IA continuait d'afficher la valeur précédente jusqu'au rechargement de la page.
      setLoadedDeals(prev => {
        if (!prev[dealId]) return prev;
        const next = { ...prev };
        next[dealId] = { ...next[dealId], manualClassification: classificationPath || undefined };
        return next;
      });
    } catch (e) { setError(e.message); }
  }, [user, dealsIndexMap, loadedDeals, setError]);

  // Mise à jour optimiste après ajout d'une photo du chat à la galerie (2026-08-21, voir
  // useDealChat.js::addPhotoToGallery) — même nécessité que handleSetClassification ci-dessus :
  // le doc complet de l'annonce n'est pas un listener temps réel (`loadedDeals` = fetch one-shot),
  // sans ce patch la galerie ouverte n'afficherait le nouvel ajout qu'après un rechargement complet.
  const handleGalleryImageAdded = useCallback((dealId, url) => {
    setLoadedDeals(prev => {
      if (!prev[dealId]) return prev;
      const existing = prev[dealId].storageImageUrls || [];
      if (existing.includes(url)) return prev;
      const next = { ...prev };
      next[dealId] = { ...next[dealId], storageImageUrls: [...existing, url] };
      return next;
    });
  }, []);

  const handleToggleFavorite = useCallback(async (dealId, currentStatus) => {
    if (!user) return;
    const chunkId = dealsIndexMap[dealId]?.h;
    try { await toggleDealFavorite(dealId, currentStatus, chunkId, user.uid); } catch (e) { setError(e.message); }
  }, [user, dealsIndexMap, setError]);

  // Multi-sélection : coche/décoche un chemin de taxonomie (ex: "guitare.acoustique_acier.formes_standard.Parlor").
  // La sélection est maintenue en anti-chaîne (aucun chemin gardé n'est ancêtre/descendant d'un
  // autre) : cocher un chemin plus profond agit comme un drill-down et retire les cases parentes
  // déjà cochées, sinon celles-ci (moins spécifiques) dominent le filtre OR-préfixe et réaffichent
  // tout — cas où "Guitare" + "Parlor" cochés ensemble ne filtraient plus rien.
  const toggleTypePath = useCallback((path) => {
    setSelectedTypePaths(prev => prev.includes(path)
      ? prev.filter(p => p !== path)
      : [...prev.filter(p => !isAncestorPath(p, path) && !isAncestorPath(path, p)), path]
    );
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

    // Une ré-analyse en cours (mise à jour optimiste locale : verdict -> 'PENDING' dès le clic,
    // avant même que le backend ne la traite) reste visible dans l'onglet verdict où l'utilisateur
    // se trouve déjà, plutôt que de disparaître le temps de l'analyse — sinon le badge "Analyse..."
    // existant (DealCardImage.jsx) n'a jamais l'occasion de s'afficher.
    if (['analyzing', 'analyzing_expert'].includes(deal.status)) return true;

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

    const analysis = deal.aiAnalysis || {};
    const hasTypeFilter = typePaths && typePaths.length > 0;
    const needle = search ? normalizeLoose(search) : '';

    // Le chemin de taxonomie résolu sert aux DEUX usages ci-dessous (recherche texte + filtre de
    // type) : on ne le résout qu'une seule fois, et uniquement si l'un des deux est actif.
    let path = null;
    if (needle || hasTypeFilter) {
      // Résolution centralisée (chemin complet → feuille unique → recherche floue). Une feuille
      // AMBIGUË (nom porté par plusieurs branches, ex: "Guitare Acoustique" = étui ET instrument)
      // n'est volontairement pas résolue : l'annonce retombe dans "OTHER" plutôt que d'être
      // rattachée à la mauvaise branche — c'est le bug des étuis classés comme guitares.
      path = resolveClassification(analysis.classification).segments;
    }

    // Recherche textuelle (titre + marque/modèle/couleur identifiés par l'IA + TAXONOMIE résolue).
    // La taxonomie dans le haystack permet à "acoustique" ou "parlor" de ramener les annonces
    // classées dans cette branche même si le mot n'apparaît nulle part dans le texte de l'annonce.
    // Comparaison via normalizeLoose() des deux côtés : insensible aux accents et à la ponctuation
    // (donc "electrique" trouve "électrique", "les paul" trouve "Les-Paul") mais respectueuse des
    // séparations de mots — voir le commentaire de normalizeLoose() pour le faux positif évité.
    if (needle) {
      const haystack = normalizeLoose(
        [deal.title, analysis.brand, analysis.model_name, analysis.color, path ? path.join(' ') : null]
          .filter(Boolean).join(' ')
      );
      if (!haystack.includes(needle)) return false;
    }

    if (!hasTypeFilter) return true; // Aucune sélection = Tous les types
    if (!path) return typePaths.includes('OTHER');

    // Un deal correspond si son chemin égale ou descend (préfixe) d'AU MOINS un des chemins
    // sélectionnés — permet de cocher "Parlor" ET "Baby / Mini" simultanément même si ces deux
    // catégories se trouvent dans des branches différentes de la taxonomie.
    const fullPathStr = path.join('.');
    return typePaths.some(selected =>
      selected === fullPathStr || fullPathStr.startsWith(`${selected}.`)
    );
  }, []);

  // 2.5 Helper pour vérifier si un deal correspond aux filtres de PRIX, CONDITION et FINITION
  // (finish_application/finish_texture : listes fermées demandées à l'IA, cf. prompts.json — mais
  // analyzer.py fait un json.loads() brut, sans response_schema/enum qui forcerait la valeur exacte.
  // Comparer en égalité stricte reproduirait le même bug déjà rencontré sur la taxonomie (l'IA
  // dérive du texte attendu — casse, espacement — et le filtre ne matche plus rien). Comparaison
  // sur chaînes normalisées (même helper que la taxonomie) plutôt qu'un `!==` brut : tolère la
  // variance de formatage sans réintroduire la recherche par sous-chaîne (qui, elle, avait causé
  // les faux-positifs sur la taxonomie — non pertinente ici, ce sont des valeurs courtes et fermées).
  const matchesConditionAndPrice = useCallback((deal, condition, priceFilter, finishApplication, finishTexture) => {
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

    // === FINITION ===
    if (finishApplication && finishApplication !== 'ALL' && normalize(deal.aiAnalysis?.finish_application) !== normalize(finishApplication)) return false;
    if (finishTexture && finishTexture !== 'ALL' && normalize(deal.aiAnalysis?.finish_texture) !== normalize(finishTexture)) return false;

    return true;
  }, []);

  // 3. Calcul des compteurs de TYPE (Basé sur les deals filtrés par VERDICT, CONDITION et PRICE)
  const typeCounts = useMemo(() => {
    const c = { OTHER: 0, all: 0 };
    deals.forEach(deal => {
      if (!matchesVerdictFilter(deal, filterType)) return;
      if (!matchesConditionAndPrice(deal, conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter)) return;

      c.all++;

      const classification = deal.aiAnalysis?.classification;
      if (!classification) {
        c.OTHER++;
        return;
      }

      const path = resolveClassification(classification).segments;

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
  }, [deals, filterType, conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter, matchesVerdictFilter, matchesConditionAndPrice]);

  // 3.5 Suggestions de catégories pour l'autocomplétion de la barre de recherche.
  // Le matching porte sur le LIBELLÉ PROPRE du nœud (son dernier segment), pas sur son chemin
  // complet : sinon taper "guitare" proposerait les ~100 nœuds de la branche, ce qui n'aide pas.
  // Les catégories déjà cochées sont retirées de la liste (les re-proposer les décocherait).
  const searchSuggestions = useMemo(() => {
    const needle = normalizeLoose(searchQuery);
    if (needle.length < 2) return []; // 1 seule lettre = trop de bruit
    return TAXONOMY_NODES
      .filter(node => !selectedTypePaths.includes(node.path))
      .map(node => {
        const position = node.labelNormalized.indexOf(needle);
        if (position < 0) return null;
        const count = typeCounts[node.path] || 0;
        return { ...node, count, startsWith: position === 0, hasResults: count > 0 };
      })
      .filter(Boolean)
      // Un libellé qui COMMENCE par la saisie d'abord, puis les catégories qui contiennent
      // réellement des annonces (cocher une catégorie vide n'affiche rien — elle reste proposée,
      // mais en bas), puis les plus larges (profondeur faible), puis les mieux fournies.
      .sort((a, b) =>
        (b.startsWith - a.startsWith) || (b.hasResults - a.hasResults) ||
        (a.depth - b.depth) || (b.count - a.count)
      )
      .slice(0, 8);
  }, [searchQuery, selectedTypePaths, typeCounts]);

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

      // On n'inclut que les deals qui passent les filtres de type, condition, prix et finition actuels
      if (!matchesTypeFilter(deal, selectedTypePaths, searchQuery)) return;
      if (!matchesConditionAndPrice(deal, conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter)) return;

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
  }, [deals, selectedTypePaths, conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter, searchQuery, matchesTypeFilter, matchesConditionAndPrice]);

  // 5. Liste finale filtrée (Intersection de tous les filtres)
  const filteredDeals = useMemo(() => {
    const result = deals.filter(deal => {
      if (filterType === 'REJECTED') return deal.status === 'rejected';
      if (filterType === 'SOLD') return deal.status === 'sold';


      // Pour les autres filtres, on combine verdict, type, condition et prix
      const verdictMatch = matchesVerdictFilter(deal, filterType);
      const typeMatch = matchesTypeFilter(deal, selectedTypePaths, searchQuery);
      const condPriceMatch = matchesConditionAndPrice(deal, conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter);

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
  }, [deals, filterType, selectedTypePaths, conditionFilter, priceFilter, finishApplicationFilter, finishTextureFilter, searchQuery, sortMode, matchesVerdictFilter, matchesTypeFilter, matchesConditionAndPrice]);

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
      searchQuery, setSearchQuery, searchSuggestions,
      selectedTypePaths, setSelectedTypePaths, toggleTypePath,
      conditionFilter, setConditionFilter,
      priceFilter, setPriceFilter,
      finishApplicationFilter, setFinishApplicationFilter,
      finishTextureFilter, setFinishTextureFilter,
      sortMode, setSortMode,
      counts,
    },
    dealActions: {
      handleRejectDeal,
      handleDeleteDeal,
      handleRetryAnalysis,
      handleForceExpertAnalysis,
      handleToggleFavorite,
      handleSetClassification,
      handleGalleryImageAdded,
      handleSelectDeal: setSelectedDeal
    }
  };
};
