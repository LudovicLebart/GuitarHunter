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
    const userIdTarget = "00737242777130596039"; // Hardcoded for now as per other files, ideally from env or context

    // Fallback if env vars are missing (though they should be there)
    const finalAppId = "c_5d118e719dbddbfc_index.html-217";

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
    <div className={`fixed bottom-4 right-4 bg-slate-900/95 backdrop-blur-sm text-slate-200 rounded-xl shadow-2xl border border-slate-700 flex flex-col transition-all duration-300 z-50 ${containerClasses}`}>
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700 bg-slate-800/80 rounded-t-xl cursor-move flex-shrink-0">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400"><Terminal size={14} /><span>Server Logs (Max: {logLimit})</span></div>
        <div className="flex items-center gap-2">
          <button onClick={() => setIsPaused(!isPaused)} className="p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-white" title={isPaused ? "Reprendre" : "Pause"}>{isPaused ? <Play size={14} /> : <Pause size={14} />}</button>
          <button onClick={() => setLogs([])} className="p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-white" title="Effacer l'affichage local"><Trash2 size={14} /></button>
          <button onClick={handleClearRemoteLogs} className="p-1 hover:bg-rose-800 rounded text-rose-400 hover:text-rose-200" title="Vider la base de données (distant)"><Trash2 size={14} /></button>
          <button onClick={() => setIsExpanded(!isExpanded)} className="p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-white">{isExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}</button>
          <button onClick={onClose} className="p-1 hover:bg-rose-900 rounded text-slate-400 hover:text-rose-400"><X size={14} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs space-y-1 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent min-h-0">
        {logs.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-600 italic">En attente de logs...</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="break-words hover:bg-slate-800/50 p-0.5 rounded">
              <span className="text-slate-500 mr-2">[{log.timestamp?.seconds ? new Date(log.timestamp.seconds * 1000).toLocaleTimeString() : '??:??:??'}]</span>
              <span className={`font-bold mr-2 ${getLevelColor(log.level)}`}>{log.level}</span>
              <span className="text-slate-300">{log.message}</span>
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
};

export default LogViewer;
