import React from 'react';
import { ChevronRight, Check } from 'lucide-react';

import promptsData from '../../prompts.json';
// Libellé partagé avec l'autocomplétion de la barre de recherche (useDealsManager::taxonomyNodes)
// et le tiroir de filtres (FilterDrawer.jsx), pour qu'une même catégorie s'affiche identiquement
// partout dans l'app.
import { formatTaxonomyLabel as formatLabel } from '../constants';

// ============================================================
// ARBRE DE TAXONOMIE DEPUIS prompts.json — généré dynamiquement, jamais codé en dur : toute
// nouvelle branche ajoutée à `taxonomy_master` apparaît automatiquement ici (et dans FilterDrawer,
// qui partage ce même composant) sans changement de code.
// IMPORTANT : les clés doivent correspondre EXACTEMENT aux valeurs de prompts.json pour que le
// filtrage/routage (Chantier G) fonctionne.
// ============================================================
const buildTaxonomyTree = (node) => {
    if (Array.isArray(node)) {
        const res = {};
        node.forEach(item => {
            res[item] = { label: item, children: null };
        });
        return res;
    }
    if (typeof node === 'object' && node !== null) {
        const res = {};
        for (const [key, value] of Object.entries(node)) {
            res[key] = {
                label: formatLabel(key),
                children: buildTaxonomyTree(value)
            };
        }
        return res;
    }
    return node;
};

export const TAXONOMY_TREE = buildTaxonomyTree(promptsData.taxonomy_master);

// ============================================================
// Option d'arbre — case à cocher multi-sélection, expand/collapse indépendant de la sélection
// (plusieurs catégories peuvent être cochées à la fois, même dans des branches différentes).
// ============================================================
const TaxonomyOption = ({ label, checked, onToggleCheck, hasChildren, expanded, onToggleExpand, depth = 0, count }) => {
    const paddingLeft = depth === 0 ? 'px-2' : depth === 1 ? 'pl-6 pr-2' : depth === 2 ? 'pl-10 pr-2' : 'pl-14 pr-2';
    const textSize = depth === 0 ? 'text-sm' : depth === 1 ? 'text-[13px]' : depth === 2 ? 'text-xs' : 'text-[11px]';

    return (
        <div className={`flex items-center gap-2.5 rounded-lg transition-all w-full ${paddingLeft} ${checked ? 'bg-blue-600/10 border border-blue-500/20' : 'hover:bg-slate-800 border border-transparent'
            }`}>
            <button
                onClick={onToggleCheck}
                aria-pressed={checked}
                className={`shrink-0 w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${checked ? 'border-blue-500 bg-blue-500' : 'border-slate-600'
                    }`}
            >
                {checked && <Check size={11} strokeWidth={3} className="text-white" />}
            </button>

            <button
                onClick={onToggleExpand || onToggleCheck}
                className="flex-1 flex items-center gap-2 min-w-0 text-left py-2.5 sm:py-2"
            >
                <span className={`flex-1 leading-tight truncate ${textSize} ${checked ? 'text-white font-semibold' : depth === 0 ? 'text-slate-300' : 'text-slate-400'
                    }`}>
                    {label}
                </span>

                {count > 0 && (
                    <span className={`shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded-md ${checked ? 'bg-blue-500/20 text-blue-200' : 'bg-slate-800 text-slate-500'}`}>
                        {count}
                    </span>
                )}

                {hasChildren && (
                    <ChevronRight size={14} className={`shrink-0 transition-transform ${expanded ? 'rotate-90' : ''} ${checked ? 'text-blue-400' : 'text-slate-600'}`} />
                )}
            </button>
        </div>
    );
};

