import React from 'react';
import { X, ChevronDown, ChevronUp } from 'lucide-react';

import TaxonomyTreePicker from './TaxonomyTreePicker';

const CONDITION_OPTIONS = [
    { value: 'all', label: 'Toutes' },
    { value: 'excellent', label: 'Excellent état' },
    { value: 'good', label: 'Bon état' },
    { value: 'project', label: 'Projet / À restaurer' },
];

const PRICE_OPTIONS = [
    { value: 'all', label: 'Tous les prix' },
    { value: 'under100', label: 'Moins de 100 $' },
    { value: '100-300', label: '100 $ – 300 $' },
    { value: '300-600', label: '300 $ – 600 $' },
    { value: 'over600', label: '600 $+' },
];

// Valeurs alignées mot pour mot avec la liste fermée de prompts.json (finish_application/
// finish_texture) — comparaison stricte côté useDealsManager, pas de fuzzy matching.
const FINISH_APPLICATION_OPTIONS = [
    { value: 'ALL', label: 'Toutes' },
    { value: 'Peinture opaque', label: 'Peinture opaque' },
    { value: 'Vernis/Laque transparente', label: 'Vernis / Laque transparente' },
    { value: 'Teinture', label: 'Teinture' },
    { value: 'Naturel/Brut', label: 'Naturel / Brut' },
];

const FINISH_TEXTURE_OPTIONS = [
    { value: 'ALL', label: 'Toutes' },
    { value: 'Brillant', label: 'Brillant' },
    { value: 'Satiné/Soyeux', label: 'Satiné / Soyeux' },
    { value: 'Mat', label: 'Mat' },
];

const SORT_OPTIONS = [
    { value: 'date', label: 'Date d\'analyse (défaut)' },
    { value: 'publish_date', label: 'Date de mise en vente' },
    { value: 'sold_date', label: 'Date de vente' },
    { value: 'interest', label: 'Plus intéressantes (note IA)' },
];

