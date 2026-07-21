import React, { useMemo } from 'react';
import { Target, Activity, DollarSign, Clock, AlertTriangle, ChevronRight, BarChart2, CheckCircle2, XCircle, TrendingUp, Zap } from 'lucide-react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell } from 'recharts';

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

// Noms lisibles pour les types de classification
const TYPE_LABELS = {
    'Guitare acoustique': 'Acoustique',
    'Guitare électrique': 'Électrique',
    'Guitare basse': 'Basse',
    'Guitare classique': 'Classique',
    'Guitare folk': 'Folk',
    'Guitare semi-acoustique': 'Semi-Acoustique',
    'Guitare résonateur': 'Résonateur',
    'Ukulélé': 'Ukulélé',
    'Mandoline': 'Mandoline',
    'Pedal Steel': 'Pedal Steel',
};

const SELL_SPEED_COLORS = ['#10b981', '#34d399', '#6ee7b7', '#a7f3d0', '#d1fae5', '#f0fdf4'];

const StatsView = ({ deals, loadedDeals = {} }) => {

    // ─── Merge : index léger + cache complet ───────────────────────────────
    // Pour les stats on fusionne ce qu'on a dans le cache avec l'index.
    // Les deals non encore chargés (lazy) utilisent les champs de l'index.
    const enrichedDeals = useMemo(() => {
        return deals.map(d => {
            const full = loadedDeals[d.id];
            return full ? { ...d, ...full } : d;
        });
    }, [deals, loadedDeals]);

    const totalDeals = enrichedDeals.length;

    const radarDeals = enrichedDeals.filter(d => ['PEPITE', 'FAST_FLIP', 'LUTHIER_PROJ', 'CASE_WIN', 'GOOD_DEAL'].includes(d.aiAnalysis?.verdict));
    const marketDeals = enrichedDeals.filter(d => ['COLLECTION', 'BAD_DEAL', 'FAIR'].includes(d.aiAnalysis?.verdict));

    // Funnel réel dérivé de aiAnalysis.model_used
    const chainTokens = (used) => (typeof used === 'string' && used.trim()) ? used.split('->').map(s => s.trim()).filter(Boolean) : [];
    const modelChainTokens = (deal) => chainTokens(deal.aiAnalysis?.model_used);
    const reachedT2Count = enrichedDeals.filter(d => modelChainTokens(d).length >= 2).length;
    const reachedT3Count = enrichedDeals.filter(d => modelChainTokens(d).some(m => m.toLowerCase().includes('pro'))).length;

    // Qualité Portier
    const portierRejectedDeals = enrichedDeals.filter(d => chainTokens(d.initialModelUsed).length === 1);
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
    const averageScore = Math.round(enrichedDeals.reduce((acc, d) => acc + (d.aiAnalysis?.deal_score != null ? d.aiAnalysis.deal_score * 10 : 0), 0) / (totalDeals || 1));

    // ─── Temps de vente réel ──────────────────────────────────────────────
    const sellTimeStats = useMemo(() => {
        const soldDeals = enrichedDeals.filter(d =>
            d.soldTimestamp?.seconds && d.publishTimestamp?.seconds
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
    }, [enrichedDeals]);

    // ─── Radar Chart : profil moyen IA (utilise enrichedDeals) ────────────
    const radarData = useMemo(() => {
        if (totalDeals === 0) return [];
        let rData = { deal: 0, auth: 0, cond: 0, liq: 0, resto: 0, count: 0 };
        enrichedDeals.forEach(d => {
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
    }, [enrichedDeals, totalDeals]);

    const radarHasData = radarData.some(d => d.A > 0);

    // ─── Distribution par marque (source : aiAnalysis.brand sur enrichedDeals) ─
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

        enrichedDeals.forEach(d => {
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
    }, [enrichedDeals, totalDeals]);

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

        enrichedDeals.forEach(deal => {
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
    }, [enrichedDeals]);

    const avgDailyVolume = useMemo(() => {
        if (dailyVolumeData.length === 0) return '0';
        const total = dailyVolumeData.reduce((acc, d) => acc + d.count, 0);
        return (total / dailyVolumeData.length).toFixed(1);
    }, [dailyVolumeData]);

    // ─── Vitesse de vente par type de guitare ─────────────────────────────
    const sellSpeedByType = useMemo(() => {
        // Deals vendus avec les deux timestamps
        const soldDeals = enrichedDeals.filter(d =>
            d.soldTimestamp?.seconds &&
            d.publishTimestamp?.seconds &&
            d.aiAnalysis?.classification
        );
        if (soldDeals.length < 2) return [];

        const byType = {};
        soldDeals.forEach(d => {
            const classification = d.aiAnalysis.classification;
            const label = TYPE_LABELS[classification] || classification.split(' ').slice(-1)[0];
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
    }, [enrichedDeals]);

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">

            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                        <BarChart2 className="text-blue-500" />
                        Intelligence Stratégique
                    </h2>
                    <p className="text-slate-400 text-sm mt-1">Statistiques calculées sur {totalDeals} annonce{totalDeals !== 1 ? 's' : ''} · {Object.keys(loadedDeals).length} chargées.</p>
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
                            {!radarHasData && <span className="text-[10px] text-amber-400 font-normal">Scroll pour charger les deals</span>}
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
                                <div className="flex items-center justify-center h-full text-slate-600 text-sm">Données en cours de chargement…</div>
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
                <p className="text-slate-500 text-xs mb-6">Délai moyen entre publication et vente · Uniquement les types avec ≥2 observations</p>

                {sellSpeedByType.length >= 2 ? (
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
                    <div className="h-[120px] flex flex-col items-center justify-center text-slate-600 text-sm gap-2">
                        <TrendingUp size={24} className="opacity-30" />
                        <span>Pas encore assez de deals vendus avec timestamp de publication</span>
                        <span className="text-xs text-slate-700">Les données s'enrichiront à mesure que les ventes sont trackées</span>
                    </div>
                )}
            </div>

        </div>
    );
};

export default StatsView;
