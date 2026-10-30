import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowLeft, BookOpen, Clock, Gauge, Search } from 'lucide-react';
import { fetchFiche, fetchFiches } from '../services/apiService';
import { RESTORATION_CATEGORIES, RESTORATION_CATEGORY_LABELS } from '../constants/restorationPlan';
import {
    CONFIDENCE_HINTS, CONFIDENCE_LABELS, FICHES_HREF, STATUT_HINTS, STATUT_LABELS, difficultyLabel, ficheHref, filterFiches,
    groupByCategory, needsWarning, parseFicheHash, resolveFicheHref, resolveFicheImage,
} from '../utils/fiches';
import SimpleMarkdown from './SimpleMarkdown';

// Page « Fiches techniques de restauration » : liste filtrable et lecture d'une fiche, par le hash de l'URL
// (`#fiches`, `#fiche/<slug>`, voir hooks/useFicheRoute.js). Les fiches viennent de l'API (base commune avec les marques,
// chargées par backend/scripts/seed_guitar_fiches.py). `api` est injectable pour pouvoir afficher la page sans serveur.

const STATUT_STYLES = {
    brouillon: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    en_revision: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    validee: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
};
const CONFIDENCE_STYLES = {
    sourced: 'bg-slate-700/50 text-slate-300 border-slate-600',
    single_source: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
};
const BADGE = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-bold';
const DEFAULT_API = { fetchFiches, fetchFiche };
const imageBase = () => (typeof import.meta !== 'undefined' && import.meta.env?.BASE_URL) || '/';

export const StatutBadge = ({ statut }) => (
    <span className={`${BADGE} ${STATUT_STYLES[statut] || STATUT_STYLES.brouillon}`} title={STATUT_HINTS[statut]}>{STATUT_LABELS[statut] || statut}</span>
);
export const ConfidenceBadge = ({ confidence }) => (
    <span className={`${BADGE} ${CONFIDENCE_STYLES[confidence] || CONFIDENCE_STYLES.single_source}`} title={CONFIDENCE_HINTS[confidence]}>{CONFIDENCE_LABELS[confidence] || confidence}</span>
);

const categoryLabel = (c) => RESTORATION_CATEGORY_LABELS[c] || c;

