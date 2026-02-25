import React from 'react';
import { X, ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';

// ============================================================
// 4-LEVEL TAXONOMY TREE
// level1 → level2 → level3 → level4
// ============================================================
const TAXONOMY_TREE = {
    electrique: {
        label: 'Électrique',
        children: {
            solid_body: {
                label: 'Solid Body',
                children: {
                    strat_style: { label: 'Strat / Tele Style', children: { fender: 'Fender', squier: 'Squier', other: 'Autre marque' } },
                    les_paul_style: { label: 'Les Paul / SG Style', children: { gibson: 'Gibson', epiphone: 'Epiphone', other: 'Autre marque' } },
                    other_solid: { label: 'Autre Solid Body', children: {} },
                },
            },
            hollow_body: {
                label: 'Semi / Hollow Body',
                children: {
                    es_style: { label: 'ES Style (335 etc.)', children: { gibson: 'Gibson', epiphone: 'Epiphone', other: 'Autre' } },
                    gretsch_style: { label: 'Gretsch / Archtop', children: { gretsch: 'Gretsch', other: 'Autre' } },
                    other_hollow: { label: 'Autre Semi-Hollow', children: {} },
                },
            },
            ampli_electrique: {
                label: 'Ampli (Électrique)',
                children: {
                    combo: { label: 'Combo', children: {} },
                    tete_baffle: { label: 'Tête + Baffle', children: {} },
                    mini_ampli: { label: 'Mini / Practice', children: {} },
                },
            },
        },
    },
    acoustique: {
        label: 'Acoustique / Vocal',
        children: {
            folk: {
                label: 'Folk / Western',
                children: {
                    dreadnought: { label: 'Dreadnought', children: {} },
                    parlor: { label: 'Parlor', children: {} },
                    jumbo: { label: 'Jumbo / Grand Auditorium', children: {} },
                },
            },
            classique: {
                label: 'Classique / Nylon',
                children: {
                    classique_concert: { label: 'Concert / Étude', children: {} },
                    flamenca: { label: 'Flamenca', children: {} },
                },
            },
            electro_acoustique: {
                label: 'Électro-acoustique',
                children: {
                    folk_electro: { label: 'Folk + Préamp', children: {} },
                    classique_electro: { label: 'Nylon + Préamp', children: {} },
                },
            },
            ampli_acoustique: {
                label: 'Ampli Acoustique',
                children: {
                    combo_acou: { label: 'Combo Acoustique', children: {} },
                    sono_portable: { label: 'Sono / Portable', children: {} },
                },
            },
        },
    },
    basse: {
        label: 'Basse',
        children: {
            basse_electrique: {
                label: 'Basse Électrique',
                children: {
                    jazz_bass: { label: 'Jazz Bass Style', children: { fender: 'Fender', squier: 'Squier', other: 'Autre' } },
                    precision_bass: { label: 'Precision Bass Style', children: { fender: 'Fender', squier: 'Squier', other: 'Autre' } },
                    other_basse: { label: 'Autre Style', children: {} },
                },
            },
            short_scale: { label: 'Short Scale', children: {} },
            basse_acoustique: { label: 'Basse Acoustique', children: {} },
            ampli_basse: {
                label: 'Ampli Basse',
                children: {
                    combo_basse: { label: 'Combo Basse', children: {} },
                    tete_basse_baffle: { label: 'Tête + Baffle', children: {} },
                },
            },
        },
    },
    accessoire: {
        label: 'Accessoire',
        children: {
            etui: {
                label: 'Étui & Gigbag',
                children: {
                    etui_rigide: { label: 'Étui Rigide', children: {} },
                    gigbag: { label: 'Gigbag', children: {} },
                    semi_rigide: { label: 'Semi-rigide', children: {} },
                },
            },
            pedales: {
                label: 'Pédales & Effets',
                children: {
                    overdrive_dist: { label: 'Overdrive / Distortion', children: {} },
                    reverb_delay: { label: 'Reverb / Delay', children: {} },
                    multi_effets: { label: 'Multi-effets', children: {} },
                    other_pedales: { label: 'Autre pédales', children: {} },
                },
            },
            cordes: { label: 'Cordes', children: { cordes_elec: 'Électrique', cordes_acou: 'Acoustique', cordes_basse: 'Basse' } },
            autre_accessoire: { label: 'Autre Accessoire', children: {} },
        },
    },
};

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

// ============================================================
// Reusable collapsible group — collapsed by default
// ============================================================
const FilterGroup = ({ label, children, sublabel, defaultOpen = false }) => {
    const [open, setOpen] = React.useState(defaultOpen);

    return (
        <div className="border-b border-slate-800 pb-3 mb-3 last:border-0 last:pb-0 last:mb-0">
            <button
                className="w-full flex items-center justify-between py-1 text-[11px] font-black uppercase tracking-widest text-slate-400 hover:text-slate-200 transition-colors"
                onClick={() => setOpen(o => !o)}
            >
                <span>
                    {label}
                    {sublabel && <span className="ml-1.5 normal-case text-slate-600 font-normal tracking-normal">· {sublabel}</span>}
                </span>
                {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            {open && <div className="mt-2 flex flex-col gap-0.5">{children}</div>}
        </div>
    );
};

// Selectable radio option row
const FilterOption = ({ label, active, onClick, hasChildren }) => (
    <button
        onClick={onClick}
        className={`flex items-center gap-2.5 text-left py-1.5 px-2 rounded-lg transition-all w-full ${active
                ? 'bg-blue-600/20 border border-blue-500/30'
                : 'hover:bg-slate-800 border border-transparent'
            }`}
    >
        <div className={`w-3.5 h-3.5 shrink-0 rounded-full border-2 flex items-center justify-center transition-all ${active ? 'border-blue-500 bg-blue-500' : 'border-slate-600'
            }`}>
            {active && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
        </div>
        <span className={`text-sm flex-1 leading-tight ${active ? 'text-white font-semibold' : 'text-slate-300'}`}>
            {label}
        </span>
        {hasChildren && <ChevronRight size={12} className={active ? 'text-blue-400' : 'text-slate-700'} />}
    </button>
);

// Simple radio option for leaf values
const LeafOption = ({ label, active, onClick }) => (
    <button
        onClick={onClick}
        className={`flex items-center gap-2 text-left py-1.5 pl-6 pr-2 rounded-lg transition-all w-full ${active ? 'bg-blue-600/20 border border-blue-500/30' : 'hover:bg-slate-800 border border-transparent'
            }`}
    >
        <div className={`w-3 h-3 shrink-0 rounded-full border-2 transition-all ${active ? 'border-blue-500 bg-blue-500' : 'border-slate-700'
            }`} />
        <span className={`text-xs flex-1 ${active ? 'text-white font-semibold' : 'text-slate-400'}`}>{label}</span>
    </button>
);

// ============================================================
// Main Drawer — 4-level cascading taxonomy
// ============================================================
const MockupFilterDrawer = ({ open, onClose, filters, onFilterChange, onReset }) => {
    const { level1, level2, level3, level4, condition, price } = filters;

    const l1Data = level1 !== 'all' ? TAXONOMY_TREE[level1] : null;
    const l2Data = l1Data && level2 !== 'all' ? l1Data.children[level2] : null;
    const l3Data = l2Data && level3 !== 'all' ? l2Data.children?.[level3] : null;

    const handleL1 = (v) => {
        onFilterChange('level1', v);
        onFilterChange('level2', 'all');
        onFilterChange('level3', 'all');
        onFilterChange('level4', 'all');
    };
    const handleL2 = (v) => {
        onFilterChange('level2', v);
        onFilterChange('level3', 'all');
        onFilterChange('level4', 'all');
    };
    const handleL3 = (v) => {
        onFilterChange('level3', v);
        onFilterChange('level4', 'all');
    };
    const handleL4 = (v) => onFilterChange('level4', v);

    const l3Children = l2Data?.children || {};
    const l4Children = l3Data?.children || {};
    const hasL3 = l2Data && Object.keys(l3Children).length > 0;
    const hasL4 = l3Data && Object.keys(l4Children).length > 0;

    const activeCount = [
        level1 !== 'all', level2 !== 'all', level3 !== 'all', level4 !== 'all',
        condition !== 'all', price !== 'all',
    ].filter(Boolean).length;

    return (
        <>
            {open && <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40" onClick={onClose} />}

            <aside className={`fixed top-0 right-0 h-full w-80 bg-slate-900 border-l border-slate-800 z-50 flex flex-col shadow-2xl shadow-black/60 transition-transform duration-300 ease-in-out ${open ? 'translate-x-0' : 'translate-x-full'}`}>

                {/* Header */}
                <div className="h-16 px-4 flex items-center justify-between border-b border-slate-800 shrink-0">
                    <div className="flex items-center gap-2">
                        <h2 className="text-sm font-black uppercase tracking-widest text-white">Filtres</h2>
                        {activeCount > 0 && (
                            <span className="bg-blue-600 text-white text-[10px] font-black w-5 h-5 rounded-full flex items-center justify-center">
                                {activeCount}
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-1.5">
                        {activeCount > 0 && (
                            <button onClick={onReset} className="text-[11px] text-slate-500 hover:text-slate-200 font-medium px-2 py-1 rounded-lg hover:bg-slate-800 transition-all">
                                Réinitialiser
                            </button>
                        )}
                        <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-all">
                            <X size={16} />
                        </button>
                    </div>
                </div>

                {/* Scrollable body */}
                <div className="flex-1 overflow-y-auto p-4 space-y-0">

                    {/* ── Level 1: Type ── */}
                    <FilterGroup label="Type d'instrument">
                        <FilterOption label="Tous les types" active={level1 === 'all'} onClick={() => handleL1('all')} />
                        {Object.entries(TAXONOMY_TREE).map(([key, cfg]) => (
                            <FilterOption
                                key={key}
                                label={cfg.label}
                                active={level1 === key}
                                onClick={() => handleL1(key)}
                                hasChildren={Object.keys(cfg.children).length > 0}
                            />
                        ))}
                    </FilterGroup>

                    {/* ── Level 2: Subcategory (only if L1 is selected) ── */}
                    {l1Data && (
                        <FilterGroup
                            label="Sous-catégorie"
                            sublabel={l1Data.label}
                            defaultOpen={true}
                        >
                            <FilterOption label="Toutes" active={level2 === 'all'} onClick={() => handleL2('all')} />
                            {Object.entries(l1Data.children).map(([key, cfg]) => (
                                <FilterOption
                                    key={key}
                                    label={cfg.label}
                                    active={level2 === key}
                                    onClick={() => handleL2(key)}
                                    hasChildren={cfg.children && Object.keys(cfg.children).length > 0}
                                />
                            ))}
                        </FilterGroup>
                    )}

                    {/* ── Level 3: Model (only if L2 is selected and has children) ── */}
                    {hasL3 && (
                        <FilterGroup
                            label="Modèle / Type"
                            sublabel={l2Data.label}
                            defaultOpen={true}
                        >
                            <FilterOption label="Tous" active={level3 === 'all'} onClick={() => handleL3('all')} />
                            {Object.entries(l3Children).map(([key, cfg]) => {
                                const label = typeof cfg === 'string' ? cfg : cfg.label;
                                const hasChildren = typeof cfg !== 'string' && cfg.children && Object.keys(cfg.children).length > 0;
                                return (
                                    <FilterOption
                                        key={key}
                                        label={label}
                                        active={level3 === key}
                                        onClick={() => handleL3(key)}
                                        hasChildren={hasChildren}
                                    />
                                );
                            })}
                        </FilterGroup>
                    )}

                    {/* ── Level 4: Brand / Detail (only if L3 is selected and has children) ── */}
                    {hasL4 && (
                        <FilterGroup
                            label="Marque / Détail"
                            sublabel={typeof l3Children[level3] === 'object' ? l3Children[level3]?.label : l3Children[level3]}
                            defaultOpen={true}
                        >
                            <FilterOption label="Toutes" active={level4 === 'all'} onClick={() => handleL4('all')} />
                            {Object.entries(l4Children).map(([key, label]) => (
                                <LeafOption
                                    key={key}
                                    label={typeof label === 'string' ? label : label.label}
                                    active={level4 === key}
                                    onClick={() => handleL4(key)}
                                />
                            ))}
                        </FilterGroup>
                    )}

                    {/* ── Condition ── */}
                    <FilterGroup label="Condition estimée">
                        {CONDITION_OPTIONS.map(opt => (
                            <FilterOption
                                key={opt.value}
                                label={opt.label}
                                active={condition === opt.value}
                                onClick={() => onFilterChange('condition', opt.value)}
                            />
                        ))}
                    </FilterGroup>

                    {/* ── Price ── */}
                    <FilterGroup label="Fourchette de prix">
                        {PRICE_OPTIONS.map(opt => (
                            <FilterOption
                                key={opt.value}
                                label={opt.label}
                                active={price === opt.value}
                                onClick={() => onFilterChange('price', opt.value)}
                            />
                        ))}
                    </FilterGroup>

                </div>
            </aside>
        </>
    );
};

export default MockupFilterDrawer;
