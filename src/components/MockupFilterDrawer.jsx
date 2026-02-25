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
// Inline Option with dynamic depth styling
// ============================================================
const InlineOption = ({ label, active, onClick, hasChildren, depth = 0, count }) => {
    // Dynamic styling based on depth
    const paddingLeft = depth === 0 ? 'px-2' : depth === 1 ? 'pl-6 pr-2' : depth === 2 ? 'pl-10 pr-2' : 'pl-14 pr-2';
    const textSize = depth === 0 ? 'text-sm' : depth === 1 ? 'text-[13px]' : depth === 2 ? 'text-xs' : 'text-[11px]';
    const indicatorSize = depth >= 2 ? 'w-2.5 h-2.5' : 'w-3.5 h-3.5';

    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-2.5 text-left py-2 rounded-lg transition-all w-full ${paddingLeft} ${active ? 'bg-blue-600/10 border border-blue-500/20' : 'hover:bg-slate-800 border border-transparent'
                }`}
        >
            <div className={`${indicatorSize} shrink-0 rounded-full border-2 flex items-center justify-center transition-all ${active ? 'border-blue-500 bg-blue-500' : 'border-slate-600'
                }`}>
                {active && depth < 2 && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
            </div>

            <span className={`flex-1 leading-tight ${textSize} ${active ? 'text-white font-semibold' : depth === 0 ? 'text-slate-300' : 'text-slate-400'
                }`}>
                {label}
            </span>

            {count > 0 && (
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-md ${active ? 'bg-blue-500/20 text-blue-200' : 'bg-slate-800 text-slate-500'}`}>
                    {count}
                </span>
            )}

            {hasChildren && <ChevronRight size={14} className={active ? 'text-blue-400' : 'text-slate-600'} />}
        </button>
    );
};


// ============================================================
// Main Drawer — Inline Cascading Taxonomy
// ============================================================
const MockupFilterDrawer = ({ open, onClose, filters, onFilterChange, onReset, counts = {} }) => {
    const { level1, level2, level3, level4, condition, price } = filters;

    const handleLevelSelect = (level, value) => {
        onFilterChange(level, value);
        // Reset all deeper levels
        if (level === 'level1') {
            onFilterChange('level2', 'all');
            onFilterChange('level3', 'all');
            onFilterChange('level4', 'all');
        } else if (level === 'level2') {
            onFilterChange('level3', 'all');
            onFilterChange('level4', 'all');
        } else if (level === 'level3') {
            onFilterChange('level4', 'all');
        }
    };

    const activeCount = [
        level1 !== 'all', level2 !== 'all', level3 !== 'all', level4 !== 'all',
        condition !== 'all', price !== 'all',
    ].filter(Boolean).length;

    // Recursive render function for the taxonomy tree
    const renderTaxonomyTree = () => {
        return (
            <div className="flex flex-col gap-0.5">
                <InlineOption
                    label="Tous les types"
                    active={level1 === 'all'}
                    onClick={() => handleLevelSelect('level1', 'all')}
                    depth={0}
                    count={counts.all}
                />

                {Object.entries(TAXONOMY_TREE).map(([l1Key, l1Cfg]) => {
                    const isL1Active = level1 === l1Key;
                    const hasL2Children = Object.keys(l1Cfg.children).length > 0;

                    return (
                        <React.Fragment key={l1Key}>
                            <InlineOption
                                label={l1Cfg.label}
                                active={isL1Active}
                                onClick={() => handleLevelSelect('level1', l1Key)}
                                hasChildren={hasL2Children && !isL1Active} // Show chevron only if it has children and is not open
                                depth={0}
                                count={counts[l1Key]}
                            />

                            {/* LEVEL 2 Rendering (Inline under L1) */}
                            {isL1Active && hasL2Children && (
                                <div className="mt-1 flex flex-col gap-0.5 mb-2 relative border-l-2 border-slate-700/50 ml-[11px]">

                                    {Object.entries(l1Cfg.children).map(([l2Key, l2Cfg]) => {
                                        const isL2Active = level2 === l2Key;
                                        const hasL3Children = l2Cfg.children && Object.keys(l2Cfg.children).length > 0;

                                        return (
                                            <React.Fragment key={l2Key}>
                                                <InlineOption
                                                    label={l2Cfg.label}
                                                    active={isL2Active}
                                                    onClick={() => handleLevelSelect('level2', l2Key)}
                                                    hasChildren={hasL3Children && !isL2Active}
                                                    depth={1}
                                                    count={counts[l2Key]}
                                                />

                                                {/* LEVEL 3 Rendering (Inline under L2) */}
                                                {isL2Active && hasL3Children && (
                                                    <div className="mt-1 flex flex-col gap-0.5 mb-2 relative border-l-2 border-slate-700/50 ml-7">

                                                        {Object.entries(l2Cfg.children).map(([l3Key, l3Cfg]) => {
                                                            const l3Label = typeof l3Cfg === 'string' ? l3Cfg : l3Cfg.label;
                                                            const isL3Active = level3 === l3Key;
                                                            const hasL4Children = typeof l3Cfg !== 'string' && l3Cfg.children && Object.keys(l3Cfg.children).length > 0;

                                                            return (
                                                                <React.Fragment key={l3Key}>
                                                                    <InlineOption
                                                                        label={l3Label}
                                                                        active={isL3Active}
                                                                        onClick={() => handleLevelSelect('level3', l3Key)}
                                                                        hasChildren={hasL4Children && !isL3Active}
                                                                        depth={2}
                                                                        count={counts[l3Key]}
                                                                    />

                                                                    {/* LEVEL 4 Rendering (Inline under L3) */}
                                                                    {isL3Active && hasL4Children && (
                                                                        <div className="mt-1 flex flex-col gap-0.5 mb-1 relative border-l-2 border-slate-700/50 ml-10">

                                                                            {Object.entries(l3Cfg.children).map(([l4Key, l4LabelObj]) => {
                                                                                const l4Label = typeof l4LabelObj === 'string' ? l4LabelObj : l4LabelObj.label;
                                                                                return (
                                                                                    <InlineOption
                                                                                        key={l4Key}
                                                                                        label={l4Label}
                                                                                        active={level4 === l4Key}
                                                                                        onClick={() => handleLevelSelect('level4', l4Key)}
                                                                                        depth={3}
                                                                                        count={counts[l4Key]}
                                                                                    />
                                                                                );
                                                                            })}
                                                                        </div>
                                                                    )}
                                                                </React.Fragment>
                                                            );
                                                        })}
                                                    </div>
                                                )}
                                            </React.Fragment>
                                        );
                                    })}
                                </div>
                            )}
                        </React.Fragment>
                    );
                })}
            </div>
        );
    };

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
                    </div>
                    <div className="flex items-center gap-2">
                        {activeCount > 0 && (
                            <button onClick={onReset} className="text-[11px] text-slate-400 hover:text-white font-semibold px-2 py-1.5 rounded-lg hover:bg-slate-800 transition-all">
                                Réinitialiser
                            </button>
                        )}
                        <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-all shadow-sm">
                            <X size={16} />
                        </button>
                    </div>
                </div>

                {/* Scrollable body */}
                <div className="flex-1 overflow-y-auto p-5 pb-20 space-y-6">

                    {/* ── Taxonomy Tree (Inline Accordion) ── */}
                    <FilterGroup label="Type d'instrument" defaultOpen={true}>
                        {renderTaxonomyTree()}
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

                </div>
            </aside>
        </>
    );
};

export default MockupFilterDrawer;
