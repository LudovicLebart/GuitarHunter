import React, { useMemo, useState } from 'react';
import { Pencil, Check, X, RotateCcw, Search } from 'lucide-react';
import { TAXONOMY_NODES, formatClassificationLabel, resolveClassification, normalizeSegment } from '../../utils/taxonomy';

/**
 * Correction manuelle de la catégorie d'une annonce (2026-08-16).
 *
 * L'IA se trompe (ou reste ambiguë) sur la classification — typiquement un étui renvoyé sous le nom
 * de feuille "Guitare Electrique", que rien ne distingue de l'instrument sans son chemin complet.
 * Ce sélecteur laisse l'utilisateur trancher lui-même.
 *
 * La valeur choisie est TOUJOURS un chemin complet en dot-notation, donc jamais ambiguë — c'est
 * précisément ce qui manque aux valeurs historiques produites par l'IA.
 */
const ClassificationEditor = ({ deal, onSetClassification }) => {
    const [editing, setEditing] = useState(false);
    const [query, setQuery] = useState('');
    const [saving, setSaving] = useState(false);

    const aiValue = deal.aiAnalysis?.classification || null;
    const manualValue = deal.manualClassification || null;
    const currentLabel = formatClassificationLabel(manualValue || aiValue);
    // Une valeur ambiguë n'est rattachée à aucune branche : le filtrage la range dans "Autres",
    // c'est exactement le cas où une correction manuelle est utile — on le signale.
    const isAmbiguous = !manualValue && resolveClassification(aiValue).ambiguous;

    const matches = useMemo(() => {
        // Comparaison sur chaînes normalisées (sans accents) : les libellés de la taxonomie n'en
        // portent pas ("Etui Housse"), donc une recherche brute rendait muet l'exemple donné par
        // le placeholder lui-même — taper "étui" ne renvoyait rien.
        const needle = normalizeSegment(query.trim());
        if (needle.length < 2) return [];
        return TAXONOMY_NODES
            .filter(node => normalizeSegment(`${node.breadcrumb} ${node.label}`).includes(needle))
            .slice(0, 20);
    }, [query]);

    const apply = async (path) => {
        setSaving(true);
        try {
            await onSetClassification(deal.id, path);
            setEditing(false);
            setQuery('');
        } finally {
            setSaving(false);
        }
    };

    if (!editing) {
        return (
            <div className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 flex items-center gap-2">
                <span className="text-[10px] text-slate-500 font-bold uppercase">Catégorie :</span>
                <span className="text-xs text-slate-200 font-semibold">
                    {currentLabel || <span className="text-slate-500 italic">non classée</span>}
                </span>
                {manualValue && (
                    <span className="text-[9px] text-emerald-400 font-bold uppercase" title="Corrigée manuellement">corrigée</span>
                )}
                {isAmbiguous && (
                    <span className="text-[9px] text-amber-400 font-bold uppercase" title="Ce nom existe dans plusieurs branches de la taxonomie : l'annonce est classée dans « Autres » tant qu'elle n'est pas précisée.">
                        ambiguë
                    </span>
                )}
                <button
                    onClick={() => setEditing(true)}
                    className="text-slate-500 hover:text-blue-400 transition-colors"
                    title="Corriger la catégorie"
                >
                    <Pencil size={12} />
                </button>
            </div>
        );
    }

    return (
        <div className="w-full bg-slate-950 border border-blue-500/40 rounded-xl p-3">
            <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">Corriger la catégorie</span>
                <button onClick={() => { setEditing(false); setQuery(''); }} className="text-slate-500 hover:text-slate-300">
                    <X size={14} />
                </button>
            </div>

            <div className="relative mb-2">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                    autoFocus
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    placeholder="Chercher une catégorie (ex: étui, parlor, combo)…"
                    className="w-full h-9 bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
            </div>

            <div className="max-h-52 overflow-y-auto rounded-lg border border-slate-800 divide-y divide-slate-800/60">
                {matches.length === 0 && (
                    <div className="px-3 py-2 text-[11px] text-slate-500">
                        {query.trim().length < 2 ? 'Tape au moins 2 caractères.' : 'Aucune catégorie ne correspond.'}
                    </div>
                )}
                {matches.map(node => (
                    <button
                        key={node.path}
                        disabled={saving}
                        onClick={() => apply(node.path)}
                        className="w-full text-left px-3 py-2 hover:bg-slate-800/70 transition-colors disabled:opacity-50"
                    >
                        <span className="block text-xs text-slate-200">{node.label}</span>
                        {node.breadcrumb && <span className="block text-[10px] text-slate-500">{node.breadcrumb}</span>}
                    </button>
                ))}
            </div>

            {manualValue && (
                <button
                    disabled={saving}
                    onClick={() => apply(null)}
                    className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-amber-400 transition-colors disabled:opacity-50"
                    title="Supprimer la correction et revenir à la catégorie déterminée par l'IA"
                >
                    <RotateCcw size={11} /> Revenir à la catégorie de l'IA
                    {aiValue && <span className="text-slate-600">({formatClassificationLabel(aiValue)})</span>}
                </button>
            )}

            {saving && (
                <div className="mt-2 flex items-center gap-1.5 text-[11px] text-blue-400">
                    <Check size={11} /> Enregistrement…
                </div>
            )}
        </div>
    );
};

export default ClassificationEditor;
