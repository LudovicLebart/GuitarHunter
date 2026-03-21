import React, { useCallback } from 'react';
import { AlertTriangle, XCircle } from 'lucide-react';

import { AuthProvider } from './context/AuthContext';
import { BotConfigProvider, useBotConfigContext } from './context/BotConfigContext';
import { DealsProvider } from './context/DealsContext';
import { CitiesProvider } from './context/CitiesContext';
import { useAuth } from './hooks/useAuth';

import Dashboard from './components/Dashboard';
import LoginPage from './components/LoginPage';

const AppContent = () => {
  const { user, authStatus } = useAuth();
  const { error, setError } = useBotConfigContext();

  if (authStatus.status === 'loading') {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-slate-400 text-sm">Vérification de la session...</div>
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return (
    <div className="font-sans text-slate-900 selection:bg-blue-100 min-h-screen bg-slate-950">
      <Dashboard onClose={() => { }} />

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
    </div>
  );
};

const App = () => (
    <AuthProvider>
      <BotConfigProvider>
        <DealsProvider>
          <CitiesProvider>
            <AppContent />
          </CitiesProvider>
        </DealsProvider>
      </BotConfigProvider>
    </AuthProvider>
);

export default App;
