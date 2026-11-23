import React, { useEffect, useState } from 'react';
import { RotateCcw, Save } from 'lucide-react';
import CollapsibleSection from './CollapsibleSection';
import { MAX_PROMPT_CHARS, PROMPT_LABELS, promptToValue, validatePrompts } from '../utils/leaf';

// Éditeur « avancé » des prompts de l'IA de Leaf (même idée que l'éditeur des prompts des guitares dans le ConfigPanel). Seules les INSTRUCTIONS
// sont modifiables : le bot ajoute toujours le format JSON et applique le garde-fou des preuves. Un texte identique au défaut est enregistré
// comme « défaut » (il suit alors les mises à jour du bot). `api` est injectable.

const AREA = 'w-full bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-slate-200 font-mono';

const LeafPrompts = ({ api }) => {
    const [state, setState] = useState({ loading: true, loadError: null, saving: false, saved: false, errors: [] });
    const [texts, setTexts] = useState({});
    const [defaults, setDefaults] = useState({});

    useEffect(() => {
        let cancelled = false;
        api.fetchLeafPrompts()
            .then((r) => { if (!cancelled) { setDefaults(r.defaults); setTexts(Object.fromEntries(Object.keys(r.defaults).map((k) => [k, r.prompts[k] ?? r.defaults[k]]))); setState((s) => ({ ...s, loading: false })); } })
            .catch((e) => { if (!cancelled) setState((s) => ({ ...s, loading: false, loadError: e })); });
        return () => { cancelled = true; };
    }, [api]);

    const edit = (key, value) => { setTexts((t) => ({ ...t, [key]: value })); setState((s) => ({ ...s, saved: false })); };
    const save = async () => {
        const errors = validatePrompts(texts);
        if (errors.length) { setState((s) => ({ ...s, errors, saved: false })); return; }
        setState((s) => ({ ...s, saving: true, errors: [] }));
        try {
            const r = await api.saveLeafPrompts(Object.fromEntries(Object.keys(defaults).map((k) => [k, promptToValue(texts[k], defaults[k])])));
            setTexts(Object.fromEntries(Object.keys(defaults).map((k) => [k, r.prompts[k] ?? defaults[k]])));
            setState((s) => ({ ...s, saving: false, saved: true }));
        } catch (e) { setState((s) => ({ ...s, saving: false, errors: [String(e.message || e)] })); }
    };

    return (
        <CollapsibleSection title="Prompts de l'IA (avancé)">
            {state.loading ? <p className="text-sm text-slate-400">Chargement…</p>
                : state.loadError ? <p className="text-sm text-rose-300">{String(state.loadError.message || state.loadError)}</p>
                    : (
                        <div className="space-y-4">
                            <p className="text-[11px] text-slate-500">Une modification relance l'analyse des annonces au prochain passage (dans le plafond quotidien). Les consignes sont celles du bot par défaut ; « Rétablir » y revient.</p>
                            {Object.entries(PROMPT_LABELS).map(([key, [label, hint]]) => (
                                <div key={key} className="space-y-1">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[11px] font-bold text-slate-400">{label}</span>
                                        <button onClick={() => edit(key, defaults[key])} className="text-[11px] font-bold text-blue-400 hover:text-blue-300" title="Revenir au prompt par défaut">
                                            <RotateCcw size={11} className="inline -mt-0.5" /> Rétablir le défaut
                                        </button>
                                    </div>
                                    <textarea className={AREA} rows={8} maxLength={MAX_PROMPT_CHARS + 500} value={texts[key] ?? ''} onChange={(e) => edit(key, e.target.value)} aria-label={label} />
                                    <p className="text-[10px] text-slate-500">{hint} ({(texts[key] ?? '').length}/{MAX_PROMPT_CHARS})</p>
                                </div>
                            ))}
                            {state.errors.length > 0 && (
                                <ul className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300 list-disc list-inside">{state.errors.map((m) => <li key={m}>{m}</li>)}</ul>
                            )}
                            <button onClick={save} disabled={state.saving} className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800 text-slate-200 text-sm font-bold disabled:opacity-50">
                                <Save size={14} className="inline -mt-0.5" /> {state.saving ? 'Enregistrement…' : 'Enregistrer les prompts'}
                            </button>
                            {state.saved && <span className="ml-3 text-sm text-emerald-300">Enregistré.</span>}
                        </div>
                    )}
        </CollapsibleSection>
    );
};

export default LeafPrompts;
