import React, { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import CollapsibleSection from './CollapsibleSection';
import { AI_PROVIDERS, LEAF_SOURCES, configToForm, validateLeafForm } from '../utils/leaf';

// Réglages de recherche Leaf (enregistrés dans `users.config.leafConfig` par `PUT /leaf/config`, relus par le bot à chaque
// passage). Réutilise `CollapsibleSection` ; la liste de villes (catalogue partagé de Guitar Hunter) sert à choisir la ville de
// référence sans saisir de coordonnées. `api` et `cities` sont injectables.

const FIELD = 'w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-sm text-slate-200';
const LABEL = 'block text-[11px] font-bold text-slate-400 mb-1';

const Field = ({ label, children, hint }) => (
    <label className="block">
        <span className={LABEL}>{label}</span>
        {children}
        {hint && <span className="block text-[10px] text-slate-500 mt-0.5">{hint}</span>}
    </label>
);
const Check = ({ checked, onChange, children }) => (
    <label className="flex items-center gap-2 text-sm text-slate-300">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /> {children}
    </label>
);

const LeafSettings = ({ api, cities = [] }) => {
    const [form, setForm] = useState(null);
    const [state, setState] = useState({ loading: true, saving: false, errors: [], saved: false, loadError: null });
    const set = (patch) => { setForm((f) => ({ ...f, ...patch })); setState((s) => ({ ...s, saved: false })); };

    useEffect(() => {
        let cancelled = false;
        api.fetchLeafConfig()
            .then((cfg) => { if (!cancelled) { setForm(configToForm(cfg)); setState((s) => ({ ...s, loading: false })); } })
            .catch((e) => { if (!cancelled) setState((s) => ({ ...s, loading: false, loadError: e })); });
        return () => { cancelled = true; };
    }, [api]);

    const usableCities = (cities || []).filter((c) => Number.isFinite(c?.latitude) && Number.isFinite(c?.longitude));
    const pickCity = (id) => {
        const c = usableCities.find((x) => String(x.id) === id);
        if (c) set({ homeName: c.name, lat: String(c.latitude), lon: String(c.longitude) });
    };

    const save = async () => {
        const { errors, body } = validateLeafForm(form);
        if (errors.length) { setState((s) => ({ ...s, errors, saved: false })); return; }
        setState((s) => ({ ...s, saving: true, errors: [] }));
        try {
            setForm(configToForm(await api.saveLeafConfig(body)));
            setState((s) => ({ ...s, saving: false, saved: true }));
        } catch (e) {
            setState((s) => ({ ...s, saving: false, errors: [String(e.message || e)] }));
        }
    };

    return (
        <CollapsibleSection title="Réglages de recherche">
            {state.loading ? <p className="text-sm text-slate-400">Chargement…</p>
                : state.loadError ? <p className="text-sm text-rose-300">{String(state.loadError.message || state.loadError)}</p>
                    : (
                        <div className="space-y-4">
                            <Check checked={form.enabled} onChange={(v) => set({ enabled: v })}>Leaf Hunter actif pour mon compte (passages automatiques)</Check>
                            <div className="grid grid-cols-2 gap-3">
                                <Field label="Prix minimum ($)"><input className={FIELD} inputMode="numeric" value={form.minPrice} onChange={(e) => set({ minPrice: e.target.value })} /></Field>
                                <Field label="Prix maximum ($)"><input className={FIELD} inputMode="numeric" value={form.maxPrice} onChange={(e) => set({ maxPrice: e.target.value })} /></Field>
                                <Field label="Kilométrage maximum"><input className={FIELD} inputMode="numeric" value={form.maxKm} onChange={(e) => set({ maxKm: e.target.value })} /></Field>
                                <Field label="Années" hint="ex. 2016, 2017, 2018"><input className={FIELD} value={form.years} onChange={(e) => set({ years: e.target.value })} /></Field>
                                <Field label="Fréquence (minutes)" hint="60 à 1 440 ; s'applique au passage suivant"><input className={FIELD} inputMode="numeric" value={form.frequency} onChange={(e) => set({ frequency: e.target.value })} /></Field>
                                <Field label="Pages Kijiji" hint="1 à 3"><input className={FIELD} inputMode="numeric" value={form.pages} onChange={(e) => set({ pages: e.target.value })} /></Field>
                            </div>
                            <div className="space-y-1.5">
                                <span className={LABEL}>Sources</span>
                                {LEAF_SOURCES.map(([key, label]) => (
                                    <Check key={key} checked={!!form.sources[key]} onChange={(v) => set({ sources: { ...form.sources, [key]: v } })}>{label}</Check>
                                ))}
                                <Check checked={form.readDetails} onChange={(v) => set({ readDetails: v })}>Lire la fiche de chaque annonce (SOH, accidents, photos complètes)</Check>
                            </div>
                            <div className="space-y-2">
                                <span className={LABEL}>Ville de référence{form.homeName ? ` : ${form.homeName}` : ''}</span>
                                {usableCities.length > 0 && (
                                    <select className={FIELD} value="" onChange={(e) => pickCity(e.target.value)} aria-label="Choisir une ville connue">
                                        <option value="">Choisir parmi mes villes…</option>
                                        {usableCities.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
                                    </select>
                                )}
                                <div className="grid grid-cols-3 gap-3">
                                    <Field label="Latitude"><input className={FIELD} inputMode="decimal" value={form.lat} onChange={(e) => set({ lat: e.target.value, homeName: '' })} /></Field>
                                    <Field label="Longitude"><input className={FIELD} inputMode="decimal" value={form.lon} onChange={(e) => set({ lon: e.target.value, homeName: '' })} /></Field>
                                    <Field label="Rayon (km)"><input className={FIELD} inputMode="numeric" value={form.radius} onChange={(e) => set({ radius: e.target.value })} /></Field>
                                </div>
                            </div>
                            <div className="space-y-2">
                                <span className={LABEL}>Analyse IA des annonces (niveau 2)</span>
                                <Check checked={form.aiEnabled} onChange={(v) => set({ aiEnabled: v })}>Activer (résumé, faits prouvés par une citation, points d'attention)</Check>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-3">
                                        <Field label="Analyses par jour (plafond)" hint="1 à 500 ; une annonce n'est ré-analysée que si son texte ou son prix change">
                                            <input className={FIELD} inputMode="numeric" value={form.aiMax} onChange={(e) => set({ aiMax: e.target.value })} />
                                        </Field>
                                        <Field label="Analyses approfondies par jour (Sonnet 5.5)" hint="1 à 50 ; seulement à la demande, bouton « Analyse approfondie »">
                                            <input className={FIELD} inputMode="numeric" value={form.aiExpertMax} onChange={(e) => set({ aiExpertMax: e.target.value })} />
                                        </Field>
                                    </div>
                                    <div className="space-y-1.5">
                                        <span className={LABEL}>Modèles, dans l'ordre d'essai</span>
                                        {AI_PROVIDERS.map(([key, label]) => (
                                            <Check key={key} checked={!!form.aiProviders[key]} onChange={(v) => set({ aiProviders: { ...form.aiProviders, [key]: v } })}>{label}</Check>
                                        ))}
                                    </div>
                                </div>
                                <p className="text-[10px] text-slate-500">Éteinte par défaut. Un fait sans citation retrouvée mot pour mot dans l'annonce est écarté ; en cas de contradiction, les règles l'emportent.</p>
                            </div>
                            <div className="space-y-1.5">
                                <span className={LABEL}>Notifications (ntfy)</span>
                                <Check checked={form.notifyEnabled} onChange={(v) => set({ notifyEnabled: v })}>Activées</Check>
                                <Check checked={form.notifyNew} onChange={(v) => set({ notifyNew: v })}>Nouvelle annonce</Check>
                                <Check checked={form.notifyDrop} onChange={(v) => set({ notifyDrop: v })}>Baisse de prix</Check>
                            </div>
                            {state.errors.length > 0 && (
                                <ul className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300 list-disc list-inside">
                                    {state.errors.map((m) => <li key={m}>{m}</li>)}
                                </ul>
                            )}
                            <button onClick={save} disabled={state.saving}
                                className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800 text-slate-200 text-sm font-bold disabled:opacity-50">
                                <Save size={14} className="inline -mt-0.5" /> {state.saving ? 'Enregistrement…' : 'Enregistrer'}
                            </button>
                            {state.saved && <span className="ml-3 text-sm text-emerald-300">Enregistré — pris en compte au prochain passage.</span>}
                        </div>
                    )}
        </CollapsibleSection>
    );
};

export default LeafSettings;
