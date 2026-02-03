import React from 'react';
import { RefreshCw, CheckCircle, XCircle } from 'lucide-react';

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

export default DebugStatus;
