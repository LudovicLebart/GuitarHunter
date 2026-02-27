import React, { useState, useEffect, useRef } from 'react';
import { Terminal, X, Minimize2, Maximize2, Trash2, Pause, Play } from 'lucide-react';
import { collection, query, limit, onSnapshot, orderBy } from 'firebase/firestore';
import { db } from '../services/firebase';
import { useAuth } from '../hooks/useAuth';
import { useBotConfigContext } from '../context/BotConfigContext';
import { requestClearLogs } from '../services/firestoreService';

const LogViewer = ({ onClose }) => {
  const { user } = useAuth();
  const { logLimit } = useBotConfigContext();
  const [logs, setLogs] = useState([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (!user) return;

    const appId = import.meta.env.VITE_FIREBASE_APP_ID;

    const finalAppId = import.meta.env.VITE_APP_ID_TARGET;
    const userIdTarget = import.meta.env.VITE_USER_ID_TARGET;

    const logsRef = collection(db, `artifacts/${finalAppId}/users/${userIdTarget}/logs`);
    // On trie par timestamp décroissant pour avoir les derniers logs, puis on limite
    const q = query(logsRef, orderBy('timestamp', 'desc'), limit(logLimit || 100));

    const unsubscribe = onSnapshot(q, (snapshot) => {
      if (isPaused) return;

      const newLogs = snapshot.docs
        .map(doc => ({ id: doc.id, ...doc.data() }))
        // On inverse le tri pour l'affichage (du plus vieux au plus récent en bas)
        .sort((a, b) => {
          const timeA = a.timestamp?.seconds || a.createdAt || 0;
          const timeB = b.timestamp?.seconds || b.createdAt || 0;
          return timeA - timeB;
        });

      setLogs(newLogs);
    }, (error) => {
      console.error("Error fetching logs: ", error);
      setLogs(prev => [...prev, { id: Date.now(), level: 'ERROR', message: 'Failed to fetch logs from Firestore: ' + error.message }]);
    });

    return () => unsubscribe();
  }, [user, isPaused, logLimit]);

  useEffect(() => {
    if (!isPaused && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, isPaused]);

  const handleClearRemoteLogs = () => {
    if (window.confirm("Voulez-vous vraiment supprimer TOUS les logs de la base de données ? Cette action est irréversible.")) {
      requestClearLogs().catch(err => alert(`Erreur lors de la demande de suppression des logs: ${err.message}`));
    }
  };

  const getLevelColor = (level) => {
    switch (level) {
      case 'INFO': return 'text-blue-400';
      case 'WARNING': return 'text-amber-400';
      case 'ERROR': return 'text-rose-400';
      case 'CRITICAL': return 'text-rose-600 font-bold';
      default: return 'text-slate-300';
    }
  };

  const containerClasses = isExpanded
    ? 'w-[90vw] h-[80vh] max-w-[1200px] max-h-[900px]'
    : 'w-[450px] h-[350px]';

  return (
    <div className={`fixed bottom-6 right-6 bg-slate-950 text-slate-200 rounded-3xl shadow-2xl border border-slate-800 flex flex-col transition-all duration-300 z-50 overflow-hidden ${containerClasses}`}>
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900 shrink-0 cursor-move">
        <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
          <Terminal size={14} className="text-blue-500" />
          <span>Console Système (Max: {logLimit})</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setIsPaused(!isPaused)} className={`w-8 h-8 flex items-center justify-center rounded-lg transition-all ${isPaused ? 'bg-amber-500/20 text-amber-400' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`} title={isPaused ? "Reprendre" : "Pause"}>{isPaused ? <Play size={14} /> : <Pause size={14} />}</button>
          <button onClick={() => setLogs([])} className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all" title="Effacer l'affichage local"><Trash2 size={14} /></button>
          <button onClick={handleClearRemoteLogs} className="w-8 h-8 flex items-center justify-center text-rose-500/50 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all" title="Vider la base de données (distant)"><Trash2 size={14} /></button>
          <button onClick={() => setIsExpanded(!isExpanded)} className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-blue-400 hover:bg-slate-800 rounded-lg transition-all hidden sm:flex">{isExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}</button>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-rose-500 hover:bg-slate-800 rounded-lg transition-all"><X size={16} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 font-mono text-[11px] space-y-1.5 scrollbar-dark min-h-0">
        {logs.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-700 italic">Console vide. En attente de flux...</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="break-words hover:bg-slate-800/50 p-1.5 rounded-lg transition-colors border border-transparent hover:border-slate-800/80">
              <span className="text-slate-600 mr-2 tabular-nums">[{log.timestamp?.seconds ? new Date(log.timestamp.seconds * 1000).toLocaleTimeString() : '??:??:??'}]</span>
              <span className={`font-black mr-2 tracking-wide ${getLevelColor(log.level)}`}>{log.level}</span>
              <span className="text-slate-300 leading-relaxed">{log.message}</span>
            </div>
          ))
        )}
        <div ref={logsEndRef} className="pt-2" />
      </div>
    </div>
  );
};

export default LogViewer;
