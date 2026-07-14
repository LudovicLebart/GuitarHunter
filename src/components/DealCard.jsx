import React, { useState } from 'react';
import { Heart, RefreshCw, XCircle, Trash2, Facebook, Sparkles, MapPin, Gem, Hammer, Briefcase, Package, AlertTriangle, Ban, X, FileText, ExternalLink, ChevronDown, Share2, MessageSquarePlus } from 'lucide-react';
import ImageGallery from './ImageGallery';
import { createSharedDeal } from '../services/firestoreService';
import { computeInterestScore } from '../constants';

// ── Verdict config ───────────────────────────────────────────
const VERDICT_CONFIG = {
    PEPITE: { label: 'Pépite', bg: 'bg-yellow-500', text: 'text-yellow-900', icon: Gem },
    FAST_FLIP: { label: 'Fast Flip', bg: 'bg-emerald-500', text: 'text-emerald-900', icon: Sparkles },
    LUTHIER_PROJ: { label: 'Projet Luthier', bg: 'bg-orange-500', text: 'text-orange-900', icon: Hammer },
    CASE_WIN: { label: 'Case Win', bg: 'bg-sky-500', text: 'text-sky-900', icon: Briefcase },
    COLLECTION: { label: 'Collection', bg: 'bg-blue-500', text: 'text-blue-900', icon: Package },
    BAD_DEAL: { label: 'Trop Cher', bg: 'bg-rose-500', text: 'text-rose-900', icon: AlertTriangle },
    REJECTED_ITEM: { label: 'Rejeté', bg: 'bg-slate-600', text: 'text-slate-200', icon: Ban },
    REJECTED_SERVICE: { label: 'Service', bg: 'bg-slate-600', text: 'text-slate-200', icon: Ban },
    ERROR: { label: 'Erreur', bg: 'bg-red-900', text: 'text-red-200', icon: AlertTriangle },
    DEFAULT: { label: 'Analyse...', bg: 'bg-slate-700', text: 'text-slate-200', icon: RefreshCw },
};

const toTitleCase = (str = '') =>
    str.toLowerCase().split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

// Format a Firestore timestamp or ISO string to a relative human string
const formatRelativeDate = (timestamp) => {
    if (!timestamp) return null;
    try {
        const date = timestamp?.toDate ? timestamp.toDate() : new Date(timestamp);
        const diff = Math.floor((Date.now() - date.getTime()) / 1000);
        if (diff < 60) return 'À l\'instant';
        if (diff < 3600) return `Il y a ${Math.floor(diff / 60)} min`;
        if (diff < 86400) return `Il y a ${Math.floor(diff / 3600)}h`;
        return `Il y a ${Math.floor(diff / 86400)}j`;
    } catch {
        return null;
    }
};

