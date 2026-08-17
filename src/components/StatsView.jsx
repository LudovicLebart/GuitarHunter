import React, { useMemo } from 'react';
import { Target, Activity, DollarSign, Clock, AlertTriangle, ChevronRight, BarChart2, CheckCircle2, XCircle, TrendingUp, Zap, MapPin, Layers, GitCompare, ShieldCheck, Coins } from 'lucide-react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, BarChart, Bar, LineChart, Line, ComposedChart, Scatter, XAxis, YAxis, Tooltip, Legend, CartesianGrid, Cell } from 'recharts';
import { RADAR_GROUP } from '../constants';
import { normalizeCityKey, pickBestLabel } from '../utils/cities';
import { resolveClassification, formatClassificationLabel } from '../utils/taxonomy';

const StatCard = ({ title, value, subtitle, icon: Icon, colorClass, trend }) => (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col relative overflow-hidden group">
        <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${colorClass} opacity-5 rounded-full blur-2xl -mr-16 -mt-16 transition-opacity group-hover:opacity-10`} />

        <div className="flex justify-between items-start mb-4 relative z-10">
            <div className={`p-3 rounded-xl bg-slate-800/80 border border-slate-700/50 ${colorClass.split(' ')[0].replace('from-', 'text-')}`}>
                <Icon size={20} />
            </div>
            {trend && (
                <span className={`text-xs font-bold px-2 py-1 rounded-lg ${trend > 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                    {trend > 0 ? '+' : ''}{trend}%
                </span>
            )}
        </div>

        <div className="relative z-10">
            <h4 className="text-slate-400 font-medium text-sm mb-1">{title}</h4>
            <div className="text-3xl font-black text-slate-100 tracking-tight">{value}</div>
            {subtitle && <p className="text-slate-500 text-xs mt-2">{subtitle}</p>}
        </div>
    </div>
);

const FunnelStage = ({ label, count, percentage, color, isLast }) => (
    <div className="flex flex-col items-center">
        <div className={`w-full max-w-[200px] h-20 rounded-xl border-2 flex flex-col items-center justify-center transition-all shadow-lg
            ${color === 'blue' ? 'bg-blue-900/20 border-blue-500/30 text-blue-400' : ''}
            ${color === 'emerald' ? 'bg-emerald-900/20 border-emerald-500/30 text-emerald-400' : ''}
            ${color === 'purple' ? 'bg-purple-900/20 border-purple-500/30 text-purple-400' : ''}
            ${color === 'slate' ? 'bg-slate-800/50 border-slate-700 text-slate-400' : ''}
        `}>
            <span className="text-2xl font-black">{count}</span>
            <span className="text-[10px] uppercase tracking-widest font-bold opacity-80">{label}</span>
        </div>
        {!isLast && (
            <div className="flex flex-col items-center my-2">
                <span className="text-xs font-mono text-slate-500 mb-1">{percentage}%</span>
                <ChevronRight size={16} className="text-slate-600 rotate-90" />
            </div>
        )}
    </div>
);

const SELL_SPEED_COLORS = ['#10b981', '#34d399', '#6ee7b7', '#a7f3d0', '#d1fae5', '#f0fdf4'];

// Seuils Cohen pour qualifier |r| (corrélation de Pearson) en mots — convention usuelle,
// pas un choix arbitraire. Voir liquidityCorrelation ci-dessous pour le calcul.
const correlationStrength = (r) => {
    const abs = Math.abs(r);
    if (abs < 0.1) return 'négligeable';
    if (abs < 0.3) return 'faible';
    if (abs < 0.5) return 'modérée';
    if (abs < 0.7) return 'forte';
    return 'très forte';
};

const PRICE_BUCKETS = [
    { label: '0-250$', min: 0, max: 250 },
    { label: '250-500$', min: 250, max: 500 },
    { label: '500-1000$', min: 500, max: 1000 },
    { label: '1000-2000$', min: 1000, max: 2000 },
    { label: '2000$+', min: 2000, max: Infinity },
];

const CATEGORY_LABELS = {
    'guitare.electrique': 'Guitare Électrique',
    'guitare.acoustique_acier': 'Guitare Acoustique',
    'guitare.electro_acoustique': 'Guitare Électro-Acoustique',
    'guitare.classique_nylon': 'Guitare Classique',
    'guitare.basse': 'Basse',
    'amplificateur.lampes': 'Ampli à Lampes',
    'amplificateur.transistor_numerique': 'Ampli Transistor/Num.',
    'etui_housse': 'Étui / Housse',
};

// Résolution déléguée au module partagé (`utils/taxonomy.js`) depuis le 2026-08-16 : la copie
// locale normalisait le chemin en supprimant les points, si bien que "guitare.electrique"
// (l'instrument) et "Guitare Electrique" (une feuille d'ÉTUI) produisaient la même clé — le bug
// corrigé partout ailleurs survivait ici, et la canonicalisation des classifications l'a même
// aggravé en généralisant les chemins complets en base.
const resolveCategoryLabel = (classification) => {
    if (!classification) return null;
    const { segments: path } = resolveClassification(classification);
    if (!path || path.length === 0) return null;
    if (path[0] === 'etui_housse') return CATEGORY_LABELS['etui_housse'];
    const key = path.length >= 2 ? `${path[0]}.${path[1]}` : path[0];
    return CATEGORY_LABELS[key] || (path[0] === 'guitare' ? 'Autre Guitare' : path[0]);
};

