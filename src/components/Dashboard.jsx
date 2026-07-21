import React, { useState, useMemo, useEffect, useRef } from 'react';
import { Target, ShoppingBag, Archive, Search, ChevronDown, Check, X, List, Map as MapIcon, Activity, RefreshCw, Heart, AlertTriangle } from 'lucide-react';
import Navbar from './Navbar';
import DealCard from './DealCard';
import FilterDrawer from './FilterDrawer';
import StatsView from './StatsView';
import ConfigPanel from './ConfigPanel';
import MapView from './MapView';
import HelpOverlay from './HelpOverlay';
import AdminDashboard from './AdminDashboard';
import { FILTER_ORDER, ALL_FILTERS_CONFIG, RADAR_GROUP, MARKET_GROUP } from '../constants';

// Contexts & hooks
import { useDealsContext } from '../context/DealsContext';
import { useBotConfigContext } from '../context/BotConfigContext';

// Remove obsolete buildDealCounts
// ============================================================
// Section Header
// ============================================================
const SectionHeader = ({ icon: Icon, title, count, color, open, onToggle }) => (
    <button className="w-full flex items-center gap-3 py-4 group" onClick={onToggle}>
        <Icon size={20} className={color} />
        <span className={`font-black uppercase tracking-wider text-sm ${color}`}>{title}</span>
        <span className="text-xs font-mono text-slate-600 bg-slate-800 px-2 py-0.5 rounded-md">{count}</span>
        <div className="flex-1 h-px bg-slate-800 group-hover:bg-slate-700 transition-colors" />
        <span className="text-slate-600 text-[10px]">{open ? '▲' : '▼'}</span>
    </button>
);

