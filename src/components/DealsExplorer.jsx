import React, { useMemo, useState } from 'react';
import { SlidersHorizontal, Zap } from 'lucide-react';
import { ComposedChart, Scatter, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts';
import { RADAR_GROUP, MARKET_GROUP } from '../constants';
import { normalizeCityKey, pickBestLabel } from '../utils/cities';
import { resolveClassification } from '../utils/taxonomy';

// ─── Métriques numériques disponibles pour les axes X/Y ────────────────────
// `soldOnly: true` restreint le nuage de points aux ventes avec un délai réel connu
// (mêmes conditions que l'ancien graphique liquidité dédié) dès que cette métrique
// est choisie sur un des deux axes.
const METRICS = [
    { key: 'liquidityScore', label: 'Score Liquidité (IA)', domain: [0, 10], get: (d) => d.aiAnalysis?.liquidity_score },
    { key: 'dealScore', label: 'Score Deal (IA)', domain: [0, 10], get: (d) => d.aiAnalysis?.deal_score },
    { key: 'authenticityScore', label: 'Score Authenticité (IA)', domain: [0, 10], get: (d) => d.aiAnalysis?.authenticity_score },
    { key: 'conditionScore', label: 'Score État (IA)', domain: [0, 10], get: (d) => d.aiAnalysis?.condition_score },
    { key: 'restorationScore', label: 'Score Restauration (IA)', domain: [0, 10], get: (d) => d.aiAnalysis?.restoration_interest_score },
    { key: 'price', label: 'Prix ($)', domain: ['auto', 'auto'], get: (d) => (typeof d.price === 'number' ? d.price : null) },
    { key: 'margin', label: 'Marge estimée ($)', domain: ['auto', 'auto'], get: (d) => d.aiAnalysis?.estimated_gross_margin },
    {
        key: 'saleDelayDays', label: 'Délai de vente réel (j)', domain: [0, 'auto'], soldOnly: true,
        get: (d) => (d.soldTimestamp?.seconds && d.publishTimestamp?.seconds && d.soldTimestamp.seconds > d.publishTimestamp.seconds)
            ? (d.soldTimestamp.seconds - d.publishTimestamp.seconds) / 86400
            : null,
    },
];

// ─── Couleur : 3 dimensions catégorielles, chacune limitée à 2-3 groupes FIXES ──
// La palette validée du design system ne garantit une séparation daltonisme-sûre
// (all-pairs, cf. `dataviz` skill) que sur ses 3 premiers slots — au-delà, il faut
// replier sur "Autre" ou faceter. Plutôt qu'un "top N + Autres" dynamique (qui violerait
// la règle "la couleur suit l'entité, jamais son rang"), chaque dimension est réduite à
// des groupes fixes et déjà établis ailleurs dans l'app (RADAR_GROUP/MARKET_GROUP pour le
// verdict, la racine de taxonomie pour la catégorie) plutôt qu'un éclatement fin (9 verdicts
// individuels, 8 catégories) qui ne validerait plus.
const SLOT_BLUE = '#3987e5';
const SLOT_ORANGE = '#d95926';
const SLOT_AQUA = '#199e70';
const SINGLE_SERIES_COLOR = '#34d399';
const TREND_COLOR = '#a78bfa';

// Verdicts de "bruit" — l'annonce n'est pas un instrument, ou n'a jamais été réellement
// analysée (rejet immédiat au Portier) : exclus par défaut du dataset (pas seulement recolorés)
// pour ne pas polluer la corrélation elle-même. `BAD_DEAL` en est délibérément exclu : c'est un
// verdict IA légitime sur une vraie guitare jugée trop chère après une vraie analyse Tier 2 (voir
// CLAUDE.md — "BAD_DEAL ≠ REJECTED") ; toute annonce visible ici a déjà un score réel de toute
// façon, donc un BAD_DEAL ne peut pas être une fiche vide.
const NOISE_VERDICTS = ['REJECTED_ITEM', 'REJECTED_SERVICE', 'REJECTED', 'INCOMPLETE_DATA'];

const verdictGroup = (verdict) => {
    if (!verdict) return null;
    if (RADAR_GROUP.includes(verdict)) return 'Opportunité';
    if (MARKET_GROUP.includes(verdict)) return 'Marché neutre';
    return 'Trop cher';
};

const CATEGORY_ROOT_LABELS = { guitare: 'Guitare', amplificateur: 'Amplificateur', etui_housse: 'Étui / Housse' };
const categoryGroup = (classification) => {
    const { segments } = resolveClassification(classification);
    if (!segments || segments.length === 0) return null;
    return CATEGORY_ROOT_LABELS[segments[0]] || 'Autre';
};

const COLOR_DIMENSIONS = [
    { key: 'none', label: 'Aucune' },
    { key: 'verdict', label: 'Verdict' },
    { key: 'source', label: 'Source' },
    { key: 'category', label: 'Catégorie' },
];

const GROUP_ORDER = {
    verdict: [
        { name: 'Opportunité', color: SLOT_BLUE },
        { name: 'Marché neutre', color: SLOT_AQUA },
        { name: 'Trop cher', color: SLOT_ORANGE },
    ],
    source: [
        { name: 'Facebook', color: SLOT_BLUE },
        { name: 'Kijiji', color: SLOT_ORANGE },
    ],
    category: [
        { name: 'Guitare', color: SLOT_BLUE },
        { name: 'Amplificateur', color: SLOT_ORANGE },
        { name: 'Étui / Housse', color: SLOT_AQUA },
        { name: 'Autre', color: '#64748b' },
    ],
};

// Seuils Cohen pour qualifier |r| (corrélation de Pearson) en mots — convention usuelle.
const correlationStrength = (r) => {
    const abs = Math.abs(r);
    if (abs < 0.1) return 'négligeable';
    if (abs < 0.3) return 'faible';
    if (abs < 0.5) return 'modérée';
    if (abs < 0.7) return 'forte';
    return 'très forte';
};

const selectClass = 'bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 px-2.5 py-1.5 outline-none focus:ring-2 focus:ring-emerald-500/30';

const DealsExplorer = ({ deals }) => {
    const [xKey, setXKey] = useState('liquidityScore');
    const [yKey, setYKey] = useState('saleDelayDays');
    const [colorKey, setColorKey] = useState('none');
    const [cityFilter, setCityFilter] = useState('ALL');
    const [includeNoise, setIncludeNoise] = useState(false);

    const cityOptions = useMemo(() => {
        const byKey = {};
        deals.forEach(d => {
            const key = normalizeCityKey(d.location);
            if (!key) return;
            if (!byKey[key]) byKey[key] = { count: 0, labels: [] };
            byKey[key].count++;
            if (d.location) byKey[key].labels.push(d.location);
        });
        return Object.entries(byKey)
            .map(([key, b]) => ({ key, label: pickBestLabel(b.labels) || key, count: b.count }))
            .sort((a, b) => b.count - a.count)
            .slice(0, 15);
    }, [deals]);

    const xMetric = METRICS.find(m => m.key === xKey);
    const yMetric = METRICS.find(m => m.key === yKey);

    const records = useMemo(() => {
        return deals
            .map(d => {
                const x = xMetric.get(d);
                const y = yMetric.get(d);
                if (typeof x !== 'number' || typeof y !== 'number' || Number.isNaN(x) || Number.isNaN(y)) return null;
                if (cityFilter !== 'ALL' && normalizeCityKey(d.location) !== cityFilter) return null;
                if (!includeNoise && NOISE_VERDICTS.includes(d.aiAnalysis?.verdict)) return null;
                return {
                    x, y,
                    verdictGroup: verdictGroup(d.aiAnalysis?.verdict),
                    source: d.id?.startsWith('kijiji_') ? 'Kijiji' : 'Facebook',
                    categoryGroup: categoryGroup(d.aiAnalysis?.classification),
                };
            })
            .filter(Boolean);
    }, [deals, xMetric, yMetric, cityFilter, includeNoise]);

    // Corrélation de Pearson + droite de régression sur l'ensemble des points filtrés, indépendamment
    // du regroupement couleur choisi (la couleur n'est qu'une lecture visuelle en plus, pas un
    // sous-échantillon différent).
    const correlation = useMemo(() => {
        const n = records.length;
        if (n < 3) return { r: null, trend: [] };
        const meanX = records.reduce((a, p) => a + p.x, 0) / n;
        const meanY = records.reduce((a, p) => a + p.y, 0) / n;
        let covXY = 0, varX = 0, varY = 0;
        records.forEach(p => {
            const dx = p.x - meanX, dy = p.y - meanY;
            covXY += dx * dy;
            varX += dx * dx;
            varY += dy * dy;
        });
        if (varX === 0 || varY === 0) return { r: null, trend: [] };
        const r = covXY / Math.sqrt(varX * varY);
        const slope = covXY / varX;
        const intercept = meanY - slope * meanX;
        const minX = Math.min(...records.map(p => p.x));
        const maxX = Math.max(...records.map(p => p.x));
        return { r, trend: [{ x: minX, y: intercept + slope * minX }, { x: maxX, y: intercept + slope * maxX }] };
    }, [records]);

    const groupField = colorKey === 'verdict' ? 'verdictGroup' : colorKey === 'source' ? 'source' : colorKey === 'category' ? 'categoryGroup' : null;

    const series = useMemo(() => {
        if (!groupField) {
            return [{ name: `Ventes (${records.length})`, color: SINGLE_SERIES_COLOR, points: records }];
        }
        const order = GROUP_ORDER[colorKey];
        return order
            .map(g => ({ name: g.name, color: g.color, points: records.filter(r => r[groupField] === g.name) }))
            .filter(s => s.points.length > 0)
            .map(s => ({ ...s, name: `${s.name} (${s.points.length})` }));
    }, [records, groupField, colorKey]);

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
            <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-1 flex items-center gap-2">
                <Zap size={16} className="text-emerald-400" />
                Explorateur de Corrélations
            </h3>
            <p className="text-slate-500 text-xs mb-4">
                Un point = une annonce. Choisis librement les deux métriques à comparer — chaque point garde sa valeur individuelle, sans moyenne ni regroupement.
            </p>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
                <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
                    <SlidersHorizontal size={12} /> Axe X
                    <select className={selectClass} value={xKey} onChange={(e) => setXKey(e.target.value)}>
                        {METRICS.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                    </select>
                </label>
                <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
                    Axe Y
                    <select className={selectClass} value={yKey} onChange={(e) => setYKey(e.target.value)}>
                        {METRICS.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                    </select>
                </label>
                <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
                    Couleur
                    <select className={selectClass} value={colorKey} onChange={(e) => setColorKey(e.target.value)}>
                        {COLOR_DIMENSIONS.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
                    </select>
                </label>
                <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
                    Ville
                    <select className={selectClass} value={cityFilter} onChange={(e) => setCityFilter(e.target.value)}>
                        <option value="ALL">Toutes</option>
                        {cityOptions.map(c => <option key={c.key} value={c.key}>{c.label} ({c.count})</option>)}
                    </select>
                </label>
                <label className="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer">
                    <input type="checkbox" checked={includeNoise} onChange={(e) => setIncludeNoise(e.target.checked)} className="accent-emerald-500" />
                    Inclure le bruit (items/annonces rejetés)
                </label>
            </div>

            <p className="text-slate-600 text-[11px] mb-4">
                {records.length} annonce{records.length !== 1 ? 's' : ''} tracée{records.length !== 1 ? 's' : ''}.
                {correlation.r !== null && (
                    <> Corrélation {correlationStrength(correlation.r)} (r = {correlation.r.toFixed(2)}).</>
                )}
                {records.length > 0 && records.length < 20 && (
                    <span className="text-amber-500"> ⚠️ Échantillon réduit — à interpréter avec prudence.</span>
                )}
            </p>

            {records.length >= 3 ? (
                <div>
                    <div className="h-[280px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart margin={{ top: 5, right: 20, left: 0, bottom: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis
                                type="number" dataKey="x" domain={xMetric.domain} allowDecimals
                                tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false}
                                label={{ value: xMetric.label, position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 11 }}
                            />
                            <YAxis
                                type="number" dataKey="y" domain={yMetric.domain} allowDecimals
                                tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false}
                                label={{ value: yMetric.label, angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }}
                            />
                            <Tooltip
                                cursor={{ stroke: '#334155' }}
                                // Contenu personnalisé : le rendu par défaut de Recharts affiche une ligne
                                // technique parasite ("x : <valeur>") en plus des séries sur un axe X numérique
                                // partagé entre plusieurs Scatter/Line.
                                content={({ active, payload }) => {
                                    if (!active || !payload?.length) return null;
                                    const point = payload.find(p => p.name !== 'Tendance')?.payload || payload[0].payload;
                                    return (
                                        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '0.5rem', padding: '8px 12px' }}>
                                            <div style={{ color: '#94a3b8', fontSize: 12 }}>{xMetric.label} : {Math.round(point.x * 10) / 10}</div>
                                            <div style={{ color: '#94a3b8', fontSize: 12 }}>{yMetric.label} : {Math.round(point.y * 10) / 10}</div>
                                        </div>
                                    );
                                }}
                            />
                            {series.map(s => (
                                <Scatter key={s.name} name={s.name} data={s.points} dataKey="y" fill={s.color} fillOpacity={0.6} stroke="#0f172a" strokeWidth={1} r={5} />
                            ))}
                            {correlation.trend.length > 0 && (
                                <Line
                                    name="Tendance" data={correlation.trend} dataKey="y" type="linear"
                                    stroke={TREND_COLOR} strokeWidth={2} strokeDasharray="6 4" dot={false} legendType="none" isAnimationActive={false}
                                />
                            )}
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>
                    {series.length > 1 && (
                        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 justify-center">
                            {series.map(s => (
                                <span key={s.name} className="flex items-center gap-1.5 text-[11px] text-slate-400">
                                    <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ backgroundColor: s.color }} />
                                    {s.name}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            ) : (
                <div className="h-[120px] flex items-center justify-center text-slate-600 text-sm">Pas assez de données pour ces deux axes (au moins 3 annonces avec les deux valeurs connues)</div>
            )}
        </div>
    );
};

export default DealsExplorer;
