import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowLeft, Car, ExternalLink, RefreshCw, Snowflake, Star, ThumbsDown } from 'lucide-react';
import { fetchLeafDeal, fetchLeafDeals, fetchLeafRuns, setLeafState, triggerLeafRefresh } from '../services/apiService';
import {
    CHECKLIST_ITEMS, SORTS, WINTER_LABELS, checklistProgress, filterAndSortDeals, flagLabel, formatKm, formatPrice, leafDealHref,
    priceTrend, winterRange, winterVerdict,
} from '../utils/leaf';

// Page Leaf Hunter (`#leaf`, `#leaf/<id>`, voir hooks/useLeafRoute.js) : liste triable des Leaf d'occasion retenues par le bot,
// et fiche d'une annonce (drapeaux, historique de prix, notes, checklist d'inspection). `api` est injectable (affichage sans serveur).

const DEFAULT_API = { fetchLeafDeals, fetchLeafDeal, setLeafState, fetchLeafRuns, triggerLeafRefresh };
const WINTER_STYLES = {
    ok: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    juste: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    insuffisant: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
    inconnu: 'bg-slate-700/50 text-slate-300 border-slate-600',
};
const BADGE = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-bold';

const Message = ({ children, tone = 'muted' }) => (
    <div className={`rounded-2xl border px-4 py-6 text-sm text-center ${tone === 'error' ? 'border-rose-500/30 bg-rose-500/10 text-rose-300' : 'border-slate-800 bg-slate-900/60 text-slate-400'}`}>{children}</div>
);

const WinterBadge = ({ analysis }) => {
    const verdict = winterVerdict(analysis);
    const range = winterRange(analysis);
    return (
        <span className={`${BADGE} ${WINTER_STYLES[verdict] || WINTER_STYLES.inconnu}`} title="Autonomie hivernale estimée (SOH annoncé ou supposé, -15 à -25 °C)">
            <Snowflake size={12} /> {range || WINTER_LABELS[verdict]}
        </span>
    );
};

const Flags = ({ flags }) => (flags?.length ? (
    <div className="flex flex-wrap gap-1.5">
        {flags.map((f) => <span key={f} className={`${BADGE} bg-slate-800 border-slate-700 text-slate-300`}>{flagLabel(f)}</span>)}
    </div>
) : null);

const DealRow = ({ deal, onToggle }) => (
    <li className="rounded-2xl border border-slate-800 bg-slate-900/60 p-3 flex gap-3">
        <a href={leafDealHref(deal.id)} className="shrink-0 w-24 h-20 rounded-xl overflow-hidden bg-slate-800 flex items-center justify-center">
            {deal.image_urls?.[0] ? <img src={deal.image_urls[0]} alt="" loading="lazy" className="w-full h-full object-cover" /> : <Car size={28} className="text-slate-600" />}
        </a>
        <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-start justify-between gap-2">
                <a href={leafDealHref(deal.id)} className="font-bold text-slate-100 text-sm leading-tight hover:underline">
                    {deal.year || '?'} Leaf {deal.trim || ''}
                </a>
                <span className="text-emerald-300 font-black text-sm whitespace-nowrap">{formatPrice(deal.price)}</span>
            </div>
            <div className="text-xs text-slate-400">
                {formatKm(deal.km)} · {deal.location || 'lieu ?'}
                {deal.soh_announced != null ? ` · SOH ${Math.round(deal.soh_announced)} %` : ''}
                {deal.price_drop_amount > 0 ? <span className="text-amber-300"> · baisse de {formatPrice(deal.price_drop_amount)}</span> : null}
                {deal.duplicate_of ? ' · doublon probable' : ''}
            </div>
            <WinterBadge analysis={deal.analysis} />
            <Flags flags={deal.flags} />
        </div>
        <div className="flex flex-col gap-1.5">
            <button onClick={() => onToggle(deal, { isFavorite: !deal.is_favorite })} title="Favori" aria-pressed={deal.is_favorite}
                className={`p-1.5 rounded-lg border ${deal.is_favorite ? 'bg-amber-500/20 border-amber-500/40 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'}`}><Star size={14} /></button>
            <button onClick={() => onToggle(deal, { isRejected: true })} title="Pas intéressé (masque l'annonce)"
                className="p-1.5 rounded-lg border bg-slate-800 border-slate-700 text-slate-400 hover:text-rose-300"><ThumbsDown size={14} /></button>
        </div>
    </li>
);

