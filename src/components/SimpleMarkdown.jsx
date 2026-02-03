import React from 'react';

// Fonction helper pour parser le gras (**texte**)
const parseBold = (text) => {
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="text-slate-800 font-bold">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
};

const SimpleMarkdown = ({ text }) => {
  if (!text) return null;

  // Découpe le texte par ligne
  const lines = text.split('\n');

  return (
    <div className="space-y-2 text-slate-600 text-sm font-medium leading-relaxed">
      {lines.map((line, index) => {
        const trimmedLine = line.trim();
        
        // Gestion des titres (###)
        if (trimmedLine.startsWith('###')) {
          return (
            <h3 key={index} className="text-blue-800 font-bold text-base mt-3 mb-1 uppercase tracking-wide">
              {trimmedLine.replace(/^###\s*/, '')}
            </h3>
          );
        }
        
        // Gestion des listes à puces (-)
        if (trimmedLine.startsWith('- ')) {
          return (
            <div key={index} className="flex items-start gap-2 ml-2">
              <span className="text-blue-400 mt-1.5">•</span>
              <span>
                {parseBold(trimmedLine.replace(/^- /, ''))}
              </span>
            </div>
          );
        }

        // Paragraphe standard (avec gestion du gras)
        if (trimmedLine.length > 0) {
           return (
             <p key={index}>
               {parseBold(trimmedLine)}
             </p>
           );
        }

        return null; // Ligne vide
      })}
    </div>
  );
};

export default SimpleMarkdown;
