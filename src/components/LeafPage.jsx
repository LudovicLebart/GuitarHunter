import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowDownUp, ArrowLeft, Car, ExternalLink, RefreshCw, Snowflake, Star, ThumbsDown } from 'lucide-react';
import { fetchLeafConfig, fetchLeafDeal, fetchLeafDeals, fetchLeafRuns, saveLeafConfig, fetchLeafPrompts, saveLeafPrompts, setLeafState, triggerLeafAnalyze, triggerLeafReanalyze, triggerLeafRefresh, watchLeafCommand } from '../services/apiService';
import ImageGallery from './ImageGallery';
import LeafSettings from './LeafSettings';
import LeafPrompts from './LeafPrompts';
import {
    CHECKLIST_ITEMS, SORTS, SORT_KEYS, WINTER_LABELS, checklistProgress, duplicateCounts, filterAndSortDeals, hiddenDuplicateIds, flagLabel, formatKm, formatPrice, leafDealHref,
    aiFactLines, expertView, formatPrice as fmtPrice, leafImages, photoFactLines, priceTrend, questionsText, verdictInfo, winterRange, winterVerdict,
} from '../utils/leaf';

// Page Leaf Hunter (`#leaf`, `#leaf/<id>`, voir hooks/useLeafRoute.js) : liste triable des Leaf d'occasion retenues par le bot,
// et fiche d'une annonce (drapeaux, historique de prix, notes, checklist d'inspection). `api` est injectable (affichage sans serveur).

const LIST_PREFS_KEY = 'leaf.listPrefs';
const readListPrefs = () => {
    const defaults = { sort: 'price', reverse: false, favoritesOnly: false, showDuplicates: false };
    try {
        const saved = JSON.parse(window.localStorage.getItem(LIST_PREFS_KEY) || '{}');
        return { sort: SORT_KEYS.includes(saved.sort) ? saved.sort : defaults.sort, reverse: saved.reverse === true, favoritesOnly: saved.favoritesOnly === true,
            showDuplicates: saved.showDuplicates === true };
    } catch { return defaults; }
};

const DEFAULT_API = { fetchLeafDeals, fetchLeafDeal, setLeafState, fetchLeafRuns, triggerLeafRefresh, triggerLeafAnalyze, triggerLeafReanalyze, watchLeafCommand, fetchLeafConfig, saveLeafConfig, fetchLeafPrompts, saveLeafPrompts };
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

const VerdictBadge = ({ code, reasons }) => {
    const info = verdictInfo(code);
    return info ? <span className={`${BADGE} ${info.style}`} title={(reasons || []).join(' · ') || undefined}>{info.label}</span> : null;
};

const Flags = ({ flags }) => (flags?.length ? (
    <div className="flex flex-wrap gap-1.5">
        {flags.map((f) => <span key={f} className={`${BADGE} bg-slate-800 border-slate-700 text-slate-300`}>{flagLabel(f)}</span>)}
    </div>
) : null);

