import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  Search, Guitar,
  AlertTriangle, RefreshCw, XCircle,
  Settings, Trash2
} from 'lucide-react';

// Contexts
import { BotConfigProvider, useBotConfigContext } from './context/BotConfigContext';
import { DealsProvider, useDealsContext } from './context/DealsContext';
import { CitiesProvider } from './context/CitiesContext';

// Hooks
import { useAuth } from './hooks/useAuth';
import { useFilters } from './hooks/useFilters';

// Components
import DebugStatus from './components/DebugStatus';
import ConfigPanel from './components/ConfigPanel';
import DealCard from './components/DealCard';
import MapView from './components/MapView';
import { FilterBar } from './components/FilterBar';

const AppContent = () => {
  const { user, authStatus } = useAuth();
  
  // Consommation des contextes
  const {
    configStatus, error, setError,
    isRefreshing, isCleaning,
    handleManualRefresh, handleManualCleanup
  } = useBotConfigContext();

  const {
    deals, loading, dbStatus,
    handleRejectDeal, handleRetryAnalysis, handleToggleFavorite
  } = useDealsContext();

  const {
    filteredDeals,
    ...filterProps
  } = useFilters(deals);

  // UI States
  const [showConfig, setShowConfig] = useState(false);
  const [viewMode, setViewMode] = useState('LIST');
  const [selectedDeal, setSelectedDeal] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(0.85);

  // Deep Linking
  useEffect(() => {
    if (loading) return;
    const params = new URLSearchParams(window.location.search);
    const dealId = params.get('dealId');
    if (dealId) {
      const deal = deals.find(d => d.id === dealId);
      if (deal) {
        setSelectedDeal(deal);
      }
    }
  }, [loading, deals]);

  const handleCloseModal = useCallback(() => {
    setSelectedDeal(null);
    const url = new URL(window.location);
    url.searchParams.delete('dealId');
    window.history.pushState({}, '', url);
  }, []);

  return (
    <div className="min-h-screen bg-[#F8FAFC] font-sans text-slate-900 selection:bg-blue-100">
      <nav className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-2 rounded-xl text-white shadow-lg shadow-blue-200"><Guitar size={24} /></div>
            <div>
              <h1 className="text-lg font-black tracking-tight text-slate-800">GUITAR HUNTER <span className="text-blue-600">AI</span></h1>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest leading-none">Scraper & Gemini Evaluator</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleManualCleanup} disabled={isCleaning} className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${isCleaning ? 'bg-slate-100 text-slate-400' : 'bg-amber-50 text-amber-600 hover:bg-amber-100 shadow-sm border border-amber-100'}`}>
              <Trash2 size={14} className={isCleaning ? "animate-bounce" : ""} />
              <span className="hidden sm:inline">{isCleaning ? 'Vérification...' : 'Vérifier Stocks'}</span>
            </button>
            <button onClick={handleManualRefresh} disabled={isRefreshing} className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${isRefreshing ? 'bg-slate-100 text-slate-400' : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100 shadow-sm border border-emerald-100'}`}>
              <RefreshCw size={14} className={isRefreshing ? "animate-spin" : ""} />
              <span className="hidden sm:inline">{isRefreshing ? 'Scan en cours...' : 'Scanner maintenant'}</span>
            </button>
            <button onClick={() => setShowConfig(!showConfig)} className={`p-2 rounded-xl transition-colors ${showConfig ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}><Settings size={20} /></button>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 py-8 grid grid-cols-1 lg:grid-cols-4 gap-8">
        <aside className="lg:col-span-1 space-y-6">
          <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-200">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Système</h3>
              <div className="flex items-center gap-1.5 bg-emerald-50 text-emerald-600 px-2 py-1 rounded-lg text-[9px] font-bold"><div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> LIVE</div>
            </div>
            <div className="space-y-1">
              <DebugStatus label="Auth" status={authStatus.status} details={authStatus.msg} />
              <DebugStatus label="Engine" status={configStatus.status} details="Python Bot Connected" />
              <DebugStatus label="Database" status={dbStatus.status} details={dbStatus.msg} />
            </div>
          </div>
          
          <ConfigPanel showConfig={showConfig} onClose={() => setShowConfig(false)} />
        </aside>

        <main className="lg:col-span-3 space-y-6">
          <FilterBar {...filterProps} viewMode={viewMode} setViewMode={setViewMode} />

          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center bg-white rounded-3xl border border-slate-200">
              <RefreshCw className="text-blue-600 animate-spin mb-4" size={40} />
              <p className="text-slate-400 font-bold uppercase tracking-widest text-xs">Synchronisation Firestore...</p>
            </div>
          ) : filteredDeals.length === 0 ? (
            <div className="py-20 flex flex-col items-center justify-center bg-white rounded-3xl border border-dashed border-slate-200">
              <div className="bg-slate-50 p-6 rounded-full mb-4"><Search className="text-slate-200" size={48} /></div>
              <h3 className="text-lg font-black text-slate-400 uppercase tracking-tight italic">Aucun trésor trouvé</h3>
              <p className="text-slate-400 text-xs mt-1">Ajustez vos filtres ou lancez un scan manuel</p>
            </div>
          ) : viewMode === 'MAP' ? (
             <MapView deals={filteredDeals} onDealSelect={setSelectedDeal} />
          ) : (
            <div className="grid grid-cols-1 gap-6">
              {filteredDeals.map((deal) => (
                <DealCard key={deal.id} deal={deal} onRetry={handleRetryAnalysis} onReject={handleRejectDeal} onToggleFavorite={handleToggleFavorite} />
              ))}
            </div>
          )}
        </main>
      </div>

      {error && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-10">
          <div className="bg-rose-600 text-white px-6 py-4 rounded-2xl shadow-2xl shadow-rose-200 flex items-center gap-4">
            <AlertTriangle size={24} />
            <div>
              <p className="font-black uppercase text-[10px] tracking-widest leading-none mb-1 opacity-80">Erreur Détectée</p>
              <p className="text-sm font-bold">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="ml-4 hover:bg-white/20 p-1 rounded-lg transition-colors"><XCircle size={20} /></button>
          </div>
        </div>
      )}

      {selectedDeal && createPortal(
        <div className="fixed inset-0 bg-black/80 z-50 flex flex-col items-center overflow-y-auto animate-in fade-in backdrop-blur-sm pt-24 pb-12" onClick={handleCloseModal}>
          <div className="fixed top-6 z-50 flex items-center gap-4" onClick={(e) => e.stopPropagation()}>
            <div className="bg-slate-900/90 text-white px-4 py-2 rounded-full flex items-center gap-3 shadow-2xl border border-white/10">
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Zoom</span>
              <input type="range" min="0.5" max="1.1" step="0.1" value={zoomLevel} onChange={(e) => setZoomLevel(parseFloat(e.target.value))} className="w-24 accent-blue-500 h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer" />
              <span className="text-[10px] font-mono w-8 text-right text-blue-400">{Math.round(zoomLevel * 100)}%</span>
            </div>
            <button onClick={handleCloseModal} className="bg-white text-slate-900 rounded-full p-2.5 shadow-2xl hover:bg-rose-500 hover:text-white transition-all"><XCircle size={20} /></button>
          </div>
          <div className="relative transition-transform duration-200 ease-out origin-top" style={{ transform: `scale(${zoomLevel})`, width: '100%', maxWidth: '60rem', padding: '1rem' }} onClick={(e) => e.stopPropagation()}>
            <DealCard key={selectedDeal.id} deal={selectedDeal} onRetry={handleRetryAnalysis} onReject={handleRejectDeal} onToggleFavorite={handleToggleFavorite} />
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

const App = () => {
  return (
    <BotConfigProvider>
      <DealsProvider>
        <CitiesProvider>
          <AppContent />
        </CitiesProvider>
      </DealsProvider>
    </BotConfigProvider>
  );
};

export default App;