const LeafList = ({ api }) => {
    const [state, setState] = useState({ loading: true, error: null, deals: [], runs: [] });
    const [sort, setSort] = useState('price');
    const [query, setQuery] = useState('');
    const [favoritesOnly, setFavoritesOnly] = useState(false);
    const [refreshing, setRefreshing] = useState(false);

    const load = useCallback(async () => {
        try {
            const [deals, runs] = await Promise.all([api.fetchLeafDeals(), api.fetchLeafRuns(6)]);
            setState({ loading: false, error: null, deals, runs });
        } catch (error) { setState((s) => ({ ...s, loading: false, error })); }
    }, [api]);
    useEffect(() => { load(); }, [load]);

    const onToggle = async (deal, patch) => {
        try { await api.setLeafState(deal.id, patch); await load(); } catch (error) { setState((s) => ({ ...s, error })); }
    };
    const onRefresh = async () => {
        setRefreshing(true);
        try { await api.triggerLeafRefresh(); } catch (error) { setState((s) => ({ ...s, error })); }
        setTimeout(() => { setRefreshing(false); load(); }, 15000);      // le passage dure quelques dizaines de secondes
    };

    const shown = useMemo(() => filterAndSortDeals(state.deals, { favoritesOnly, query, sort }), [state.deals, favoritesOnly, query, sort]);
    const lastRun = state.runs[0];

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Rechercher (ville, version…)"
                    className="flex-1 min-w-[10rem] bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-sm text-slate-200" />
                <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Tri"
                    className="bg-slate-900 border border-slate-700 rounded-xl px-2 py-1.5 text-sm text-slate-200">
                    {Object.entries(SORTS).map(([key, s]) => <option key={key} value={key}>{s.label}</option>)}
                </select>
                <button onClick={() => setFavoritesOnly((v) => !v)} aria-pressed={favoritesOnly}
                    className={`px-3 py-1.5 rounded-xl border text-sm font-bold ${favoritesOnly ? 'bg-amber-500/20 border-amber-500/40 text-amber-300' : 'bg-slate-900 border-slate-700 text-slate-300'}`}>
                    <Star size={14} className="inline -mt-0.5" /> Favoris
                </button>
                <button onClick={onRefresh} disabled={refreshing} title="Lancer un passage maintenant"
                    className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-900 text-slate-300 text-sm font-bold disabled:opacity-50">
                    <RefreshCw size={14} className={`inline -mt-0.5 ${refreshing ? 'animate-spin' : ''}`} /> Actualiser
                </button>
            </div>
            {lastRun && <p className="text-[11px] text-slate-500">Dernier passage ({lastRun.source.replace('leaf_', '')}) : {lastRun.outcome}{lastRun.cards_seen != null ? `, ${lastRun.cards_seen} annonces lues` : ''}.</p>}
            {state.error && <Message tone="error">{String(state.error.message || state.error)}</Message>}
            {state.loading ? <Message>Chargement…</Message>
                : shown.length === 0 ? <Message>{state.deals.length ? 'Aucune annonce ne correspond.' : 'Aucune annonce pour le moment : le prochain passage du bot les ajoutera.'}</Message>
                    : <ul className="space-y-3">{shown.map((d) => <DealRow key={d.id} deal={d} onToggle={onToggle} />)}</ul>}
        </div>
    );
};

