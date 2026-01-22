import React, { useState, useEffect } from 'react';
import {
  Search, ExternalLink, Guitar,
  AlertTriangle, RefreshCw, Copy, ShieldCheck, Clock,
  CheckCircle, XCircle, Activity
} from 'lucide-react';

// --- Configuration Firebase ---
import { initializeApp } from 'firebase/app';
import {
  getFirestore, collection, onSnapshot, doc, getDoc
} from 'firebase/firestore';
import {
  getAuth, signInAnonymously, signInWithCustomToken, onAuthStateChanged
} from 'firebase/auth';

// --- RÉCUPÉRATION DE LA CONFIGURATION SYSTÈME ---
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
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

// --- CONSTANTES DE SYNCHRONISATION (Correspondance avec votre script Python) ---
const PYTHON_APP_ID = "c_5d118e719dbddbfc_index.html-217";
const PYTHON_USER_ID = "00737242777130596039";
const appId = PYTHON_APP_ID;

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

  // États de diagnostic pour aider l'utilisateur
  const [diag, setDiag] = useState({
    auth: { status: 'loading', msg: 'Connexion...' },
    appDoc: { status: 'pending', msg: 'En attente' },
    userDoc: { status: 'pending', msg: 'En attente' },
    collection: { status: 'pending', msg: 'En attente' }
  });

  // 1. Authentification Automatique
  useEffect(() => {
    const initAuth = async () => {
      try {
        // CORRECTION : On tente d'abord l'authentification anonyme
        // L'erreur "custom-token-mismatch" indique que le token injecté n'est pas valide pour ce projet
        // ou qu'il est mal formé. On privilégie l'accès anonyme direct.
        await signInAnonymously(auth);
        setDiag(prev => ({ ...prev, auth: { status: 'success', msg: 'Authentifié (Anonyme)' } }));
      } catch (err) {
        console.error("Auth Error:", err);
        // Tentative de fallback si l'anonyme échoue (rare)
        setDiag(prev => ({ ...prev, auth: { status: 'error', msg: err.message } }));
        setError(`Erreur Auth: ${err.message}`);
      }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  // 2. Diagnostic des chemins de données
  useEffect(() => {
    if (!user) return;

    const runDiagnostics = async () => {
      const targetUserId = PYTHON_USER_ID;

      // Vérification du document de l'application
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

      // Vérification du dossier utilisateur cible
      setDiag(prev => ({ ...prev, userDoc: { status: 'loading', msg: `Vérif users/${targetUserId}...` } }));
      try {
        const userDocRef = doc(db, 'artifacts', appId, 'users', targetUserId);
        const userDocSnap = await getDoc(userDocRef);
        if (userDocSnap.exists()) {
          setDiag(prev => ({ ...prev, userDoc: { status: 'success', msg: 'Dossier Python trouvé' } }));
        } else {
          setDiag(prev => ({ ...prev, userDoc: { status: 'error', msg: 'Dossier Python absent' } }));
        }
      } catch (e) {
        setDiag(prev => ({ ...prev, userDoc: { status: 'error', msg: e.message } }));
      }
    };

    runDiagnostics();
  }, [user]);

  // 3. Écoute des données temps réel
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

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-8 font-sans text-slate-900 text-[14px]">
      <header className="max-w-6xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold flex items-center gap-2 italic tracking-tight">
            <Guitar className="text-blue-600" size={32} />
            GUITAR HUNTER <span className="text-blue-600 underline">AI</span>
          </h1>
          <div className="mt-2 flex flex-col gap-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">
             <div className="flex items-center gap-4">
                 <span>Python Target: <span className="text-blue-600">{PYTHON_USER_ID}</span></span>
                 <span className="flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-green-500" /> Connecté</span>
             </div>
             <div>App ID: <span className="text-slate-600">{PYTHON_APP_ID}</span></div>
             <div>Path: <span className="text-slate-500 normal-case">artifacts/{PYTHON_APP_ID}/users/{PYTHON_USER_ID}/guitar_deals</span></div>
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 min-w-[250px]">
          <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2 flex items-center gap-1">
            <Activity size={12} /> État du Système
          </h4>
          <DebugStatus label="Authentification" status={diag.auth.status} details={diag.auth.msg} />
          <DebugStatus label="Structure App" status={diag.appDoc.status} details={diag.appDoc.msg} />
          <DebugStatus label="Structure User" status={diag.userDoc.status} details={diag.userDoc.msg} />
          <DebugStatus label="Base de données" status={diag.collection.status} details={diag.collection.msg} />
        </div>
      </header>

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
                        <p className="text-3xl font-black text-blue-600 tracking-tighter">{deal.price} $</p>
                        <p className="text-[10px] text-slate-400 font-black uppercase">Valeur Est.: {deal.estimated_value} $</p>
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