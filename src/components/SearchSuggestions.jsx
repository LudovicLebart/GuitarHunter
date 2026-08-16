import React from 'react';
import { CornerDownLeft, Tag } from 'lucide-react';

/**
 * Liste déroulante de suggestions de CATÉGORIES sous la barre de recherche.
 *
 * Sélectionner une suggestion ne remplit pas le champ de recherche : elle coche la catégorie
 * correspondante dans `selectedTypePaths` (même mécanisme que les cases du FilterDrawer). C'est
 * donc un vrai filtre de taxonomie — persisté dans `uiFilters`, compté dans le badge de filtres
 * actifs, et soumis à la logique anti-chaîne qui retire les ancêtres/descendants déjà cochés.
 *
 * `activeIndex` est piloté par le parent (navigation clavier) : -1 = aucune ligne survolée.
 */
/**
 * Navigation clavier de la liste (↓ ↑ Entrée Échap), fournie ici plutôt que dans le parent pour
 * que le composant et son comportement clavier restent une seule et même unité testable.
 * Entrée ne fait rien tant qu'aucune ligne n'est active (`activeIndex < 0`) : la touche garde son
 * sens habituel de "je valide ma recherche texte", elle ne coche une catégorie que si l'utilisateur
 * est explicitement descendu dans la liste.
 */
export const createSuggestionKeyHandler = ({ suggestions, activeIndex, setActiveIndex, onSelect, onClose }) => (e) => {
    if (e.key === 'Escape') {
        onClose();
        return;
    }
    if (!suggestions || suggestions.length === 0) return;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex(i => (i + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex(i => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === 'Enter' && activeIndex >= 0) {
        e.preventDefault();
        onSelect(suggestions[activeIndex]);
    }
};

const SearchSuggestions = ({ suggestions, activeIndex, onSelect, onHoverIndex }) => {
    if (!suggestions || suggestions.length === 0) return null;

    return (
        <div
            role="listbox"
            aria-label="Catégories suggérées"
            className="absolute z-30 left-0 right-0 top-full mt-2 bg-slate-900 border border-slate-700 rounded-xl shadow-xl shadow-black/40 overflow-hidden animate-in fade-in slide-in-from-top-1 duration-150"
        >
            <div className="px-3 py-2 text-[10px] font-black uppercase tracking-widest text-slate-500 border-b border-slate-800">
                Filtrer par catégorie
            </div>

            {suggestions.map((suggestion, index) => (
                <button
                    key={suggestion.path}
                    type="button"
                    role="option"
                    aria-selected={index === activeIndex}
                    // onMouseDown plutôt que onClick : le blur de l'input (qui referme la liste)
                    // se déclenche avant le click et emporterait la sélection avec lui.
                    onMouseDown={(e) => { e.preventDefault(); onSelect(suggestion); }}
                    onMouseEnter={() => onHoverIndex?.(index)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors border-b border-slate-800/50 last:border-0 ${index === activeIndex ? 'bg-slate-800' : 'hover:bg-slate-800/60'
                        }`}
                >
                    <Tag size={14} className="shrink-0 text-blue-400/70" />

                    <span className="min-w-0 flex-1">
                        <span className="block text-sm text-slate-200 truncate">{suggestion.label}</span>
                        {suggestion.breadcrumb && (
                            <span className="block text-[11px] text-slate-500 truncate">{suggestion.breadcrumb}</span>
                        )}
                    </span>

                    <span className="shrink-0 text-[11px] font-bold text-slate-400 bg-slate-800 border border-slate-700 rounded-lg px-2 py-0.5">
                        {suggestion.count}
                    </span>

                    {index === activeIndex && (
                        <CornerDownLeft size={12} className="shrink-0 text-slate-500" />
                    )}
                </button>
            ))}
        </div>
    );
};

export default SearchSuggestions;
