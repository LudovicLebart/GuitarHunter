import React, { useMemo } from 'react';
import { Target, Activity, DollarSign, Clock, AlertTriangle, ChevronRight, BarChart2, CheckCircle2, XCircle } from 'lucide-react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

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

const StatsView = ({ deals }) => {
    // Basic Calculations based on real data
    const totalDeals = deals.length;
    const radarDeals = deals.filter(d => ['PEPITE', 'FAST_FLIP', 'LUTHIER_PROJ', 'CASE_WIN', 'GOOD_DEAL'].includes(d.aiAnalysis?.verdict));
    const marketDeals = deals.filter(d => ['COLLECTION', 'BAD_DEAL', 'FAIR'].includes(d.aiAnalysis?.verdict));
    const archiveDeals = totalDeals - radarDeals.length - marketDeals.length;

    // Funnel réel dérivé de aiAnalysis.model_used (ex: "flash-lite -> flash -> pro")
    const chainTokens = (used) => (typeof used === 'string' && used.trim()) ? used.split('->').map(s => s.trim()).filter(Boolean) : [];
    const modelChainTokens = (deal) => chainTokens(deal.aiAnalysis?.model_used);
    // "pro" couvre aussi bien la cascade normale (3 maillons) que les réanalyses "Luthier Expert"
    // forcées qui sautent le Portier (2 maillons : Analyste -> Expert)
    const reachedT2Count = deals.filter(d => modelChainTokens(d).length >= 2).length;
    const reachedT3Count = deals.filter(d => modelChainTokens(d).some(m => m.toLowerCase().includes('pro'))).length;

    // Qualité Portier : annonces initialement arrêtées au Tier 1 seul (chaîne à 1 maillon),
    // puis réanalysées manuellement jusqu'à atteindre l'Analyste ou plus (= rejet initial infirmé).
    // `initialVerdict`/`initialModelUsed` sont figés à la création (backend/repository.py) et ne
    // sont jamais réécrits par les réanalyses suivantes - contrairement à `aiAnalysis` actuel.
    const portierRejectedDeals = deals.filter(d => chainTokens(d.initialModelUsed).length === 1);
    const portierErrorsCorrected = portierRejectedDeals.filter(d => modelChainTokens(d).length >= 2);
    const portierErrorRate = portierRejectedDeals.length > 0
        ? Math.round((portierErrorsCorrected.length / portierRejectedDeals.length) * 100)
        : 0;

    // Financials (Only calculating positive margins from radar deals)
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
    const averageScore = Math.round(deals.reduce((acc, d) => acc + (d.aiAnalysis?.deal_score != null ? d.aiAnalysis.deal_score * 10 : 0), 0) / (totalDeals || 1));

    // Radar Chart Data Calculation (Averages across all deals with scores)
    const radarData = useMemo(() => {
        if (totalDeals === 0) return [];
        let rData = { deal: 0, auth: 0, cond: 0, liq: 0, resto: 0, count: 0 };
        deals.forEach(d => {
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
    }, [deals, totalDeals]);

    // Brand Distribution Data Calculation
    const brandData = useMemo(() => {
        if (totalDeals === 0) return [];
        const counts = {};
        deals.forEach(d => {
            // Priority to the new explicit brand field, fallback to naive text search in title if not available yet (for legacy)
            let rawBrand = d.aiAnalysis?.brand;
            if (!rawBrand || typeof rawBrand !== 'string' || rawBrand.includes('Inconnue') || rawBrand.includes('Unknown')) {
                // Very naive fallback just to have some data if 'brand' is missing in old deals
                const title = (d.title || '').toLowerCase();
                if (title.includes('fender')) rawBrand = 'Fender';
                else if (title.includes('gibson')) rawBrand = 'Gibson';
                else if (title.includes('epiphone')) rawBrand = 'Epiphone';
                else if (title.includes('ibanez')) rawBrand = 'Ibanez';
                else if (title.includes('squier')) rawBrand = 'Squier';
                else if (title.includes('yamaha')) rawBrand = 'Yamaha';
                else rawBrand = 'Autres';
            }

            // Clean up brand name (keep only first word usually to avoid "Fender USA")
            const cleanBrand = rawBrand.split(' ')[0].replace(/[^a-zA-Z]/g, '');
            if (cleanBrand.length > 1) {
                counts[cleanBrand] = (counts[cleanBrand] || 0) + 1;
            } else {
                counts['Autres'] = (counts['Autres'] || 0) + 1;
            }
        });

        // Convert to array and sort by count descending
        return Object.entries(counts)
            .map(([name, count]) => ({ name, count }))
            .sort((a, b) => b.count - a.count)
            .slice(0, 5); // Take top 5
    }, [deals, totalDeals]);

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">

            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                        <BarChart2 className="text-blue-500" />
                        Intelligence Stratégique
                    </h2>
                    <p className="text-slate-400 text-sm mt-1">Vue d'ensemble simulée des performances du marché et de l'IA.</p>
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
                    title="Temps de Vente (Est.)"
                    value="48h"
                    subtitle="Requis: 'soldAt' tracker"
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

                    {/* Qualité Portier : rejets Tier 1 infirmés par une réanalyse manuelle ultérieure */}
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
                            {radarData.length > 0 ? (
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
                                <div className="flex items-center justify-center h-full text-slate-600 text-sm">Pas assez de données</div>
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
                                        <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 11 }} width={70} />
                                        <Tooltip
                                            cursor={{ fill: '#1e293b' }}
                                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '0.5rem' }}
                                            itemStyle={{ color: '#38bdf8' }}
                                        />
                                        <Bar dataKey="count" fill="#38bdf8" radius={[0, 4, 4, 0]} barSize={20} />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="flex items-center justify-center h-full text-slate-600 text-sm">Pas assez de données</div>
                            )}
                        </div>
                    </div>

                </div>
            </div>

        </div>
    );
};

export default StatsView;
