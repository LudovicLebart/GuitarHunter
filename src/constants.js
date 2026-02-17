import { Gem, Sparkles, CheckCircle, AlertTriangle, Ban, XCircle, RefreshCw, Star, List, Zap, Wrench, Briefcase, Archive } from 'lucide-react';

export const VERDICTS = {
  // --- OPPORTUNITÉS (RADAR) ---
  PEPITE: {
    id: 'PEPITE',
    label: 'Pépite !',
    pluralLabel: 'Pépites',
    color: 'bg-yellow-400',
    textColor: 'text-yellow-700',
    bgColor: 'bg-yellow-50',
    icon: Gem,
    group: 'RADAR'
  },
  FAST_FLIP: {
    id: 'FAST_FLIP',
    label: 'Fast Flip',
    pluralLabel: 'Fast Flips',
    color: 'bg-emerald-500',
    textColor: 'text-emerald-700',
    bgColor: 'bg-emerald-50',
    icon: Zap,
    group: 'RADAR'
  },
  LUTHIER_PROJ: {
    id: 'LUTHIER_PROJ',
    label: 'Projet Luthier',
    pluralLabel: 'Projets Luthier',
    color: 'bg-purple-500',
    textColor: 'text-purple-700',
    bgColor: 'bg-purple-50',
    icon: Wrench,
    group: 'RADAR'
  },
  CASE_WIN: {
    id: 'CASE_WIN',
    label: 'Règle de l\'Étui',
    pluralLabel: 'Règle de l\'Étui',
    color: 'bg-indigo-500',
    textColor: 'text-indigo-700',
    bgColor: 'bg-indigo-50',
    icon: Briefcase,
    group: 'RADAR'
  },
  
  // --- NEUTRES (MARKET) ---
  COLLECTION: {
    id: 'COLLECTION',
    label: 'Collection / Fair',
    pluralLabel: 'Collection / Fair',
    color: 'bg-blue-500',
    textColor: 'text-blue-700',
    bgColor: 'bg-blue-50',
    icon: CheckCircle,
    group: 'MARKET'
  },
  // Legacy support
  GOOD_DEAL: {
    id: 'GOOD_DEAL',
    label: 'Bonne Affaire',
    pluralLabel: 'Bonnes Affaires',
    color: 'bg-emerald-500',
    textColor: 'text-emerald-700',
    bgColor: 'bg-emerald-50',
    icon: Sparkles,
    group: 'MARKET'
  },
  FAIR: {
    id: 'FAIR',
    label: 'Prix Correct',
    pluralLabel: 'Prix Juste',
    color: 'bg-blue-500',
    textColor: 'text-blue-700',
    bgColor: 'bg-blue-50',
    icon: CheckCircle,
    group: 'MARKET'
  },

  // --- BRUIT (NOISE) ---
  BAD_DEAL: {
    id: 'BAD_DEAL',
    label: 'Trop Cher',
    pluralLabel: 'Trop Cher',
    color: 'bg-rose-500',
    textColor: 'text-rose-700',
    bgColor: 'bg-rose-50',
    icon: AlertTriangle,
    group: 'NOISE'
  },
  REJECTED_ITEM: {
    id: 'REJECTED_ITEM',
    label: 'Rejet (Objet)',
    pluralLabel: 'Rejets (Objet)',
    color: 'bg-slate-600',
    textColor: 'text-slate-700',
    bgColor: 'bg-slate-100',
    icon: Ban,
    group: 'NOISE'
  },
  REJECTED_SERVICE: {
    id: 'REJECTED_SERVICE',
    label: 'Rejet (Service)',
    pluralLabel: 'Rejets (Service)',
    color: 'bg-slate-600',
    textColor: 'text-slate-700',
    bgColor: 'bg-slate-100',
    icon: Ban,
    group: 'NOISE'
  },
  INCOMPLETE_DATA: {
    id: 'INCOMPLETE_DATA',
    label: 'Données Incomplètes',
    pluralLabel: 'Données Incomplètes',
    color: 'bg-slate-400',
    textColor: 'text-slate-600',
    bgColor: 'bg-slate-100',
    icon: Archive,
    group: 'NOISE'
  },
  // Legacy support
  REJECTED: {
    id: 'REJECTED',
    label: 'Rejeté',
    pluralLabel: 'Rejetées',
    color: 'bg-slate-600',
    textColor: 'text-slate-700',
    bgColor: 'bg-slate-100',
    icon: Ban,
    group: 'NOISE'
  },
};

export const SPECIAL_FILTERS = {
  ALL: {
    id: 'ALL',
    label: 'Toutes',
    icon: List
  },
  FAVORITES: {
    id: 'FAVORITES',
    label: 'Favoris',
    icon: Star
  },
  ERROR: {
    id: 'ERROR',
    label: 'Erreurs',
    icon: XCircle
  },
};

// Ordre d'affichage des filtres (Legacy, utilisé par FilterBar si non groupé)
export const FILTER_ORDER = [
  'ALL',
  'FAVORITES',
  'PEPITE',
  'FAST_FLIP',
  'LUTHIER_PROJ',
  'CASE_WIN',
  'COLLECTION',
  'BAD_DEAL',
  'REJECTED_ITEM',
  'ERROR'
];

// Combinaison pour un accès facile
export const ALL_FILTERS_CONFIG = {
  ...VERDICTS,
  ...SPECIAL_FILTERS,
  DEFAULT: {
      id: 'DEFAULT',
      label: 'Analyse...',
      color: 'bg-slate-400',
      textColor: 'text-slate-600',
      bgColor: 'bg-slate-100',
      icon: RefreshCw
  }
};
