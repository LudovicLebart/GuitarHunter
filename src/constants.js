import { Gem, Sparkles, CheckCircle, AlertTriangle, Ban, XCircle, RefreshCw, Star, List } from 'lucide-react';

export const VERDICTS = {
  PEPITE: {
    id: 'PEPITE',
    label: 'Pépite !',
    pluralLabel: 'Pépites',
    color: 'bg-yellow-400',
    icon: Gem
  },
  GOOD_DEAL: {
    id: 'GOOD_DEAL',
    label: 'Bonne Affaire',
    pluralLabel: 'Bonnes Affaires',
    color: 'bg-emerald-500',
    icon: Sparkles
  },
  FAIR: {
    id: 'FAIR',
    label: 'Prix Correct',
    pluralLabel: 'Prix Juste',
    color: 'bg-blue-500',
    icon: CheckCircle
  },
  BAD_DEAL: {
    id: 'BAD_DEAL',
    label: 'Trop Cher',
    pluralLabel: 'Trop Cher',
    color: 'bg-rose-500',
    icon: AlertTriangle
  },
  REJECTED: {
    id: 'REJECTED',
    label: 'Rejeté',
    pluralLabel: 'Rejetées',
    color: 'bg-slate-600',
    icon: Ban
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

// Ordre d'affichage des filtres
export const FILTER_ORDER = [
  'ALL',
  'FAVORITES',
  'PEPITE',
  'GOOD_DEAL',
  'FAIR',
  'BAD_DEAL',
  'REJECTED',
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
      icon: RefreshCw
  }
};
