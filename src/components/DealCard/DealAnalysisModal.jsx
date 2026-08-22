import React, { useEffect, useState } from 'react';
import { X, Ban, Gem, ChevronDown, ShoppingBag, Wrench } from 'lucide-react';
import { toTitleCase, formatRelativeDate } from './utils';
import { ManagementActions, ShareActions } from './DealCardActions';
import DealChatPanel from './DealChatPanel';
import ClassificationEditor from './ClassificationEditor';
import RestorationPlanPanel from './RestorationPlanPanel';
import { useRestorationPlan } from '../../hooks/useRestorationPlan';
import { useAuth } from '../../hooks/useAuth';

const DealAnalysisModal = ({
    deal,
    images,
    vc,
    isSold,
    isPurchased,
    alsoPepite,
    price,
    estValue,
    priceDrop,
    margin,
    confidence,
    modelUsed,
    reasoning,
    showDetailedAnalysis,
    setShowDetailedAnalysis,
    onClose,
    setImageError,
    onRetry,
    onForceExpert,
    onReject,
    onToggleFavorite,
    onTogglePurchased,
    onDelete,
    isAnalyzing,
    onSetClassification,
    onGalleryImageAdded
}) => {
    const [activeView, setActiveView] = useState('analysis'); // 'analysis' | 'chat' | 'restoration'
    // { text, autoSend } | null — "Demander conseil" (autoSend=false, éditable) vs "Faire le
    // point"/"Préparer l'annonce" (autoSend=true, prompt prédéfini envoyé directement).
    const [chatDraftRequest, setChatDraftRequest] = useState(null);
    const { user } = useAuth();
    const restorationPlan = useRestorationPlan(deal, user);

    const askInChat = (item) => {
        setChatDraftRequest({ text: `Concernant l'étape "${item.label}" : comment procéder, et coût réaliste ?`, autoSend: false });
        setActiveView('chat');
    };

    const sendQuickPrompt = (text) => {
        setChatDraftRequest({ text, autoSend: true });
        setActiveView('chat');
    };

    // Escape key listener for closing modal
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                onClose();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onClose]);

    const specs = [
        { label: 'Marque', value: deal.aiAnalysis?.brand },
        { label: 'Modèle', value: deal.aiAnalysis?.model_name },
        { label: 'Année', value: deal.aiAnalysis?.production_year },
        { label: 'Pays', value: deal.aiAnalysis?.country_of_origin },
        { label: 'Couleur', value: deal.aiAnalysis?.color },
        { label: 'Finition', value: deal.aiAnalysis?.finish_application },
        { label: 'Brillance', value: deal.aiAnalysis?.finish_texture },
        { label: 'Longueur manche', value: deal.aiAnalysis?.neck_scale_length },
    ].filter(spec => spec.value && !/^inconnu(e)?$/i.test(String(spec.value).trim()));

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
            <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-md cursor-pointer" onClick={onClose}></div>

            <div className="relative w-full max-w-5xl max-h-[90vh] bg-slate-900 border border-slate-700 rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 pointer-events-auto">
                {/* Modal Header */}
                <div className="flex flex-col gap-3 p-4 sm:p-6 border-b border-slate-800 bg-slate-950/50 shrink-0">
                    <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0 flex-1">
                            <h2 className="text-lg sm:text-xl font-black text-white leading-tight mb-1 truncate">
                                Rapport d'Expertise IA
                            </h2>
                            <h3 className="text-sm text-slate-400 truncate sm:max-w-md">
                                {toTitleCase(deal.title || '')}
                            </h3>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                            <ShareActions
                                deal={deal}
                                isModal={true}
                                onOpenChat={() => setActiveView('chat')}
                            />
                            <div className="w-px h-6 bg-slate-800 mx-1 hidden sm:block"></div>
                            <button
                                onClick={onClose}
                                className="w-10 h-10 sm:w-9 sm:h-9 flex items-center justify-center bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded-xl transition-colors border border-slate-700/50 shrink-0"
                            >
                                <X size={20} />
                            </button>
                        </div>
                    </div>
                    <div className="flex items-center justify-end gap-2">
                        <ManagementActions
                            deal={deal}
                            isAnalyzing={isAnalyzing}
                            onToggleFavorite={onToggleFavorite}
                            onTogglePurchased={onTogglePurchased}
                            onReject={onReject}
                            onDelete={onDelete}
                            onRetry={onRetry}
                            onForceExpert={onForceExpert}
                            isModal={true}
                        />
                    </div>
                </div>

                {/* Modal Body — les vues alternatives restent montées (masquées via `hidden`)
                    plutôt que démontées au changement de vue : perdre le brouillon de message et
                    les photos jointes du chat à chaque bascule vers le plan de restauration (et
                    inversement) serait gênant, puisque jongler entre les deux est l'usage visé
                    par le pont "Demander conseil". */}
                <div className={`flex-1 flex flex-col min-h-0 ${activeView === 'chat' ? '' : 'hidden'}`}>
                    <DealChatPanel
                        deal={deal}
                        onBack={() => setActiveView('analysis')}
                        onGalleryImageAdded={onGalleryImageAdded}
                        initialDraft={chatDraftRequest?.text}
                        autoSend={chatDraftRequest?.autoSend}
                        onDraftConsumed={() => setChatDraftRequest(null)}
                        restorationItems={restorationPlan.items}
                    />
                </div>
                {isPurchased && (
                    <div className={`flex-1 flex flex-col min-h-0 ${activeView === 'restoration' ? '' : 'hidden'}`}>
                        <RestorationPlanPanel deal={deal} plan={restorationPlan} onBack={() => setActiveView('analysis')} onAskInChat={askInChat} onQuickPrompt={sendQuickPrompt} />
                    </div>
                )}
                <div className={`flex-1 flex flex-col md:flex-row min-h-0 ${activeView === 'analysis' ? '' : 'hidden'}`}>
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
                                {isSold && (
                                    <div className="bg-slate-950 border border-slate-500 text-slate-200 px-2.5 py-1 rounded-full text-xs font-black tracking-wider flex items-center gap-1.5 shadow-lg">
                                        <Ban size={12} strokeWidth={3} />
                                        Vendu
                                    </div>
                                )}
                                {isPurchased && (
                                    <div className="bg-emerald-950 border border-emerald-600 text-emerald-300 px-2.5 py-1 rounded-full text-xs font-black tracking-wider flex items-center gap-1.5 shadow-lg">
                                        <ShoppingBag size={12} strokeWidth={3} />
                                        Acheté
                                    </div>
                                )}
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
                            {isPurchased && (
                                <div className="bg-emerald-500/10 px-4 py-2 rounded-xl border border-emerald-500/20">
                                    <div className="text-[10px] text-emerald-500/70 font-bold uppercase flex items-center gap-1">
                                        <ShoppingBag size={11} /> Achetée
                                    </div>
                                    <div className="text-sm font-black text-emerald-400">
                                        {deal.purchasePrice != null ? `${deal.purchasePrice}$` : 'Prix non précisé'}
                                        {deal.purchasedAt && <span className="text-emerald-500/70 font-normal ml-1.5">le {formatRelativeDate(deal.purchasedAt)}</span>}
                                    </div>
                                    <button
                                        onClick={() => setActiveView('restoration')}
                                        className="flex items-center gap-1 text-xs font-bold text-emerald-300/80 hover:text-emerald-200 mt-1 pt-1 border-t border-emerald-500/20 transition-colors"
                                    >
                                        <Wrench size={11} />
                                        Restauration {restorationPlan.totals.doneCount}/{restorationPlan.totals.itemCount}
                                        {restorationPlan.totals.totalEstimatedCost > 0 && ` · ${restorationPlan.totals.totalEstimatedCost}$ estimés`}
                                    </button>
                                </div>
                            )}
                        </div>

                        {/* Summary Text */}
                        <div className="text-sm sm:text-base text-slate-200 font-medium leading-relaxed pl-4 mb-6">
                            {deal.aiAnalysis?.summary || 'Résumé global non fourni par l\'IA pour cette annonce. Ouvrez l\'analyse détaillée pour lire le raisonnement textuel.'}
                        </div>

                        {/* Fiche Technique */}
                        {(specs.length > 0 || onSetClassification) && (
                            <div className="pl-4 mb-6">
                                <div className="text-[10px] text-slate-500 font-bold uppercase tracking-widest mb-2">Fiche Technique</div>
                                <div className="flex flex-wrap gap-2">
                                    {onSetClassification && (
                                        <ClassificationEditor deal={deal} onSetClassification={onSetClassification} />
                                    )}
                                    {specs.map(spec => (
                                        <div key={spec.label} className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5">
                                            <span className="text-[10px] text-slate-500 font-bold uppercase mr-1.5">{spec.label} :</span>
                                            <span className="text-xs text-slate-200 font-semibold">{spec.value}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

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
    );
};

export default DealAnalysisModal;