// ============================================================
// Reusable collapsible group
// ============================================================
const FilterGroup = ({ label, children, defaultOpen = false }) => {
    const [open, setOpen] = React.useState(defaultOpen);

    return (
        <div className="border-b border-slate-800 pb-3 mb-3 last:border-0 last:pb-0 last:mb-0">
            <button
                className="w-full flex items-center justify-between py-2 text-[11px] font-black uppercase tracking-widest text-slate-400 hover:text-slate-200 transition-colors"
                onClick={() => setOpen(o => !o)}
            >
                <span>{label}</span>
                {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {open && <div className="mt-1 flex flex-col gap-0.5">{children}</div>}
        </div>
    );
};

// ============================================================
// Inline Option — single-select (radio-style, ex: condition/prix/tri)
// ============================================================
const InlineOption = ({ label, active, onClick, depth = 0 }) => {
    const paddingLeft = depth === 0 ? 'px-2' : 'pl-6 pr-2';
    const indicatorSize = 'w-3.5 h-3.5';

    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-3 text-left py-2.5 sm:py-2 rounded-lg transition-all w-full ${paddingLeft} ${active ? 'bg-blue-600/10 border border-blue-500/20' : 'hover:bg-slate-800 border border-transparent'
                }`}
        >
            <div className={`${indicatorSize} shrink-0 rounded-full border-2 flex items-center justify-center transition-all ${active ? 'border-blue-500 bg-blue-500' : 'border-slate-600'
                }`}>
                {active && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
            </div>
            <span className={`flex-1 leading-tight text-sm ${active ? 'text-white font-semibold' : 'text-slate-300'}`}>
                {label}
            </span>
        </button>
    );
};

// ============================================================
// Main Drawer — Taxonomie en Multi-Sélection
// ============================================================
const FilterDrawer = ({ open, onClose, filters, onFilterChange, onReset, counts = {}, selectedTypePaths = [], onToggleType, onClearTypes }) => {
    const { condition, price, finishApplication = 'ALL', finishTexture = 'ALL', sort = 'date' } = filters;

    const activeCount = [
        selectedTypePaths.length,
        condition !== 'all' ? 1 : 0,
        price !== 'all' ? 1 : 0,
        finishApplication !== 'ALL' ? 1 : 0,
        finishTexture !== 'ALL' ? 1 : 0,
    ].reduce((a, b) => a + b, 0);

    return (
        <>
            {open && <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40" onClick={onClose} />}

            <aside className={`fixed top-0 right-0 h-full w-80 bg-slate-900 border-l border-slate-800 z-50 flex flex-col shadow-2xl shadow-black/80 transition-transform duration-300 ease-in-out ${open ? 'translate-x-0' : 'translate-x-full'}`}>

                {/* Header */}
                <div className="h-16 px-5 flex items-center justify-between border-b border-slate-800 shrink-0 bg-slate-900/50 backdrop-blur-md">
                    <div className="flex items-center gap-3">
                        <h2 className="text-sm font-black uppercase tracking-widest text-white">Filtres</h2>
                        {activeCount > 0 && (
                            <span className="bg-blue-600 text-white text-[10px] font-black w-5 h-5 rounded-full flex items-center justify-center">
                                {activeCount}
                            </span>
                        )}
                        {/* DEBUG helper: <span className="text-[10px] text-red-500">{Object.keys(counts).length} counts</span> */}
                    </div>
                    <div className="flex items-center gap-2">
                        {activeCount > 0 && (
                            <button onClick={onReset} className="text-[10px] uppercase font-bold text-slate-400 hover:text-white transition-colors">
                                Réinitialiser
                            </button>
                        )}
                        <button onClick={onClose} className="p-1 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors">
                            <X size={20} />
                        </button>
                    </div>
                </div>

                {/* Scrollable body */}
                {/* Scrollable body */}
                <div className="flex-1 overflow-y-auto p-5 pb-20 space-y-6 scrollbar-dark">

                    {/* ── Tri ── */}
                    <FilterGroup label="Trier par" defaultOpen={true}>
                        {SORT_OPTIONS.map(opt => (
                            <InlineOption
                                key={opt.value}
                                label={opt.label}
                                active={sort === opt.value}
                                onClick={() => onFilterChange('sort', opt.value)}
                                depth={0}
                            />
                        ))}
                    </FilterGroup>

                    {/* ── Taxonomy Tree (Inline Accordion) ── */}
                    <FilterGroup label="Type d'instrument" defaultOpen={true}>
                        <TaxonomyTreePicker
                            selectedPaths={selectedTypePaths}
                            onTogglePath={onToggleType}
                            showClearAllOption
                            onClearPaths={onClearTypes}
                            clearAllLabel="Tous les types"
                            counts={counts}
                        />
                    </FilterGroup>

                    {/* ── Condition ── */}
                    <FilterGroup label="Condition estimée" defaultOpen={true}>
                        {CONDITION_OPTIONS.map(opt => (
                            <InlineOption
                                key={opt.value}
                                label={opt.label}
                                active={condition === opt.value}
                                onClick={() => onFilterChange('condition', opt.value)}
                                depth={0}
                            />
                        ))}
                    </FilterGroup>

                    {/* ── Price ── */}
                    <FilterGroup label="Fourchette de prix" defaultOpen={true}>
                        {PRICE_OPTIONS.map(opt => (
                            <InlineOption
                                key={opt.value}
                                label={opt.label}
                                active={price === opt.value}
                                onClick={() => onFilterChange('price', opt.value)}
                                depth={0}
                            />
                        ))}
                    </FilterGroup>

                    {/* ── Finition (application) ── */}
                    <FilterGroup label="Finition">
                        {FINISH_APPLICATION_OPTIONS.map(opt => (
                            <InlineOption
                                key={opt.value}
                                label={opt.label}
                                active={finishApplication === opt.value}
                                onClick={() => onFilterChange('finishApplication', opt.value)}
                                depth={0}
                            />
                        ))}
                    </FilterGroup>

                    {/* ── Finition (brillance) ── */}
                    <FilterGroup label="Brillance">
                        {FINISH_TEXTURE_OPTIONS.map(opt => (
                            <InlineOption
                                key={opt.value}
                                label={opt.label}
                                active={finishTexture === opt.value}
                                onClick={() => onFilterChange('finishTexture', opt.value)}
                                depth={0}
                            />
                        ))}
                    </FilterGroup>

                </div>
            </aside>
        </>
    );
};

export default FilterDrawer;
