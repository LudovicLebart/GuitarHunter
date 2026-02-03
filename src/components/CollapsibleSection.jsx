import React, { useState } from 'react';
import { ChevronRight } from 'lucide-react';

const CollapsibleSection = ({ title, children }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mt-4 border-t border-slate-200 pt-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex justify-between items-center w-full text-left text-sm font-bold text-slate-600 hover:text-blue-600 transition-colors"
      >
        <span>{title}</span>
        <ChevronRight
          size={16}
          className={`transform transition-transform duration-200 ${
            isOpen ? 'rotate-90' : ''
          }`}
        />
      </button>
      {isOpen && <div className="mt-2 animate-in fade-in">{children}</div>}
    </div>
  );
};

export default CollapsibleSection;
