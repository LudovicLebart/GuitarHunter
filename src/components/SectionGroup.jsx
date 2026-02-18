import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

const SectionGroup = ({ title, count, children, defaultOpen = true, icon: Icon, colorClass = "text-slate-800" }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (count === 0) return null;

  return (
    <div className="mb-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-3 w-full mb-4 group hover:bg-slate-50 p-2 rounded-xl transition-colors"
      >
        <div className={`p-2 rounded-lg ${isOpen ? 'bg-slate-200' : 'bg-slate-100'} transition-colors`}>
            {isOpen ? <ChevronDown size={20} className="text-slate-500" /> : <ChevronRight size={20} className="text-slate-500" />}
        </div>
        
        <div className="flex items-center gap-3">
            {Icon && <Icon size={24} className={colorClass} />}
            <h2 className={`text-xl font-black uppercase tracking-tight ${colorClass}`}>{title}</h2>
            <span className="bg-slate-100 text-slate-500 text-xs font-bold px-2 py-1 rounded-full">{count}</span>
        </div>
        
        <div className="flex-1 h-px bg-slate-100 ml-4 group-hover:bg-slate-200 transition-colors" />
      </button>

      {isOpen && (
        <div className="grid grid-cols-1 gap-6 animate-in fade-in slide-in-from-top-2 duration-300">
          {children}
        </div>
      )}
    </div>
  );
};

export default SectionGroup;