const DealRow = ({ deal, onToggle, duplicates = 0 }) => (
    <li className="rounded-2xl border border-slate-800 bg-slate-900/60 p-3 flex gap-3">
        <a href={leafDealHref(deal.id)} className="shrink-0 w-24 h-20 rounded-xl overflow-hidden bg-slate-800 flex items-center justify-center">
            {deal.image_urls?.[0] ? <img src={leafImages([deal.image_urls[0]], 'thumb')[0] || deal.image_urls[0]} alt="" loading="lazy" className="w-full h-full object-cover" /> : <Car size={28} className="text-slate-600" />}
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
                {duplicates > 0 ? <span className="text-sky-300" title="Annonces semblables (même titre, même prix, même endroit) masquées"> · +{duplicates} doublon{duplicates > 1 ? 's' : ''} masqué{duplicates > 1 ? 's' : ''}</span> : null}
            </div>
            <div className="flex flex-wrap gap-1.5"><VerdictBadge code={deal.verdict} reasons={deal.analysis?.verdict_reasons} /><WinterBadge analysis={deal.analysis} /></div>
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

const LeafList = ({ api, cities }) => {
    const [state, setState] = useState({ loading: true, error: null, deals: [], runs: [] });
    // Choix de tri, de sens et de filtre mémorisés dans ce navigateur (jamais bloquant : sans stockage, valeurs par défaut).
    const [prefs, setPrefs] = useState(readListPrefs);
    const { sort, reverse, favoritesOnly, showDuplicates } = prefs;
    const setSort = (value) => setPrefs((p) => ({ ...p, sort: value }));
    const setReverse = (value) => setPrefs((p) => ({ ...p, reverse: value }));
    const setFavoritesOnly = (updater) => setPrefs((p) => ({ ...p, favoritesOnly: typeof updater === 'function' ? updater(p.favoritesOnly) : updater }));
    useEffect(() => { try { window.localStorage.setItem(LIST_PREFS_KEY, JSON.stringify(prefs)); } catch { /* stockage indisponible : sans effet */ } }, [prefs]);
    const [query, setQuery] = useState('');
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
    // Le bouton reste désactivé tant que la COMMANDE n'est pas terminée (suivie par son statut, pas par un délai fixe) ;
    // le suivi est annulé si l'on quitte la page.
    const stopWatching = useRef(null);
    useEffect(() => () => { if (stopWatching.current) stopWatching.current(); }, []);
    const onRefresh = async (forceAi = false) => {
        setRefreshing(true);
        try {
            const command = await api.triggerLeafRefresh(forceAi);
            stopWatching.current = api.watchLeafCommand(command.id, (c) => {
                if (c.status === 'pending') return;
                setRefreshing(false);
                if (c.status === 'failed') setState((s) => ({ ...s, error: new Error(c.error || 'Le passage Leaf a échoué.') }));
                else load();
            });
        } catch (error) { setRefreshing(false); setState((s) => ({ ...s, error })); }
    };

    const shown = useMemo(() => filterAndSortDeals(state.deals, { favoritesOnly, query, sort, reverse, hideDuplicates: !showDuplicates }), [state.deals, favoritesOnly, query, sort, reverse, showDuplicates]);
    const dupCounts = useMemo(() => duplicateCounts(state.deals), [state.deals]);
    const hiddenCount = useMemo(() => hiddenDuplicateIds(state.deals).size, [state.deals]);
    const lastRun = state.runs[0];

    return (
        <div className="space-y-4">
            <LeafSettings api={api} cities={cities} />
            <LeafPrompts api={api} />
            <div className="flex flex-wrap items-center gap-2">
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Rechercher (ville, version…)"
                    className="flex-1 min-w-[10rem] bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-sm text-slate-200" />
                <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Tri"
                    className="bg-slate-900 border border-slate-700 rounded-xl px-2 py-1.5 text-sm text-slate-200">
                    {Object.entries(SORTS).map(([key, s]) => <option key={key} value={key}>{s.label}</option>)}
                </select>
                <button onClick={() => setReverse(!reverse)} aria-pressed={reverse} title="Inverser l'ordre (les valeurs inconnues restent en bas)"
                    className={`px-2.5 py-1.5 rounded-xl border text-sm font-bold ${reverse ? 'bg-blue-500/20 border-blue-500/40 text-blue-300' : 'bg-slate-900 border-slate-700 text-slate-300'}`}>
                    <ArrowDownUp size={14} className="inline -mt-0.5" /><span className="sr-only">Inverser l'ordre</span>
                </button>
                <button onClick={() => setFavoritesOnly((v) => !v)} aria-pressed={favoritesOnly}
                    className={`px-3 py-1.5 rounded-xl border text-sm font-bold ${favoritesOnly ? 'bg-amber-500/20 border-amber-500/40 text-amber-300' : 'bg-slate-900 border-slate-700 text-slate-300'}`}>
                    <Star size={14} className="inline -mt-0.5" /> Favoris
                </button>
                {hiddenCount > 0 && (
                    <button onClick={() => setPrefs((p) => ({ ...p, showDuplicates: !p.showDuplicates }))} aria-pressed={showDuplicates}
                        title="Annonces semblables (même titre, même prix, même endroit) : masquées par défaut, l'ancienne reste affichée"
                        className={`px-3 py-1.5 rounded-xl border text-sm font-bold ${showDuplicates ? 'bg-sky-500/20 border-sky-500/40 text-sky-300' : 'bg-slate-900 border-slate-700 text-slate-300'}`}>
                        {showDuplicates ? 'Doublons affichés' : `Doublons masqués (${hiddenCount})`}
                    </button>
                )}
                <button onClick={() => onRefresh(false)} disabled={refreshing} title="Lancer un passage maintenant"
                    className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-900 text-slate-300 text-sm font-bold disabled:opacity-50">
                    <RefreshCw size={14} className={`inline -mt-0.5 ${refreshing ? 'animate-spin' : ''}`} /> Actualiser
                </button>
                <button onClick={() => onRefresh(true)} disabled={refreshing}
                    title="Passage complet + nouvelle analyse IA de chaque annonce (dans le plafond quotidien d'analyses)"
                    className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-900 text-slate-300 text-sm font-bold disabled:opacity-50">
                    Ré-analyser (IA)
                </button>
            </div>
            {lastRun && <p className="text-[11px] text-slate-500">Dernier passage ({lastRun.source.replace('leaf_', '')}) : {lastRun.outcome}{lastRun.cards_seen != null ? `, ${lastRun.cards_seen} annonces lues` : ''}.</p>}
            {state.error && <Message tone="error">{String(state.error.message || state.error)}</Message>}
            {state.loading ? <Message>Chargement…</Message>
                : shown.length === 0 ? <Message>{state.deals.length ? 'Aucune annonce ne correspond.' : 'Aucune annonce pour le moment : le prochain passage du bot les ajoutera.'}</Message>
                    : <ul className="space-y-3">{shown.map((d) => <DealRow key={d.id} deal={d} onToggle={onToggle} duplicates={showDuplicates ? 0 : (dupCounts[d.id] || 0)} />)}</ul>}
        </div>
    );
};

const LeafDetail = ({ id, api }) => {
    const [state, setState] = useState({ loading: true, error: null, deal: null });
    const [notes, setNotes] = useState('');
    const [saved, setSaved] = useState(true);
    const [expertState, setExpertState] = useState({ running: false, error: null });
    const [reState, setReState] = useState({ running: false, error: null, done: false });
    const [galleryStart, setGalleryStart] = useState(0);
    const stopWatching = useRef(null);
    useEffect(() => () => { if (stopWatching.current) stopWatching.current(); }, []);

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

    // Ré-analyse : relit la fiche de l'annonce et refait règles, scores, verdict et IA avec le code actuel. Un refus (annonce qui ne passe
    // plus les règles, fiche illisible) s'affiche tel quel.
    const runReanalyze = async () => {
        setReState({ running: true, error: null, done: false });
        try {
            const command = await api.triggerLeafReanalyze(id);
            stopWatching.current = api.watchLeafCommand(command.id, async (c) => {
                if (c.status === 'pending') return;
                if (c.status === 'failed') { setReState({ running: false, error: c.error || 'La ré-analyse a échoué.', done: false }); return; }
                try { const deal = await api.fetchLeafDeal(id); setState((s) => ({ ...s, deal })); setReState({ running: false, error: null, done: true }); }
                catch (error) { setReState({ running: false, error: String(error.message || error), done: false }); }
            });
        } catch (error) { setReState({ running: false, error: String(error.message || error), done: false }); }
    };

    // Analyse approfondie : commande suivie par son statut ; un refus (IA éteinte, plafond atteint) s'affiche tel quel.
    const runExpert = async () => {
        setExpertState({ running: true, error: null });
        try {
            const command = await api.triggerLeafAnalyze(id);
            stopWatching.current = api.watchLeafCommand(command.id, async (c) => {
                if (c.status === 'pending') return;
                if (c.status === 'failed') { setExpertState({ running: false, error: c.error || "L'analyse approfondie a échoué." }); return; }
                try { const deal = await api.fetchLeafDeal(id); setState((s) => ({ ...s, deal })); setExpertState({ running: false, error: null }); }
                catch (error) { setExpertState({ running: false, error: String(error.message || error) }); }
            });
        } catch (error) { setExpertState({ running: false, error: String(error.message || error) }); }
    };

    if (state.loading) return <Message>Chargement…</Message>;
    if (state.error && !state.deal) return <Message tone="error">{String(state.error.message || state.error)}</Message>;
    const d = state.deal;
    const trend = priceTrend(d.priceHistory);
    const progress = checklistProgress(d.checklist);
    const equipment = d.analysis?.equipment;
    const ai = d.analysis?.ai;
    const aiLines = aiFactLines(ai);
    const expert = expertView(d.analysis?.expert);
    const photoLines = photoFactLines(d.analysis?.photos);
    const photos = leafImages(d.image_urls, 'medium');
    const photosLarge = leafImages(d.image_urls, 'large');
    return (
        <div className="space-y-4">
            {state.error && <Message tone="error">{String(state.error.message || state.error)}</Message>}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                    <h2 className="text-lg font-black text-slate-100">{d.year || '?'} Nissan Leaf {d.trim || ''}</h2>
                    <span className="text-emerald-300 font-black text-lg">{formatPrice(d.price)}</span>
                </div>
                <p className="text-sm text-slate-300">{formatKm(d.km)} · {d.location || 'lieu ?'}{d.seller_type ? ` · vendeur : ${d.seller_type === 'delr' ? 'commerçant' : d.seller_type === 'ownr' ? 'particulier' : d.seller_type}` : ''}</p>
                <div className="flex flex-wrap gap-1.5"><VerdictBadge code={d.verdict} reasons={d.analysis?.verdict_reasons} /><WinterBadge analysis={d.analysis} /></div>
                {d.analysis?.verdict_reasons?.length > 0 && <p className="text-xs text-slate-400">Verdict calculé par le code : {d.analysis.verdict_reasons.join(' · ')}.</p>}
                <div className="text-xs text-slate-400 space-y-0.5">
                    <p>Batterie : {d.battery_kwh_low ? (d.battery_kwh_low === d.battery_kwh_high ? `${d.battery_kwh_low} kWh` : `${d.battery_kwh_low} ou ${d.battery_kwh_high} kWh`) : 'inconnue'}
                        {d.battery_source === 'inferred' ? ' (déduite de l\'année)' : ''}</p>
                    <p>SOH annoncé : {d.soh_announced != null ? `${Math.round(d.soh_announced)} %${d.soh_evidence ? ` — « ${d.soh_evidence} »` : ''}` : 'non annoncé'}</p>
                    {equipment && <p>Équipement d'hiver : {equipment.score}/10{equipment.heat_pump_inferred ? ' (pompe à chaleur déduite de la version, à confirmer)' : ''}</p>}
                    {trend && <p>Prix : {formatPrice(trend.first)} → {formatPrice(trend.last)} ({trend.delta < 0 ? '' : '+'}{formatPrice(trend.delta)})</p>}
                </div>
                <Flags flags={d.flags} />
                {reState.error && <p className="text-sm text-rose-300">{reState.error}</p>}
                {reState.done && !reState.error && <p className="text-sm text-emerald-300">Ré-analyse terminée : fiche relue et verdict recalculé.</p>}
                {d.link && <a href={d.link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm font-bold text-blue-400 hover:text-blue-300"><ExternalLink size={14} /> Voir l'annonce</a>}
                <div className="flex gap-2">
                    <button onClick={() => patch({ isFavorite: !d.is_favorite })} aria-pressed={d.is_favorite}
                        className={`px-3 py-1.5 rounded-xl border text-sm font-bold ${d.is_favorite ? 'bg-amber-500/20 border-amber-500/40 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-300'}`}><Star size={14} className="inline -mt-0.5" /> Favori</button>
                    <button onClick={runReanalyze} disabled={reState.running} title="Relire la fiche et refaire règles, verdict et analyse IA"
                        className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800 text-slate-300 text-sm font-bold disabled:opacity-50">
                        <RefreshCw size={14} className={`inline -mt-0.5 ${reState.running ? 'animate-spin' : ''}`} /> {reState.running ? 'Ré-analyse…' : 'Ré-analyser'}
                    </button>
                    <button onClick={() => patch({ isRejected: !d.is_rejected })} aria-pressed={d.is_rejected}
                        className={`px-3 py-1.5 rounded-xl border text-sm font-bold ${d.is_rejected ? 'bg-rose-500/20 border-rose-500/40 text-rose-300' : 'bg-slate-800 border-slate-700 text-slate-300'}`}><ThumbsDown size={14} className="inline -mt-0.5" /> {d.is_rejected ? 'Rejetée' : 'Pas intéressé'}</button>
                </div>
            </div>

            {photos.length > 0 && (
                // Même galerie que les guitares (ImageGallery) : photos moyennes à l'écran, HAUTE résolution en plein écran.
                <div className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden h-72 sm:h-96" title="Cliquer pour agrandir">
                    <ImageGallery key={galleryStart} initialIndex={galleryStart} images={photos} fullImages={photosLarge} title={`${d.year || ''} Leaf ${d.trim || ''}`} />
                </div>
            )}

            {photoLines.length > 0 && (
                <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-2">
                    <h3 className="text-sm font-black text-amber-200">Lu sur les photos (à confirmer)</h3>
                    <ul className="space-y-1.5">
                        {photoLines.map((l) => (
                            <li key={l.key} className="text-sm text-slate-300">
                                <span className="font-bold">{l.label} : {l.value}</span>
                                {l.photo && <button onClick={() => { setGalleryStart(l.photo - 1); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                                    className="ml-2 text-xs font-bold text-blue-400 hover:text-blue-300">voir la photo n°{l.photo}</button>}
                                {l.evidence && <blockquote className="mt-0.5 border-l-2 border-slate-700 pl-2 text-xs italic text-slate-400">« {l.evidence} »</blockquote>}
                            </li>
                        ))}
                    </ul>
                    <p className="text-[10px] text-slate-500">Recopié par un modèle depuis l'image, confiance faible : jamais utilisé pour rejeter une annonce ni pour la classer « candidat fort ». Vérifiez la photo.</p>
                </div>
            )}

            {ai && (
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                        <h3 className="text-sm font-black text-slate-200">Analyse IA</h3>
                        <span className="text-[10px] text-slate-500">{ai.model} · {ai.provider === 'local' ? 'Dell' : 'Gemini'}{ai.at ? ` · ${new Date(ai.at).toLocaleDateString('fr-CA')}` : ''}</span>
                    </div>
                    {d.analysis?.ai_stale && <p className="text-xs text-amber-300">Analyse périmée : le texte ou le prix de l'annonce a changé depuis ; elle n'est pas appliquée.</p>}
                    {ai.summary && <p className="text-sm text-slate-300">{ai.summary}</p>}
                    {aiLines.length > 0 && (
                        <ul className="space-y-2">
                            {aiLines.map((l) => (
                                <li key={l.key} className="text-sm text-slate-300">
                                    <span className="font-bold">{l.label} : {l.value}</span> <span className="text-[10px] text-slate-500">({l.confidence}{l.corrected ? ', sens corrigé d\'après la citation' : ''})</span>
                                    {l.evidence && <blockquote className="mt-0.5 border-l-2 border-slate-700 pl-2 text-xs italic text-slate-400">« {l.evidence} »</blockquote>}
                                </li>
                            ))}
                        </ul>
                    )}
                    {ai.attention?.length > 0 && (
                        <div>
                            <p className="text-xs font-bold text-slate-400 mb-1">À vérifier</p>
                            <ul className="space-y-1.5">
                                {ai.attention.map((a) => (
                                    <li key={a.text} className="text-sm text-slate-300">{a.text}
                                        {a.evidence && <blockquote className="mt-0.5 border-l-2 border-slate-700 pl-2 text-xs italic text-slate-400">« {a.evidence} »</blockquote>}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    <p className="text-[10px] text-slate-500">Seuls les faits dont la citation est retrouvée dans l'annonce sont affichés ; le résumé est un texte libre de l'IA, à lire avec recul.{ai.rejected ? ` ${ai.rejected} fait(s) sans preuve écarté(s).` : ''}</p>
                </div>
            )}

            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-black text-slate-200">Analyse approfondie (Expert)</h3>
                    <button onClick={runExpert} disabled={expertState.running}
                        className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800 text-slate-200 text-xs font-bold disabled:opacity-50">
                        {expertState.running ? 'Analyse en cours…' : (expert ? 'Refaire l\'analyse' : 'Analyse approfondie')}
                    </button>
                </div>
                {expertState.error && <p className="text-sm text-rose-300">{expertState.error}</p>}
                {!expert && !expertState.running && !expertState.error && (
                    <p className="text-xs text-slate-500">À la demande seulement (appel payant à Claude Sonnet 5.5, plafonné par jour dans les réglages) : avis argumenté, questions à poser au vendeur, points d'inspection et prix plafond.</p>
                )}
                {expert && (
                    <div className="space-y-3">
                        <div className="flex flex-wrap items-center gap-2">
                            <span className={`${BADGE} ${expert.worth.style}`}>{expert.worth.label}</span>
                            {expert.ceiling && <span className="text-sm text-slate-300">Prix plafond : <b>{fmtPrice(expert.ceiling.amount)}</b> <span className="text-[10px] text-slate-500">({expert.ceiling.basis})</span></span>}
                        </div>
                        <p className="text-sm text-slate-300">{expert.opinion}</p>
                        {expert.ceiling?.reasoning && <p className="text-xs text-slate-400">{expert.ceiling.reasoning}</p>}
                        {expert.questions.length > 0 && (
                            <div>
                                <div className="flex items-center justify-between"><p className="text-xs font-bold text-slate-400 mb-1">Questions à poser au vendeur</p>
                                    <button onClick={() => navigator.clipboard?.writeText(questionsText(expert.questions))} className="text-[11px] font-bold text-blue-400 hover:text-blue-300">Copier</button></div>
                                <ol className="list-decimal list-inside space-y-1 text-sm text-slate-300">{expert.questions.map((q) => <li key={q}>{q}</li>)}</ol>
                            </div>
                        )}
                        {expert.inspection.length > 0 && (
                            <div><p className="text-xs font-bold text-slate-400 mb-1">À inspecter sur place</p>
                                <ul className="list-disc list-inside space-y-1 text-sm text-slate-300">{expert.inspection.map((p) => <li key={p}>{p}</li>)}</ul></div>
                        )}
                        {expert.risks.length > 0 && (
                            <div><p className="text-xs font-bold text-slate-400 mb-1">Risques relevés dans l'annonce</p>
                                <ul className="space-y-1.5">{expert.risks.map((r) => (
                                    <li key={r.text} className="text-sm text-slate-300">{r.text}<blockquote className="mt-0.5 border-l-2 border-slate-700 pl-2 text-xs italic text-slate-400">« {r.evidence} »</blockquote></li>))}</ul></div>
                        )}
                        <p className="text-[10px] text-slate-500">{expert.model}{expert.at ? ` · ${new Date(expert.at).toLocaleDateString('fr-CA')}` : ''} — un risque sans citation exacte de l'annonce est écarté ; le prix plafond reste cohérent avec le prix demandé et le marché estimé.</p>
                    </div>
                )}
            </div>

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

const LeafPage = ({ route, api = DEFAULT_API, cities = [] }) => (
    <div className="min-h-screen bg-slate-950 text-slate-200">
        <header className="sticky top-0 z-10 bg-slate-950/90 backdrop-blur border-b border-slate-800 px-4 py-3 flex items-center gap-3">
            <a href={route?.view === 'detail' ? '#leaf' : '#'} className="p-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300" title={route?.view === 'detail' ? 'Retour à la liste' : 'Retour à l\'application'}>
                <ArrowLeft size={16} />
            </a>
            <Car size={18} className="text-emerald-400" />
            <h1 className="font-black text-slate-100">Leaf Hunter</h1>
        </header>
        <main className="max-w-3xl mx-auto p-4">
            {route?.view === 'detail' ? <LeafDetail id={route.id} api={api} /> : <LeafList api={api} cities={cities} />}
        </main>
    </div>
);

export default LeafPage;
