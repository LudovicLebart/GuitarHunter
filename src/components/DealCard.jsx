import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { MapPin, Guitar, TrendingUp, Activity, Sparkles, Clock, Heart, RefreshCw, Ban, Share2, ExternalLink, CheckCircle, Trash2, BrainCircuit } from 'lucide-react';
import ImageGallery from './ImageGallery';
import VerdictBadge from './VerdictBadge';
import SimpleMarkdown from './SimpleMarkdown';
import CollapsibleSection from './CollapsibleSection';

const ExpertMenu = ({ position, onExpertClick, onClose }) => {
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  if (!position) return null;

  return createPortal(
    <div 
      ref={menuRef}
      style={{ 
        position: 'absolute', 
        top: position.top - 60, // Positionne le menu au-dessus du bouton
        left: position.left + (position.width / 2), 
        transform: 'translateX(-50%)',
        zIndex: 9999 
      }}
      className="animate-in slide-in-from-bottom-2 fade-in duration-200"
    >
      <button 
        onClick={(e) => { e.stopPropagation(); onExpertClick(); }}
        className="flex items-center justify-center gap-2 px-4 py-3 rounded-2xl text-xs font-black uppercase tracking-widest bg-purple-600 text-white shadow-xl hover:bg-purple-700 transition-colors whitespace-nowrap"
      >
        <BrainCircuit size={14} /> Expert
      </button>
    </div>,
    document.body
  );
};

