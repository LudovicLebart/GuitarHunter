import React, { useMemo } from 'react';
import { Target, Activity, DollarSign, Clock, AlertTriangle, ChevronRight, BarChart2, CheckCircle2, XCircle } from 'lucide-react';

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

const MockupStatsView = ({ deals }) => {
    // Basic Calculations based on real data
    const totalDeals = deals.length;
    const radarDeals = deals.filter(d => ['PEPITE', 'FAST_FLIP', 'LUTHIER_PROJ', 'CASE_WIN', 'GOOD_DEAL'].includes(d.aiAnalysis?.verdict));
    const marketDeals = deals.filter(d => ['COLLECTION', 'BAD_DEAL', 'FAIR'].includes(d.aiAnalysis?.verdict));
    const archiveDeals = totalDeals - radarDeals.length - marketDeals.length;

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
                    Mockup Data
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
                        <FunnelStage label="Total Scrappé" count={totalDeals * 4} percentage={100} color="slate" />
                        <FunnelStage label="Passé Portier (T1)" count={totalDeals} percentage={25} color="blue" />
                        <FunnelStage label="Qualifié (T2)" count={radarDeals.length + marketDeals.length} percentage={Math.round(((radarDeals.length + marketDeals.length) / totalDeals) * 100)} color="emerald" />
                        <FunnelStage label="Certifié (T3 Pro)" count={2} percentage={12} color="purple" isLast={true} />
                    </div>
                </div>

                {/* Placeholders for future charts */}
                <div className="lg:col-span-2 space-y-6">

                    <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 h-[250px] flex flex-col justify-center items-center relative overflow-hidden group">
                        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-5 mix-blend-overlay"></div>
                        <AlertTriangle size={32} className="text-slate-600 mb-3" />
                        <h4 className="font-bold text-slate-400">Radar Chart des 5 Scores</h4>
                        <p className="text-xs text-slate-500 text-center mt-2 max-w-sm">Nécessite une librairie comme Recharts pour dessiner le polygone (Authenticité, État, Deal, Liquidation, Restauration).</p>
                    </div>

                    <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 h-[250px] flex flex-col justify-center items-center relative overflow-hidden group">
                        <div className="absolute inset-0 bg-gradient-to-r from-slate-900 via-slate-800/20 to-slate-900"></div>
                        <BarChart2 size={32} className="text-slate-600 mb-3" />
                        <h4 className="font-bold text-slate-400">Distribution par Marque</h4>
                        <p className="text-xs text-slate-500 text-center mt-2 max-w-sm">Sera alimenté une fois que le champ `brand` sera extrait dynamiquement par l'Analyste Gemini.</p>
                    </div>

                </div>
            </div>

        </div>
    );
};

export default MockupStatsView;
