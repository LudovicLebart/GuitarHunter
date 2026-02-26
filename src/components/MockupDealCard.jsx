import React, { useState } from 'react';
import { Heart, RefreshCw, XCircle, Trash2, Facebook, Sparkles, MapPin, Gem, Hammer, Briefcase, Package, AlertTriangle, Ban, ChevronDown, ChevronUp, X, FileText } from 'lucide-react';
import ImageGallery from './ImageGallery';

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
    const [showAnalysisModal, setShowAnalysisModal] = useState(false);
    const [liked, setLiked] = useState(false);

    const verdict = deal.verdict || 'DEFAULT';
    const vc = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.DEFAULT;
    const VIcon = vc.icon;

    return (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 flex flex-col overflow-hidden hover:border-slate-600 transition-all duration-300 hover:shadow-2xl hover:shadow-black/40 group">

            {/* Image Gallery Container */}
            <div className="relative w-full h-[280px] bg-slate-950 overflow-hidden flex items-center justify-center shrink-0">
                <div className="h-full w-full">
                    <ImageGallery images={deal.imageUrls || [deal.image || '']} title={deal.title} />
                </div>

                {/* Verdict Badge */}
                <div className={`absolute top-3 left-3 ${vc.bg} px-2.5 py-1 rounded-full text-[11px] font-black tracking-wider flex items-center gap-1.5 shadow-lg z-10 ${vc.text}`}>
                    <VIcon size={12} />
                    {vc.label}
                </div>
                {/* Price Badge */}
                <div className="absolute top-3 right-3 bg-slate-950/90 backdrop-blur-sm border border-slate-700 text-white px-3 py-1.5 rounded-xl text-base font-black shadow-lg z-10 pointer-events-none">
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

                {/* AI Reasoning button — opens modal */}
                {deal.reasoning && (
                    <div className="bg-slate-950 rounded-xl border border-slate-800 relative z-10 w-full">
                        <button
                            className="w-full h-full flex items-center justify-between px-3 py-2 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
                            onClick={() => setShowAnalysisModal(true)}
                        >
                            <span className="flex items-center gap-1.5 font-bold">
                                <span title={`Modèles: ${deal.models || 'N/A'}`} className="cursor-help flex items-center gap-1.5">
                                    <FileText size={12} className="text-blue-400" /> Analyse IA
                                </span>
                            </span>
                            <div className="flex items-center gap-2">
                                <div className="flex items-center gap-1.5">
                                    <div className="w-14 h-1 bg-slate-800 rounded-full overflow-hidden">
                                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${deal.confidence || 0}%` }}></div>
                                    </div>
                                    <span className="text-blue-400 font-bold">{deal.confidence}%</span>
                                </div>
                                <span className="text-slate-500 font-mono ml-1">Lire</span>
                            </div>
                        </button>
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

            {/* AI Reasoning Full-Screen Modal */}
            {showAnalysisModal && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
                    <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-md cursor-pointer" onClick={() => setShowAnalysisModal(false)}></div>

                    <div className="relative w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-slate-700 rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 pointer-events-auto">
                        {/* Modal Header */}
                        <div className="flex items-center justify-between p-4 sm:p-6 border-b border-slate-800 bg-slate-950/50 shrink-0">
                            <div>
                                <h2 className="text-lg sm:text-xl font-black text-white leading-tight mb-1">
                                    Rapport d'Expertise IA
                                </h2>
                                <h3 className="text-sm text-slate-400 truncate max-w-[200px] sm:max-w-md">
                                    {toTitleCase(deal.title)}
                                </h3>
                            </div>
                            <button
                                onClick={() => setShowAnalysisModal(false)}
                                className="w-10 h-10 flex items-center justify-center bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded-full transition-colors border border-slate-700/50 shrink-0"
                            >
                                <X size={20} />
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div className="flex-1 flex flex-col md:flex-row min-h-0">
                            {/* Left column: Image ref */}
                            <div className="hidden md:flex flex-col w-1/3 bg-slate-950 border-r border-slate-800 p-6 items-center shrink-0 overflow-y-auto scrollbar-dark">
                                <div className="w-full aspect-[4/5] rounded-xl overflow-hidden bg-black mb-6 shadow-inner relative border border-slate-800 shrink-0">
                                    <img
                                        src={deal.imageUrls?.[0] || deal.image}
                                        alt={deal.title}
                                        className="w-full h-full object-contain"
                                    />
                                    {/* Verdict Badge Replica */}
                                    <div className={`absolute top-3 left-3 ${vc.bg} px-2.5 py-1 rounded-full text-xs font-black tracking-wider flex items-center gap-1.5 shadow-lg ${vc.text}`}>
                                        <VIcon size={14} />
                                        {vc.label}
                                    </div>
                                </div>
                                <div className="w-full space-y-4">
                                    <div className="bg-slate-900 rounded-xl p-4 border border-slate-800">
                                        <div className="text-xs text-slate-500 font-bold uppercase mb-1">Prix demandé</div>
                                        <div className="text-2xl font-black text-white">{deal.price}$ <span className="text-sm font-normal text-slate-400 line-through ml-2">{deal.estValue}$</span></div>
                                    </div>

                                    {deal.margin != null && (
                                        <div className={`rounded-xl p-4 border ${deal.margin > 0 ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/20'}`}>
                                            <div className={`text-xs font-bold uppercase mb-1 ${deal.margin > 0 ? 'text-emerald-500/70' : 'text-rose-500/70'}`}>Marge Estimée</div>
                                            <div className={`text-xl font-black ${deal.margin > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{deal.margin > 0 ? '+' : ''}{deal.margin}$</div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Right column: The markdown text */}
                            <div className="flex-1 p-6 sm:p-8 overflow-y-auto scrollbar-dark">
                                <div className="flex items-center gap-4 mb-6 pb-6 border-b border-slate-800/50 shrink-0">
                                    <div className="flex-1">
                                        <div className="text-xs text-slate-500 font-bold uppercase mb-2">Modèles utilisés</div>
                                        <div className="text-sm text-slate-300 font-mono bg-slate-950 px-3 py-1.5 rounded-lg inline-block border border-slate-800">{deal.models || 'Indisponible'}</div>
                                    </div>
                                    <div>
                                        <div className="text-xs text-slate-500 font-bold uppercase mb-2 text-right">Confiance Globale</div>
                                        <div className="flex items-center justify-end gap-3">
                                            <span className="text-2xl font-black text-blue-400">{deal.confidence || 0}%</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="prose prose-invert prose-sm sm:prose-base max-w-none 
                                    prose-p:text-slate-300 prose-p:leading-relaxed
                                    prose-strong:text-white prose-strong:font-bold
                                    prose-ul:text-slate-300 prose-li:my-1
                                    font-mono marker:text-blue-500">
                                    {deal.reasoning.split('\n').map((line, i) => {
                                        // A very simple markdown-ish renderer for the modal
                                        if (line.trim() === '') return <br key={i} className="my-2" />;
                                        if (line.startsWith('##')) return <h3 key={i} className="text-lg font-bold text-white mt-6 mb-3 pb-2 border-b border-slate-800">{line.replace('##', '').trim()}</h3>;
                                        if (line.startsWith('•') || line.startsWith('-')) {
                                            // Bold parsing for specific patterns like `**Authenticité**`
                                            const parts = line.split(/(\*\*.*?\*\*)/g);
                                            return (
                                                <div key={i} className="flex gap-3 mb-2 items-start text-[13px] sm:text-[15px]">
                                                    <span className="text-blue-500 shrink-0 mt-0.5">•</span>
                                                    <span>
                                                        {parts.map((p, j) =>
                                                            p.startsWith('**') && p.endsWith('**')
                                                                ? <strong key={j} className="text-white font-bold">{p.slice(2, -2)}</strong>
                                                                : p.replace(/^[-•]/, '').trim()
                                                        )}
                                                    </span>
                                                </div>
                                            );
                                        }
                                        return <p key={i} className="text-[13px] sm:text-[15px] mb-3">{line}</p>;
                                    })}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default MockupDealCard;