const StatsView = ({ deals, allDeals, loadedDeals = {} }) => {

    // ─── Jeu de données unique : l'inventaire complet, jamais l'onglet actif ──
    // Les stats sont des statistiques générales de marché — elles ne doivent pas dépendre du
    // filtre/onglet actuellement sélectionné dans le Dashboard (2026-08-06, retour utilisateur :
    // "trop cher"/"rejetées"/etc. disparaissaient des stats selon l'onglet "Toutes" actif).
    // `allDeals` (inventaire complet, toujours fourni par Dashboard.jsx) prime sur `deals` (onglet
    // filtré, gardé en repli défensif uniquement). Fusionné avec `loadedDeals` (cache des documents
    // complets) uniquement pour les champs qui n'existent pas dans l'index léger (ex: reasoning) —
    // tous les scores IA et champs utilisés ci-dessous sont désormais indexés (voir
    // repository.py::_update_deal_index), donc disponibles même pour un deal jamais ouvert.
    const analysisDeals = useMemo(() => {
        const source = allDeals || deals;
        return source.map(d => {
            const full = loadedDeals[d.id];
            return full ? { ...d, ...full } : d;
        });
    }, [allDeals, deals, loadedDeals]);

    const totalDeals = analysisDeals.length;

    const radarDeals = analysisDeals.filter(d => ['PEPITE', 'FAST_FLIP', 'LUTHIER_PROJ', 'CASE_WIN', 'GOOD_DEAL'].includes(d.aiAnalysis?.verdict));
    const marketDeals = analysisDeals.filter(d => ['COLLECTION', 'BAD_DEAL', 'FAIR'].includes(d.aiAnalysis?.verdict));

    // Funnel réel dérivé de aiAnalysis.model_used
    const chainTokens = (used) => (typeof used === 'string' && used.trim()) ? used.split('->').map(s => s.trim()).filter(Boolean) : [];
    const modelChainTokens = (deal) => chainTokens(deal.aiAnalysis?.model_used);
    const reachedT2Count = analysisDeals.filter(d => modelChainTokens(d).length >= 2).length;
    const reachedT3Count = analysisDeals.filter(d => modelChainTokens(d).some(m => m.toLowerCase().includes('pro'))).length;

    // Qualité Portier
    const portierRejectedDeals = analysisDeals.filter(d => chainTokens(d.initialModelUsed).length === 1);
    const portierErrorsCorrected = portierRejectedDeals.filter(d => modelChainTokens(d).length >= 2);
    const portierErrorRate = portierRejectedDeals.length > 0
        ? Math.round((portierErrorsCorrected.length / portierRejectedDeals.length) * 100)
        : 0;

    // Financials
    let totalPotentialMargin = 0;
    let totalEstimatedValue = 0;
    let validMarginsCount = 0;

    radarDeals.forEach(deal => {
        const estValue = deal.aiAnalysis?.estimated_value ?? deal.aiAnalysis?.estimated_guitar_value ?? null;
        const price = deal.price ?? null;
        const computedMargin = (estValue != null && price != null) ? Math.round(estValue - price) : null;
        const margin = deal.aiAnalysis?.estimated_gross_margin !== undefined ? deal.aiAnalysis.estimated_gross_margin : computedMargin;

        if (margin && margin > 0) {
            totalPotentialMargin += margin;
            validMarginsCount++;
        }
        if (estValue) totalEstimatedValue += estValue;
    });

    const averageMargin = validMarginsCount > 0 ? Math.round(totalPotentialMargin / validMarginsCount) : 0;
    // Moyenne sur les annonces réellement analysées (deal_score renseigné), pas sur l'inventaire
    // complet (2026-08-12, bug confirmé) : diviser par totalDeals inclut les milliers d'annonces
    // rejetées au Portier seul (jamais scorées par l'Analyste), diluant la moyenne vers 0.
    const scoredDeals = analysisDeals.filter(d => d.aiAnalysis?.deal_score != null);
    const averageScore = scoredDeals.length > 0
        ? Math.round(scoredDeals.reduce((acc, d) => acc + d.aiAnalysis.deal_score * 10, 0) / scoredDeals.length)
        : 0;

    // ─── Temps de vente réel ──────────────────────────────────────────────
    // `> publishTimestamp` (pas juste la présence des deux) : exclut les paires de timestamps
    // incohérentes (vente antérieure à la publication — erreur de données ponctuelle) plutôt que
    // de laisser un delta négatif fausser la moyenne, surtout visible sur les petits échantillons
    // (croisements par tranche ci-dessous).
    const sellTimeStats = useMemo(() => {
        const soldDeals = analysisDeals.filter(d =>
            d.soldTimestamp?.seconds && d.publishTimestamp?.seconds && d.soldTimestamp.seconds > d.publishTimestamp.seconds
        );
        if (soldDeals.length === 0) return { avg: null, count: 0 };

        const deltas = soldDeals.map(d => {
            const diffH = (d.soldTimestamp.seconds - d.publishTimestamp.seconds) / 3600;
            return diffH;
        });

        const avg = deltas.reduce((a, b) => a + b, 0) / deltas.length;
        return {
            avg: avg < 24 ? `${Math.round(avg)}h` : `${Math.round(avg / 24)}j`,
            count: soldDeals.length,
        };
    }, [analysisDeals]);

    // ─── Radar Chart : profil moyen IA ─────────────────────────────────────
    // Scores individuels tous indexés (2026-08-06) : plus besoin d'avoir chargé le document complet
    // d'une annonce pour que son profil compte ici — voir useDealsManager.js.
    const radarData = useMemo(() => {
        if (totalDeals === 0) return [];
        let rData = { deal: 0, auth: 0, cond: 0, liq: 0, resto: 0, count: 0 };
        analysisDeals.forEach(d => {
            const ai = d.aiAnalysis;
            if (ai && ai.deal_score != null) {
                rData.deal += ai.deal_score;
                rData.auth += ai.authenticity_score ?? 0;
                rData.cond += ai.condition_score ?? 0;
                rData.liq += ai.liquidity_score ?? 0;
                rData.resto += ai.restoration_interest_score ?? 0;
                rData.count++;
            }
        });
        const c = rData.count || 1;
        return [
            { subject: 'Attractivité', A: Math.round((rData.deal / c) * 10), fullMark: 100 },
            { subject: 'Authenticité', A: Math.round((rData.auth / c) * 10), fullMark: 100 },
            { subject: 'État', A: Math.round((rData.cond / c) * 10), fullMark: 100 },
            { subject: 'Liquidité', A: Math.round((rData.liq / c) * 10), fullMark: 100 },
            { subject: 'Potentiel Resto.', A: Math.round((rData.resto / c) * 10), fullMark: 100 },
        ];
    }, [analysisDeals, totalDeals]);

    const radarHasData = radarData.some(d => d.A > 0);

    // ─── Distribution par marque (source : aiAnalysis.brand) ──────────────
    const brandData = useMemo(() => {
        if (totalDeals === 0) return [];
        const counts = {};

        // Marques connues dans le marché QC — fallback titre si brand absente
        const KNOWN_BRANDS = [
            'fender', 'gibson', 'epiphone', 'ibanez', 'squier', 'yamaha',
            'taylor', 'martin', 'guild', 'norman', 'seagull', 'art&lutherie',
            'simon&patrick', 'godin', 'parkwood', 'gretsch', 'prs', 'esp',
            'jackson', 'schecter', 'washburn', 'ovation', 'takamine', 'breedlove',
        ];

        analysisDeals.forEach(d => {
            let rawBrand = d.aiAnalysis?.brand;

            // Invalider les valeurs génériques
            const isInvalidBrand = !rawBrand
                || typeof rawBrand !== 'string'
                || rawBrand.length < 2
                || rawBrand.toLowerCase().includes('inconnue')
                || rawBrand.toLowerCase().includes('unknown')
                || rawBrand.toLowerCase().includes('n/a')
                || rawBrand.toLowerCase() === 'autre'
                || rawBrand.toLowerCase() === 'autres';

            if (isInvalidBrand) {
                // Fallback : recherche dans le titre parmi les marques connues
                const title = (d.title || '').toLowerCase();
                const found = KNOWN_BRANDS.find(b => title.includes(b));
                if (found) {
                    // Capitaliser proprement
                    rawBrand = found.charAt(0).toUpperCase() + found.slice(1);
                    // Cas spéciaux
                    if (found === 'art&lutherie') rawBrand = 'Art&Lutherie';
                    if (found === 'simon&patrick') rawBrand = 'Simon&Patrick';
                } else {
                    counts['Autres'] = (counts['Autres'] || 0) + 1;
                    return;
                }
            }

            // Normaliser : premier mot, uniquement alpha (évite "Fender USA" → "Fender")
            const cleanBrand = rawBrand.split(' ')[0].replace(/[^a-zA-Z&]/g, '');
            if (cleanBrand.length > 1) {
                counts[cleanBrand] = (counts[cleanBrand] || 0) + 1;
            } else {
                counts['Autres'] = (counts['Autres'] || 0) + 1;
            }
        });

        // Top 6 hors "Autres", puis on ajoute Autres si significatif
        const sorted = Object.entries(counts)
            .filter(([name]) => name !== 'Autres')
            .map(([name, count]) => ({ name, count }))
            .sort((a, b) => b.count - a.count)
            .slice(0, 6);

        const autresCount = counts['Autres'] || 0;
        if (autresCount > 0) sorted.push({ name: 'Autres', count: autresCount });

        return sorted;
    }, [analysisDeals, totalDeals]);

    // ─── Distribution par couleur/finition (source : aiAnalysis.color) ────
    const colorData = useMemo(() => {
        if (totalDeals === 0) return [];
        const counts = {};

        analysisDeals.forEach(d => {
            const rawColor = d.aiAnalysis?.color;
            const isInvalid = !rawColor
                || typeof rawColor !== 'string'
                || rawColor.trim().length < 2
                || rawColor.toLowerCase().includes('inconnue')
                || rawColor.toLowerCase().includes('unknown')
                || rawColor.toLowerCase() === 'n/a';
            if (isInvalid) return;

            const cleanColor = rawColor.trim();
            counts[cleanColor] = (counts[cleanColor] || 0) + 1;
        });

        return Object.entries(counts)
            .map(([name, count]) => ({ name, count }))
            .sort((a, b) => b.count - a.count)
            .slice(0, 8);
    }, [analysisDeals, totalDeals]);

    // ─── Volume de scraping quotidien (fenêtre glissante) ─────────────────
    const VOLUME_WINDOW_DAYS = 14;
    const dailyVolumeData = useMemo(() => {
        const days = [];
        const now = new Date();
        for (let i = VOLUME_WINDOW_DAYS - 1; i >= 0; i--) {
            const d = new Date(now);
            d.setDate(d.getDate() - i);
            days.push(d);
        }
        const counts = {};
        days.forEach(d => { counts[d.toISOString().slice(0, 10)] = 0; });

        analysisDeals.forEach(deal => {
            const seconds = deal.timestamp?.seconds;
            if (!seconds) return;
            const key = new Date(seconds * 1000).toISOString().slice(0, 10);
            if (key in counts) counts[key]++;
        });

        return days.map(d => {
            const key = d.toISOString().slice(0, 10);
            return {
                date: d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' }),
                count: counts[key],
            };
        });
    }, [analysisDeals]);

    const avgDailyVolume = useMemo(() => {
        if (dailyVolumeData.length === 0) return '0';
        const total = dailyVolumeData.reduce((acc, d) => acc + d.count, 0);
        return (total / dailyVolumeData.length).toFixed(1);
    }, [dailyVolumeData]);

    // ─── Vitesse de vente par type de guitare ─────────────────────────────
    const sellSpeedByType = useMemo(() => {
        // Deals vendus avec les deux timestamps (cohérents — vente après publication)
        const soldDeals = analysisDeals.filter(d =>
            d.soldTimestamp?.seconds &&
            d.publishTimestamp?.seconds &&
            d.soldTimestamp.seconds > d.publishTimestamp.seconds &&
            d.aiAnalysis?.classification
        );
        if (soldDeals.length < 2) return [];

        const byType = {};
        soldDeals.forEach(d => {
            // formatClassificationLabel plutôt qu'un découpage manuel : avec les chemins complets
            // désormais stockés ("guitare.electrique.solid_body.Double_Cut.SG"), un split(' ')
            // affichait le chemin technique entier — ou un mot isolé ("Paul" pour "Les Paul").
            const label = formatClassificationLabel(d.aiAnalysis.classification) || 'Inconnue';
            const diffH = (d.soldTimestamp.seconds - d.publishTimestamp.seconds) / 3600;
            if (!byType[label]) byType[label] = [];
            byType[label].push(diffH);
        });

        return Object.entries(byType)
            .map(([name, deltas]) => ({
                name,
                avgH: Math.round(deltas.reduce((a, b) => a + b, 0) / deltas.length),
                count: deltas.length,
            }))
            .filter(e => e.count >= 2) // Au moins 2 observations
            .sort((a, b) => a.avgH - b.avgH); // Plus rapide en premier
    }, [analysisDeals]);

    // ─── Sweet Spot : score IA moyen et marge moyenne par tranche de prix ─
    const priceScoreData = useMemo(() => {
        const buckets = PRICE_BUCKETS.map(b => ({ ...b, scoreSum: 0, scoreCount: 0, marginSum: 0, marginCount: 0, count: 0 }));
        analysisDeals.forEach(d => {
            const price = d.price;
            if (!(price > 0)) return;
            const bucket = buckets.find(b => price >= b.min && price < b.max);
            if (!bucket) return;
            bucket.count++;
            const score = d.interestScore ?? d.aiAnalysis?.deal_score;
            if (typeof score === 'number') {
                bucket.scoreSum += score;
                bucket.scoreCount++;
            }
            const margin = d.aiAnalysis?.estimated_gross_margin;
            if (typeof margin === 'number') {
                bucket.marginSum += margin;
                bucket.marginCount++;
            }
        });
        return buckets
            // Au moins une annonce avec un score dans la tranche — sinon la barre serait un 0
            // trompeur (aucune donnée) plutôt qu'une vraie moyenne.
            .filter(b => b.scoreCount > 0)
            .map(b => ({
                name: `${b.label} (${b.scoreCount})`,
                count: b.count,
                scoreCount: b.scoreCount,
                avgScore: Math.round((b.scoreSum / b.scoreCount) * 10),
                avgMargin: b.marginCount > 0 ? Math.round(b.marginSum / b.marginCount) : 0,
            }));
    }, [analysisDeals]);
    const priceScoreTotal = priceScoreData.reduce((sum, b) => sum + b.scoreCount, 0);

    // ─── Marge moyenne par catégorie (taxonomie résolue via resolveCategoryLabel) ─
    const categoryData = useMemo(() => {
        const buckets = {};
        analysisDeals.forEach(d => {
            const label = resolveCategoryLabel(d.aiAnalysis?.classification);
            if (!label) return;
            if (!buckets[label]) buckets[label] = { count: 0, scoreSum: 0, scoreCount: 0, marginSum: 0, marginCount: 0 };
            const b = buckets[label];
            b.count++;
            const score = d.interestScore ?? d.aiAnalysis?.deal_score;
            if (typeof score === 'number') { b.scoreSum += score; b.scoreCount++; }
            const margin = d.aiAnalysis?.estimated_gross_margin;
            if (typeof margin === 'number') { b.marginSum += margin; b.marginCount++; }
        });
        return Object.entries(buckets)
            .map(([name, b]) => ({
                name,
                count: b.count,
                avgScore: b.scoreCount > 0 ? Math.round((b.scoreSum / b.scoreCount) * 10) : 0,
                avgMargin: b.marginCount > 0 ? Math.round(b.marginSum / b.marginCount) : 0,
            }))
            .filter(b => b.count >= 2) // Au moins 2 observations
            .sort((a, b) => b.avgMargin - a.avgMargin);
    }, [analysisDeals]);

    // ─── Véracité IA : score initial des annonces réellement vendues vs l'ensemble ─
    const aiAccuracyData = useMemo(() => {
        const HIGH_SCORE_THRESHOLD = 7;
        const withScore = analysisDeals.filter(d => typeof (d.interestScore ?? d.aiAnalysis?.deal_score) === 'number');
        const soldWithScore = withScore.filter(d => d.status === 'sold');
        if (soldWithScore.length === 0) return null;

        const highScoreRate = (list) => {
            if (list.length === 0) return 0;
            const high = list.filter(d => (d.interestScore ?? d.aiAnalysis?.deal_score) >= HIGH_SCORE_THRESHOLD).length;
            return Math.round((high / list.length) * 100);
        };

        return {
            soldCount: soldWithScore.length,
            marketCount: withScore.length,
            data: [
                { name: `Vendues (${soldWithScore.length})`, rate: highScoreRate(soldWithScore) },
                { name: `Ensemble (${withScore.length})`, rate: highScoreRate(withScore) },
            ],
        };
    }, [analysisDeals]);

    // ─── Facebook vs Kijiji (source dérivée du préfixe `kijiji_` de l'ID, même convention que le backend) ─
    const sourceComparisonData = useMemo(() => {
        const bySource = {
            Facebook: { count: 0, priceSum: 0, priceCount: 0, marginSum: 0, marginCount: 0, opportunityCount: 0 },
            Kijiji: { count: 0, priceSum: 0, priceCount: 0, marginSum: 0, marginCount: 0, opportunityCount: 0 },
        };
        analysisDeals.forEach(d => {
            const source = d.id?.startsWith('kijiji_') ? 'Kijiji' : 'Facebook';
            const b = bySource[source];
            b.count++;
            if (typeof d.price === 'number' && d.price > 0) { b.priceSum += d.price; b.priceCount++; }
            const margin = d.aiAnalysis?.estimated_gross_margin;
            if (typeof margin === 'number') { b.marginSum += margin; b.marginCount++; }
            if (RADAR_GROUP.includes(d.aiAnalysis?.verdict)) b.opportunityCount++;
        });
        return Object.entries(bySource)
            .map(([name, b]) => ({
                name,
                count: b.count,
                avgPrice: b.priceCount > 0 ? Math.round(b.priceSum / b.priceCount) : 0,
                avgMargin: b.marginCount > 0 ? Math.round(b.marginSum / b.marginCount) : 0,
                opportunityRate: b.count > 0 ? Math.round((b.opportunityCount / b.count) * 100) : 0,
            }))
            .filter(s => s.count > 0);
    }, [analysisDeals]);

    // ─── Géographie des opportunités : volume + marge moyenne par ville ───
    // Regroupement par CLÉ canonique de ville, pas par chaîne brute : Facebook stocke
    // "Montréal, QC" pendant que Kijiji écrivait "montreal" (la clé de la ville configurée) —
    // la même ville apparaissait donc en double dans ce graphique. Le libellé affiché est la
    // graphie la plus riche rencontrée (région + accents), voir `utils/cities.js`.
    const geoOpportunityData = useMemo(() => {
        const byCity = {};
        analysisDeals.forEach(d => {
            if (!RADAR_GROUP.includes(d.aiAnalysis?.verdict)) return;
            const key = normalizeCityKey(d.location) || 'inconnue';
            if (!byCity[key]) byCity[key] = { count: 0, marginSum: 0, marginCount: 0, labels: [] };
            byCity[key].count++;
            if (d.location) byCity[key].labels.push(d.location);
            const margin = d.aiAnalysis?.estimated_gross_margin;
            if (typeof margin === 'number') { byCity[key].marginSum += margin; byCity[key].marginCount++; }
        });
        return Object.entries(byCity)
            .map(([key, b]) => ({
                name: pickBestLabel(b.labels) || (key === 'inconnue' ? 'Inconnue' : key),
                count: b.count,
                avgMargin: b.marginCount > 0 ? Math.round(b.marginSum / b.marginCount) : 0,
            }))
            .sort((a, b) => b.count - a.count)
            .slice(0, 8);
    }, [analysisDeals]);

    // ─── Score de liquidité prédit vs délai de vente réel ──────────────────
    // Valide (ou pas) la prédiction de liquidité de l'IA contre le délai de vente réellement
    // observé — score désormais indexé (voir repository.py::_update_deal_index), donc calculé sur
    // l'inventaire complet plutôt que sur le seul sous-ensemble déjà chargé en entier.
    //
    // ⚠️ Ancienne version (jusqu'au 2026-08-17) : regroupait les ventes en 3 tranches fixes
    // (Faible/Moyenne/Élevée) puis traçait la MOYENNE du score IA au sein de chaque tranche comme
    // "prédiction" — une droite quasi garantie par construction, puisque ces tranches sont elles-
    // mêmes définies par ce même score. Peu importe la vraie relation entre score et vitesse de
    // vente, la courbe "prédite" grimpait presque toujours en ligne droite (remarqué par
    // l'utilisateur — "les résultats prédits par l'IA forment une droite, c'est très suspect").
    // Remplacé par un nuage de points sur les valeurs individuelles (un point = une vente) et un
    // coefficient de corrélation de Pearson calculé sur ces valeurs brutes — un test honnête de
    // la relation, qui ne peut pas produire une droite par simple artefact de calcul.
    const liquidityCorrelation = useMemo(() => {
        const points = analysisDeals
            .filter(d =>
                d.soldTimestamp?.seconds &&
                d.publishTimestamp?.seconds &&
                d.soldTimestamp.seconds > d.publishTimestamp.seconds &&
                typeof d.aiAnalysis?.liquidity_score === 'number'
            )
            .map(d => ({
                x: d.aiAnalysis.liquidity_score,
                y: (d.soldTimestamp.seconds - d.publishTimestamp.seconds) / 86400, // jours
            }));

        const n = points.length;
        if (n < 3) return { points, r: null, trend: [], n };

        const meanX = points.reduce((a, p) => a + p.x, 0) / n;
        const meanY = points.reduce((a, p) => a + p.y, 0) / n;
        let covXY = 0, varX = 0, varY = 0;
        points.forEach(p => {
            const dx = p.x - meanX, dy = p.y - meanY;
            covXY += dx * dy;
            varX += dx * dx;
            varY += dy * dy;
        });

        // Variance nulle sur un axe (ex: tous les scores identiques) : la corrélation est
        // mathématiquement indéfinie, pas "nulle" — distinct de r=0 (aucune relation détectée).
        if (varX === 0 || varY === 0) return { points, r: null, trend: [], n };

        const r = covXY / Math.sqrt(varX * varY);
        const slope = covXY / varX;
        const intercept = meanY - slope * meanX;
        const trend = [{ x: 0, y: intercept }, { x: 10, y: intercept + slope * 10 }];

        return { points, r, trend, n };
    }, [analysisDeals]);

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">

            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                        <BarChart2 className="text-blue-500" />
                        Intelligence Stratégique
                    </h2>
                    <p className="text-slate-400 text-sm mt-1">Statistiques calculées sur l'inventaire complet : {totalDeals} annonce{totalDeals !== 1 ? 's' : ''}, tous statuts confondus.</p>
                </div>
                <div className="bg-purple-500/10 border border-purple-500/30 text-purple-400 px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-2">
                    <Activity size={14} className="animate-pulse" />
                    Market Insights
                </div>
            </div>

            {/* Financial KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                    title="Marge Nette Latente"
                    value={`${totalPotentialMargin}$`}
                    subtitle="Cumul des annonces Radar"
                    icon={DollarSign}
                    colorClass="from-emerald-500 to-teal-500"
                    trend={12}
                />
                <StatCard
                    title="Marge Moy. / Pépite"
                    value={`${averageMargin}$`}
                    subtitle="Profit estimé par deal"
                    icon={Target}
                    colorClass="from-blue-500 to-indigo-500"
                />
                <StatCard
                    title="Score IA Moyen"
                    value={`${averageScore}/100`}
                    subtitle="Confiance globale des analyses"
                    icon={CheckCircle2}
                    colorClass="from-purple-500 to-pink-500"
                />
                <StatCard
                    title="Temps de Vente Moy."
                    value={sellTimeStats.avg ?? 'N/A'}
                    subtitle={sellTimeStats.count > 0
                        ? `Sur ${sellTimeStats.count} deal${sellTimeStats.count > 1 ? 's' : ''} vendus tracés`
                        : 'Aucun deal avec soldAt + publishAt'}
                    icon={Clock}
                    colorClass="from-amber-500 to-orange-500"
                />
            </div>

            {/* Funnel & Market Health */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Funnel */}
                <div className="lg:col-span-1 bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-inner">
                    <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-6 flex items-center gap-2">
                        <Activity size={16} className="text-slate-500" />
                        Funnel d'Analyse (Tiers)
                    </h3>

                    <div className="flex flex-col items-center space-y-2 pt-4">
                        <FunnelStage label="Analysé (Portier T1)" count={totalDeals} percentage={100} color="blue" />
                        <FunnelStage label="Qualifié (Analyste T2)" count={reachedT2Count} percentage={totalDeals > 0 ? Math.round((reachedT2Count / totalDeals) * 100) : 0} color="emerald" />
                        <FunnelStage label="Certifié (Expert T3)" count={reachedT3Count} percentage={reachedT2Count > 0 ? Math.round((reachedT3Count / reachedT2Count) * 100) : 0} color="purple" isLast={true} />
                    </div>

                    {/* Qualité Portier */}
                    <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-slate-400 text-xs">
                            <AlertTriangle size={14} className="text-amber-500" />
                            Erreurs Portier corrigées
                        </div>
                        <div className="text-sm font-bold text-slate-200">
                            {portierErrorsCorrected.length}/{portierRejectedDeals.length}
                            <span className="text-slate-500 font-normal ml-1">({portierErrorRate}%)</span>
                        </div>
                    </div>
                </div>

                {/* Charts */}
                <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6">

                    {/* Radar Chart */}
                    <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 h-[300px] flex flex-col relative overflow-hidden group">
                        <h4 className="font-bold text-slate-300 mb-2 flex items-center justify-between z-10">
                            Profil Moyen (Scores IA)
                        </h4>
                        <div className="flex-1 w-full min-h-0 relative z-10 -ml-4">
                            {radarHasData ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                                        <PolarGrid stroke="#334155" />
                                        <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                                        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                                        <Radar name="Moyenne" dataKey="A" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.3} />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                            itemStyle={{ color: '#c4b5fd' }}
                                        />
                                    </RadarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="flex items-center justify-center h-full text-slate-600 text-sm">Pas encore de scores IA disponibles</div>
                            )}
                        </div>
                    </div>

                    {/* Bar Chart - Brand Distribution */}
                    <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 h-[300px] flex flex-col relative overflow-hidden group">
                        <h4 className="font-bold text-slate-300 mb-2 flex items-center justify-between z-10">
                            Distribution (Top Marques)
                        </h4>
                        <div className="flex-1 w-full min-h-0 relative z-10">
                            {brandData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={brandData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#1e293b" />
                                        <XAxis type="number" hide />
                                        <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 11 }} width={75} />
                                        <Tooltip
                                            cursor={{ fill: '#1e293b' }}
                                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                            itemStyle={{ color: '#38bdf8' }}
                                        />
                                        <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={18}>
                                            {brandData.map((entry, index) => (
                                                <Cell
                                                    key={`brand-${index}`}
                                                    fill={entry.name === 'Autres' ? '#334155' : '#38bdf8'}
                                                    fillOpacity={entry.name === 'Autres' ? 0.5 : 1}
                                                />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="flex items-center justify-center h-full text-slate-600 text-sm">Pas assez de données</div>
                            )}
                        </div>
                    </div>

                    {/* Bar Chart - Color Distribution */}
                    <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 h-[300px] flex flex-col relative overflow-hidden group">
                        <h4 className="font-bold text-slate-300 mb-2 flex items-center justify-between z-10">
                            Distribution (Couleurs / Finitions)
                        </h4>
                        <div className="flex-1 w-full min-h-0 relative z-10">
                            {colorData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={colorData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#1e293b" />
                                        <XAxis type="number" hide />
                                        <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 11 }} width={95} />
                                        <Tooltip
                                            cursor={{ fill: '#1e293b' }}
                                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                            itemStyle={{ color: '#f472b6' }}
                                        />
                                        <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={16} fill="#f472b6" />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="flex items-center justify-center h-full text-slate-600 text-sm">Pas assez de données</div>
                            )}
                        </div>
                    </div>

                </div>
            </div>

            {/* Volume de scraping quotidien */}
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
                <div className="flex items-center justify-between mb-1">
                    <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest flex items-center gap-2">
                        <TrendingUp size={16} className="text-blue-400" />
                        Volume de Scraping Quotidien (FB)
                    </h3>
                    <span className="text-xs font-bold text-slate-400">Moy. {avgDailyVolume}/jour</span>
                </div>
                <p className="text-slate-500 text-xs mb-6">Annonces découvertes par jour · {VOLUME_WINDOW_DAYS} derniers jours</p>

                <div className="h-[200px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={dailyVolumeData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                            <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                            <YAxis allowDecimals={false} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                            <Tooltip
                                cursor={{ fill: '#1e293b' }}
                                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                itemStyle={{ color: '#38bdf8' }}
                                formatter={(value) => [value, 'Annonces']}
                            />
                            <Bar dataKey="count" fill="#38bdf8" radius={[4, 4, 0, 0]} barSize={20} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Sell Speed by Guitar Type */}
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
                <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-1 flex items-center gap-2">
                    <Zap size={16} className="text-amber-400" />
                    Vitesse de vente par type de guitare
                </h3>
                <p className="text-slate-500 text-xs mb-6">Délai moyen entre publication et vente</p>

                {sellSpeedByType.length > 0 ? (
                    <div className="h-[220px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={sellSpeedByType} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                                <YAxis
                                    tick={{ fill: '#64748b', fontSize: 10 }}
                                    axisLine={false}
                                    tickLine={false}
                                    tickFormatter={v => v < 24 ? `${v}h` : `${Math.round(v / 24)}j`}
                                />
                                <Tooltip
                                    cursor={{ fill: '#1e293b' }}
                                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                    formatter={(value, name) => [
                                        value < 24 ? `${value}h` : `${Math.round(value / 24)}j`,
                                        `Délai moy. (${sellSpeedByType.find(d => d.avgH === value)?.count ?? ''} ventes)`
                                    ]}
                                />
                                <Bar dataKey="avgH" radius={[4, 4, 0, 0]} barSize={32}>
                                    {sellSpeedByType.map((entry, index) => (
                                        <Cell
                                            key={`speed-${index}`}
                                            fill={SELL_SPEED_COLORS[Math.min(index, SELL_SPEED_COLORS.length - 1)]}
                                        />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                ) : (
                    <div className="h-[120px] flex flex-col items-center justify-center text-slate-600 text-sm gap-2 text-center px-4">
                        <TrendingUp size={24} className="opacity-30" />
                        <span>Pas encore assez de deals vendus ayant été classifiés par l'IA</span>
                        <span className="text-xs text-slate-700">Les données s'enrichiront à mesure que de nouvelles ventes scannées trouveront preneur</span>
                    </div>
                )}
            </div>

            {/* Croisements : Sweet Spot Prix x Score & Marge par catégorie */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                {/* Score moyen par tranche de prix */}
                <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
                    <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-1 flex items-center gap-2">
                        <Coins size={16} className="text-emerald-400" />
                        Score moyen par tranche de prix
                    </h3>
                    <p className="text-slate-500 text-xs mb-1">
                        Les annonces les mieux notées par l'IA sont-elles plutôt bon marché ou plus chères ?
                    </p>
                    <p className="text-slate-600 text-[11px] mb-4">
                        Chiffre entre parenthèses = nombre d'annonces analysées dans la tranche.
                        {priceScoreTotal > 0 && priceScoreTotal < 30 && (
                            <span className="text-amber-500"> ⚠️ Seulement {priceScoreTotal} annonces au total — à interpréter avec prudence.</span>
                        )}
                    </p>

                    {priceScoreData.length > 0 ? (
                        <div className="h-[220px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={priceScoreData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                                    <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                                    <Tooltip
                                        cursor={{ fill: '#1e293b' }}
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                        formatter={(value, name, props) => [
                                            `${value}/100`,
                                            `Score moy. sur ${props.payload.scoreCount} annonce${props.payload.scoreCount > 1 ? 's' : ''} (marge moy. ${props.payload.avgMargin}$)`
                                        ]}
                                    />
                                    <Bar dataKey="avgScore" fill="#10b981" radius={[4, 4, 0, 0]} barSize={28} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[120px] flex items-center justify-center text-slate-600 text-sm">Pas assez de données</div>
                    )}
                </div>

                {/* Marge moyenne par catégorie */}
                <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
                    <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-1 flex items-center gap-2">
                        <Layers size={16} className="text-blue-400" />
                        Marge moyenne par catégorie
                    </h3>
                    <p className="text-slate-500 text-xs mb-6">Marge brute estimée par type d'instrument</p>

                    {categoryData.length > 0 ? (
                        <div className="h-[220px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={categoryData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#1e293b" />
                                    <XAxis type="number" hide />
                                    <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 11 }} width={140} />
                                    <Tooltip
                                        cursor={{ fill: '#1e293b' }}
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                        formatter={(value, name, props) => [
                                            `${value}$`,
                                            `Marge moy. (${props.payload.count} annonces, score moy. ${props.payload.avgScore}/100)`
                                        ]}
                                    />
                                    <Bar dataKey="avgMargin" fill="#38bdf8" radius={[0, 4, 4, 0]} barSize={18} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[120px] flex items-center justify-center text-slate-600 text-sm">Pas assez de données</div>
                    )}
                </div>

            </div>

            {/* Croisements : Facebook vs Kijiji & Véracité IA */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                {/* Facebook vs Kijiji */}
                <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
                    <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-1 flex items-center gap-2">
                        <GitCompare size={16} className="text-amber-400" />
                        Facebook vs Kijiji
                    </h3>
                    <p className="text-slate-500 text-xs mb-6">Volume, prix et marge moyens par source</p>

                    {sourceComparisonData.length > 0 ? (
                        <div className="space-y-3">
                            {sourceComparisonData.map(s => (
                                <div key={s.name} className="flex items-center justify-between bg-slate-800/50 border border-slate-700/50 rounded-xl px-4 py-3">
                                    <div>
                                        <div className="text-sm font-bold text-slate-200">{s.name}</div>
                                        <div className="text-xs text-slate-500">{s.count} annonce{s.count > 1 ? 's' : ''} · {s.opportunityRate}% opportunités</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-sm font-bold text-emerald-400">{s.avgMargin}$ marge moy.</div>
                                        <div className="text-xs text-slate-500">{s.avgPrice}$ prix moy.</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="h-[120px] flex items-center justify-center text-slate-600 text-sm">Pas assez de données</div>
                    )}
                </div>

                {/* Véracité IA */}
                <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
                    <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-1 flex items-center gap-2">
                        <ShieldCheck size={16} className="text-purple-400" />
                        Score IA élevé = vendu plus souvent ?
                    </h3>
                    <p className="text-slate-500 text-xs mb-1">
                        Les annonces bien notées par l'IA se vendent-elles vraiment plus souvent que la moyenne du marché ?
                    </p>
                    <p className="text-slate-600 text-[11px] mb-4">
                        {aiAccuracyData?.soldCount > 0
                            ? `Chiffre entre parenthèses = nombre d'annonces derrière chaque barre (${aiAccuracyData.soldCount} vente${aiAccuracyData.soldCount > 1 ? 's' : ''} tracée${aiAccuracyData.soldCount > 1 ? 's' : ''} avec score, sur ${aiAccuracyData.marketCount} au total).`
                            : "Nécessite des annonces vendues avec score IA"}
                        {aiAccuracyData?.soldCount > 0 && aiAccuracyData.soldCount < 20 && (
                            <span className="text-amber-500"> ⚠️ Seulement {aiAccuracyData.soldCount} ventes tracées — à interpréter avec prudence.</span>
                        )}
                    </p>

                    {aiAccuracyData ? (
                        <div className="h-[180px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={aiAccuracyData.data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                                    <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                                    <Tooltip
                                        cursor={{ fill: '#1e293b' }}
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                        formatter={(value) => [`${value}%`, 'Score élevé (≥7/10)']}
                                    />
                                    <Bar dataKey="rate" radius={[4, 4, 0, 0]} barSize={40}>
                                        {aiAccuracyData.data.map((entry, index) => (
                                            <Cell key={`accuracy-${index}`} fill={index === 0 ? '#a78bfa' : '#475569'} />
                                        ))}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[120px] flex items-center justify-center text-slate-600 text-sm">Pas assez de données</div>
                    )}
                </div>

            </div>

            {/* Géographie des opportunités */}
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
                <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-1 flex items-center gap-2">
                    <MapPin size={16} className="text-rose-400" />
                    Géographie des opportunités
                </h3>
                <p className="text-slate-500 text-xs mb-6">Volume de Pépites/Fast Flip/Luthier/Case Win par ville</p>

                {geoOpportunityData.length > 0 ? (
                    <div className="h-[240px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={geoOpportunityData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#1e293b" />
                                <XAxis type="number" hide />
                                <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 11 }} width={110} />
                                <Tooltip
                                    cursor={{ fill: '#1e293b' }}
                                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                    formatter={(value, name, props) => [
                                        `${value} opportunité${value > 1 ? 's' : ''}`,
                                        `Marge moy. ${props.payload.avgMargin}$`
                                    ]}
                                />
                                <Bar dataKey="count" fill="#fb7185" radius={[0, 4, 4, 0]} barSize={18} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                ) : (
                    <div className="h-[120px] flex items-center justify-center text-slate-600 text-sm">Pas assez de données</div>
                )}
            </div>

            {/* Vitesse de vente réelle vs Liquidité prédite par l'IA */}
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6">
                <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest mb-1 flex items-center gap-2">
                    <Zap size={16} className="text-emerald-400" />
                    La liquidité prédite par l'IA se confirme-t-elle ?
                </h3>
                <p className="text-slate-500 text-xs mb-1">
                    Un point = une vente : score de liquidité prédit par l'IA (0-10) en abscisse, délai réel jusqu'à la vente (jours) en ordonnée. La ligne pointillée est la tendance mesurée sur ces points (régression linéaire) — si la prédiction est fiable, elle descend (score élevé → délai court).
                </p>
                <p className="text-slate-600 text-[11px] mb-4">
                    {liquidityCorrelation.n} vente{liquidityCorrelation.n !== 1 ? 's' : ''} tracée{liquidityCorrelation.n !== 1 ? 's' : ''}.
                    {liquidityCorrelation.r !== null && (
                        <> Corrélation {correlationStrength(liquidityCorrelation.r)} (r = {liquidityCorrelation.r.toFixed(2)}){liquidityCorrelation.r < -0.1
                            ? ' — dans le sens attendu : score élevé associé à une vente plus rapide.'
                            : liquidityCorrelation.r > 0.1
                                ? ' — contraire à l\'attendu : score élevé associé à une vente plus LENTE.'
                                : ' — pas de relation détectable entre score et délai.'}</>
                    )}
                    {liquidityCorrelation.n > 0 && liquidityCorrelation.n < 20 && (
                        <span className="text-amber-500"> ⚠️ Échantillon réduit — à interpréter avec prudence.</span>
                    )}
                </p>

                {liquidityCorrelation.n >= 3 ? (
                    <div className="h-[220px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis
                                    type="number" dataKey="x" domain={[0, 10]}
                                    tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false}
                                    label={{ value: 'Score de liquidité prédit', position: 'insideBottom', offset: -5, fill: '#64748b', fontSize: 11 }}
                                />
                                <YAxis
                                    type="number" dataKey="y" domain={[0, 'auto']}
                                    tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false}
                                    label={{ value: 'Délai (jours)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }}
                                />
                                <Tooltip
                                    cursor={{ stroke: '#334155' }}
                                    // Contenu personnalisé plutôt que le rendu par défaut : sur un ComposedChart
                                    // avec un axe X numérique partagé (dataKey="x"), Recharts affiche aussi une
                                    // ligne technique "x : <valeur>" en plus des séries — bruit à masquer.
                                    content={({ active, payload }) => {
                                        if (!active || !payload?.length) return null;
                                        const point = payload[0].payload;
                                        return (
                                            <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '0.5rem', padding: '8px 12px' }}>
                                                <div style={{ color: '#34d399', fontSize: 12 }}>Score prédit : {point.x}/10</div>
                                                <div style={{ color: '#94a3b8', fontSize: 12 }}>Délai réel : {Math.round(point.y * 10) / 10} j</div>
                                            </div>
                                        );
                                    }}
                                />
                                <Scatter
                                    name="Ventes" data={liquidityCorrelation.points} dataKey="y"
                                    fill="#34d399" fillOpacity={0.55} stroke="#0f172a" strokeWidth={1} r={5}
                                />
                                {liquidityCorrelation.trend.length > 0 && (
                                    <Line
                                        name="Tendance" data={liquidityCorrelation.trend} dataKey="y" type="linear"
                                        stroke="#a78bfa" strokeWidth={2} strokeDasharray="6 4" dot={false} legendType="none" isAnimationActive={false}
                                    />
                                )}
                            </ComposedChart>
                        </ResponsiveContainer>
                    </div>
                ) : (
                    <div className="h-[120px] flex items-center justify-center text-slate-600 text-sm">Pas assez de données (au moins 3 ventes avec un score de liquidité connu)</div>
                )}
            </div>

        </div>
    );
};

export default StatsView;
