import React, { useState } from 'react';
import { Heart, RefreshCw, XCircle, Trash2, Facebook, Sparkles, MapPin, Gem, Hammer, Briefcase, Package, AlertTriangle, Ban, ChevronDown, ChevronUp } from 'lucide-react';

const VERDICT_CONFIG = {
    PEPITE: { label: 'Pépite', bg: 'bg-yellow-500', text: 'text-yellow-900', icon: Gem },
    FAST_FLIP: { label: 'Fast Flip', bg: 'bg-emerald-500', text: 'text-emerald-900', icon: Sparkles },
    LUTHIER_PROJ: { label: 'Projet Luthier', bg: 'bg-orange-500', text: 'text-orange-900', icon: Hammer },
    CASE_WIN: { label: 'Case Win', bg: 'bg-sky-500', text: 'text-sky-900', icon: Briefcase },
    COLLECTION: { label: 'Collection', bg: 'bg-blue-500', text: 'text-blue-900', icon: Package },
    BAD_DEAL: { label: 'Trop Cher', bg: 'bg-rose-500', text: 'text-rose-900', icon: AlertTriangle },
    DEFAULT: { label: 'Analyse...', bg: 'bg-slate-600', text: 'text-slate-200', icon: RefreshCw },
};

const toTitleCase = (str = '') =>
    str.toLowerCase().split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

const MockupDealCard = ({ deal }) => {
    const [expanded, setExpanded] = useState(false);
    const [liked, setLiked] = useState(false);

    const verdict = deal.verdict || 'DEFAULT';
    const vc = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.DEFAULT;
    const VIcon = vc.icon;

    return (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 flex flex-col overflow-hidden hover:border-slate-600 transition-all duration-300 hover:shadow-2xl hover:shadow-black/40 group">

            {/* Image */}
            <div className="relative w-full aspect-video overflow-hidden">
                <img
                    src={deal.image}
                    alt={deal.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
                {/* Verdict Badge */}
                <div className={`absolute top-3 left-3 ${vc.bg} px-2.5 py-1 rounded-full text-[11px] font-black tracking-wider flex items-center gap-1.5 shadow-lg ${vc.text}`}>
                    <VIcon size={12} />
                    {vc.label}
                </div>
                {/* Price Badge */}
                <div className="absolute top-3 right-3 bg-slate-950/90 backdrop-blur-sm border border-slate-700 text-white px-3 py-1.5 rounded-xl text-base font-black shadow-lg">
                    {deal.price}$
                </div>
            </div>

            {/* Body */}
            <div className="p-4 flex flex-col gap-3 flex-1">

                {/* Title & Location */}
                <div>
                    <h3 className="text-sm font-bold text-white leading-snug line-clamp-2">
                        {toTitleCase(deal.title)}
                    </h3>
                    <div className="flex items-center gap-1.5 mt-1 text-[11px] text-slate-400">
                        <MapPin size={11} />
                        <span>{deal.location}</span>
                        {deal.taxonomy && (
                            <>
                                <span className="text-slate-700">•</span>
                                <span className="text-purple-400">{deal.taxonomy}</span>
                            </>
                        )}
                    </div>
                </div>

                {/* Financial Summary — visible immediately */}
                {deal.margin != null && (
                    <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold px-2.5 py-1 rounded-lg ${deal.margin > 0 ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/15 text-rose-400 border border-rose-500/20'}`}>
                            Marge {deal.margin > 0 ? '+' : ''}{deal.margin}$
                        </span>
                        <span className="text-[11px] text-slate-500">Val. Est. {deal.estValue}$</span>
                    </div>
                )}

                {/* AI Reasoning block — collapsible */}
                {deal.reasoning && (
                    <div className="bg-slate-950 rounded-xl border border-slate-800">
                        <button
                            className="w-full flex items-center justify-between px-3 py-2 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
                            onClick={() => setExpanded(!expanded)}
                        >
                            <span className="flex items-center gap-1.5 font-bold">
                                {/* Hidden model debug — tooltip only */}
                                <span title={`Modèles: ${deal.models || 'N/A'}`} className="cursor-help">✨ Analyse IA</span>
                            </span>
                            <div className="flex items-center gap-2">
                                <div className="flex items-center gap-1.5">
                                    <div className="w-14 h-1 bg-slate-800 rounded-full overflow-hidden">
                                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${deal.confidence || 0}%` }}></div>
                                    </div>
                                    <span className="text-blue-400 font-bold">{deal.confidence}%</span>
                                </div>
                                {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            </div>
                        </button>
                        {expanded && (
                            <p className="px-3 pb-3 text-[11px] text-slate-300 leading-relaxed border-t border-slate-800 pt-2">
                                {deal.reasoning}
                            </p>
                        )}
                    </div>
                )}

                {/* Footer actions */}
                <div className="flex items-center justify-between mt-auto pt-2 border-t border-slate-800/50">
                    <span className="text-[10px] text-slate-600 font-mono flex items-center gap-1">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/60"></div>
                        {deal.date || 'Il y a 15 min'}
                    </span>
                    <div className="flex items-center gap-1">
                        <button onClick={() => setLiked(!liked)} className={`w-9 h-9 flex items-center justify-center rounded-xl border transition-all ${liked ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' : 'bg-slate-800/50 text-slate-500 border-slate-700/50 hover:text-rose-400 hover:bg-rose-500/10'}`} title="Favori">
                            <Heart size={16} fill={liked ? 'currentColor' : 'none'} />
                        </button>
                        <button className="w-9 h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-blue-400 hover:bg-blue-500/10 border border-slate-700/50 transition-all" title="Ré-analyser">
                            <RefreshCw size={16} />
                        </button>
                        <button className="w-9 h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-orange-400 hover:bg-orange-500/10 border border-slate-700/50 transition-all" title="Rejeter">
                            <XCircle size={16} />
                        </button>
                        <button className="w-9 h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-red-400 hover:bg-red-500/10 border border-slate-700/50 transition-all" title="Supprimer">
                            <Trash2 size={16} />
                        </button>
                        <div className="w-px h-5 bg-slate-800 mx-0.5"></div>
                        <button className="w-9 h-9 flex items-center justify-center rounded-xl bg-blue-700 text-white hover:bg-blue-600 border border-blue-600 transition-all" title="Voir sur Facebook">
                            <Facebook size={16} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default MockupDealCard;
