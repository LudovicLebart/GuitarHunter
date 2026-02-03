import React from 'react';
import { Gem, Sparkles, CheckCircle, AlertTriangle, Ban, XCircle, RefreshCw } from 'lucide-react';

const VerdictBadge = ({ verdict }) => {
  const configs = {
    'PEPITE': { label: 'Pépite !', color: 'bg-yellow-400', icon: <Gem size={12}/> },
    'GOOD_DEAL': { label: 'Bonne Affaire', color: 'bg-emerald-500', icon: <Sparkles size={12}/> },
    'FAIR': { label: 'Prix Correct', color: 'bg-blue-500', icon: <CheckCircle size={12}/> },
    'BAD_DEAL': { label: 'Trop Cher', color: 'bg-rose-500', icon: <AlertTriangle size={12}/> },
    'REJECTED': { label: 'Rejeté', color: 'bg-slate-600', icon: <Ban size={12}/> },
    'ERROR': { label: 'Erreur Analyse', color: 'bg-rose-600', icon: <XCircle size={12}/> },
    'DEFAULT': { label: 'Analyse...', color: 'bg-slate-400', icon: <RefreshCw size={12} className="animate-spin"/> }
  };
  const config = configs[verdict] || configs.DEFAULT;
  return (
    <span className={`${config.color} text-white px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest shadow-lg flex items-center gap-1.5`}>
      {config.icon} {config.label}
    </span>
  );
};

export default VerdictBadge;
