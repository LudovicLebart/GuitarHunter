import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { XCircle } from 'lucide-react';
import DealCard from './DealCard';

const DealModal = ({ deal, onClose, onRetry, onReject, onToggleFavorite, onDelete }) => {
  const [zoomLevel, setZoomLevel] = useState(0.85);

  if (!deal) return null;

  const handleClose = () => {
    const url = new URL(window.location);
    url.searchParams.delete('dealId');
    window.history.pushState({}, '', url);
    onClose();
  };

  return createPortal(
    <div className="fixed inset-0 bg-black/80 z-50 flex flex-col items-center overflow-y-auto animate-in fade-in backdrop-blur-sm pt-24 pb-12" onClick={handleClose}>
      <div className="fixed top-6 z-50 flex items-center gap-4" onClick={(e) => e.stopPropagation()}>
        <div className="bg-slate-900/90 text-white px-4 py-2 rounded-full flex items-center gap-3 shadow-2xl border border-white/10">
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Zoom</span>
          <input type="range" min="0.5" max="1.1" step="0.1" value={zoomLevel} onChange={(e) => setZoomLevel(parseFloat(e.target.value))} className="w-24 accent-blue-500 h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer" />
          <span className="text-[10px] font-mono w-8 text-right text-blue-400">{Math.round(zoomLevel * 100)}%</span>
        </div>
        <button onClick={handleClose} className="bg-white text-slate-900 rounded-full p-2.5 shadow-2xl hover:bg-rose-500 hover:text-white transition-all"><XCircle size={20} /></button>
      </div>
      <div className="relative transition-transform duration-200 ease-out origin-top" style={{ transform: `scale(${zoomLevel})`, width: '100%', maxWidth: '60rem', padding: '1rem' }} onClick={(e) => e.stopPropagation()}>
        <DealCard 
            key={deal.id} 
            deal={deal} 
            onRetry={onRetry} 
            onReject={onReject} 
            onToggleFavorite={onToggleFavorite}
            onDelete={onDelete}
        />
      </div>
    </div>,
    document.body
  );
};

export default DealModal;