// ── DealCard ────────────────────────────────────────────
const DealCard = ({ deal, onRetry, onForceExpert, onReject, onToggleFavorite, onDelete }) => {
    const [showAnalysisModal, setShowAnalysisModal] = useState(false);
    const [showDetailedAnalysis, setShowDetailedAnalysis] = useState(false);
    const [showRescanMenu, setShowRescanMenu] = useState(false);
    const [showModalRescanMenu, setShowModalRescanMenu] = useState(false);
    const [isCopying, setIsCopying] = useState(false);
    const [showCommentModal, setShowCommentModal] = useState(false);
    const [commentText, setCommentText] = useState('');

    const openCommentModal = () => setShowCommentModal(true);
    const submitComment = () => {
        onForceExpert(commentText.trim());
        setCommentText('');
        setShowCommentModal(false);
    };

    const handleShare = async (e) => {
        e.stopPropagation();
        if (!deal.id) return;

        try {
            await createSharedDeal(deal);
        } catch (err) {
            console.error('Erreur création shared_deal:', err);
        }

        const shareableLink = `${window.location.origin}${window.location.pathname}?shareId=${deal.id}`;

        const shareData = {
            title: `Guitar Hunter AI : ${deal.title}`,
            text: `Découvre cette annonce analysée par Guitar Hunter AI : ${deal.title}`,
            url: shareableLink
        };

        if (navigator.share) {
            try {
                await navigator.share(shareData);
            } catch (err) {
                if (err.name !== 'AbortError') {
                    console.error('Erreur de partage:', err);
                }
            }
        } else {
            try {
                await navigator.clipboard.writeText(shareableLink);
                setIsCopying(true);
                setTimeout(() => setIsCopying(false), 2000);
            } catch (err) {
                console.error('Erreur de copie:', err);
                alert("Impossible de copier le lien. Copiez-le manuellement depuis la barre d'adresse.");
            }
        }
    };

    const renderActionButtons = (isModal = false) => {
        const menuOpen = isModal ? showModalRescanMenu : showRescanMenu;
        const setMenuOpen = isModal ? setShowModalRescanMenu : setShowRescanMenu;

        return (
            <div className="flex items-center gap-1.5 sm:gap-2">
                {/* Favori */}
                <button
                    onClick={onToggleFavorite}
                    className={`w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl border transition-all ${deal.isFavorite ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' : 'bg-slate-800/50 text-slate-500 border-slate-700/50 hover:text-rose-400 hover:bg-rose-500/10'}`}
                    title="Favori"
                >
                    <Heart size={18} className="sm:w-4 sm:h-4" fill={deal.isFavorite ? 'currentColor' : 'none'} />
                </button>
                {/* Ré-analyser Dropdown */}
                <div
                    className="relative"
                    onMouseEnter={() => setMenuOpen(true)}
                    onMouseLeave={() => setMenuOpen(false)}
                >
                    <button
                        onClick={() => setMenuOpen(!menuOpen)}
                        className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-blue-400 hover:bg-blue-500/10 border border-slate-700/50 transition-all"
                        title="Ré-analyser"
                    >
                        <RefreshCw size={18} className={`sm:w-4 sm:h-4 ${isAnalyzing ? 'animate-spin' : ''}`} />
                    </button>

                    {menuOpen && (
                        <div className={`absolute ${isModal ? 'top-full mt-2' : 'bottom-full mb-2'} left-1/2 -translate-x-1/2 w-48 bg-slate-800 border border-slate-700 rounded-xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] z-50 overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150`}>
                            <button
                                onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onRetry(); }}
                                className="w-full px-4 py-2.5 text-left text-sm font-bold text-slate-200 hover:bg-slate-700 hover:text-white flex items-center gap-2 border-b border-slate-700/50 transition-colors"
                            >
                                <Sparkles size={14} className="text-blue-400" />
                                Scan Standard
                            </button>
                            <button
                                onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onForceExpert(); }}
                                className="w-full px-4 py-2.5 text-left text-sm font-bold text-purple-300 hover:bg-slate-700 hover:text-purple-200 flex items-center gap-2 border-b border-slate-700/50 transition-colors"
                            >
                                <Gem size={14} className="text-purple-400" />
                                Luthier Expert
                            </button>
                            <button
                                onClick={(e) => { e.stopPropagation(); setMenuOpen(false); openCommentModal(); }}
                                className="w-full px-4 py-2.5 text-left text-sm font-bold text-amber-300 hover:bg-slate-700 hover:text-amber-200 flex items-center gap-2 transition-colors"
                            >
                                <MessageSquarePlus size={14} className="text-amber-400" />
                                Avec commentaire...
                            </button>
                        </div>
                    )}
                </div>
                {/* Rejeter */}
                <button
                    onClick={onReject}
                    className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-orange-400 hover:bg-orange-500/10 border border-slate-700/50 transition-all"
                    title="Rejeter"
                >
                    <XCircle size={18} className="sm:w-4 sm:h-4" />
                </button>
                <button
                    onClick={onDelete}
                    className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-red-400 hover:bg-red-500/10 border border-slate-700/50 transition-all"
                    title="Supprimer"
                >
                    <Trash2 size={18} className="sm:w-4 sm:h-4" />
                </button>

                <div className="w-px h-6 bg-slate-800 mx-0.5 sm:h-5"></div>

                {/* Partager */}
                <button
                    onClick={handleShare}
                    disabled={!deal.link}
                    className={`w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl border transition-all ${isCopying ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-slate-800/50 text-slate-500 border-slate-700/50 hover:text-blue-400 hover:bg-blue-500/10'}`}
                    title={isCopying ? "Lien copié !" : "Partager l'annonce"}
                >
                    <Share2 size={18} className="sm:w-4 sm:h-4" />
                </button>
                {/* Facebook */}
                {deal.link ? (
                    <a
                        href={deal.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-blue-700 text-white hover:bg-blue-600 border border-blue-600 transition-all"
                        title="Voir sur Facebook"
                    >
                        <Facebook size={18} className="sm:w-4 sm:h-4" />
                    </a>
                ) : (
                    <button className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-700 border border-slate-700/50 cursor-not-allowed" title="Lien indisponible" disabled>
                        <Facebook size={18} className="sm:w-4 sm:h-4" />
                    </button>
                )}
            </div>
        );
    };

    // ── Map real deal model to UI fields ──────────────────────
    const ai = deal.aiAnalysis || {};
    const verdict = ai.verdict || 'DEFAULT';
    const reasoning = ai.analysis || ai.reasoning || null;
    const modelUsed = ai.model_used || null;
    const dealScore = ai.deal_score != null ? ai.deal_score : null;
    const confidence = dealScore != null ? dealScore * 10 : null; // 0-10 → 0-100%

    // Financial fields — support both real (estimated_value) and legacy field names
    const estValue = ai.estimated_value ?? ai.estimated_guitar_value ?? null;
    const price = deal.price ?? null;
    const originalPrice = deal.original_price ?? null;
    const priceDrop = deal.price_drop_amount ?? null;
    const computedMargin = (estValue != null && price != null) ? Math.round(estValue - price) : null;
    const margin = ai.estimated_gross_margin !== undefined ? ai.estimated_gross_margin : computedMargin;

    const taxonomy = ai.classification || null;
    const relDate = formatRelativeDate(deal.timestamp);
    const images = deal.storageImageUrls?.length > 0 ? deal.storageImageUrls : (deal.imageUrls || []);

    const vc = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.DEFAULT;
    const VIcon = vc.icon;
    const interestScore = computeInterestScore(ai);
    const alsoPepite = verdict !== 'PEPITE' && !!ai.also_qualifies_pepite;

    const isAnalyzing = ['analyzing', 'analyzing_expert'].includes(deal.status);

    return (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 flex flex-col overflow-hidden hover:border-slate-600 transition-all duration-300 hover:shadow-2xl hover:shadow-black/40 group">

            {/* Image Gallery Container */}
            <div className="relative w-full h-[280px] bg-slate-950 overflow-hidden flex items-center justify-center shrink-0">
                <div className="h-full w-full">
                    <ImageGallery images={images.length > 0 ? images : ['']} title={deal.title} />
                </div>

                {/* Verdict Badge */}
                <div className="absolute top-3 left-3 flex flex-col items-start gap-1 z-10">
                    <div className={`${vc.bg} px-2.5 py-1 rounded-full text-[11px] font-black tracking-wider flex items-center gap-1.5 shadow-lg ${vc.text}`}>
                        <VIcon size={12} className={isAnalyzing ? 'animate-spin' : ''} />
                        {isAnalyzing ? 'Analyse...' : vc.label}
                    </div>
                    {alsoPepite && (
                        <div className="bg-yellow-500 text-yellow-900 px-2 py-0.5 rounded-full text-[10px] font-black tracking-wider flex items-center gap-1 shadow-lg">
                            <Gem size={10} />
                            Aussi Pépite
                        </div>
                    )}
                    {interestScore != null && (
                        <div className="bg-slate-950/90 backdrop-blur-sm border border-slate-700 text-white px-2 py-0.5 rounded-full text-[10px] font-black tracking-wider shadow-lg">
                            Note {interestScore.toFixed(1)}/10
                        </div>
                    )}
                </div>
                {/* Price Badge */}
                {price != null && (
                    <div className="absolute top-3 right-3 flex flex-col items-end gap-1 z-10 pointer-events-none">
                        <div className="bg-slate-950/90 backdrop-blur-sm border border-slate-700 text-white px-3 py-1.5 rounded-xl text-base font-black shadow-lg">
                            {price}$
                        </div>
                        {priceDrop > 0 && (
                            <div className="bg-emerald-500/90 backdrop-blur-sm border border-emerald-400 text-emerald-950 px-2.5 py-1 rounded-lg text-xs font-black shadow-lg">
                                Baisse -{priceDrop}$
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Body */}
            <div className="p-4 flex flex-col gap-3 flex-1">

                {/* Title & Location */}
                <div>
                    <h3 className="text-sm font-bold text-white leading-snug line-clamp-2">
                        {toTitleCase(deal.title || '')}
                    </h3>
                    <div className="flex items-center gap-1.5 mt-1 text-[11px] text-slate-400 flex-wrap">
                        <MapPin size={11} />
                        <span>{deal.location}</span>
                        {taxonomy && (
                            <>
                                <span className="text-slate-700">•</span>
                                <span className="text-purple-400 truncate max-w-[120px]" title={taxonomy}>{taxonomy}</span>
                            </>
                        )}
                    </div>
                </div>

                {/* Financial Summary — visible immediately */}
                {margin != null && (
                    <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold px-2.5 py-1 rounded-lg ${margin > 0 ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/15 text-rose-400 border border-rose-500/20'}`}>
                            Marge {margin > 0 ? '+' : ''}{margin}$
                        </span>
                        <span className="text-[11px] text-slate-500">Val. Est. {estValue}$</span>
                    </div>
                )}

                {/* AI Reasoning button — opens modal */}
                {reasoning && (
                    <div className="bg-slate-950 rounded-xl border border-slate-800 relative z-10 w-full mb-2">
                        <button
                            className="w-full h-full flex items-center justify-between px-3 py-2 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
                            onClick={() => setShowAnalysisModal(true)}
                        >
                            <span className="flex items-center gap-1.5 font-bold">
                                <span title={`Modèles: ${modelUsed || 'N/A'}`} className="cursor-help flex items-center gap-1.5">
                                    <FileText size={12} className="text-blue-400" /> Analyse IA
                                </span>
                            </span>
                            <div className="flex items-center gap-2">
                                {confidence != null && (
                                    <div className="flex items-center gap-1.5">
                                        <div className="w-14 h-1 bg-slate-800 rounded-full overflow-hidden hidden sm:block">
                                            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${confidence}%` }}></div>
                                        </div>
                                        <span className="text-blue-400 font-bold">{Math.round(confidence)}%</span>
                                    </div>
                                )}
                                <span className="text-slate-500 font-mono ml-1">Lire</span>
                            </div>
                        </button>
                    </div>
                )}

                {/* Footer actions */}
                <div className="flex items-center justify-between mt-auto pt-3 border-t border-slate-800/50">
                    <span className="text-[10px] sm:text-xs text-slate-600 font-mono flex items-center gap-1">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/60"></div>
                        {relDate || 'Récent'}
                    </span>
                    <div className="flex items-center gap-1.5 sm:gap-2">
                        {/* Favori */}
                        <button
                            onClick={onToggleFavorite}
                            className={`w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl border transition-all ${deal.isFavorite ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' : 'bg-slate-800/50 text-slate-500 border-slate-700/50 hover:text-rose-400 hover:bg-rose-500/10'}`}
                            title="Favori"
                        >
                            <Heart size={18} className="sm:w-4 sm:h-4" fill={deal.isFavorite ? 'currentColor' : 'none'} />
                        </button>
                        {/* Ré-analyser Dropdown */}
                        <div
                            className="relative"
                            onMouseEnter={() => setShowRescanMenu(true)}
                            onMouseLeave={() => setShowRescanMenu(false)}
                        >
                            <button
                                onClick={() => setShowRescanMenu(!showRescanMenu)}
                                className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-blue-400 hover:bg-blue-500/10 border border-slate-700/50 transition-all"
                                title="Ré-analyser"
                            >
                                <RefreshCw size={18} className={`sm:w-4 sm:h-4 ${isAnalyzing ? 'animate-spin' : ''}`} />
                            </button>

                            {showRescanMenu && (
                                <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 w-48 bg-slate-800 border border-slate-700 rounded-xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] z-50 overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
                                    <button
                                        onClick={(e) => { e.stopPropagation(); setShowRescanMenu(false); onRetry(); }}
                                        className="w-full px-4 py-2.5 text-left text-sm font-bold text-slate-200 hover:bg-slate-700 hover:text-white flex items-center gap-2 border-b border-slate-700/50 transition-colors"
                                    >
                                        <Sparkles size={14} className="text-blue-400" />
                                        Scan Standard
                                    </button>
                                    <button
                                        onClick={(e) => { e.stopPropagation(); setShowRescanMenu(false); onForceExpert(); }}
                                        className="w-full px-4 py-2.5 text-left text-sm font-bold text-purple-300 hover:bg-slate-700 hover:text-purple-200 flex items-center gap-2 border-b border-slate-700/50 transition-colors"
                                    >
                                        <Gem size={14} className="text-purple-400" />
                                        Luthier Expert
                                    </button>
                                    <button
                                        onClick={(e) => { e.stopPropagation(); setShowRescanMenu(false); openCommentModal(); }}
                                        className="w-full px-4 py-2.5 text-left text-sm font-bold text-amber-300 hover:bg-slate-700 hover:text-amber-200 flex items-center gap-2 transition-colors"
                                    >
                                        <MessageSquarePlus size={14} className="text-amber-400" />
                                        Avec commentaire...
                                    </button>
                                </div>
                            )}
                        </div>
                        {/* Rejeter */}
                        <button
                            onClick={onReject}
                            className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-orange-400 hover:bg-orange-500/10 border border-slate-700/50 transition-all"
                            title="Rejeter"
                        >
                            <XCircle size={18} className="sm:w-4 sm:h-4" />
                        </button>
                        <button
                            onClick={onDelete}
                            className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-500 hover:text-red-400 hover:bg-red-500/10 border border-slate-700/50 transition-all"
                            title="Supprimer"
                        >
                            <Trash2 size={18} className="sm:w-4 sm:h-4" />
                        </button>

                        <div className="w-px h-6 bg-slate-800 mx-0.5 sm:h-5"></div>

                        {/* Partager */}
                        <button
                            onClick={handleShare}
                            disabled={!deal.link}
                            className={`w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl border transition-all ${isCopying ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-slate-800/50 text-slate-500 border-slate-700/50 hover:text-blue-400 hover:bg-blue-500/10'}`}
                            title={isCopying ? "Lien copié !" : "Partager l'annonce"}
                        >
                            <Share2 size={18} className="sm:w-4 sm:h-4" />
                        </button>
                        {/* Facebook */}
                        {deal.link ? (
                            <a
                                href={deal.link}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-blue-700 text-white hover:bg-blue-600 border border-blue-600 transition-all"
                                title="Voir sur Facebook"
                            >
                                <Facebook size={18} className="sm:w-4 sm:h-4" />
                            </a>
                        ) : (
                            <button className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-slate-800/50 text-slate-700 border border-slate-700/50 cursor-not-allowed" title="Lien indisponible" disabled>
                                <Facebook size={18} className="sm:w-4 sm:h-4" />
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* AI Reasoning Full-Screen Modal */}
            {showAnalysisModal && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
                    <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-md cursor-pointer" onClick={() => setShowAnalysisModal(false)}></div>

                    <div className="relative w-full max-w-5xl max-h-[90vh] bg-slate-900 border border-slate-700 rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 pointer-events-auto">
                        {/* Modal Header */}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 sm:p-6 border-b border-slate-800 bg-slate-950/50 shrink-0">
                            <div>
                                <h2 className="text-lg sm:text-xl font-black text-white leading-tight mb-1">
                                    Rapport d'Expertise IA
                                </h2>
                                <h3 className="text-sm text-slate-400 truncate max-w-[250px] sm:max-w-md">
                                    {toTitleCase(deal.title || '')}
                                </h3>
                            </div>
                            <div className="flex items-center justify-end gap-2 self-end sm:self-auto">
                                {renderActionButtons(true)}
                                <div className="w-px h-6 bg-slate-800 mx-1 hidden sm:block"></div>
                                <button
                                    onClick={() => setShowAnalysisModal(false)}
                                    className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded-xl transition-colors border border-slate-700/50 shrink-0"
                                >
                                    <X size={20} />
                                </button>
                            </div>
                        </div>

                        {/* Modal Body */}
                        <div className="flex-1 flex flex-col md:flex-row min-h-0">
                            {/* Left column: Image only */}
                            <div className="hidden md:flex flex-col w-1/3 bg-slate-950 border-r border-slate-800 p-6 items-center justify-start shrink-0 overflow-y-auto scrollbar-dark">
                                <div className="w-full aspect-[4/5] rounded-xl overflow-hidden bg-black shadow-inner relative border border-slate-800 shrink-0">
                                    <img
                                        src={images[0] || ''}
                                        alt={deal.title}
                                        className="w-full h-full object-contain"
                                        onError={() => setImageError(true)}
                                    />
                                    <div className="absolute top-3 left-3 flex flex-col items-start gap-1">
                                        <div className={`${vc.bg} px-2.5 py-1 rounded-full text-xs font-black tracking-wider flex items-center gap-1.5 shadow-lg ${vc.text}`}>
                                            <vc.icon size={12} strokeWidth={3} />
                                            {vc.label}
                                        </div>
                                        {alsoPepite && (
                                            <div className="bg-yellow-500 text-yellow-900 px-2 py-0.5 rounded-full text-[10px] font-black tracking-wider flex items-center gap-1 shadow-lg">
                                                <Gem size={10} />
                                                Aussi Pépite
                                            </div>
                                        )}
                                    </div>
                                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-4 flex justify-between items-end">
                                        <div className="text-white/80 font-mono text-xs shadow-black drop-shadow-md">
                                            Demandé: <span className="text-white font-black text-lg">{price}$</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Right column: Split content layout */}
                            <div className="flex-1 flex flex-col p-6 sm:p-8 overflow-y-auto scrollbar-dark bg-slate-900 relative">
                                {/* Border accent on the left, like a quote block */}
                                <div className="absolute left-0 top-0 bottom-0 w-1 bg-purple-500 rounded-r-full"></div>

                                {/* Header with Sparkles and Model Chain */}
                                <div className="flex flex-wrap items-center gap-2 text-[11px] font-black uppercase tracking-wider text-purple-400 mb-4 pl-4">
                                    <span className="text-purple-300">✨</span>
                                    {modelUsed ? modelUsed.split(' -> ').map(m => m.trim().toUpperCase()).join(' -> ') : 'GÉNÉRATION IA'}
                                </div>

                                {/* Financials & Verdict row moved here */}
                                <div className="flex flex-wrap items-center gap-4 pl-4 mb-8">
                                    <div className="bg-slate-950 px-4 py-2 rounded-xl border border-slate-800">
                                        <div className="text-[10px] text-slate-500 font-bold uppercase">Prix et Est.</div>
                                        <div className="text-lg font-black text-white flex items-center gap-2">
                                            {price}$
                                            {priceDrop > 0 && <span className="text-sm font-bold text-emerald-400 bg-emerald-500/10 px-1.5 rounded">-{priceDrop}$</span>}
                                            <span className="text-sm font-normal text-slate-400 line-through">{estValue}$</span>
                                        </div>
                                    </div>
                                    {margin != null && (
                                        <div className={`px-4 py-2 rounded-xl border ${margin > 0 ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/20'}`}>
                                            <div className={`text-[10px] font-bold uppercase ${margin > 0 ? 'text-emerald-500/70' : 'text-rose-500/70'}`}>Marge</div>
                                            <div className={`text-lg font-black ${margin > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{margin > 0 ? '+' : ''}{margin}$</div>
                                        </div>
                                    )}
                                    <div className="bg-slate-950 px-4 py-2 rounded-xl border border-slate-800">
                                        <div className="text-[10px] text-slate-500 font-bold uppercase">Confiance IA</div>
                                        <div className="text-lg font-black text-blue-400">{Math.round(confidence || 0)}%</div>
                                    </div>
                                </div>

                                {/* Summary Text */}
                                <div className="text-sm sm:text-base text-slate-200 font-medium leading-relaxed pl-4 mb-6">
                                    {deal.aiAnalysis.summary || 'Résumé global non fourni par l\'IA pour cette annonce. Ouvrez l\'analyse détaillée pour lire le raisonnement textuel.'}
                                </div>

                                {/* Separator */}
                                <div className="border-t border-slate-800/60 ml-4 mb-6"></div>

                                {/* Sub-Content: Voir l'analyse détaillée */}
                                <div className="pl-4 pb-4">
                                    <button
                                        onClick={() => setShowDetailedAnalysis(!showDetailedAnalysis)}
                                        className="flex items-center justify-between w-full text-left font-bold text-slate-300 hover:text-white transition-colors py-2"
                                    >
                                        <span>Voir l'analyse détaillée</span>
                                        <ChevronDown size={18} className={`text-slate-500 transition-transform ${showDetailedAnalysis ? 'rotate-180' : ''}`} />
                                    </button>

                                    {showDetailedAnalysis && reasoning && (
                                        <div className="mt-6 text-[13px] sm:text-[15px] text-slate-300 font-mono leading-relaxed whitespace-pre-wrap animate-in fade-in slide-in-from-top-2">
                                            {reasoning.split('\n').map((line, i) => {
                                                if (line.trim() === '') return <div key={i} className="h-4"></div>;

                                                const isHeader = line.startsWith('#');
                                                const isList = line.trim().startsWith('-') || line.trim().startsWith('* ');

                                                // Parse bold text **like this**
                                                const formattedLine = line.split(/(\*\*.*?\*\*)/g).map((part, index) => {
                                                    if (part.startsWith('**') && part.endsWith('**')) {
                                                        return <strong key={index} className="text-blue-400 font-bold tracking-wide">{part.slice(2, -2)}</strong>;
                                                    }
                                                    return part;
                                                });

                                                if (isHeader) {
                                                    // Strip # and render as header
                                                    const text = line.replace(/^#+\s*/, '');
                                                    return <h3 key={i} className="text-blue-400 font-black text-sm uppercase tracking-widest mt-6 mb-2 border-b border-slate-800 pb-2">{text}</h3>;
                                                }

                                                if (isList) {
                                                    // Strip list marker and render with indent
                                                    const text = line.replace(/^[-*]\s*/, '');
                                                    const listParts = text.split(/(\*\*.*?\*\*)/g).map((part, index) => {
                                                        if (part.startsWith('**') && part.endsWith('**')) {
                                                            return <strong key={index} className="text-white font-bold tracking-wide">{part.slice(2, -2)}</strong>;
                                                        }
                                                        return part;
                                                    });

                                                    return (
                                                        <div key={i} className="flex gap-3 mb-2 items-start pl-2">
                                                            <span className="text-blue-500 shrink-0 mt-0.5">•</span>
                                                            <span className="text-slate-300">{listParts}</span>
                                                        </div>
                                                    );
                                                }

                                                return <div key={i} className="mb-3">{formattedLine}</div>;
                                            })}
                                        </div>
                                    )}
                                </div>

                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Modale Commentaire (Réanalyse avec correction utilisateur) */}
            {showCommentModal && (
                <div
                    className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
                    onClick={(e) => { e.stopPropagation(); setShowCommentModal(false); }}
                >
                    <div
                        className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-5 animate-in fade-in zoom-in-95 duration-150"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center gap-2 mb-3">
                            <MessageSquarePlus size={18} className="text-amber-400" />
                            <h3 className="text-sm font-black text-slate-100 uppercase tracking-wide">Réanalyse avec commentaire</h3>
                        </div>
                        <p className="text-xs text-slate-400 mb-3">
                            Ex : "Tu as identifié une PRS mais c'est une GWD." Le commentaire est transmis en priorité à l'Expert Pro pour la contre-analyse.
                        </p>
                        <textarea
                            value={commentText}
                            onChange={(e) => setCommentText(e.target.value)}
                            placeholder="Ta correction ou précision..."
                            rows={4}
                            autoFocus
                            className="w-full bg-slate-800 border border-slate-700 rounded-xl p-3 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition-all resize-none"
                        />
                        <div className="flex justify-end gap-2 mt-4">
                            <button
                                onClick={() => { setCommentText(''); setShowCommentModal(false); }}
                                className="px-4 py-2 rounded-xl text-sm font-bold text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                            >
                                Annuler
                            </button>
                            <button
                                onClick={submitComment}
                                disabled={!commentText.trim()}
                                className="px-4 py-2 rounded-xl text-sm font-bold text-amber-900 bg-amber-400 hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            >
                                Lancer l'analyse Expert
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default DealCard;
