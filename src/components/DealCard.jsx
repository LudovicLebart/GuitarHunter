import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { MapPin, Guitar, TrendingUp, Activity, Sparkles, Clock, Heart, RefreshCw, Ban, Share2, ExternalLink, CheckCircle, Trash2, BrainCircuit, Hammer, DollarSign, ChevronDown, Calculator } from 'lucide-react';
import ImageGallery from './ImageGallery';
import VerdictBadge from './VerdictBadge';
import SimpleMarkdown from './SimpleMarkdown';
import CollapsibleSection from './CollapsibleSection';

// Nouveau menu de réanalyse
const ReanalysisMenu = ({ position, onRetry, onForceExpert, onClose, buttonRef }) => {
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      // Ignore les clics sur le bouton qui ouvre le menu
      if (buttonRef.current && buttonRef.current.contains(event.target)) {
        return;
      }
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose, buttonRef]);

  if (!position) return null;

  return createPortal(
    <div
      ref={menuRef}
      style={{
        position: 'absolute',
        top: position.top + position.height + 8, // Positionne le menu en dessous du bouton
        left: position.left + position.width / 2,
        transform: 'translateX(-50%)',
        zIndex: 9999
      }}
      className="flex flex-col gap-2 animate-in slide-in-from-bottom-2 fade-in duration-200"
    >
      <button
        onClick={(e) => { e.stopPropagation(); onRetry(); }}
        className="flex items-center justify-center gap-2 px-4 py-3 rounded-2xl text-xs font-black uppercase tracking-widest bg-amber-500 text-white shadow-xl hover:bg-amber-600 transition-colors whitespace-nowrap"
      >
        <RefreshCw size={14} /> Standard
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); onForceExpert(); }}
        className="flex items-center justify-center gap-2 px-4 py-3 rounded-2xl text-xs font-black uppercase tracking-widest bg-purple-600 text-white shadow-xl hover:bg-purple-700 transition-colors whitespace-nowrap"
      >
        <BrainCircuit size={14} /> Expert
      </button>
    </div>,
    document.body
  );
};


