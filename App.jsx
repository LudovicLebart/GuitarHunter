import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search, ExternalLink, Guitar,
  AlertTriangle, RefreshCw, CheckCircle, XCircle,
  Activity, Settings, Clock,
  MapPin, Sparkles, TrendingUp, Plus, Trash2, ChevronLeft, ChevronRight
} from 'lucide-react';

// --- Configuration Firebase ---
import { initializeApp } from 'firebase/app';
import {
  getFirestore, collection, onSnapshot, doc, setDoc, deleteField, addDoc, deleteDoc
} from 'firebase/firestore';
import {
  getAuth, signInAnonymously, onAuthStateChanged
} from 'firebase/auth';

// --- CONFIGURATION FIREBASE (Extraite de ton code) ---
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
const VerdictBadge = ({ verdict }) => {
  const configs = {
    'GOOD_DEAL': { label: 'Excellente Affaire', color: 'bg-emerald-500', icon: <Sparkles size={12}/> },
    'FAIR': { label: 'Prix Correct', color: 'bg-blue-500', icon: <CheckCircle size={12}/> },
    'BAD_DEAL': { label: 'Trop Cher', color: 'bg-rose-500', icon: <AlertTriangle size={12}/> },
    'DEFAULT': { label: 'Analyse...', color: 'bg-slate-400', icon: <RefreshCw size={12} className="animate-spin"/> }
  };
  const config = configs[verdict] || configs.DEFAULT;
  return (
    <span className={`${config.color} text-white px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest shadow-lg flex items-center gap-1.5`}>
      {config.icon} {config.label}
    </span>
  );
};

const DebugStatus = ({ label, status, details }) => (
  <div className="flex items-start gap-2 text-[10px] font-mono mb-2 p-2 bg-slate-50 rounded-lg border border-slate-100">
    <div className="mt-0.5">
      {status === 'loading' && <RefreshCw size={12} className="animate-spin text-blue-500" />}
      {status === 'success' && <CheckCircle size={12} className="text-emerald-500" />}
      {status === 'error' && <XCircle size={12} className="text-rose-500" />}
      {status === 'pending' && <div className="w-3 h-3 rounded-full border-2 border-slate-300" />}
    </div>
    <div className="flex-1">
      <div className={`font-bold uppercase ${status === 'error' ? 'text-rose-600' : 'text-slate-600'}`}>{label}</div>
      {details && <p className="text-slate-400 leading-tight mt-0.5 break-all">{details}</p>}
    </div>
  </div>
);

