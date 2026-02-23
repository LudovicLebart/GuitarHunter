import React from 'react';
import { ALL_FILTERS_CONFIG } from '../constants';

const VerdictBadge = ({ verdict, status }) => {
  if (!verdict && status === 'sold') {
    return null; // Pas de verdict générique "Analyse..." si l'annonce a été liquidée avant l'analyse
  }

  const config = ALL_FILTERS_CONFIG[verdict] || ALL_FILTERS_CONFIG.DEFAULT;
  const Icon = config.icon;

  return (
    <span className={`${config.color} text-white px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest shadow-lg flex items-center gap-1.5`}>
      <Icon size={12} className={!verdict || verdict === 'DEFAULT' ? 'animate-spin' : ''} />
      {config.label}
    </span>
  );
};

export default VerdictBadge;