const DealCard = ({ deal, filterType, onRetry, onForceExpert, onReject, onToggleFavorite, onDelete }) => {
  const [copied, setCopied] = useState(false);
  const [isReanalysisMenuOpen, setIsReanalysisMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState(null);
  const reanalysisButtonRef = useRef(null);
  const [showFinanceDetails, setShowFinanceDetails] = useState(false);


  const handleShare = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const url = `${window.location.origin}${window.location.pathname}?dealId=${deal.id}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const getModelName = (deal) => {
    if (['analyzing', 'retry_analysis', 'retry_analysis_expert', 'analyzing_expert'].includes(deal.status)) {
      return 'Analyse en cours...';
    }
    if (deal.aiAnalysis?.model_used) {
      return deal.aiAnalysis.model_used;
    }
    if (deal.status === 'analyzed' && !deal.aiAnalysis?.model_used) {
      return 'Modèle non spécifié';
    }
    return deal.aiAnalysis?.model_used || 'Analyse initiale';
  };

  const modelName = getModelName(deal);
  const isExpertAnalysis = modelName.includes('pro') || modelName.includes('expert');
  const isAnalyzing = ['retry_analysis', 'retry_analysis_expert', 'analyzing', 'analyzing_expert'].includes(deal.status);

  const handleReanalysisButtonClick = () => {
    if (reanalysisButtonRef.current) {
      const rect = reanalysisButtonRef.current.getBoundingClientRect();
      setMenuPosition({
        top: rect.top + window.scrollY,
        left: rect.left + window.scrollX,
        width: rect.width,
        height: rect.height
      });
    }
    setIsReanalysisMenuOpen(prev => !prev);
  };
  
  const closeMenu = () => {
    setIsReanalysisMenuOpen(false);
  };

  // --- NOUVEAUX CHAMPS CALCULÉS ---
  const grossMargin = deal.aiAnalysis?.estimated_gross_margin;
  const netCost = deal.aiAnalysis?.net_guitar_cost;
  const resalePotential = deal.aiAnalysis?.resale_potential || deal.aiAnalysis?.estimated_value_after_repair;
  const isLuthierProject = deal.aiAnalysis?.verdict === 'LUTHIER_PROJ';
  const estimatedValue = deal.aiAnalysis?.estimated_value;
  const repairCost = netCost - parseInt(deal.price);


  return (
    <div className={`group bg-white rounded-[2rem] shadow-sm border border-slate-200 flex flex-col md:flex-row items-start hover:shadow-2xl hover:shadow-blue-500/5 transition-all duration-500 animate-in fade-in slide-in-from-bottom-4 ${deal.status === 'rejected' ? 'opacity-50' : ''}`}>
      <div className="md:w-80 md:sticky md:top-24 self-start shrink-0 relative bg-slate-100 md:rounded-l-[2rem] rounded-t-[2rem] md:rounded-tr-none overflow-hidden">
        <div className="h-64 md:h-80 w-full"><ImageGallery images={deal.imageUrls || [deal.imageUrl]} title={deal.title} /></div>
        <div className="absolute top-4 left-4 z-10 pointer-events-none"><VerdictBadge verdict={deal.aiAnalysis?.verdict} /></div>
        <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent pointer-events-none" />
      </div>

      <div className="flex-1 p-6 md:p-8 flex flex-col w-full md:rounded-r-[2rem] rounded-b-[2rem] md:rounded-bl-none">
        <div className="flex justify-between items-start gap-4 mb-2">
          <div>
            <div className="flex items-center gap-2 text-blue-600 font-bold text-[10px] uppercase tracking-widest mb-1"><MapPin size={10} /> {deal.location || 'Québec'}</div>
            <h2 className="text-2xl font-black text-slate-800 leading-tight group-hover:text-blue-600 transition-colors uppercase tracking-tight">{deal.title}</h2>
            
            <div className="flex flex-wrap gap-2 mt-2">
                {deal.aiAnalysis?.classification && (<div className="flex items-center gap-2 text-purple-600 bg-purple-50 px-3 py-1 rounded-full text-xs font-bold"><Guitar size={12} /><span>{deal.aiAnalysis.classification}</span></div>)}
                {isLuthierProject && (<div className="flex items-center gap-2 text-orange-600 bg-orange-50 px-3 py-1 rounded-full text-xs font-bold"><Hammer size={12} /><span>Travaux Requis</span></div>)}
            </div>
          </div>
          
          <div className="text-right flex flex-col items-end gap-1 shrink-0">
            <div className="flex items-center gap-2">
                <div 
                    className="bg-slate-900 text-white px-4 py-2 rounded-2xl shadow-xl cursor-pointer"
                    onClick={() => setShowFinanceDetails(!showFinanceDetails)}
                >
                    <span className="block text-[8px] font-black uppercase text-slate-400 tracking-tighter">Prix Demandé</span>
                    <span className="text-2xl font-black tabular-nums">{deal.price} $</span>
                </div>
                <button 
                    onClick={() => setShowFinanceDetails(!showFinanceDetails)} 
                    className="p-2 bg-slate-100 rounded-full hover:bg-slate-200 transition-colors"
                >
                    <ChevronDown size={16} className={`transition-transform ${showFinanceDetails ? 'rotate-180' : ''}`} />
                </button>
            </div>

            {/* --- VALEURS DE MARCHÉ (TOUJOURS VISIBLES) --- */}
            <div className="flex items-center gap-3 text-xs font-bold mt-1 text-slate-500">
                {estimatedValue > 0 && (
                    <div className="flex items-center gap-1">
                        <Activity size={12} /> Val. Actuelle: <span className="font-black">{estimatedValue}$</span>
                    </div>
                )}
                {resalePotential > 0 && (
                    <div className="flex items-center gap-1 text-purple-600">
                        <TrendingUp size={12} /> Potentiel Max: <span className="font-black">{resalePotential}$</span>
                    </div>
                )}
            </div>

            {/* --- DROPDOWN : DÉTAILS FINANCIERS --- */}
            {showFinanceDetails && (
                <div className="mt-2 p-3 bg-slate-50 rounded-xl border border-slate-200 w-full space-y-2 text-left animate-in fade-in slide-in-from-top-2">
                    {netCost !== undefined && (
                        <div className="flex justify-between items-center text-xs">
                            <span className="font-bold text-slate-500 flex items-center gap-1"><DollarSign size={12} /> Coût Net Est.</span>
                            <span className="font-black text-sky-600">{netCost}$</span>
                        </div>
                    )}
                    {repairCost > 0 && (
                         <div className="flex justify-between items-center text-xs pl-4">
                            <span className="text-slate-400 flex items-center gap-1"><Hammer size={12} /> Dont réparations</span>
                            <span className="font-bold text-orange-500">{repairCost}$</span>
                        </div>
                    )}
                    {grossMargin !== undefined && (
                        <div className={`flex justify-between items-center text-sm font-black p-2 rounded-lg ${grossMargin >= 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                            <span className="flex items-center gap-1"><Calculator size={14} /> Marge Brute Est.</span>
                            <span>{grossMargin >= 0 ? `+${grossMargin}` : grossMargin}$</span>
                        </div>
                    )}
                </div>
            )}
        </div>
        </div>

        <div className="relative mb-6">
          <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-full ${isExpertAnalysis ? 'bg-purple-500' : 'bg-blue-100'}`} />
          <div className="pl-5 py-1">
            <div className={`flex items-center gap-1.5 mb-2 ${isExpertAnalysis ? 'text-purple-600' : 'text-blue-600'}`}><Sparkles size={14} /><span className="text-[10px] font-black uppercase tracking-widest">{modelName}</span></div>
            <div className="mt-2">
              {/* --- LOGIQUE D'AFFICHAGE STANDARDISÉE --- */}
              {deal.aiAnalysis?.summary ? (
                  <>
                    <SimpleMarkdown text={deal.aiAnalysis.summary} />
                    {deal.aiAnalysis.analysis && (
                        <CollapsibleSection title="Voir l'analyse détaillée">
                            <SimpleMarkdown text={deal.aiAnalysis.analysis} />
                        </CollapsibleSection>
                    )}
                  </>
              ) : deal.aiAnalysis?.reasoning ? (
                  // Fallback pour les annonces qui n'ont qu'un 'reasoning'
                  <SimpleMarkdown text={deal.aiAnalysis.reasoning} />
              ) : (<p className="text-slate-400 italic text-sm">Analyse de l'état et de la valeur en cours par l'intelligence artificielle...</p>)}
            </div>
          </div>
        </div>

        <div className="mt-auto pt-6 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2 text-slate-400 text-[10px] font-bold"><Clock size={14} /><span className="uppercase tracking-widest">{deal.timestamp?.seconds ? new Date(deal.timestamp.seconds * 1000).toLocaleString() : 'Juste maintenant'}</span></div>
            {deal.aiAnalysis?.confidence && (<div className="flex items-center gap-2"><div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className="h-full bg-blue-500 rounded-full" style={{width: `${deal.aiAnalysis.confidence * 100}%`}} /></div><span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Confiance {Math.round(deal.aiAnalysis.confidence * 100)}%</span></div>)}
          </div>

          <div className="flex items-center gap-2">
            <button onClick={() => onToggleFavorite(deal.id, deal.isFavorite)} className={`flex items-center gap-2 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-sm ${deal.isFavorite ? 'bg-rose-100 text-rose-600' : 'bg-slate-100 text-slate-400 hover:text-rose-400'}`} title={deal.isFavorite ? "Retirer des favoris" : "Ajouter aux favoris"}><Heart size={14} fill={deal.isFavorite ? "currentColor" : "none"} /></button>
            
            {/* Bouton de réanalyse : Maintenant accessible même si rejeté */}
            <button
                ref={reanalysisButtonRef}
                onClick={handleReanalysisButtonClick}
                disabled={isAnalyzing}
                className={`flex items-center gap-2 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-sm relative overflow-hidden ${isAnalyzing ? 'bg-amber-100 text-amber-600 cursor-wait' : 'bg-slate-100 text-slate-400 hover:text-amber-500'}`}
                title="Relancer l'analyse"
            >
                {isAnalyzing ? (<RefreshCw size={14} className="animate-spin" />) : (<RefreshCw size={14} />)}
            </button>
            {isReanalysisMenuOpen && (
                <ReanalysisMenu
                    position={menuPosition}
                    buttonRef={reanalysisButtonRef}
                    onRetry={() => {
                        if (onRetry) onRetry(deal.id);
                        closeMenu();
                    }}
                    onForceExpert={() => {
                        if (onForceExpert) onForceExpert(deal.id);
                        closeMenu();
                    }}
                    onClose={closeMenu}
                />
            )}

            {deal.status !== 'rejected' && (<button onClick={() => onReject(deal.id)} className="flex items-center gap-2 bg-slate-100 hover:bg-rose-600 hover:text-white text-slate-600 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all group/btn shadow-sm" title="Rejeter l'annonce"><Ban size={14} /></button>)}
            <button onClick={() => onDelete(deal.id)} className="flex items-center gap-2 bg-red-50 hover:bg-red-600 hover:text-white text-red-600 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all group/btn shadow-sm" title="Supprimer définitivement"><Trash2 size={14} /></button>
            <button onClick={handleShare} className={`flex items-center gap-2 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-sm ${copied ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-100 text-slate-400 hover:text-blue-500'}`} title="Copier le lien de l'analyse">{copied ? <CheckCircle size={14} /> : <Share2 size={14} />}</button>
            <a href={deal.link} target="_blank" rel="noreferrer" className="flex items-center gap-2 bg-slate-100 hover:bg-blue-600 hover:text-white text-slate-600 px-6 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all group/btn shadow-sm">Voir sur Facebook <ExternalLink size={14} className="group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5 transition-transform" /></a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DealCard;
