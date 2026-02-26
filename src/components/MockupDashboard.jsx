import React, { useState, useMemo } from 'react';
import { Target, ShoppingBag, Archive, Search, ChevronDown, Check, X, List, Map as MapIcon, Activity } from 'lucide-react';
import MockupNavbar from './MockupNavbar';
import MockupDealCard from './MockupDealCard';
import MockupFilterDrawer from './MockupFilterDrawer';
import MockupStatsView from './MockupStatsView';
import ConfigPanel from './ConfigPanel';
import { FILTER_ORDER, ALL_FILTERS_CONFIG } from '../constants';

// ============================================================
// Dummy data — 8 varied fake deals
// ============================================================
const FAKE_DEALS = [
    {
        id: '1', verdict: 'FAST_FLIP',
        title: "AMPLI DE GUITARE CRATE DANS MONT-ST-HILAIRE, QC",
        price: 50, estValue: 150, margin: 100,
        location: "Mont-St-Hilaire, QC", taxonomy: "Acoustique_Vocal", classification: 'electrique.ampli_electrique.combo', type: 'electrique',
        imageUrls: [
            "https://images.unsplash.com/photo-1519782483849-cbe3387eb7f1?auto=format&fit=crop&q=80&w=600&h=800", // Amp verticalish
            "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?auto=format&fit=crop&q=80&w=600&h=800"
        ],
        confidence: 92,
        reasoning: "• 💰 Prix demandé : 50 $ CAD\n• 💡 Valeur marché : ~150 $ CAD (Crate CA30D occasion)\n• 📈 Marge Potentielle : 100 $ CAD\n• 🎯 Authenticité (9/10) : Ampli entrée de gamme, rarement contrefait.\n• 🛠️ État (7/10) : Semble poussiéreux, usure normale.\n• 💨 Liquidité (8/10) : Ampli acoustique pas cher, part très vite pour débutants.\n\nVerdict : Excellent point d'entrée pour un quick-flip après un simple nettoyage des potards.",
        models: "gemini-2.5-flash-lite → gemini-2.5-flash", date: "Il y a 8 min",
    },
    {
        id: '2', verdict: 'PEPITE',
        title: "GIBSON LES PAUL STUDIO 1996 AVEC ÉTUI",
        price: 680, estValue: 1200, margin: 520,
        location: "Montréal, QC", taxonomy: "Électrique", classification: 'electrique.solid_body.les_paul_style.gibson', type: 'electrique',
        imageUrls: [
            "https://images.unsplash.com/photo-1605020420620-20c943cc4669?auto=format&fit=crop&q=80&w=600&h=800", // LP vertical
            "https://images.unsplash.com/photo-1549488344-c687eec86751?auto=format&fit=crop&q=80&w=600&h=800",
            "https://images.unsplash.com/photo-1510915361894-db8b60106cb1?auto=format&fit=crop&q=80&w=600&h=800"
        ],
        confidence: 97,
        reasoning: "## RAPPORT D'EXPERTISE (TIER 3)\n- **Authenticité (9/10)** : Tête, logo, bridge (Nashville TOM) conformes aux specs de 1996.\n- **État (8/10)** : Finition Wine Red, quelques pocs mineurs (buckle rash standard).\n- **Prix/Valeur (10/10)** : 680$ avec le hardcase brun intérieur rose original (qui vaut 150$ seul). Prix exceptionnel.\n- **Potentiel Marge (9/10)** : Se revendra facilement 1100-1200$ sans aucun effort.\n**Décision finale** : Pépite absolue. Contacter immédiatement.",
        models: "gemini-2.5-flash → gemini-2.5-pro", date: "Il y a 22 min",
    },
    {
        id: '3', verdict: 'LUTHIER_PROJ',
        title: "STRATOCASTER SQUIER MANCHE FISSURÉ - PROJET",
        price: 85, estValue: 280, margin: 195,
        location: "Laval, QC", taxonomy: "Électrique", classification: 'electrique.solid_body.strat_style.squier', type: 'electrique',
        imageUrls: [
            "https://images.unsplash.com/photo-1550291652-6ea9114a47b1?auto=format&fit=crop&q=80&w=600&h=800",
            "https://images.unsplash.com/photo-1604547990520-a7d08f49a888?auto=format&fit=crop&q=80&w=600&h=800"
        ],
        confidence: 79,
        reasoning: "• 💰 Prix : 85$\n• 💡 Valeur après travaux : ~280$\n• 🛠️ Intérêt Restauration (8/10) : Corps Standard Series des années 2000 (bois massif). Fissure au talon du manche.\n• 📈 Marge Estimée : Remplacement manche (~60$), reste ~135$ de marge.\nParfaitement adapté pour un assemblage partcaster ou un training de lutherie.",
        models: "gemini-2.5-flash-lite → gemini-2.5-flash", date: "Il y a 45 min",
    },
    {
        id: '4', verdict: 'CASE_WIN',
        title: "GUITARE CLASSIQUE INCONNUE DANS BEL ÉTUI",
        price: 60, estValue: 120, margin: 60,
        location: "Brossard, QC", taxonomy: "Acoustique_Vocal", classification: 'accessoire.etui.etui_rigide', type: 'accessoire',
        imageUrls: [
            "https://plus.unsplash.com/premium_photo-1681406994511-925208ebcb73?auto=format&fit=crop&q=80&w=600&h=800",
            "https://images.unsplash.com/photo-1558299834-8c83e206000c?auto=format&fit=crop&q=80&w=600&h=800"
        ],
        confidence: 85,
        reasoning: "• 🎯 Authenticité (N/A) : Guitare copie asiatique sans valeur (plywood).\n• 💼 Accessoire (9/10) : L'étui sur les photos 2 et 3 est un étui rigide vintage style TKL des années 80.\n• 📈 Marge Potentielle : La guitare vaut 0$, mais l'étui seul se vend entre 80$ et 120$.\nAchat justifié uniquement pour conserver/revendre l'étui.",
        models: "gemini-2.5-flash", date: "Il y a 1h12",
    },
    {
        id: '5', verdict: 'COLLECTION',
        title: "TAKAMINE EG523SC ELECTRO-ACOUSTIQUE",
        price: 450, estValue: 550, margin: 100,
        location: "Longueuil, QC", taxonomy: "Acoustique_Vocal", classification: 'acoustique.electro_acoustique.folk_electro', type: 'acoustique',
        imageUrls: [
            "https://images.unsplash.com/photo-1516924962500-2b4b3b99ea02?auto=format&fit=crop&q=80&w=600&h=800",
            "https://images.unsplash.com/photo-1525201548942-d8732f6617a0?auto=format&fit=crop&q=80&w=600&h=800"
        ],
        confidence: 71,
        reasoning: "• 💰 Prix demandé : 450 $ CAD\n• 💡 Valeur marché : ~550 $ CAD\n• 🎯 Authenticité (9/10)\n• 💨 Liquidité (6/10) : Modèle Jumbo, clientèle un peu plus restreinte.\nPrix au marché de l'occasion particulier. Bonne guitare mais marge insuffisante pour un flip (bloquera de la trésorerie). Convient à un joueur personnel.",
        models: "gemini-2.5-flash", date: "Il y a 2h",
    },
    {
        id: '6', verdict: 'FAST_FLIP',
        title: "BASSE FENDER PLAYER JAZZ BASS SUNBURST",
        price: 480, estValue: 750, margin: 270,
        location: "Verdun, QC", taxonomy: "Basse", classification: 'basse.basse_electrique.jazz_bass.fender', type: 'basse',
        imageUrls: [
            "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&q=80&w=600&h=800",
            "https://images.unsplash.com/photo-1514649923863-ceaf75b7ec00?auto=format&fit=crop&q=80&w=600&h=800"
        ],
        confidence: 88,
        reasoning: "• 💰 Prix demandé : 480 $ CAD\n• 💡 Valeur marché : ~750 $ CAD\n• 🎯 Authenticité (8/10) : Tête et logo conformes à la série Player (MIM).\n• 💨 Liquidité (10/10) : Instrument extrêmement liquide.\nMarge de ~270$. À acheter rapidement, pas de surprise majeure.",
        models: "gemini-2.5-flash-lite → gemini-2.5-flash", date: "Il y a 3h30",
    },
    {
        id: '7', verdict: 'BAD_DEAL',
        title: "EPIPHONE LES PAUL STANDARD TRES BON ETAT",
        price: 750, estValue: 450, margin: -300,
        location: "Repentigny, QC", taxonomy: "Électrique", classification: 'electrique.solid_body.les_paul_style.epiphone', type: 'electrique',
        imageUrls: [
            "https://images.unsplash.com/photo-1562080006-251f284c2dd7?auto=format&fit=crop&q=80&w=600&h=800"
        ],
        confidence: 94,
        reasoning: "• 💰 Prix demandé : 750 $ CAD\n• 💡 Valeur marché : ~450 $ CAD\n• 🚨 ALERTE : Le vendeur demande le prix d'une guitare neuve + taxes pour une occasion standard.\nAucune discussion possible, perte sèche de trésorerie garantie.",
        models: "gemini-2.5-flash", date: "Il y a 5h",
    },
    {
        id: '8', verdict: 'REJECTED_ITEM',
        title: "MÉDIATORS DUNLOP JAZZ III",
        price: 5, estValue: null, margin: null,
        location: "Saint-Hyacinthe, QC", taxonomy: "Autre", classification: 'accessoire', type: 'accessoire',
        imageUrls: [
            "https://images.unsplash.com/photo-1627993325603-c0d10e53e414?auto=format&fit=crop&q=80&w=600&h=800"
        ],
        confidence: 99,
        reasoning: "REJET PORTIER TIER 1: Accessoire mineur ou consommable (Médiators). Hors scope luthier/revendeur.",
        models: "gemini-2.5-flash-lite", date: "Il y a 6h",
    },
];