// Chargement asynchrone lié à `deps`. Le résultat est rattaché au jeu de dépendances qui l'a produit (`token`) : dès que
// les dépendances changent (autre fiche), l'ancien résultat n'est plus renvoyé — pas un seul rendu avec la fiche précédente.
const useAsync = (load, deps) => {
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const token = useMemo(() => ({}), deps);
    const [state, setState] = useState({ token, loading: true, error: null, data: null });
    useEffect(() => {
        let cancelled = false;
        load().then((data) => { if (!cancelled) setState({ token, loading: false, error: null, data }); })
            .catch((error) => { if (!cancelled) setState({ token, loading: false, error, data: null }); });
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [token]);
    return state.token === token ? state : { loading: true, error: null, data: null };
};

const Message = ({ children, tone = 'muted' }) => (
    <div className={`rounded-2xl border px-4 py-6 text-sm text-center ${tone === 'error' ? 'border-rose-500/30 bg-rose-500/10 text-rose-300' : 'border-slate-800 bg-slate-900/60 text-slate-400'}`}>{children}</div>
);

const FichesList = ({ api }) => {
    const { loading, error, data } = useAsync(() => api.fetchFiches(), [api]);
    const [categorie, setCategorie] = useState('');
    const [query, setQuery] = useState('');
    const filtered = useMemo(() => filterFiches(data, { categorie, query }), [data, categorie, query]);
    const groups = useMemo(() => groupByCategory(filtered, RESTORATION_CATEGORIES), [filtered]);
    const presentCategories = useMemo(() => RESTORATION_CATEGORIES.filter((c) => (data || []).some((f) => f.categorie === c)), [data]);

    return (
        <div className="space-y-5">
            <div className="flex flex-col sm:flex-row gap-3">
                <label className="relative flex-1">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                    <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Chercher une fiche (truss rod, action, touche…)"
                        className="w-full h-10 pl-9 pr-3 rounded-xl bg-slate-900 border border-slate-700 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500" />
                </label>
                <select value={categorie} onChange={(e) => setCategorie(e.target.value)} aria-label="Catégorie"
                    className="h-10 px-3 rounded-xl bg-slate-900 border border-slate-700 text-sm text-slate-200 focus:outline-none focus:border-blue-500">
                    <option value="">Toutes les catégories</option>
                    {presentCategories.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}
                </select>
            </div>

            {loading && <Message>Chargement des fiches…</Message>}
            {error && <Message tone="error">Impossible de charger les fiches : {error.message}</Message>}
            {!loading && !error && data.length === 0 && <Message>Aucune fiche n'est encore chargée dans la base.</Message>}
            {!loading && !error && data.length > 0 && filtered.length === 0 && <Message>Aucune fiche ne correspond à cette recherche.</Message>}

            {groups.map(([cat, fiches]) => (
                <section key={cat} className="space-y-2">
                    <h2 className="text-xs font-black uppercase tracking-widest text-slate-500">{categoryLabel(cat)}</h2>
                    <ul className="grid gap-2 sm:grid-cols-2">
                        {fiches.map((f) => (
                            <li key={f.slug}>
                                <a href={ficheHref(f.slug)} className="block h-full rounded-2xl border border-slate-800 bg-slate-900/70 p-4 hover:border-blue-500/50 hover:bg-slate-900 transition-colors">
                                    <div className="flex items-start justify-between gap-2">
                                        <h3 className="font-bold text-white leading-snug">{f.titre}</h3>
                                        <StatutBadge statut={f.statut} />
                                    </div>
                                    {f.resume && <p className="mt-1.5 text-xs text-slate-400 leading-relaxed line-clamp-3">{f.resume}</p>}
                                    <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                                        {difficultyLabel(f.difficulte) && <span className="inline-flex items-center gap-1"><Gauge size={12} /> {difficultyLabel(f.difficulte)}</span>}
                                        {f.duree && <span className="inline-flex items-center gap-1"><Clock size={12} /> {f.duree}</span>}
                                        <ConfidenceBadge confidence={f.confidence} />
                                    </div>
                                </a>
                            </li>
                        ))}
                    </ul>
                </section>
            ))}
        </div>
    );
};

const FicheDetail = ({ slug, api }) => {
    const { loading, error, data: fiche } = useAsync(() => api.fetchFiche(slug), [api, slug]);
    const base = imageBase();
    // Sommaire : les titres `##` EFFECTIVEMENT rendus (avec leur ancre, posée par rehype-slug), lus dans la page une fois la fiche affichée.
    const bodyRef = useRef(null);
    const [sommaire, setSommaire] = useState([]);
    useLayoutEffect(() => {
        const titles = bodyRef.current ? [...bodyRef.current.querySelectorAll('h2[id]')] : [];
        setSommaire(titles.map((h) => ({ id: h.id, text: h.textContent })));
    }, [fiche]);

    if (loading) return <Message>Chargement de la fiche…</Message>;
    if (error) return <Message tone="error">Impossible de charger la fiche : {error.message}</Message>;
    if (!fiche) return <Message>Cette fiche n'existe pas (ou plus). <a href={FICHES_HREF} className="text-blue-400 underline">Voir toutes les fiches</a></Message>;

    const publishers = new Set((fiche.sources || []).map((s) => s.publisher)).size;
    return (
        <article className="space-y-5">
            <header className="space-y-3">
                <p className="text-xs font-black uppercase tracking-widest text-slate-500">{categoryLabel(fiche.categorie)}</p>
                <h1 className="text-2xl sm:text-3xl font-black text-white leading-tight">{fiche.titre}</h1>
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                    <StatutBadge statut={fiche.statut} />
                    <ConfidenceBadge confidence={fiche.confidence} />
                    {difficultyLabel(fiche.difficulte) && <span className="inline-flex items-center gap-1"><Gauge size={13} /> Difficulté {difficultyLabel(fiche.difficulte)}</span>}
                    {fiche.duree && <span className="inline-flex items-center gap-1"><Clock size={13} /> {fiche.duree}</span>}
                    {fiche.revision && <span>Révisée le {fiche.revision}</span>}
                    {publishers > 0 && <span>{publishers} éditeur{publishers > 1 ? 's' : ''} cité{publishers > 1 ? 's' : ''}</span>}
                </div>
            </header>

            {needsWarning(fiche) && (
                <div className="flex items-start gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                    <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                    <p>
                        {fiche.statut !== 'validee' && <><strong>{STATUT_LABELS[fiche.statut]}.</strong> {STATUT_HINTS[fiche.statut]} </>}
                        {fiche.confidence === 'single_source' && <>{CONFIDENCE_HINTS.single_source} </>}
                        Les valeurs chiffrées sont des repères : confirmer sur l'instrument avant d'intervenir.
                    </p>
                </div>
            )}

            {sommaire.length > 2 && (
                <nav aria-label="Sommaire" className="rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
                    <p className="text-[11px] font-black uppercase tracking-widest text-slate-500 mb-1">Sommaire</p>
                    <ol className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                        {sommaire.map((h) => (
                            <li key={h.id}><a href={`#${h.id}`} onClick={(e) => scrollToHeading(e, h.id)} className="text-blue-400 hover:text-blue-300">{h.text}</a></li>
                        ))}
                    </ol>
                </nav>
            )}

            <div ref={bodyRef}>
                <SimpleMarkdown text={fiche.body_md} skipFirstH1 resolveHref={resolveFicheHref} resolveImage={(src) => resolveFicheImage(src, base)}
                    isRouteHref={(href) => parseFicheHash(href) !== null} />
            </div>
        </article>
    );
};

// L'ancre d'un titre est son `id` (voir SimpleMarkdown) ; le hash de l'URL sert déjà à la navigation entre pages, donc le
// sommaire fait défiler la page sans toucher au hash.
const scrollToHeading = (event, id) => {
    event.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const FichesPage = ({ route, api = DEFAULT_API }) => {
    useEffect(() => { window.scrollTo?.(0, 0); }, [route?.name, route?.slug]);
    const detail = route?.name === 'detail';
    return (
        <div className="min-h-screen bg-slate-950 text-slate-200 font-sans">
            <header className="sticky top-0 z-30 bg-slate-900/80 backdrop-blur-lg border-b border-slate-800">
                <div className="max-w-4xl mx-auto px-4 h-14 flex items-center justify-between gap-3">
                    <a href={detail ? FICHES_HREF : '#'} className="inline-flex items-center gap-2 text-sm font-bold text-slate-300 hover:text-white">
                        <ArrowLeft size={16} /> {detail ? 'Toutes les fiches' : "Retour à l'application"}
                    </a>
                    <span className="inline-flex items-center gap-2 text-sm font-black text-white"><BookOpen size={16} className="text-blue-400" /> Fiches techniques</span>
                </div>
            </header>
            <main className="max-w-4xl mx-auto px-4 py-6">
                {detail ? <FicheDetail slug={route.slug} api={api} /> : <FichesList api={api} />}
            </main>
        </div>
    );
};

export default FichesPage;