const ImageGallery = ({ images, title }) => {
  const [currentIndex, setCurrentIndex] = useState(0);

  if (!images || images.length === 0) {
    return (
      <div className="w-full h-full bg-slate-100 flex items-center justify-center text-slate-400">
        <Guitar size={48} className="opacity-20" />
      </div>
    );
  }

  const nextImage = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex((prev) => (prev + 1) % images.length);
  };

  const prevImage = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex((prev) => (prev - 1 + images.length) % images.length);
  };

  return (
    <div className="relative w-full h-full group">
      <img
        src={images[currentIndex]}
        className="w-full h-full object-cover transition-transform duration-700"
        alt={`${title} - ${currentIndex + 1}`}
      />
      
      {images.length > 1 && (
        <>
          <button 
            onClick={prevImage}
            className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <ChevronLeft size={20} />
          </button>
          <button 
            onClick={nextImage}
            className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <ChevronRight size={20} />
          </button>
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
            {images.map((_, idx) => (
              <div 
                key={idx} 
                className={`w-1.5 h-1.5 rounded-full ${idx === currentIndex ? 'bg-white' : 'bg-white/50'}`}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
};

const App = () => {
  const [user, setUser] = useState(null);
  const [deals, setDeals] = useState([]);
  const [cities, setCities] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  // UI States
  const [showConfig, setShowConfig] = useState(false);

  // Filter States
  const [filterType, setFilterType] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Config States
  const [prompt, setPrompt] = useState("Evalue cette guitare Au quebec (avec le prix).");
  const [verdictRules, setVerdictRules] = useState("");
  const [reasoningInstruction, setReasoningInstruction] = useState("");
  const [scanConfig, setScanConfig] = useState({
      maxAds: 5, frequency: 60, location: 'montreal', distance: 60, minPrice: 0, maxPrice: 10000, searchQuery: "electric guitar"
  });
  const [isRefreshing, setIsRefreshing] = useState(false);
  
  // New City Form State
  const [newCityName, setNewCityName] = useState('');
  const [newCityId, setNewCityId] = useState('');

  // Diagnostic State
  const [diag, setDiag] = useState({
    auth: { status: 'loading', msg: 'Connexion...' },
    userDoc: { status: 'pending', msg: 'En attente' },
    collection: { status: 'pending', msg: 'En attente' }
  });

  // 1. Auth Init
  useEffect(() => {
    const initAuth = async () => {
      try {
        await signInAnonymously(auth);
        setDiag(prev => ({ ...prev, auth: { status: 'success', msg: 'Authentifié' } }));
      } catch (err) {
        setDiag(prev => ({ ...prev, auth: { status: 'error', msg: err.message } }));
        setError(`Auth Error: ${err.message}`);
      }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  // 2. User Config & Diag Sync (Real-time)
  useEffect(() => {
    if (!user) return;
    const userDocRef = doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID);
    
    const unsubscribe = onSnapshot(userDocRef, (docSnap) => {
      if (docSnap.exists()) {
        setDiag(prev => ({ ...prev, userDoc: { status: 'success', msg: 'Dossier Python trouvé' } }));
        const data = docSnap.data();
        
        // Synchronise le prompt et la config depuis Firestore
        if (data.prompt) setPrompt(data.prompt);
        if (data.verdictRules) setVerdictRules(data.verdictRules);
        if (data.reasoningInstruction) setReasoningInstruction(data.reasoningInstruction);
        if (data.scanConfig) setScanConfig(prev => ({ ...prev, ...data.scanConfig }));

        // Gère l'erreur de scan envoyée par le bot
        if (data.scanError) {
          setError(data.scanError);
        } else {
          // Si l'erreur a été résolue (champ supprimé), on nettoie le message d'erreur
          if (error && error.startsWith("Ville")) {
             setError(null);
          }
        }

      } else {
        setDiag(prev => ({ ...prev, userDoc: { status: 'error', msg: "Dossier Python introuvable" } }));
      }
    }, (e) => {
      setDiag(prev => ({ ...prev, userDoc: { status: 'error', msg: e.message } }));
    });

    return () => unsubscribe();
  }, [user, error]);

  // 3. Firestore Deals Sync
  useEffect(() => {
    if (!user) return;
    const collectionRef = collection(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'guitar_deals');
    const unsubscribe = onSnapshot(collectionRef, (snapshot) => {
      const dealsData = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      dealsData.sort((a, b) => (b.timestamp?.seconds || 0) - (a.timestamp?.seconds || 0));
      setDeals(dealsData);
      setLoading(false);
      setDiag(prev => ({ ...prev, collection: { status: 'success', msg: `${snapshot.size} annonces` } }));
    }, (err) => {
      setError(err.message);
      setLoading(false);
    });
    return () => unsubscribe();
  }, [user]);

  // 4. Firestore Cities Sync
  useEffect(() => {
    if (!user) return;
    const citiesRef = collection(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'cities');
    const unsubscribe = onSnapshot(citiesRef, (snapshot) => {
      const citiesData = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      setCities(citiesData);
    });
    return () => unsubscribe();
  }, [user]);

  // Actions
  const saveConfig = useCallback(async (newVal) => {
    try {
      const userDocRef = doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID);
      await setDoc(userDocRef, newVal, { merge: true });
    } catch (e) { setError("Erreur de sauvegarde"); }
  }, []);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    // On efface l'ancienne erreur avant de relancer
    await saveConfig({ forceRefresh: Date.now(), scanError: deleteField() });
    setTimeout(() => setIsRefreshing(false), 5000);
  };

  const handleAddCity = async () => {
    if (!newCityName || !newCityId) return;
    try {
      const citiesRef = collection(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'cities');
      await addDoc(citiesRef, {
        name: newCityName,
        id: newCityId,
        createdAt: new Date()
      });
      setNewCityName('');
      setNewCityId('');
    } catch (e) {
      setError("Erreur ajout ville: " + e.message);
    }
  };

  const handleDeleteCity = async (docId) => {
    try {
      await deleteDoc(doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'cities', docId));
    } catch (e) {
      setError("Erreur suppression ville");
    }
  };

  // Memoized Filtered List
  const filteredDeals = useMemo(() => {
    return deals.filter(deal => {
      const verdict = deal.aiAnalysis?.verdict || deal.verdict || 'PENDING';
      const matchesType = filterType === 'ALL' || verdict === filterType;
      const matchesSearch = deal.title?.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesType && matchesSearch;
    });
  }, [deals, filterType, searchQuery]);

  return (
    <div className="min-h-screen bg-[#F8FAFC] font-sans text-slate-900 selection:bg-blue-100">

      {/* NAVBAR */}
      <nav className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-2 rounded-xl text-white shadow-lg shadow-blue-200">
              <Guitar size={24} />
            </div>
            <div>
              <h1 className="text-lg font-black tracking-tight text-slate-800">GUITAR HUNTER <span className="text-blue-600">AI</span></h1>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest leading-none">Scraper & Gemini Evaluator</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
                onClick={handleManualRefresh}
                disabled={isRefreshing}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${isRefreshing ? 'bg-slate-100 text-slate-400' : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100 shadow-sm border border-emerald-100'}`}
            >
              <RefreshCw size={14} className={isRefreshing ? "animate-spin" : ""} />
              <span className="hidden sm:inline">{isRefreshing ? 'Scan en cours...' : 'Scanner maintenant'}</span>
            </button>
            <button
              onClick={() => setShowConfig(!showConfig)}
              className="p-2 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors"
            >
              <Settings size={20} />
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 py-8 grid grid-cols-1 lg:grid-cols-4 gap-8">

        {/* SIDEBAR - CONTROLS & STATUS */}
        <aside className="lg:col-span-1 space-y-6">

          {/* Status Card */}
          <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-200">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Système</h3>
              <div className="flex items-center gap-1.5 bg-emerald-50 text-emerald-600 px-2 py-1 rounded-lg text-[9px] font-bold">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> LIVE
              </div>
            </div>
            <div className="space-y-1">
              <DebugStatus label="Auth" status={diag.auth.status} details={diag.auth.msg} />
              <DebugStatus label="Engine" status={diag.userDoc.status} details="Python Bot Connected" />
              <DebugStatus label="Database" status={diag.collection.status} details={diag.collection.msg} />
            </div>
          </div>

          {/* Config Card (Si ouvert) */}
          {showConfig && (
            <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-200 space-y-4 animate-in fade-in slide-in-from-top-4 duration-300">
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Paramètres</h3>

              {/* SECTION 1: FACEBOOK SEARCH */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-blue-600 mb-2">
                  <Search size={14} />
                  <span className="text-[10px] font-black uppercase tracking-widest">Recherche Facebook</span>
                </div>
                
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Lieu</label>
                    <select
                      value={scanConfig.location}
                      onChange={(e) => setScanConfig({...scanConfig, location: e.target.value})}
                      onBlur={() => saveConfig({ scanConfig })}
                      className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="" disabled>Choisir une ville</option>
                      {cities.map(city => (
                        <option key={city.id} value={city.name}>{city.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Dist (km)</label>
                    <input type="number" value={scanConfig.distance} onChange={(e) => setScanConfig({...scanConfig, distance: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Min Price</label>
                    <input type="number" value={scanConfig.minPrice} onChange={(e) => setScanConfig({...scanConfig, minPrice: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Max Price</label>
                    <input type="number" value={scanConfig.maxPrice} onChange={(e) => setScanConfig({...scanConfig, maxPrice: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Max Ads</label>
                    <input type="number" value={scanConfig.maxAds} onChange={(e) => setScanConfig({...scanConfig, maxAds: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Search Query</label>
                    <input type="text" value={scanConfig.searchQuery} onChange={(e) => setScanConfig({...scanConfig, searchQuery: e.target.value})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                </div>
              </div>

              {/* SECTION 2: GESTION DES VILLES (Déplacé ici) */}
              <div className="pt-4 border-t border-slate-100">
                <label className="text-[9px] font-bold text-slate-400 uppercase block mb-2">Villes Autorisées</label>
                
                <div className="space-y-2 mb-3 max-h-40 overflow-y-auto">
                  {cities.map(city => (
                    <div key={city.id} className="flex items-center justify-between bg-slate-50 p-2 rounded-lg text-xs">
                      <div>
                        <span className="font-bold block">{city.name}</span>
                        <span className="text-[9px] text-slate-400 font-mono">{city.id}</span>
                      </div>
                      <button onClick={() => handleDeleteCity(city.id)} className="text-rose-400 hover:text-rose-600 p-1">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                  {cities.length === 0 && <p className="text-[10px] text-slate-400 italic">Aucune ville configurée.</p>}
                </div>

                <div className="flex gap-2">
                  <input 
                    type="text" 
                    placeholder="Nom (ex: Montreal)" 
                    value={newCityName}
                    onChange={(e) => setNewCityName(e.target.value)}
                    className="w-1/2 p-2 bg-slate-50 border border-slate-200 rounded-lg text-[10px]"
                  />
                  <input 
                    type="text" 
                    placeholder="ID Facebook" 
                    value={newCityId}
                    onChange={(e) => setNewCityId(e.target.value)}
                    className="w-1/2 p-2 bg-slate-50 border border-slate-200 rounded-lg text-[10px]"
                  />
                </div>
                <button
                  onClick={handleAddCity}
                  disabled={!newCityName || !newCityId}
                  className="w-full mt-2 bg-blue-50 text-blue-600 py-2 rounded-xl text-[10px] font-bold uppercase hover:bg-blue-100 disabled:opacity-50 flex items-center justify-center gap-1"
                >
                  <Plus size={12} /> Ajouter Ville
                </button>
              </div>

              {/* SECTION 3: AI BOT CONFIG */}
              <div className="space-y-3 pt-4 border-t border-slate-100">
                <div className="flex items-center gap-2 text-purple-600 mb-2">
                  <Sparkles size={14} />
                  <span className="text-[10px] font-black uppercase tracking-widest">Intelligence Artificielle</span>
                </div>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Prompt Gemini</label>
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onBlur={() => saveConfig({ prompt })}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24 italic"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Règles de Verdict</label>
                  <textarea
                    value={verdictRules}
                    onChange={(e) => setVerdictRules(e.target.value)}
                    onBlur={() => saveConfig({ verdictRules })}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Instruction de Raisonnement</label>
                  <textarea
                    value={reasoningInstruction}
                    onChange={(e) => setReasoningInstruction(e.target.value)}
                    onBlur={() => saveConfig({ reasoningInstruction })}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24"
                  />
                </div>
              </div>

            </div>
          )}
        </aside>

        {/* MAIN FEED */}
        <main className="lg:col-span-3 space-y-6">

          {/* SEARCH & FILTERS BAR */}
          <div className="bg-white p-4 rounded-3xl shadow-sm border border-slate-200 flex flex-wrap gap-4 items-center">
            <div className="flex-1 min-w-[200px] relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type="text"
                placeholder="Rechercher par modèle..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>
            <div className="flex items-center gap-2 overflow-x-auto pb-1">
              {['ALL', 'GOOD_DEAL', 'FAIR', 'BAD_DEAL'].map((type) => (
                <button
                  key={type}
                  onClick={() => setFilterType(type)}
                  className={`px-4 py-2 rounded-2xl text-xs font-bold whitespace-nowrap transition-all ${filterType === type ? 'bg-blue-600 text-white shadow-md' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                >
                  {type === 'ALL' ? 'Toutes' : type === 'GOOD_DEAL' ? 'Bonnes Affaires' : type === 'FAIR' ? 'Prix Juste' : 'Trop Cher'}
                </button>
              ))}
            </div>
          </div>

          {/* LISTING GRID */}
          <div className="grid grid-cols-1 gap-6">
            {loading ? (
              <div className="py-20 flex flex-col items-center justify-center bg-white rounded-3xl border border-slate-200">
                <RefreshCw className="text-blue-600 animate-spin mb-4" size={40} />
                <p className="text-slate-400 font-bold uppercase tracking-widest text-xs">Synchronisation Firestore...</p>
              </div>
            ) : filteredDeals.length === 0 ? (
              <div className="py-20 flex flex-col items-center justify-center bg-white rounded-3xl border border-dashed border-slate-200">
                <div className="bg-slate-50 p-6 rounded-full mb-4">
                  <Search className="text-slate-200" size={48} />
                </div>
                <h3 className="text-lg font-black text-slate-400 uppercase tracking-tight italic">Aucun trésor trouvé</h3>
                <p className="text-slate-400 text-xs mt-1">Ajustez vos filtres ou lancez un scan manuel</p>
              </div>
            ) : (
              filteredDeals.map((deal) => (
                <div key={deal.id} className="group bg-white rounded-[2rem] shadow-sm border border-slate-200 overflow-hidden flex flex-col md:flex-row hover:shadow-2xl hover:shadow-blue-500/5 transition-all duration-500 animate-in fade-in slide-in-from-bottom-4">
                  {/* Image Section */}
                  <div className="md:w-80 h-64 md:h-auto overflow-hidden relative">
                    <ImageGallery images={deal.imageUrls || [deal.imageUrl]} title={deal.title} />
                    <div className="absolute top-4 left-4 z-10">
                      <VerdictBadge verdict={deal.aiAnalysis?.verdict || deal.verdict} />
                    </div>
                    {/* Overlay gradient */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent pointer-events-none" />
                  </div>

                  {/* Content Section */}
                  <div className="flex-1 p-6 md:p-8 flex flex-col">
                    <div className="flex justify-between items-start gap-4 mb-4">
                      <div>
                        <div className="flex items-center gap-2 text-blue-600 font-bold text-[10px] uppercase tracking-widest mb-1">
                          <MapPin size={10} /> {deal.location || 'Québec'}
                        </div>
                        <h2 className="text-2xl font-black text-slate-800 leading-tight group-hover:text-blue-600 transition-colors uppercase tracking-tight">{deal.title}</h2>
                      </div>
                      <div className="text-right flex flex-col items-end">
                        <div className="bg-slate-900 text-white px-4 py-2 rounded-2xl shadow-xl">
                          <span className="block text-[8px] font-black uppercase text-slate-400 tracking-tighter">Prix Demandé</span>
                          <span className="text-2xl font-black tabular-nums">{deal.price} $</span>
                        </div>
                        {deal.aiAnalysis?.estimated_value && (
                          <div className="mt-2 text-emerald-600 flex items-center gap-1 font-bold text-xs bg-emerald-50 px-2 py-1 rounded-lg">
                            <TrendingUp size={12} /> Val. Est: {deal.aiAnalysis.estimated_value}$
                          </div>
                        )}
                      </div>
                    </div>

                    {/* AI Insights */}
                    <div className="relative mb-6">
                      <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-100 rounded-full" />
                      <div className="pl-5 py-1">
                        <div className="flex items-center gap-1.5 text-blue-600 mb-2">
                          <Sparkles size={14} />
                          <span className="text-[10px] font-black uppercase tracking-widest">Analyse Gemini Flash</span>
                        </div>
                        <p className="text-slate-600 text-sm font-medium italic leading-relaxed">
                          "{deal.aiAnalysis?.reasoning || deal.reasoning || "Analyse de l'état et de la valeur en cours par l'intelligence artificielle..."}"
                        </p>
                      </div>
                    </div>

                    {/* Meta & Action */}
                    <div className="mt-auto pt-6 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4">
                      <div className="flex items-center gap-6">
                        <div className="flex items-center gap-2 text-slate-400 text-[10px] font-bold">
                          <Clock size={14} />
                          <span className="uppercase tracking-widest">
                            {deal.timestamp?.seconds ? new Date(deal.timestamp.seconds * 1000).toLocaleString() : 'Juste maintenant'}
                          </span>
                        </div>
                        {deal.aiAnalysis?.confidence && (
                          <div className="flex items-center gap-2">
                            <div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                              <div className="h-full bg-blue-500 rounded-full" style={{width: `${deal.aiAnalysis.confidence}%`}} />
                            </div>
                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Confiance {deal.aiAnalysis.confidence}%</span>
                          </div>
                        )}
                      </div>

                      <a
                        href={deal.link}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2 bg-slate-100 hover:bg-blue-600 hover:text-white text-slate-600 px-6 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all group/btn shadow-sm"
                      >
                        Voir sur Facebook <ExternalLink size={14} className="group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5 transition-transform" />
                      </a>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </main>
      </div>

      {/* ERROR TOAST */}
      {error && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-10">
          <div className="bg-rose-600 text-white px-6 py-4 rounded-2xl shadow-2xl shadow-rose-200 flex items-center gap-4">
            <AlertTriangle size={24} />
            <div>
              <p className="font-black uppercase text-[10px] tracking-widest leading-none mb-1 opacity-80">Erreur Détectée</p>
              <p className="text-sm font-bold">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="ml-4 hover:bg-white/20 p-1 rounded-lg transition-colors">
              <XCircle size={20} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;