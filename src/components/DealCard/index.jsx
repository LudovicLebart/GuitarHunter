import React, { useState, useRef } from 'react';
import { MapPin, FileText, RefreshCw } from 'lucide-react';
import { computeInterestScore } from '../../constants';
import { VERDICT_CONFIG, toTitleCase, formatRelativeDate } from './utils';
import DealCardImage from './DealCardImage';
import DealCardActions from './DealCardActions';
import DealAnalysisModal from './DealAnalysisModal';

const DealCard = ({ deal, onRetry, onForceExpert, onReject, onToggleFavorite, onDelete }) => {
    const [showAnalysisModal, setShowAnalysisModal] = useState(false);
    const [showDetailedAnalysis, setShowDetailedAnalysis] = useState(false);
    const [imageError, setImageError] = useState(false);

    // ── Map real deal model to UI fields ──────────────────────
    if (deal.isLoading) {
        return (
            <div className="bg-slate-900 rounded-2xl border border-slate-800 flex flex-col h-[400px] overflow-hidden animate-pulse">
                <div className="w-full h-[280px] bg-slate-950/50 flex items-center justify-center shrink-0">
                    <RefreshCw className="text-slate-700 animate-spin" size={24} />
                </div>
                <div className="p-4 flex flex-col gap-3 flex-1 justify-center">
                    <div className="h-4 bg-slate-800 rounded w-3/4"></div>
                    <div className="h-3 bg-slate-800 rounded w-1/2"></div>
                </div>
            </div>
        );
    }

    const ai = deal.aiAnalysis || {};
    const verdict = ai.verdict || 'DEFAULT';
    const reasoning = ai.analysis || ai.reasoning || null;
    const modelUsed = ai.model_used || null;
    const dealScore = ai.deal_score != null ? ai.deal_score : null;
    const confidence = dealScore != null ? dealScore * 10 : null; // 0-10 → 0-100%

    // Financial fields — support both real (estimated_value) and legacy field names
    const estValue = ai.estimated_value ?? ai.estimated_guitar_value ?? null;
    const price = deal.price ?? null;
    const priceDrop = deal.price_drop_amount ?? null;
    const computedMargin = (estValue != null && price != null) ? Math.round(estValue - price) : null;
    const margin = ai.estimated_gross_margin !== undefined ? ai.estimated_gross_margin : computedMargin;

    const taxonomy = ai.classification || null;
    const relDate = formatRelativeDate(deal.timestamp);
    const pubDate = formatRelativeDate(deal.publishTimestamp);
    const images = deal.storageImageUrls?.length > 0 ? deal.storageImageUrls : (deal.imageUrls || []);

    const vc = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.DEFAULT;
    const interestScore = computeInterestScore(ai);
    const alsoPepite = verdict !== 'PEPITE' && !!ai.also_qualifies_pepite;

    const isAnalyzing = ['analyzing', 'analyzing_expert'].includes(deal.status);
    const isSold = deal.status === 'sold';

    return (
        <div className={`bg-slate-900 rounded-2xl border border-slate-800 flex flex-col overflow-hidden hover:border-slate-600 transition-all duration-300 hover:shadow-2xl hover:shadow-black/40 group ${isSold ? 'opacity-60 saturate-50' : ''}`}>

            <DealCardImage
                images={images}
                title={deal.title}
                isSold={isSold}
                vc={vc}
                isAnalyzing={isAnalyzing}
                alsoPepite={alsoPepite}
                interestScore={interestScore}
                price={price}
                priceDrop={priceDrop}
            />

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
                    <div className="flex flex-col gap-0.5">
                        <span className="text-[10px] text-slate-500 font-mono flex items-center gap-1" title="Date de mise en vente">
                            <div className={`w-1.5 h-1.5 rounded-full ${deal.publishTimestamp ? 'bg-blue-500/60' : 'bg-amber-500/60'}`}></div>
                            Publiée: {deal.publishTimestamp ? formatRelativeDate(deal.publishTimestamp) : (relDate ? `${relDate} (estimé)` : 'Inconnue')}
                        </span>
                        <span className="text-[10px] text-slate-600 font-mono flex items-center gap-1" title="Date d'analyse par l'IA">
                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/60"></div>
                            Analysée: {relDate || 'Récent'}
                        </span>
                    </div>
                    
                    {/* The Action Buttons Component */}
                    <DealCardActions
                        deal={deal}
                        isAnalyzing={isAnalyzing}
                        onToggleFavorite={onToggleFavorite}
                        onReject={onReject}
                        onDelete={onDelete}
                        onRetry={onRetry}
                        onForceExpert={onForceExpert}
                    />
                </div>
            </div>

            {/* AI Reasoning Full-Screen Modal */}
            {showAnalysisModal && (
                <DealAnalysisModal
                    deal={deal}
                    images={images}
                    vc={vc}
                    isSold={isSold}
                    alsoPepite={alsoPepite}
                    price={price}
                    estValue={estValue}
                    priceDrop={priceDrop}
                    margin={margin}
                    confidence={confidence}
                    modelUsed={modelUsed}
                    reasoning={reasoning}
                    showDetailedAnalysis={showDetailedAnalysis}
                    setShowDetailedAnalysis={setShowDetailedAnalysis}
                    onClose={() => setShowAnalysisModal(false)}
                    setImageError={setImageError}
                    onRetry={onRetry}
                    onForceExpert={onForceExpert}
                    onReject={onReject}
                    onToggleFavorite={onToggleFavorite}
                    onDelete={onDelete}
                    isAnalyzing={isAnalyzing}
                />
            )}
        </div>
    );
};

export default DealCard;