/**
 * Sélecteur d'arbre de taxonomie réutilisable — même composant que celui utilisé par
 * `FilterDrawer.jsx` (tiroir de filtres de la liste d'annonces), pour que toute évolution de
 * `taxonomy_master` (prompts.json) se reflète automatiquement partout, sans logique dupliquée
 * qui pourrait diverger silencieusement (piège déjà rencontré sur ce projet, voir
 * `utils/taxonomy.js` et `ARCHITECTURE.md`).
 *
 * Props :
 * - selectedPaths : tableau de chemins cochés (dot-notation, ex: "guitare.acoustique_acier...")
 * - onTogglePath(path) : coche/décoche un chemin
 * - showClearAllOption : si true, affiche une option "Tous les types" en tête, cochée quand
 *   `selectedPaths` est vide, qui appelle `onClearPaths` au clic (utilisé par FilterDrawer où le
 *   vide a un sens de filtre actif à réinitialiser explicitement).
 * - onClearPaths : callback pour l'option ci-dessus.
 * - counts : { [path]: nombre } optionnel, affiché à droite de chaque libellé (ex: compteur de
 *   résultats dans FilterDrawer) — omis si non fourni.
 */
const TaxonomyTreePicker = ({
    selectedPaths = [],
    onTogglePath,
    showClearAllOption = false,
    onClearPaths,
    clearAllLabel = 'Tous les types',
    counts = {},
}) => {
    // Overrides explicites (clic sur le chevron) — priment sur la règle auto (coché/descendant
    // coché) tant qu'ils existent, dans les deux sens. Sans ça, un Set "déjà déplié" ne peut
    // qu'ajouter : tant qu'un descendant reste coché, `expanded = auto || dansLeSet` reste vrai
    // quoi qu'on fasse, et cliquer le chevron pour replier n'a aucun effet ; une fois le
    // descendant décoché, l'entrée oubliée dans le Set garde la branche ouverte indéfiniment.
    const [expandOverrides, setExpandOverrides] = React.useState(() => new Map());
    const toggleExpand = (path, currentlyExpanded) => setExpandOverrides(prev => {
        const next = new Map(prev);
        next.set(path, !currentlyExpanded);
        return next;
    });

    const renderTaxonomyTree = (node = TAXONOMY_TREE, parentPath = "") => {
        return (
            <div className="flex flex-col gap-0.5">
                {parentPath === "" && showClearAllOption && (
                    <TaxonomyOption
                        label={clearAllLabel}
                        checked={selectedPaths.length === 0}
                        onToggleCheck={() => onClearPaths?.()}
                        depth={0}
                        count={counts.all}
                    />
                )}

                {Object.entries(node).map(([key, cfg]) => {
                    const currentPath = parentPath ? `${parentPath}.${key}` : key;
                    const depth = parentPath.split('.').filter(Boolean).length;

                    const isChecked = selectedPaths.includes(currentPath);
                    const hasChildren = cfg.children && Object.keys(cfg.children).length > 0;
                    // Une catégorie se déplie automatiquement si elle est cochée, OU si un de ses
                    // descendants l'est (sélection en anti-chaîne : cocher "Parlor" ne coche plus
                    // ses parents, donc c'est la présence d'un descendant coché qui doit ouvrir la
                    // branche pour qu'il reste visible) — sauf override explicite (clic manuel sur
                    // le chevron), qui l'emporte tant qu'il n'a pas été re-cliqué.
                    const autoExpanded = isChecked || selectedPaths.some(p => p.startsWith(`${currentPath}.`));
                    const isExpanded = expandOverrides.has(currentPath) ? expandOverrides.get(currentPath) : autoExpanded;
                    const showChildren = isExpanded && hasChildren;

                    return (
                        <React.Fragment key={key}>
                            <TaxonomyOption
                                label={cfg.label}
                                checked={isChecked}
                                onToggleCheck={() => onTogglePath?.(currentPath)}
                                hasChildren={hasChildren}
                                expanded={isExpanded}
                                onToggleExpand={hasChildren ? () => toggleExpand(currentPath, isExpanded) : undefined}
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

    return renderTaxonomyTree();
};

export default TaxonomyTreePicker;