const DealCard = React.memo(({ deal, filterType, onRetry, onForceExpert, onReject, onToggleFavorite, onDelete }) => {
  const [copied, setCopied] = useState(false);
  const [showExpertOption, setShowExpertOption] = useState(false);
  const [menuPosition, setMenuPosition] = useState(null);
  const timerRef = useRef(null);
  const buttonRef = useRef(null);

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
    if (['analyzing', 'retry_analysis', 'retry_analysis_expert'].includes(deal.status)) {
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
  const isAnalyzing = ['retry_analysis', 'retry_analysis_expert', 'analyzing'].includes(deal.status);

  const handleButtonDown = () => {
    timerRef.current = setTimeout(() => {
      if (buttonRef.current) {
        const rect = buttonRef.current.getBoundingClientRect();
        setMenuPosition({
          top: rect.top + window.scrollY,
          left: rect.left + window.scrollX,
          width: rect.width
        });
        setShowExpertOption(true);
      }
    }, 500);
  };

  const handleButtonUp = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  };

  const handleRetryClick = () => {
    if (!showExpertOption) {
        if (onRetry) onRetry(deal.id);
    } else {
        if (onRetry) onRetry(deal.id);
        setShowExpertOption(false);
    }
  };

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
            {deal.aiAnalysis?.classification && (<div className="mt-2 flex items-center gap-2 text-purple-600 bg-purple-50 px-3 py-1 rounded-full text-xs font-bold"><Guitar size={12} /><span>{deal.aiAnalysis.classification}</span></div>)}
          </div>
          <div className="text-right flex flex-col items-end">
            <div className="bg-slate-900 text-white px-4 py-2 rounded-2xl shadow-xl"><span className="block text-[8px] font-black uppercase text-slate-400 tracking-tighter">Prix Demandé</span><span className="text-2xl font-black tabular-nums">{deal.price} $</span></div>
            {deal.aiAnalysis?.estimated_value && deal.status !== 'rejected' && (<div className="mt-2 text-emerald-600 flex items-center gap-1 font-bold text-xs bg-emerald-50 px-2 py-1 rounded-lg"><TrendingUp size={12} /> Val. Est: {deal.aiAnalysis.estimated_value}$</div>)}
            {deal.aiAnalysis?.estimated_value_after_repair > 0 && deal.status !== 'rejected' && (<div className="mt-1 text-purple-600 flex items-center gap-1 font-bold text-xs bg-purple-50 px-2 py-1 rounded-lg"><Activity size={12} /> Val. Revente: {deal.aiAnalysis.estimated_value_after_repair}$</div>)}
          </div>
        </div>

        <div className="relative mb-6">
          <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-full ${isExpertAnalysis ? 'bg-purple-500' : 'bg-blue-100'}`} />
          <div className="pl-5 py-1">
            <div className={`flex items-center gap-1.5 mb-2 ${isExpertAnalysis ? 'text-purple-600' : 'text-blue-600'}`}><Sparkles size={14} /><span className="text-[10px] font-black uppercase tracking-widest">{modelName}</span></div>
            <div className="mt-2">
              {deal.aiAnalysis?.reasoning ? (() => {
                  const reasoningText = deal.aiAnalysis.reasoning;
                  const summaryMatch = reasoningText.match(/### RÉSUMÉ\n([\s\S]*?)(?=\n###|$)/);
                  const summary = summaryMatch ? summaryMatch[1].trim() : reasoningText;
                  const detailsMatch = reasoningText.match(/(### (?!RÉSUMÉ)[\s\S]*)/);
                  const details = detailsMatch ? detailsMatch[1].trim() : null;
                  return (<><SimpleMarkdown text={summary} />{details && (<CollapsibleSection title="Voir l'analyse détaillée"><SimpleMarkdown text={details} /></CollapsibleSection>)}</>);
              })() : (<p className="text-slate-400 italic text-sm">Analyse de l'état et de la valeur en cours par l'intelligence artificielle...</p>)}
            </div>
          </div>
        </div>

        <div className="mt-auto pt-6 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2 text-slate-400 text-[10px] font-bold"><Clock size={14} /><span className="uppercase tracking-widest">{deal.timestamp?.seconds ? new Date(deal.timestamp.seconds * 1000).toLocaleString() : 'Juste maintenant'}</span></div>
            {deal.aiAnalysis?.confidence && (<div className="flex items-center gap-2"><div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className="h-full bg-blue-500 rounded-full" style={{width: `${deal.aiAnalysis.confidence}%`}} /></div><span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Confiance {deal.aiAnalysis.confidence}%</span></div>)}
          </div>

          <div className="flex items-center gap-2">
            <button onClick={() => onToggleFavorite(deal.id, deal.isFavorite)} className={`flex items-center gap-2 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-sm ${deal.isFavorite ? 'bg-rose-100 text-rose-600' : 'bg-slate-100 text-slate-400 hover:text-rose-400'}`} title={deal.isFavorite ? "Retirer des favoris" : "Ajouter aux favoris"}><Heart size={14} fill={deal.isFavorite ? "currentColor" : "none"} /></button>
            {deal.status !== 'rejected' && (
                <>
                    <button 
                        ref={buttonRef}
                        onMouseDown={handleButtonDown} 
                        onMouseUp={handleButtonUp} 
                        onMouseLeave={handleButtonUp} 
                        onTouchStart={handleButtonDown} 
                        onTouchEnd={handleButtonUp} 
                        onClick={handleRetryClick} 
                        disabled={isAnalyzing}
                        className={`flex items-center gap-2 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-sm relative overflow-hidden ${isAnalyzing ? 'bg-amber-100 text-amber-600 cursor-wait' : isExpertAnalysis ? 'bg-purple-50 text-purple-600 hover:bg-purple-100 border border-purple-100' : 'bg-slate-100 text-slate-400 hover:text-amber-500'}`} 
                        title="Clic: Relancer / Maintenir: Options Expert"
                    >
                        {isAnalyzing ? (<RefreshCw size={14} className="animate-spin" />) : (<><RefreshCw size={14} /><span className="absolute bottom-0 left-0 h-0.5 bg-purple-500 transition-all duration-[500ms] ease-linear" style={{ width: showExpertOption ? '100%' : '0%' }} /></>)}
                    </button>
                    {showExpertOption && (
                        <ExpertMenu 
                            position={menuPosition} 
                            onExpertClick={() => {
                                if (onForceExpert) onForceExpert(deal.id);
                                setShowExpertOption(false);
                            }}
                            onClose={() => setShowExpertOption(false)}
                        />
                    )}
                </>
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
});

export default DealCard;
