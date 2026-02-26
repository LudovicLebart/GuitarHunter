import React from 'react';
import { X, ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';

import promptsData from '../../prompts.json';

// ============================================================
// TAXONOMY TREE FROM PROMPTS.JSON
// dynamically format to: { key: { label: '...', children: {...} } }
// IMPORTANT: keys must EXACTLY match the values in prompt.json arrays for filtering to work
// ============================================================
const formatLabel = (str) => {
    return str.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

const buildTaxonomyTree = (node) => {
    if (Array.isArray(node)) {
        const res = {};
        node.forEach(item => {
            // Leaf node: key is the exact item string, no children
            res[item] = { label: item, children: null };
        });
        return res;
    }
    if (typeof node === 'object' && node !== null) {
        const res = {};
        for (const [key, value] of Object.entries(node)) {
            // Intermediate node: key is the exact string block
            res[key] = {
                label: formatLabel(key),
                children: buildTaxonomyTree(value)
            };
        }
        return res;
    }
    return node;
};

const TAXONOMY_TREE = buildTaxonomyTree(promptsData.taxonomy_master);


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
            className={`flex items-center gap-3 text-left py-2.5 sm:py-2 rounded-lg transition-all w-full ${paddingLeft} ${active ? 'bg-blue-600/10 border border-blue-500/20' : 'hover:bg-slate-800 border border-transparent'
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
const FilterDrawer = ({ open, onClose, filters, onFilterChange, onReset, counts = {} }) => {
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
    const renderTaxonomyTree = (node = TAXONOMY_TREE, parentPath = "") => {
        return (
            <div className="flex flex-col gap-0.5">
                {parentPath === "" && (
                    <InlineOption
                        label="Tous les types"
                        active={level1 === 'all'}
                        onClick={() => handleLevelSelect('level1', 'all')}
                        depth={0}
                        count={counts.all}
                    />
                )}

                {Object.entries(node).map(([key, cfg]) => {
                    const currentPath = parentPath ? `${parentPath}.${key}` : key;
                    const depth = parentPath.split('.').filter(Boolean).length;
                    
                    // Logic to determine if this specific node is "active" based on levels
                    const isActive = (depth === 0 && level1 === key) ||
                                   (depth === 1 && level2 === key && level1 === parentPath) ||
                                   (depth === 2 && level3 === key && level2 === parentPath.split('.')[1]) ||
                                   (depth === 3 && level4 === key);

                    const hasChildren = cfg.children && Object.keys(cfg.children).length > 0;
                    const showChildren = isActive && hasChildren;

                    return (
                        <React.Fragment key={key}>
                            <InlineOption
                                label={cfg.label}
                                active={isActive}
                                onClick={() => handleLevelSelect(`level${depth + 1}`, key)}
                                hasChildren={hasChildren && !isActive}
                                depth={depth}
                                count={counts[currentPath] || 0}
                            />

                            {showChildren && (
                                <div className={`mt-1 flex flex-col gap-0.5 mb-2 relative border-l-2 border-slate-700/50 ${
                                    depth === 0 ? 'ml-[11px]' : depth === 1 ? 'ml-7' : 'ml-10'
                                }`}>
                                    {renderTaxonomyTree(cfg.children, currentPath)}
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

export default FilterDrawer;