// ============================================================
// Custom Dropdown for Verdict/Status filtering
// ============================================================
const VerdictDropdown = ({ currentVerdict, onSelect, counts }) => {
    const [isOpen, setIsOpen] = useState(false);

    // Réorganisation pour inclure les statuts spéciaux (Vendu, Rejeté, Erreur)
    const OPTIONS = [
        { id: 'ALL', label: 'Toutes les annonces' },
        { id: 'FAVORITES', label: 'Favoris' },
        { divider: true },
        // Verdicts positifs
        ...['PEPITE', 'FAST_FLIP', 'LUTHIER_PROJ', 'CASE_WIN', 'COLLECTION']
            .filter(id => ALL_FILTERS_CONFIG[id])
            .map(id => ({
                id,
                label: ALL_FILTERS_CONFIG[id]?.pluralLabel || ALL_FILTERS_CONFIG[id]?.label || id,
            })),
        { divider: true },
        // Verdicts de "bruit" ou négatifs
        ...['BAD_DEAL', 'REJECTED_ITEM', 'INCOMPLETE_DATA']
            .filter(id => ALL_FILTERS_CONFIG[id])
            .map(id => ({ id, label: ALL_FILTERS_CONFIG[id]?.label || id })),
        { divider: true },
        // Statuts spéciaux
        { id: 'SOLD', label: 'Annonces Vendues' },
        { id: 'REJECTED', label: 'Annonces Rejetées' },
        { id: 'ERROR', label: 'Erreurs d\'analyse' },
    ];

    const currentLabel = OPTIONS.find(o => o.id === currentVerdict)?.label || 'Toutes les annonces';

    return (
        <div className="relative flex-1 sm:flex-none min-w-0">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full sm:w-auto flex items-center justify-between sm:justify-start gap-2 h-10 px-4 bg-slate-800 border border-slate-700 hover:bg-slate-700 hover:border-slate-600 rounded-xl text-sm font-bold text-slate-200 transition-all shadow-sm"
            >
                <div className="flex items-center min-w-0">
                    <span className="text-slate-400 font-normal mr-1.5 hidden sm:inline shrink-0">Statut :</span>
                    <span className="truncate block">{currentLabel}</span>
                </div>
                <ChevronDown size={14} className={`text-slate-500 transition-transform shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <>
                    <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
                    <div className="absolute top-full left-0 sm:right-0 mt-2 w-56 sm:w-64 max-w-[calc(100vw-2rem)] bg-slate-900 border border-slate-700 rounded-2xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] z-50 py-2 animate-in fade-in slide-in-from-top-2">
                        {OPTIONS.map((opt, i) => {
                            if (opt.divider) return <div key={`div-${i}`} className="h-px bg-slate-800 my-1 mx-2" />;
                            const count = counts[opt.id] || 0;
                            const isActive = currentVerdict === opt.id;

                            return (
                                <button
                                    key={opt.id}
                                    onClick={() => { onSelect(opt.id); setIsOpen(false); }}
                                    className={`w-full flex items-center justify-between px-4 py-2 text-xs transition-colors hover:bg-slate-800 ${isActive ? 'text-white font-bold bg-blue-600/10' : 'text-slate-400 font-medium'}`}
                                >
                                    <div className="flex items-center gap-2 whitespace-nowrap">
                                        {isActive ? <Check size={14} className="text-blue-500 shrink-0" /> : <div className="w-3.5 shrink-0" />}
                                        <span className="truncate">{opt.label}</span>
                                    </div>
                                    <span className={`shrink-0 font-mono ml-2 ${isActive ? 'text-blue-400' : 'text-slate-600 bg-slate-950 px-1.5 py-0.5 rounded-md'}`}>
                                        {count}
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                </>
            )}
        </div>
    );
};

// ============================================================
// Dashboard
// ============================================================
// ============================================================
// Map View Header / Wrapper
// ============================================================
const MapViewOverlay = ({ deals, renderDealCard, selectedDeal, onDealSelect, onClearSelection }) => {
    const selectedDealId = selectedDeal ? selectedDeal.id : null;

    return (
        <div className="flex flex-col lg:flex-row gap-6 h-[70vh] min-h-[500px] relative">
            {/* Real Map filling the whole space */}
            <div className="flex-1 rounded-3xl overflow-hidden relative flex flex-col shadow-inner border border-slate-800 w-full h-full">
                <MapView deals={deals} onDealSelect={onDealSelect} selectedDealId={selectedDealId} />
            </div>

            {/* Selected Deal Sidebar (Desktop) or Full Overlay (Mobile) */}
            {selectedDeal && (
                <div className="
                    lg:relative lg:w-96 lg:h-full lg:flex-col lg:pb-0 
                    absolute inset-0 z-10 w-full h-full flex flex-col pt-2 lg:pt-0 
                    bg-slate-950/95 lg:bg-transparent backdrop-blur-md lg:backdrop-blur-none rounded-3xl lg:rounded-none
                    animate-in slide-in-from-bottom-8 lg:slide-in-from-right-8 fade-in lg:shadow-none
                ">
                    <div className="flex items-center justify-between mb-2 lg:hidden px-4 pt-2">
                        <span className="text-sm font-bold text-slate-300">Détails de l'annonce</span>
                        <button onClick={onClearSelection} className="p-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors">
                            <X size={16} />
                        </button>
                    </div>
                    {/* Dark wrapper for the card to fit V2 theme */}
                    <div className="h-full overflow-y-auto scrollbar-dark px-4 pb-4 lg:px-0 lg:pb-0">
                        {renderDealCard(selectedDeal)}
                    </div>
                </div>
            )}
        </div>
    );
};

const Dashboard = ({ onClose }) => {
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [showConfig, setShowConfig] = useState(false);
    const [viewMode, setViewMode] = useState('LIST');
    const [openSections, setOpenSections] = useState({ radar: true, market: true, archive: false });
    const [showHelp, setShowHelp] = useState(false);
    const [showAdmin, setShowAdmin] = useState(false);

    // ── Real data & actions ──────────────────────────────────
    const {
        loading,
        deals,
        filteredDeals,
        totalFilteredDeals = [],
        loadedDeals,
        hasMore,
        loadMore,
        filterProps,
        dealActions,
        selectedDeal,
        counts,
    } = useDealsContext();

    const {
        isRefreshing,
        isCleaning,
        error,
        setError,
        handleManualRefresh,
        handleManualCleanup,
        isNewUser,
    } = useBotConfigContext();

    const loadMoreRef = useRef(null);

    // Infinite Scroll trigger
    useEffect(() => {
        if (!hasMore || !loadMore) return;
        
        const observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                loadMore();
            }
        }, {
            rootMargin: '300px' // Charge 300px avant le bas pour un scroll fluide
        });

        const current = loadMoreRef.current;
        if (current) {
            observer.observe(current);
        }

        return () => {
            if (current) {
                observer.unobserve(current);
            }
        };
    }, [hasMore, loadMore]);

    // Effet pour ouvrir une annonce depuis l'URL au chargement
    useEffect(() => {
        // Ne s'exécute que si les deals sont chargés et qu'aucune modale n'est déjà ouverte
        if (deals.length > 0 && !selectedDeal) {
            const params = new URLSearchParams(window.location.search);
            const dealIdFromUrl = params.get('dealId');

            if (dealIdFromUrl) {
                // On cherche dans TOUTES les annonces, pas seulement les filtrées
                const dealToSelect = deals.find(d => d.id === dealIdFromUrl);
                if (dealToSelect) {
                    dealActions.handleSelectDeal(dealToSelect);
                    setViewMode('MAP');
                    // On nettoie l'URL pour éviter de rouvrir la modale à chaque changement de filtre
                    window.history.replaceState({}, document.title, window.location.pathname + window.location.hash);
                }
            }
        }
    }, [deals, selectedDeal, dealActions, setViewMode]);

    // Effet pour forcer l'affichage de l'aide pour un nouvel utilisateur
    useEffect(() => {
        if (isNewUser) {
            setShowHelp(true);
        }
    }, [isNewUser]);

    // ── Adapt filterProps to local filter state ───────────────
    // filterProps from useDealsManager exposes: filterType/setFilterType,
    //   level1Filter/setLevel1Filter, ..., searchQuery, setSearchQuery
    const {
        filterType = 'ALL',
        setFilterType,
        level1Filter = 'ALL',
        setLevel1Filter,
        level2Filter = 'ALL',
        setLevel2Filter,
        level3Filter = 'ALL',
        setLevel3Filter,
        level4Filter = 'ALL',
        setLevel4Filter,
        conditionFilter = 'ALL',
        setConditionFilter,
        priceFilter = 'ALL',
        setPriceFilter,
        sortMode = 'date',
        setSortMode,
        searchQuery = '',
        setSearchQuery,
    } = filterProps || {};

    // Map filterProps keys to the format MockupFilterDrawer expects
    // MockupFilterDrawer uses lowercase 'all', useDealsManager uses uppercase 'ALL'
    const filters = {
        verdict: filterType,
        level1: level1Filter === 'ALL' ? 'all' : level1Filter,
        level2: level2Filter === 'ALL' ? 'all' : level2Filter,
        level3: level3Filter === 'ALL' ? 'all' : level3Filter,
        level4: level4Filter === 'ALL' ? 'all' : level4Filter,
        condition: conditionFilter === 'ALL' ? 'all' : conditionFilter,
        price: priceFilter === 'ALL' ? 'all' : priceFilter,
        sort: sortMode,
    };

    const handleFilterChange = (key, value) => {
        // MockupFilterDrawer sends lowercase 'all', useDealsManager expects uppercase 'ALL'
        const normalized = value === 'all' ? 'ALL' : value;
        switch (key) {
            case 'verdict': setFilterType?.(normalized); break;
            case 'level1': setLevel1Filter?.(normalized); break;
            case 'level2': setLevel2Filter?.(normalized); break;
            case 'level3': setLevel3Filter?.(normalized); break;
            case 'level4': setLevel4Filter?.(normalized); break;
            case 'condition': setConditionFilter?.(normalized); break;
            case 'price': setPriceFilter?.(normalized); break;
            case 'sort': setSortMode?.(value); break; // 'date' | 'interest', pas de mapping 'all'
            default: break;
        }
    };

    const handleReset = () => {
        setFilterType?.('ALL');
        setLevel1Filter?.('ALL');
        setLevel2Filter?.('ALL');
        setLevel3Filter?.('ALL');
        setLevel4Filter?.('ALL');
        setConditionFilter?.('ALL');
        setPriceFilter?.('ALL');
        setSearchQuery?.('');
    };


    // ── Section grouping from real filtered deals ────────────
    const radarDeals = useMemo(() =>
        filteredDeals.filter(d => RADAR_GROUP.includes(d.aiAnalysis?.verdict || 'DEFAULT')),
        [filteredDeals]
    );
    const marketDeals = useMemo(() =>
        filteredDeals.filter(d => MARKET_GROUP.includes(d.aiAnalysis?.verdict || 'DEFAULT')),
        [filteredDeals]
    );
    const archiveDeals = useMemo(() =>
        filteredDeals.filter(d =>
            !RADAR_GROUP.includes(d.aiAnalysis?.verdict || 'DEFAULT') &&
            !MARKET_GROUP.includes(d.aiAnalysis?.verdict || 'DEFAULT')
        ),
        [filteredDeals]
    );
 

    const activeFilterCount = [
        filterType !== 'ALL' ? 1 : 0,
        level1Filter !== 'ALL' ? 1 : 0,
        level2Filter !== 'ALL' ? 1 : 0,
        level3Filter !== 'ALL' ? 1 : 0,
        level4Filter !== 'ALL' ? 1 : 0,
        conditionFilter !== 'ALL' ? 1 : 0,
        priceFilter !== 'ALL' ? 1 : 0,
    ].reduce((a, b) => a + b, 0);

    const toggle = (s) => setOpenSections(prev => ({ ...prev, [s]: !prev[s] }));

    // ── Render a real deal card with real actions ─────────────
    const renderDealCard = (d) => (
        <DealCard
            key={d.id}
            deal={d}
            onRetry={(userComment) => dealActions?.handleRetryAnalysis(d.id, userComment)}
            onForceExpert={(userComment) => dealActions?.handleForceExpertAnalysis(d.id, userComment)}
            onReject={() => dealActions?.handleRejectDeal(d.id)}
            onToggleFavorite={() => dealActions?.handleToggleFavorite(d.id, d.isFavorite)}
            onDelete={() => dealActions?.handleDeleteDeal(d.id)}
        />
    );

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
            <Navbar
                onOpenFilters={() => setDrawerOpen(true)}
                onOpenSettings={() => setShowConfig(s => !s)}
                onClose={onClose}
                filterCount={activeFilterCount}
                onRefresh={handleManualRefresh}
                onCleanup={handleManualCleanup}
                isRefreshing={isRefreshing}
                isCleaning={isCleaning}
                onOpenHelp={() => setShowHelp(true)}
                onOpenAdmin={() => setShowAdmin(true)}
            />

            {showAdmin && <AdminDashboard onClose={() => setShowAdmin(false)} />}

            {/* Error Banner */}
            {error && (
                <div className="w-full bg-rose-500/10 border-b border-rose-500/20 py-3 px-4 animate-in slide-in-from-top duration-500">
                    <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3 text-rose-400">
                            <AlertTriangle size={18} className="shrink-0" />
                            <p className="text-xs font-bold uppercase tracking-wide">
                                <span className="opacity-60 mr-2">Erreur :</span>
                                {error}
                            </p>
                        </div>
                        <button 
                            onClick={() => setError(null)}
                            className="p-1.5 hover:bg-rose-500/20 rounded-lg text-rose-500/50 hover:text-rose-400 transition-colors"
                        >
                            <X size={16} />
                        </button>
                    </div>
                </div>
            )}

            {showHelp && <HelpOverlay onClose={() => setShowHelp(false)} />}

            <FilterDrawer
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                filters={filters}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                counts={counts || {}}
            />

            {/* Real ConfigPanel — opens via gear icon */}
            <ConfigPanel showConfig={showConfig} onClose={() => setShowConfig(false)} />

            <div className="w-full max-w-7xl mx-auto px-4 py-6 md:py-8">

                {/* ─── Search & Actions ─── */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-3 md:p-4 mb-6 grid grid-cols-1 md:flex md:flex-row gap-3 shadow-sm">
                    {/* Search */}
                    <div className="relative flex-1">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 shrink-0" />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={e => setSearchQuery?.(e.target.value)}
                            placeholder="Rechercher par modèle, lieu..."
                            className="w-full h-10 bg-slate-800 border border-slate-700 rounded-xl pl-9 pr-10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all"
                        />
                        {searchQuery && (
                            <button
                                onClick={() => setSearchQuery?.('')}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                            >
                                <X size={14} />
                            </button>
                        )}
                    </div>

                    <div className="flex flex-col sm:flex-row sm:justify-between md:justify-start gap-2 shrink-0">
                        <div className="flex gap-2 shrink-0">
                            {/* Favorite Shortcut Toggle */}
                            <button
                                onClick={() => setFilterType?.(filterType === 'FAVORITES' ? 'ALL' : 'FAVORITES')}
                                className={`h-10 px-3 flex items-center justify-center rounded-xl transition-all border shadow-sm ${filterType === 'FAVORITES' ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-rose-400 hover:bg-slate-700 hover:border-slate-600'}`}
                                title="Afficher uniquement les favoris"
                            >
                                <Heart size={16} fill={filterType === 'FAVORITES' ? 'currentColor' : 'none'} />
                            </button>

                            {/* Verdict Filter Dropdown */}
                            <VerdictDropdown
                                currentVerdict={filterType}
                                onSelect={(v) => setFilterType?.(v)}
                                counts={counts || {}}
                            />
                        </div>

                        <div className="flex justify-between sm:justify-start gap-2 shrink-0 md:ml-auto">
                            {/* View Mode Toggle */}
                            <div className="flex bg-slate-800 p-1 rounded-xl shrink-0 h-10 border border-slate-700">
                                <button onClick={() => setViewMode('LIST')} className={`px-3 flex items-center justify-center rounded-lg transition-all ${viewMode === 'LIST' ? 'bg-slate-700 shadow-sm text-blue-400' : 'text-slate-500 hover:text-slate-300'}`}><List size={16} /></button>
                                <button onClick={() => setViewMode('MAP')} className={`px-3 flex items-center justify-center rounded-lg transition-all ${viewMode === 'MAP' ? 'bg-slate-700 shadow-sm text-blue-400' : 'text-slate-500 hover:text-slate-300'}`}><MapIcon size={16} /></button>
                                <button onClick={() => setViewMode('STATS')} className={`px-3 flex items-center justify-center rounded-lg transition-all ${viewMode === 'STATS' ? 'bg-slate-700 shadow-sm text-purple-400' : 'text-slate-500 hover:text-slate-300'}`}>
                                    <Activity size={16} />
                                </button>
                            </div>

                            {/* Results Count & Clear Filters */}
                            <div className="flex items-center justify-center gap-2 shrink-0">
                                <span className="text-xs text-slate-500 font-mono hidden xl:block">
                                    {totalFilteredDeals.length} annonce{totalFilteredDeals.length !== 1 ? 's' : ''}
                                </span>
                                {(activeFilterCount > 0 || searchQuery) && (
                                    <button onClick={handleReset} className="flex items-center justify-center h-10 w-10 bg-rose-500/10 hover:bg-rose-500/20 rounded-xl text-rose-400 hover:text-rose-300 transition-colors border border-rose-500/20" title="Effacer tous les filtres">
                                        <X size={16} />
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                {/* ─── Loading State ─── */}
                {loading ? (
                    <div className="py-20 flex flex-col items-center justify-center bg-slate-900 rounded-2xl border border-slate-800">
                        <RefreshCw className="text-blue-500 animate-spin mb-4" size={36} />
                        <p className="text-slate-500 font-bold uppercase tracking-widest text-xs">Synchronisation Firestore...</p>
                    </div>
                ) : viewMode === 'STATS' ? (
                    <StatsView deals={totalFilteredDeals} allDeals={deals} loadedDeals={loadedDeals} />
                ) : viewMode === 'MAP' ? (
                    <MapViewOverlay
                        deals={totalFilteredDeals}
                        renderDealCard={renderDealCard}
                        selectedDeal={selectedDeal}
                        onDealSelect={(deal) => dealActions.handleSelectDeal(deal)}
                        onClearSelection={() => dealActions.handleSelectDeal(null)}
                    />
                ) : (
                    <>
                        {/* ─── Sections ─── */}
                        {radarDeals.length > 0 && (
                            <div>
                                <SectionHeader icon={Target} title="Radar" count={radarDeals.length} color="text-emerald-400" open={openSections.radar} onToggle={() => toggle('radar')} />
                                {openSections.radar && (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-4">
                                        {radarDeals.map(renderDealCard)}
                                    </div>
                                )}
                            </div>
                        )}

                        {marketDeals.length > 0 && (
                            <div>
                                <SectionHeader icon={ShoppingBag} title="Marché" count={marketDeals.length} color="text-blue-400" open={openSections.market} onToggle={() => toggle('market')} />
                                {openSections.market && (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-4">
                                        {marketDeals.map(renderDealCard)}
                                    </div>
                                )}
                            </div>
                        )}

                        {archiveDeals.length > 0 && (
                            <div>
                                <SectionHeader icon={Archive} title="Archives & Bruit" count={archiveDeals.length} color="text-slate-500" open={openSections.archive} onToggle={() => toggle('archive')} />
                                {openSections.archive && (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-4">
                                        {archiveDeals.map(renderDealCard)}
                                    </div>
                                )}
                            </div>
                        )}

                        {hasMore && (
                            <div ref={loadMoreRef} className="flex justify-center items-center py-12 mb-4 shrink-0">
                                <RefreshCw className="text-blue-500 animate-spin" size={28} />
                            </div>
                        )}

                        {totalFilteredDeals.length === 0 && !loading && (
                            <div className="py-20 flex flex-col items-center justify-center bg-slate-900 rounded-2xl border border-dashed border-slate-800">
                                <Search size={40} className="text-slate-800 mb-4" />
                                <h3 className="text-base font-black text-slate-500 uppercase tracking-tight">Aucun résultat</h3>
                                <button onClick={handleReset} className="mt-3 text-xs text-blue-400 hover:text-blue-300 transition-colors">
                                    Effacer les filtres
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
};

export default Dashboard;
