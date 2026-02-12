import React, { useState, useEffect, useCallback } from 'react';
import { Search, Guitar, AlertTriangle, RefreshCw, XCircle, Settings, Trash2 } from 'lucide-react';

// Contexts & Main Hook
import { BotConfigProvider, useBotConfigContext } from './context/BotConfigContext';
import { DealsProvider, useDealsContext } from './context/DealsContext';
import { CitiesProvider } from './context/CitiesContext';
import { useAuth } from './hooks/useAuth';

// Components
import DebugStatus from './components/DebugStatus';
import ConfigPanel from './components/ConfigPanel';
import DealCard from './components/DealCard';
import MapView from './components/MapView';
import { FilterBar } from './components/FilterBar';
import DealModal from './components/DealModal';

const AppContent = () => {
  const { user, authStatus } = useAuth();
  
  const {
    configStatus, error, setError,
    isRefreshing, isCleaning,
    handleManualRefresh, handleManualCleanup
  } = useBotConfigContext();

  const {
    loading, dbStatus,
    filteredDeals,
    filterProps,
    dealActions
  } = useDealsContext();

  const [showConfig, setShowConfig] = useState(false);
  const [viewMode, setViewMode] = useState('LIST');
  const [selectedDeal, setSelectedDeal] = useState(null);

  useEffect(() => {
    if (loading) return;
    const params = new URLSearchParams(window.location.search);
    const dealId = params.get('dealId');
    if (dealId) {
      const deal = filteredDeals.find(d => d.id === dealId);
      if (deal) setSelectedDeal(deal);
    }
  }, [loading, filteredDeals]);

  const handleCloseModal = useCallback(() => setSelectedDeal(null), []);

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
            <h3 className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">Système</h3>
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
                <DealCard 
                    key={deal.id} 
                    deal={deal} 
                    onRetry={() => dealActions.handleRetryAnalysis(deal.id)}
                    onForceExpert={() => dealActions.handleForceExpertAnalysis(deal.id)}
                    onReject={() => dealActions.handleRejectDeal(deal.id)}
                    onToggleFavorite={() => dealActions.handleToggleFavorite(deal.id, deal.isFavorite)}
                    onDelete={() => dealActions.handleDeleteDeal(deal.id)}
                />
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

      <DealModal 
        deal={selectedDeal}
        onClose={handleCloseModal}
        onRetry={() => dealActions.handleRetryAnalysis(selectedDeal.id)}
        onForceExpert={() => dealActions.handleForceExpertAnalysis(selectedDeal.id)}
        onReject={() => dealActions.handleRejectDeal(selectedDeal.id)}
        onToggleFavorite={() => dealActions.handleToggleFavorite(selectedDeal.id, selectedDeal.isFavorite)}
        onDelete={() => dealActions.handleDeleteDeal(selectedDeal.id)}
      />
    </div>
  );
};

const App = () => (
  <BotConfigProvider>
    <DealsProvider>
      <CitiesProvider>
        <AppContent />
      </CitiesProvider>
    </DealsProvider>
  </BotConfigProvider>
);

export default App;