const LeafDetail = ({ id, api }) => {
    const [state, setState] = useState({ loading: true, error: null, deal: null });
    const [notes, setNotes] = useState('');
    const [saved, setSaved] = useState(true);

    useEffect(() => {
        let cancelled = false;
        setState({ loading: true, error: null, deal: null });
        api.fetchLeafDeal(id).then((deal) => { if (!cancelled) { setState({ loading: false, error: null, deal }); setNotes(deal.notes || ''); setSaved(true); } })
            .catch((error) => { if (!cancelled) setState({ loading: false, error, deal: null }); });
        return () => { cancelled = true; };
    }, [id, api]);

    const patch = async (fields) => {
        try { const next = await api.setLeafState(id, fields); setState((s) => ({ ...s, deal: { ...s.deal, ...next } })); return true; }
        catch (error) { setState((s) => ({ ...s, error })); return false; }
    };

    if (state.loading) return <Message>Chargement…</Message>;
    if (state.error && !state.deal) return <Message tone="error">{String(state.error.message || state.error)}</Message>;
    const d = state.deal;
    const trend = priceTrend(d.priceHistory);
    const progress = checklistProgress(d.checklist);
    const equipment = d.analysis?.equipment;
    return (
        <div className="space-y-4">
            {state.error && <Message tone="error">{String(state.error.message || state.error)}</Message>}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                    <h2 className="text-lg font-black text-slate-100">{d.year || '?'} Nissan Leaf {d.trim || ''}</h2>
                    <span className="text-emerald-300 font-black text-lg">{formatPrice(d.price)}</span>
                </div>
                <p className="text-sm text-slate-300">{formatKm(d.km)} · {d.location || 'lieu ?'}{d.seller_type ? ` · vendeur : ${d.seller_type === 'delr' ? 'commerçant' : d.seller_type === 'ownr' ? 'particulier' : d.seller_type}` : ''}</p>
                <WinterBadge analysis={d.analysis} />
                <div className="text-xs text-slate-400 space-y-0.5">
                    <p>Batterie : {d.battery_kwh_low ? (d.battery_kwh_low === d.battery_kwh_high ? `${d.battery_kwh_low} kWh` : `${d.battery_kwh_low} ou ${d.battery_kwh_high} kWh`) : 'inconnue'}
                        {d.battery_source === 'inferred' ? ' (déduite de l\'année)' : ''}</p>
                    <p>SOH annoncé : {d.soh_announced != null ? `${Math.round(d.soh_announced)} %${d.soh_evidence ? ` — « ${d.soh_evidence} »` : ''}` : 'non annoncé'}</p>
                    {equipment && <p>Équipement d'hiver : {equipment.score}/10{equipment.heat_pump_inferred ? ' (pompe à chaleur déduite de la version, à confirmer)' : ''}</p>}
                    {trend && <p>Prix : {formatPrice(trend.first)} → {formatPrice(trend.last)} ({trend.delta < 0 ? '' : '+'}{formatPrice(trend.delta)})</p>}
                </div>
                <Flags flags={d.flags} />
                {d.link && <a href={d.link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm font-bold text-blue-400 hover:text-blue-300"><ExternalLink size={14} /> Voir l'annonce</a>}
                <div className="flex gap-2">
                    <button onClick={() => patch({ isFavorite: !d.is_favorite })} aria-pressed={d.is_favorite}
                        className={`px-3 py-1.5 rounded-xl border text-sm font-bold ${d.is_favorite ? 'bg-amber-500/20 border-amber-500/40 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-300'}`}><Star size={14} className="inline -mt-0.5" /> Favori</button>
                    <button onClick={() => patch({ isRejected: !d.is_rejected })} aria-pressed={d.is_rejected}
                        className={`px-3 py-1.5 rounded-xl border text-sm font-bold ${d.is_rejected ? 'bg-rose-500/20 border-rose-500/40 text-rose-300' : 'bg-slate-800 border-slate-700 text-slate-300'}`}><ThumbsDown size={14} className="inline -mt-0.5" /> {d.is_rejected ? 'Rejetée' : 'Pas intéressé'}</button>
                </div>
            </div>

            {d.image_urls?.length > 0 && (
                <div className="flex gap-2 overflow-x-auto pb-1">
                    {d.image_urls.slice(0, 12).map((u) => <img key={u} src={u} alt="" loading="lazy" className="h-32 rounded-xl border border-slate-800 object-cover" />)}
                </div>
            )}

            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-2">
                <h3 className="text-sm font-black text-slate-200">Checklist d'inspection ({progress.done}/{progress.total})</h3>
                {CHECKLIST_ITEMS.map(([key, label]) => (
                    <label key={key} className="flex items-center gap-2 text-sm text-slate-300">
                        <input type="checkbox" checked={d.checklist?.[key] === true}
                            onChange={(e) => patch({ checklist: { ...(d.checklist || {}), [key]: e.target.checked } })} />
                        {label}
                    </label>
                ))}
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-2">
                <h3 className="text-sm font-black text-slate-200">Notes</h3>
                <textarea value={notes} maxLength={5000} rows={4} onChange={(e) => { setNotes(e.target.value); setSaved(false); }}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl p-2 text-sm text-slate-200" placeholder="Questions au vendeur, impressions…" />
                <button disabled={saved} onClick={async () => { if (await patch({ notes })) setSaved(true); }}
                    className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800 text-slate-200 text-sm font-bold disabled:opacity-40">{saved ? 'Enregistrées' : 'Enregistrer'}</button>
            </div>

            {d.description && (
                <details className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                    <summary className="text-sm font-black text-slate-200 cursor-pointer">Description de l'annonce</summary>
                    <p className="mt-2 text-sm text-slate-300 whitespace-pre-wrap">{d.description}</p>
                </details>
            )}
        </div>
    );
};

const LeafPage = ({ route, api = DEFAULT_API }) => (
    <div className="min-h-screen bg-slate-950 text-slate-200">
        <header className="sticky top-0 z-10 bg-slate-950/90 backdrop-blur border-b border-slate-800 px-4 py-3 flex items-center gap-3">
            <a href={route?.view === 'detail' ? '#leaf' : '#'} className="p-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300" title={route?.view === 'detail' ? 'Retour à la liste' : 'Retour à l\'application'}>
                <ArrowLeft size={16} />
            </a>
            <Car size={18} className="text-emerald-400" />
            <h1 className="font-black text-slate-100">Leaf Hunter</h1>
        </header>
        <main className="max-w-3xl mx-auto p-4">
            {route?.view === 'detail' ? <LeafDetail id={route.id} api={api} /> : <LeafList api={api} />}
        </main>
    </div>
);

export default LeafPage;