const INITIAL_FILTERS = {
    verdict: 'ALL',
    level1: 'all',
    level2: 'all',
    level3: 'all',
    level4: 'all',
    condition: 'all',
    price: 'all',
};

const RADAR_VERDICTS = ['PEPITE', 'FAST_FLIP', 'LUTHIER_PROJ', 'CASE_WIN', 'GOOD_DEAL'];
const MARKET_VERDICTS = ['COLLECTION', 'BAD_DEAL', 'FAIR'];

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
// Count helpers for badge display
// ============================================================
const buildDealCounts = (deals) => {
    const verdict = { ALL: deals.length };
    const type = { all: deals.length };

    deals.forEach(d => {
        verdict[d.verdict] = (verdict[d.verdict] || 0) + 1;
        type[d.type] = (type[d.type] || 0) + 1;

        if (d.classification) {
            d.classification.split('.').forEach(part => {
                const key = part;
                type[key] = (type[key] || 0) + 1;
            });
        }
    });
    return { verdict, type };
};

// ============================================================
// Custom Dropdown for Verdict/Status filtering
// ============================================================
const VerdictDropdown = ({ currentVerdict, onSelect, counts }) => {
    const [isOpen, setIsOpen] = useState(false);

    // Group options logically
    const OPTIONS = [
        { id: 'ALL', label: 'Toutes les annonces' },
        { divider: true },
        ...['PEPITE', 'FAST_FLIP', 'LUTHIER_PROJ', 'CASE_WIN', 'COLLECTION', 'BAD_DEAL', 'REJECTED_ITEM', 'INCOMPLETE_DATA']
            .filter(id => ALL_FILTERS_CONFIG[id]) // Safe guard
            .map(id => ({
                id,
                label: ALL_FILTERS_CONFIG[id]?.pluralLabel || ALL_FILTERS_CONFIG[id]?.label || id,
            }))
    ];

    const currentLabel = OPTIONS.find(o => o.id === currentVerdict)?.label || 'Toutes les annonces';

    return (
        <div className="relative shrink-0">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full sm:w-auto flex items-center justify-between sm:justify-start gap-2 h-10 px-4 bg-slate-800 border border-slate-700 hover:bg-slate-700 hover:border-slate-600 rounded-xl text-sm font-bold text-slate-200 transition-all shadow-sm"
            >
                <div>
                    <span className="text-slate-400 font-normal mr-1.5 hidden sm:inline">Statut :</span>
                    <span>{currentLabel}</span>
                </div>
                <ChevronDown size={14} className={`text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <>
                    <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
                    <div className="absolute top-full left-0 sm:right-0 mt-2 w-full sm:w-64 bg-slate-900 border border-slate-700 rounded-2xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] z-50 py-2 animate-in fade-in slide-in-from-top-2">
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
                                    <div className="flex items-center gap-2">
                                        {isActive ? <Check size={14} className="text-blue-500" /> : <div className="w-3.5" />}
                                        <span>{opt.label}</span>
                                    </div>
                                    <span className={`font-mono ${isActive ? 'text-blue-400' : 'text-slate-600 bg-slate-950 px-1.5 py-0.5 rounded-md'}`}>
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
// Mockup Map View Placeholder
// ============================================================
const MockupMapView = ({ deals }) => {
    const [selectedDealId, setSelectedDealId] = useState(null);
    const selectedDeal = deals.find(d => d.id === selectedDealId);

    return (
        <div className="flex flex-col lg:flex-row gap-6 h-[70vh] min-h-[500px]">
            {/* Map Placeholder */}
            <div className="flex-1 bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden relative flex flex-col shadow-inner">
                <div className="flex-1 p-4 relative">
                    {/* Fake Map Background */}
                    <div className="absolute inset-0 bg-slate-800/50" style={{ backgroundImage: 'radial-gradient(circle at 2px 2px, rgba(255,255,255,0.05) 1px, transparent 0)', backgroundSize: '16px 16px' }} />
                    <div className="absolute inset-x-0 bottom-4 text-center pointer-events-none">
                        <span className="bg-slate-900/80 backdrop-blur text-slate-400 text-xs px-4 py-2 rounded-full font-bold uppercase tracking-widest border border-slate-700/50">
                            Interaction Carte Désactivée (Mockup)
                        </span>
                    </div>
                    {/* Fake Pins */}
                    {deals.map((d, i) => (
                        <button
                            key={d.id}
                            onClick={() => setSelectedDealId(d.id)}
                            className={`absolute w-8 h-8 -ml-4 -mt-4 rounded-full flex items-center justify-center font-bold text-xs shadow-xl transition-all hover:scale-125 hover:z-50 ${selectedDealId === d.id ? 'bg-blue-500 text-white ring-4 ring-blue-500/30 z-40' : 'bg-slate-700 text-slate-300 border-2 border-slate-600 z-10'}`}
                            style={{
                                left: `${15 + (i * 27) % 70}%`,
                                top: `${20 + (i * 31) % 60}%`
                            }}
                        >
                            {i + 1}
                        </button>
                    ))}
                </div>
            </div>

            {/* Selected Deal Sidebar (Desktop) or Overlay (Mobile) */}
            {selectedDeal && (
                <div className="w-full lg:w-96 shrink-0 animate-in slide-in-from-right-8 fade-in flex flex-col pt-2 lg:pt-0">
                    <div className="flex items-center justify-between mb-2 lg:hidden px-1">
                        <span className="text-sm font-bold text-slate-300">Détails de l'annonce</span>
                        <button onClick={() => setSelectedDealId(null)} className="p-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors">
                            <X size={16} />
                        </button>
                    </div>
                    <MockupDealCard deal={selectedDeal} />
                </div>
            )}
            {!selectedDeal && (
                <div className="w-full lg:w-96 shrink-0 hidden lg:flex flex-col items-center justify-center bg-slate-900/50 border border-dashed border-slate-800 rounded-3xl p-6 text-center">
                    <MapIcon size={48} className="text-slate-800 mb-4" />
                    <h3 className="text-sm font-black text-slate-500 uppercase tracking-tight mb-2">Sélectionnez une annonce</h3>
                    <p className="text-xs text-slate-600">Cliquez sur un marqueur sur la carte pour afficher les détails ici.</p>
                </div>
            )}
        </div>
    );
};

// ============================================================
// Dashboard
// ============================================================
const MockupDashboard = ({ onClose }) => {
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [showConfig, setShowConfig] = useState(false);
    const [viewMode, setViewMode] = useState('LIST');
    const [openSections, setOpenSections] = useState({ radar: true, market: true, archive: false });
    const [search, setSearch] = useState('');
    const [filters, setFilters] = useState(INITIAL_FILTERS);

    const handleFilterChange = (key, value) => {
        setFilters(prev => ({ ...prev, [key]: value }));
    };

    const handleReset = () => {
        setFilters(INITIAL_FILTERS);
        setSearch('');
    };

    // Counts for the badge on filter drawer button
    const allCounts = useMemo(() => buildDealCounts(FAKE_DEALS), []);

    // Live filtering
    const filtered = useMemo(() => {
        return FAKE_DEALS.filter(d => {
            if (filters.verdict !== 'ALL' && d.verdict !== filters.verdict) return false;
            if (filters.level1 !== 'all' && d.type !== filters.level1) return false;
            // Price range filter
            if (filters.price !== 'all') {
                if (filters.price === 'under100' && d.price >= 100) return false;
                if (filters.price === '100-300' && (d.price < 100 || d.price > 300)) return false;
                if (filters.price === '300-600' && (d.price < 300 || d.price > 600)) return false;
                if (filters.price === 'over600' && d.price <= 600) return false;
            }
            if (search && !d.title.toLowerCase().includes(search.toLowerCase()) && !d.location.toLowerCase().includes(search.toLowerCase())) return false;
            return true;
        });
    }, [filters, search]);

    const radarDeals = filtered.filter(d => RADAR_VERDICTS.includes(d.verdict));
    const marketDeals = filtered.filter(d => MARKET_VERDICTS.includes(d.verdict));
    const archiveDeals = filtered.filter(d => !RADAR_VERDICTS.includes(d.verdict) && !MARKET_VERDICTS.includes(d.verdict));

    const activeFilterCount = Object.entries(filters).filter(([k, v]) => v !== 'ALL' && v !== 'all').length;

    const toggle = (s) => setOpenSections(prev => ({ ...prev, [s]: !prev[s] }));

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
            <MockupNavbar
                onOpenFilters={() => setDrawerOpen(true)}
                onOpenSettings={() => setShowConfig(s => !s)}
                onClose={onClose}
                filterCount={activeFilterCount}
            />

            <MockupFilterDrawer
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                filters={filters}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                counts={{ ...allCounts.type, all: FAKE_DEALS.length }}
            />

            {/* Real ConfigPanel — opens via gear icon */}
            <ConfigPanel showConfig={showConfig} onClose={() => setShowConfig(false)} />

            <div className="max-w-7xl mx-auto px-4 py-8">

                {/* ─── Search & Actions ─── */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 mb-6 flex flex-col sm:flex-row gap-3">
                    {/* Search */}
                    <div className="relative flex-1">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 shrink-0" />
                        <input
                            type="text"
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            placeholder="Rechercher par modèle, lieu..."
                            className="w-full h-10 bg-slate-800 border border-slate-700 rounded-xl pl-9 pr-10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all"
                        />
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                            >
                                <X size={14} />
                            </button>
                        )}
                    </div>

                    {/* Verdict Filter Dropdown */}
                    <VerdictDropdown
                        currentVerdict={filters.verdict}
                        onSelect={(v) => handleFilterChange('verdict', v)}
                        counts={allCounts.verdict}
                    />

                    {/* View Mode Toggle */}
                    <div className="flex bg-slate-800 p-1 rounded-xl shrink-0 h-10 border border-slate-700">
                        <button onClick={() => setViewMode('LIST')} className={`px-3 flex items-center justify-center rounded-lg transition-all ${viewMode === 'LIST' ? 'bg-slate-700 shadow-sm text-blue-400' : 'text-slate-500 hover:text-slate-300'}`}><List size={16} /></button>
                        <button onClick={() => setViewMode('MAP')} className={`px-3 flex items-center justify-center rounded-lg transition-all ${viewMode === 'MAP' ? 'bg-slate-700 shadow-sm text-blue-400' : 'text-slate-500 hover:text-slate-300'}`}><MapIcon size={16} /></button>
                        <button onClick={() => setViewMode('STATS')} className={`px-3 flex items-center justify-center rounded-lg transition-all ${viewMode === 'STATS' ? 'bg-slate-700 shadow-sm text-purple-400' : 'text-slate-500 hover:text-slate-300'}`}>
                            <Activity size={16} />
                        </button>
                    </div>

                    {/* Results Count & Clear Filters (Moved into the bar) */}
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-2 shrink-0 sm:ml-2">
                        <span className="text-xs text-slate-500 font-mono hidden xl:block">
                            {filtered.length} annonce{filtered.length !== 1 ? 's' : ''}
                        </span>
                        {(activeFilterCount > 0 || search) && (
                            <button onClick={handleReset} className="flex items-center justify-center h-10 w-10 bg-rose-500/10 hover:bg-rose-500/20 rounded-xl text-rose-400 hover:text-rose-300 transition-colors border border-rose-500/20" title="Effacer tous les filtres">
                                <X size={16} />
                            </button>
                        )}
                    </div>
                </div>


                {viewMode === 'STATS' ? (
                    <MockupStatsView deals={filtered} />
                ) : viewMode === 'MAP' ? (
                    <MockupMapView deals={filtered} />
                ) : (
                    <>
                        {/* ─── Sections ─── */}
                        {radarDeals.length > 0 && (
                            <div>
                                <SectionHeader icon={Target} title="Radar" count={radarDeals.length} color="text-emerald-400" open={openSections.radar} onToggle={() => toggle('radar')} />
                                {openSections.radar && (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-4">
                                        {radarDeals.map(d => <MockupDealCard key={d.id} deal={d} />)}
                                    </div>
                                )}
                            </div>
                        )}

                        {marketDeals.length > 0 && (
                            <div>
                                <SectionHeader icon={ShoppingBag} title="Marché" count={marketDeals.length} color="text-blue-400" open={openSections.market} onToggle={() => toggle('market')} />
                                {openSections.market && (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-4">
                                        {marketDeals.map(d => <MockupDealCard key={d.id} deal={d} />)}
                                    </div>
                                )}
                            </div>
                        )}

                        {archiveDeals.length > 0 && (
                            <div>
                                <SectionHeader icon={Archive} title="Archives & Bruit" count={archiveDeals.length} color="text-slate-500" open={openSections.archive} onToggle={() => toggle('archive')} />
                                {openSections.archive && (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-4">
                                        {archiveDeals.map(d => <MockupDealCard key={d.id} deal={d} />)}
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}

                {filtered.length === 0 && (
                    <div className="py-20 flex flex-col items-center justify-center bg-slate-900 rounded-2xl border border-dashed border-slate-800">
                        <Search size={40} className="text-slate-800 mb-4" />
                        <h3 className="text-base font-black text-slate-500 uppercase tracking-tight">Aucun résultat</h3>
                        <button onClick={handleReset} className="mt-3 text-xs text-blue-400 hover:text-blue-300 transition-colors">
                            Effacer les filtres
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default MockupDashboard;
