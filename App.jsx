import React, { useState, useEffect } from 'react';
import {
  Search, ExternalLink, Guitar,
  AlertTriangle, RefreshCw, CheckCircle, XCircle, 
  Activity, ChevronDown, ChevronUp, Settings, Clock
} from 'lucide-react';

// --- Configuration Firebase ---
import { initializeApp } from 'firebase/app';
import {
  getFirestore, collection, onSnapshot, doc, getDoc, setDoc
} from 'firebase/firestore';
import {
  getAuth, signInAnonymously, onAuthStateChanged
} from 'firebase/auth';

// --- CONFIGURATION FIREBASE ---
const firebaseConfig = {
  apiKey: "AIzaSyDtr1pAc2oTWxnDyMHUclkt4G34qdAAAXw",
  authDomain: "guitarehunter-d6e35.firebaseapp.com",
  projectId: "guitarehunter-d6e35",
  storageBucket: "guitarehunter-d6e35.firebasestorage.app",
  messagingSenderId: "832778342585",
  appId: "1:832778342585:web:ff1f8ccd8daf15be60cb68",
  measurementId: "G-RREDDZGFMR"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

// --- CONSTANTES ---
const PYTHON_APP_ID = "c_5d118e719dbddbfc_index.html-217";
const PYTHON_USER_ID = "00737242777130596039";
const appId = PYTHON_APP_ID;

// --- COMPOSANTS UTILITAIRES ---
const DealScore = ({ score }) => {
  const s = parseFloat(score) || 0;
  const getColor = (val) => {
    if (val >= 8) return 'bg-green-100 text-green-700 border-green-200';
    if (val >= 6) return 'bg-yellow-100 text-yellow-700 border-yellow-200';
    return 'bg-red-100 text-red-700 border-red-200';
  };
  return (
    <div className={`px-3 py-1 rounded-full border text-sm font-bold ${getColor(s)}`}>
      Score Gemini: {s}/10
    </div>
  );
};

const DebugStatus = ({ label, status, details }) => (
  <div className="flex items-start gap-2 text-[10px] font-mono mb-1">
    <div className="mt-0.5">
      {status === 'loading' && <RefreshCw size={10} className="animate-spin text-blue-500" />}
      {status === 'success' && <CheckCircle size={10} className="text-green-500" />}
      {status === 'error' && <XCircle size={10} className="text-red-500" />}
      {status === 'pending' && <div className="w-2.5 h-2.5 rounded-full border border-slate-300" />}
    </div>
    <div>
      <span className={`font-bold ${status === 'error' ? 'text-red-600' : 'text-slate-600'}`}>{label}</span>
      {details && <p className="text-slate-400 leading-tight mt-0.5">{details}</p>}
    </div>
  </div>
);

const App = () => {
  const [user, setUser] = useState(null);
  const [deals, setDeals] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // UI States
  const [showDebug, setShowDebug] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  
  // Config States
  const [prompt, setPrompt] = useState("Evalue cette guitare Au quebec (avec le prix).");
  const [isEditingPrompt, setIsEditingPrompt] = useState(false);
  const [scanConfig, setScanConfig] = useState({ maxAds: 5, frequency: 60 });
  const [isEditingConfig, setIsEditingConfig] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Diagnostic State
  const [diag, setDiag] = useState({
    auth: { status: 'loading', msg: 'Connexion...' },
    appDoc: { status: 'pending', msg: 'En attente' },
    userDoc: { status: 'pending', msg: 'En attente' },
    collection: { status: 'pending', msg: 'En attente' }
  });

  // 1. Auth
  useEffect(() => {
    const initAuth = async () => {
      try {
        await signInAnonymously(auth);
        setDiag(prev => ({ ...prev, auth: { status: 'success', msg: 'Authentifié (Anonyme)' } }));
      } catch (err) {
        console.error("Auth Error:", err);
        setDiag(prev => ({ ...prev, auth: { status: 'error', msg: err.message } }));
        setError(`Erreur Auth: ${err.message}`);
      }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  // 2. Diagnostics & Load Config
  useEffect(() => {
    if (!user) return;

    const runDiagnostics = async () => {
      const targetUserId = PYTHON_USER_ID;

      // App Doc
      setDiag(prev => ({ ...prev, appDoc: { status: 'loading', msg: `Vérif artifacts/${appId}...` } }));
      try {
        const appDocRef = doc(db, 'artifacts', appId);
        const appDocSnap = await getDoc(appDocRef);
        if (appDocSnap.exists()) {
          setDiag(prev => ({ ...prev, appDoc: { status: 'success', msg: 'Document App trouvé' } }));
        } else {
          setDiag(prev => ({ ...prev, appDoc: { status: 'error', msg: 'Structure racine absente' } }));
        }
      } catch (e) {
        setDiag(prev => ({ ...prev, appDoc: { status: 'error', msg: e.message } }));
      }

      // User Doc & Config
      setDiag(prev => ({ ...prev, userDoc: { status: 'loading', msg: `Vérif users/${targetUserId}...` } }));
      try {
        const userDocRef = doc(db, 'artifacts', appId, 'users', targetUserId);
        const userDocSnap = await getDoc(userDocRef);
        if (userDocSnap.exists()) {
          setDiag(prev => ({ ...prev, userDoc: { status: 'success', msg: 'Dossier Python trouvé' } }));
          const userData = userDocSnap.data();
          if (userData) {
             if (userData.prompt) setPrompt(userData.prompt);
             if (userData.scanConfig) setScanConfig(prev => ({ ...prev, ...userData.scanConfig }));
          }
        } else {
          setDiag(prev => ({ ...prev, userDoc: { status: 'error', msg: 'Dossier Python absent' } }));
        }
      } catch (e) {
        setDiag(prev => ({ ...prev, userDoc: { status: 'error', msg: e.message } }));
      }
    };

    runDiagnostics();
  }, [user]);

  // 3. Realtime Deals
  useEffect(() => {
    if (!user) return;

    setLoading(true);
    const targetUserId = PYTHON_USER_ID;
    const collectionRef = collection(db, 'artifacts', appId, 'users', targetUserId, 'guitar_deals');

    setDiag(prev => ({ ...prev, collection: { status: 'loading', msg: 'Écoute lancée...' } }));

    const unsubscribe = onSnapshot(collectionRef, (snapshot) => {
      if (snapshot.empty) {
        setDiag(prev => ({ ...prev, collection: { status: 'error', msg: 'Collection vide' } }));
      } else {
        setDiag(prev => ({ ...prev, collection: { status: 'success', msg: `${snapshot.size} annonces` } }));
      }

      const dealsData = [];
      snapshot.forEach((doc) => {
        dealsData.push({ id: doc.id, ...doc.data() });
      });

      dealsData.sort((a, b) => (b.timestamp?.seconds || 0) - (a.timestamp?.seconds || 0));
      setDeals(dealsData);
      setLoading(false);
      setError(null);
    }, (err) => {
      console.error("Firestore Error:", err);
      setDiag(prev => ({ ...prev, collection: { status: 'error', msg: err.message } }));
      setError(`Erreur de données: ${err.message}`);
      setLoading(false);
    });

    return () => unsubscribe();
  }, [user]);

  // Handlers
  const handleSavePrompt = async () => {
      try {
          const targetUserId = PYTHON_USER_ID;
          const userDocRef = doc(db, 'artifacts', appId, 'users', targetUserId);
          await setDoc(userDocRef, { prompt: prompt }, { merge: true });
          setIsEditingPrompt(false);
      } catch (e) {
          console.error("Erreur sauvegarde prompt :", e);
          setError("Impossible de sauvegarder le prompt.");
      }
  };

  const handleSaveConfig = async () => {
      try {
          const targetUserId = PYTHON_USER_ID;
          const userDocRef = doc(db, 'artifacts', appId, 'users', targetUserId);
          await setDoc(userDocRef, { scanConfig: scanConfig }, { merge: true });
          setIsEditingConfig(false);
      } catch (e) {
          console.error("Erreur sauvegarde config :", e);
          setError("Impossible de sauvegarder la config.");
      }
  };

  const handleManualRefresh = async () => {
      try {
          setIsRefreshing(true);
          const targetUserId = PYTHON_USER_ID;
          const userDocRef = doc(db, 'artifacts', appId, 'users', targetUserId);
          await setDoc(userDocRef, { forceRefresh: Date.now() }, { merge: true });
          setTimeout(() => setIsRefreshing(false), 5000);
      } catch (e) {
          console.error("Erreur refresh :", e);
          setIsRefreshing(false);
      }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-8 font-sans text-slate-900 text-[14px]">
      
      {/* HEADER */}
      <header className="max-w-6xl mx-auto flex flex-col md:flex-row md:items-start justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold flex items-center gap-2 italic tracking-tight">
            <Guitar className="text-blue-600" size={32} />
            GUITAR HUNTER <span className="text-blue-600 underline">AI</span>
          </h1>
          <div className="mt-2 flex flex-col gap-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">
             <div className="flex items-center gap-4">
                 <span>Target: <span className="text-blue-600">{PYTHON_USER_ID}</span></span>
                 <span className="flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-green-500" /> Connecté</span>
             </div>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-4">
            
            {/* CONFIGURATION PANEL */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 min-w-[250px] md:w-[350px] overflow-hidden">
              <button 
                onClick={() => setShowConfig(!showConfig)}
                className="w-full p-3 flex items-center justify-between bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center gap-1">
                  <Settings size={12} /> Configuration
                </h4>
                {showConfig ? <ChevronUp size={14} className="text-slate-400"/> : <ChevronDown size={14} className="text-slate-400"/>}
              </button>
              
              {showConfig && (
                <div className="p-4 border-t border-slate-100">
                    {/* Prompt */}
                    <div className="mb-4 pb-4 border-b border-slate-100">
                        <div className="flex items-center justify-between mb-2">
                            <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Prompt IA</h5>
                            <button onClick={() => setIsEditingPrompt(!isEditingPrompt)} className="text-blue-600 text-[10px] font-bold uppercase">
                                {isEditingPrompt ? 'Fermer' : 'Modifier'}
                            </button>
                        </div>
                        {isEditingPrompt ? (
                            <div className="flex flex-col gap-2">
                                <textarea 
                                    value={prompt}
                                    onChange={(e) => setPrompt(e.target.value)}
                                    className="w-full p-2 bg-slate-50 border border-slate-200 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[80px]"
                                    placeholder="Instructions pour l'IA..."
                                />
                                <button onClick={handleSavePrompt} className="bg-blue-600 text-white py-1 rounded text-[10px] font-bold uppercase">Sauvegarder</button>
                            </div>
                        ) : (
                            <p className="text-xs text-slate-600 italic line-clamp-3">"{prompt}"</p>
                        )}
                    </div>

                    {/* Scan Config */}
                    <div className="mb-4 pb-4 border-b border-slate-100">
                        <div className="flex items-center justify-between mb-2">
                            <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Recherche</h5>
                            <button onClick={() => setIsEditingConfig(!isEditingConfig)} className="text-blue-600 text-[10px] font-bold uppercase">
                                {isEditingConfig ? 'Fermer' : 'Modifier'}
                            </button>
                        </div>
                        {isEditingConfig ? (
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="block text-[9px] font-bold text-slate-400 uppercase mb-1">Max Annonces</label>
                                    <input 
                                        type="number" 
                                        value={scanConfig?.maxAds || 5}
                                        onChange={(e) => setScanConfig({...scanConfig, maxAds: parseInt(e.target.value) || 5})}
                                        className="w-full p-1 bg-slate-50 border border-slate-200 rounded text-xs"
                                    />
                                </div>
                                <div>
                                    <label className="block text-[9px] font-bold text-slate-400 uppercase mb-1">Fréquence (min)</label>
                                    <input 
                                        type="number" 
                                        value={scanConfig?.frequency || 60}
                                        onChange={(e) => setScanConfig({...scanConfig, frequency: parseInt(e.target.value) || 60})}
                                        className="w-full p-1 bg-slate-50 border border-slate-200 rounded text-xs"
                                    />
                                </div>
                                <button onClick={handleSaveConfig} className="col-span-2 bg-blue-600 text-white py-1 rounded text-[10px] font-bold uppercase mt-1">Sauvegarder</button>
                            </div>
                        ) : (
                            <div className="flex justify-between text-xs text-slate-600">
                                <span>Max: <b>{scanConfig?.maxAds || 5}</b></span>
                                <span>Freq: <b>{scanConfig?.frequency || 60} min</b></span>
                            </div>
                        )}
                    </div>

                    {/* Refresh Button */}
                    <button 
                        onClick={handleManualRefresh}
                        disabled={isRefreshing}
                        className={`w-full py-2 rounded-lg text-[10px] font-bold uppercase tracking-widest flex items-center justify-center gap-2 ${isRefreshing ? 'bg-slate-100 text-slate-400' : 'bg-green-100 text-green-700 hover:bg-green-200'}`}
                    >
                        <RefreshCw size={12} className={isRefreshing ? "animate-spin" : ""} />
                        {isRefreshing ? "Scan en cours..." : "Lancer Scan Manuel"}
                    </button>
                </div>
              )}
            </div>

            {/* SYSTEM STATUS PANEL */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 min-w-[250px] overflow-hidden">
              <button 
                onClick={() => setShowDebug(!showDebug)}
                className="w-full p-3 flex items-center justify-between bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center gap-1">
                  <Activity size={12} /> État du Système
                </h4>
                {showDebug ? <ChevronUp size={14} className="text-slate-400"/> : <ChevronDown size={14} className="text-slate-400"/>}
              </button>
              
              {showDebug && (
                <div className="p-4 border-t border-slate-100">
                  <div className="mb-3 text-[10px] text-slate-400">
                    <div>App ID: <span className="text-slate-600 font-mono">{PYTHON_APP_ID}</span></div>
                    <div className="mt-1">Path: <span className="text-slate-500 font-mono break-all">artifacts/{PYTHON_APP_ID}/users/{PYTHON_USER_ID}/guitar_deals</span></div>
                  </div>
                  <DebugStatus label="Authentification" status={diag.auth.status} details={diag.auth.msg} />
                  <DebugStatus label="Structure App" status={diag.appDoc.status} details={diag.appDoc.msg} />
                  <DebugStatus label="Structure User" status={diag.userDoc.status} details={diag.userDoc.msg} />
                  <DebugStatus label="Base de données" status={diag.collection.status} details={diag.collection.msg} />
                </div>
              )}
            </div>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main className="max-w-6xl mx-auto">
        {deals.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-3xl border-2 border-dashed border-slate-200 shadow-inner">
            <Search className="mx-auto text-slate-100 mb-4" size={80} />
            <h2 className="text-xl text-slate-400 font-black uppercase tracking-tighter italic">Recherche de pépites...</h2>
            <p className="mt-4 text-[11px] text-slate-400 font-medium">
              Vérifiez que votre script Python utilise bien l'App ID : <br/>
              <code className="bg-slate-100 px-2 py-1 rounded mt-2 inline-block text-blue-600">{appId}</code>
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6">
            {deals.map((deal) => (
              <div key={deal.id} className="bg-white rounded-3xl shadow-sm border border-slate-200 overflow-hidden flex flex-col md:flex-row hover:shadow-xl transition-all duration-300">
                <div className="md:w-72 h-56 md:h-auto bg-slate-100 relative">
                  <img src={deal.imageUrl} className="w-full h-full object-cover" alt="guitar" />
                  <div className="absolute top-4 left-4">
                    <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest text-white shadow-lg ${ (deal.aiAnalysis?.verdict === 'GOOD_DEAL' || deal.verdict === 'GOOD_DEAL') ? 'bg-green-500' : 'bg-slate-800/80'}`}>
                      {deal.aiAnalysis?.verdict || deal.verdict || 'ANALYSE'}
                    </span>
                  </div>
                </div>
                <div className="flex-1 p-8 flex flex-col justify-between">
                  <div>
                    <div className="flex justify-between items-start mb-4">
                      <h2 className="text-2xl font-black text-slate-800 leading-tight pr-4 capitalize">{deal.title || "Modèle Non Précisé"}</h2>
                      <div className="text-right">
                        <div className="flex flex-col items-end">
                            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-0.5">Prix Demandé</span>
                            <p className="text-3xl font-black text-blue-600 tracking-tighter">{deal.price} $</p>
                        </div>
                        <div className="mt-2 flex flex-col items-end">
                            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-0.5">Valeur Estimée</span>
                            <p className="text-xl font-black text-slate-700">{deal.aiAnalysis?.estimated_value || deal.estimated_value || "?"} $</p>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 mb-6">
                       <DealScore score={(deal.aiAnalysis?.confidence || deal.confidence || 0) / 10} />
                       <div className="h-1.5 flex-1 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500 transition-all duration-1000" style={{width: `${deal.aiAnalysis?.confidence || deal.confidence || 0}%`}}></div>
                       </div>
                    </div>

                    <div className="bg-slate-50 p-5 rounded-2xl border border-slate-100 italic">
                      <p className="text-slate-600 text-sm font-medium italic">"{deal.aiAnalysis?.reasoning || deal.reasoning || "Analyse Gemini en cours..."}"</p>
                    </div>
                  </div>

                  <div className="mt-8 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-slate-300 font-bold text-[10px]">
                      <Clock size={14} />
                      <span className="uppercase tracking-widest">{deal.timestamp?.seconds ? new Date(deal.timestamp.seconds * 1000).toLocaleTimeString() : 'Maintenant'}</span>
                    </div>
                    <a href={deal.link} target="_blank" className="bg-slate-900 text-white px-8 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] hover:bg-blue-600 transition-all shadow-lg flex items-center gap-2">
                      Voir sur Marketplace <ExternalLink size={14} />
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {error && (
        <div className="fixed bottom-6 right-6 bg-red-600 text-white px-6 py-4 rounded-2xl shadow-2xl text-xs font-bold flex items-center gap-3 animate-pulse">
          <AlertTriangle size={20} />
          <p>{error}</p>
        </div>
      )}
    </div>
  );
};

export default App;
