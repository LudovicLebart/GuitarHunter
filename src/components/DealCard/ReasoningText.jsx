import React from 'react';

// Rendu du raisonnement détaillé de l'IA (markdown léger : titres #, listes, **gras*).
// Partagé par la modale d'expertise et la page d'annonce partagée.
const ReasoningText = ({ text }) => (
    <div className="text-[13px] sm:text-[15px] text-slate-300 font-mono leading-relaxed whitespace-pre-wrap">
        {text.split('\n').map((line, i) => {
            if (line.trim() === '') return <div key={i} className="h-4"></div>;

            const isHeader = line.startsWith('#');
            const isList = line.trim().startsWith('-') || line.trim().startsWith('* ');

            // Parse bold text **like this**
            const formattedLine = line.split(/(\*\*.*?\*\*)/g).map((part, index) => {
                if (part.startsWith('**') && part.endsWith('**')) {
                    return <strong key={index} className="text-blue-400 font-bold tracking-wide">{part.slice(2, -2)}</strong>;
                }
                return part;
            });

            if (isHeader) {
                const title = line.replace(/^#+\s*/, '');
                return <h3 key={i} className="text-blue-400 font-black text-sm uppercase tracking-widest mt-6 mb-2 border-b border-slate-800 pb-2">{title}</h3>;
            }

            if (isList) {
                const item = line.replace(/^[-*]\s*/, '');
                const listParts = item.split(/(\*\*.*?\*\*)/g).map((part, index) => {
                    if (part.startsWith('**') && part.endsWith('**')) {
                        return <strong key={index} className="text-white font-bold tracking-wide">{part.slice(2, -2)}</strong>;
                    }
                    return part;
                });

                return (
                    <div key={i} className="flex gap-3 mb-2 items-start pl-2">
                        <span className="text-blue-500 shrink-0 mt-0.5">•</span>
                        <span className="text-slate-300">{listParts}</span>
                    </div>
                );
            }

            return <div key={i} className="mb-3">{formattedLine}</div>;
        })}
    </div>
);

export default ReasoningText;
