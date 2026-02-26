import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

const CollapsibleSection = ({ title, children, defaultOpen = false }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-slate-800 rounded-2xl overflow-hidden bg-slate-900/50 mb-2">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex justify-between items-center w-full px-5 py-4 text-left group hover:bg-slate-800/50 transition-all"
      >
        <span className="text-[10px] font-black uppercase tracking-[0.15em] text-slate-500 group-hover:text-blue-400 transition-colors">{title}</span>
        <ChevronRight
          size={16}
          className={`text-slate-600 group-hover:text-blue-400 transform transition-transform duration-300 ${
            isOpen ? 'rotate-90' : ''
          }`}
        />
      </button>
      {isOpen && (
        <div className="px-5 pb-5 animate-in fade-in slide-in-from-top-1 duration-200">
            {children}
        </div>
      )}
    </div>
  );
};

export default CollapsibleSection;
