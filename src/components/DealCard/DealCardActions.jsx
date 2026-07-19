import React, { useState } from 'react';
import { Heart, RefreshCw, XCircle, Trash2, Facebook, Sparkles, Gem, MessageSquarePlus, Share2 } from 'lucide-react';
import { createSharedDeal } from '../../services/firestoreService';

const DealCardActions = ({ 
    deal, 
    isAnalyzing, 
    onToggleFavorite, 
    onReject, 
    onDelete, 
    onRetry, 
    onForceExpert, 
    isModal = false
}) => {
    const [showRescanMenu, setShowRescanMenu] = useState(false);
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

        let shareData = null;
        const shareableLink = `${window.location.origin}${window.location.pathname}?shareId=${deal.id}`;
        
        try {
            await createSharedDeal(deal);
            shareData = {
                title: `Guitar Hunter AI : ${deal.title}`,
                text: `Découvre cette annonce analysée par Guitar Hunter AI : ${deal.title}`,
                url: shareableLink
            };
        } catch (err) {
            console.error('Erreur création shared_deal:', err);
        }

        if (navigator.share && shareData) {
            try {
                await navigator.share(shareData);
                return; // success
            } catch (err) {
                if (err.name !== 'AbortError') {
                    console.error('Erreur de partage natif, tentative via presse-papier:', err);
                } else {
                    return; // user aborted
                }
            }
        }
        
        // Fallback to clipboard
        try {
            await navigator.clipboard.writeText(shareableLink);
            setIsCopying(true);
            setTimeout(() => setIsCopying(false), 2000);
        } catch (err) {
            console.error('Erreur de copie:', err);
            alert("Impossible de copier le lien. Copiez-le manuellement depuis la barre d'adresse.");
        }
    };

    return (
        <>
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
                    className="relative group"
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
                        <div className={`absolute ${isModal ? 'top-full pt-2' : 'bottom-full pb-2'} left-1/2 -translate-x-1/2 w-48 z-50`}>
                            <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
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
            
            {/* Modale Commentaire */}
            {showCommentModal && (
                <div
                    className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
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
        </>
    );
};

export default DealCardActions;
