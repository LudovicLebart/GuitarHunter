import { Gem, Sparkles, CheckCircle, AlertTriangle, Ban, XCircle, RefreshCw, Star, List, Hammer, Briefcase, Archive, Search, UserX, Package, Tag } from 'lucide-react';

// --- NOUVELLE GRILLE DE CLASSIFICATION (V2) ---
export const NEW_VERDICTS = {
  // Opportunités
  PEPITE: {
    id: 'PEPITE',
    label: 'Pépite',
    pluralLabel: 'Pépites',
    color: 'bg-yellow-400',
    icon: Gem
  },
  FAST_FLIP: {
    id: 'FAST_FLIP',
    label: 'Fast Flip',
    pluralLabel: 'Fast Flips',
    color: 'bg-emerald-500',
    icon: Sparkles
  },
  LUTHIER_PROJ: {
    id: 'LUTHIER_PROJ',
    label: 'Projet Luthier',
    pluralLabel: 'Projets Luthier',
    color: 'bg-orange-500',
    icon: Hammer
  },
  CASE_WIN: {
    id: 'CASE_WIN',
    label: 'Étui "Gratuit"',
    pluralLabel: 'Case Wins',
    color: 'bg-sky-500',
    icon: Briefcase
  },
  // Neutre
  COLLECTION: {
    id: 'COLLECTION',
    label: 'Collection',
    pluralLabel: 'Collection',
    color: 'bg-blue-500',
    icon: Package
  },
  // Bruit
  BAD_DEAL: {
    id: 'BAD_DEAL',
    label: 'Trop Cher',
    pluralLabel: 'Trop Cher',
    color: 'bg-rose-500',
    icon: AlertTriangle
  },
  REJECTED_ITEM: {
    id: 'REJECTED_ITEM',
    label: 'Item Rejeté',
    pluralLabel: 'Items Rejetés',
    color: 'bg-slate-600',
    icon: Ban
  },
  REJECTED_SERVICE: {
    id: 'REJECTED_SERVICE',
    label: 'Service Rejeté',
    pluralLabel: 'Services Rejetés',
    color: 'bg-slate-600',
    icon: UserX
  },
  INCOMPLETE_DATA: {
    id: 'INCOMPLETE_DATA',
    label: 'Données Manquantes',
    pluralLabel: 'Données Manquantes',
    color: 'bg-slate-400',
    icon: Search
  }
};

// --- ANCIENS VERDICTS (POUR RÉTROCOMPATIBILITÉ) ---
export const LEGACY_VERDICTS = {
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
  REJECTED: {
    id: 'REJECTED',
    label: 'Rejeté',
    pluralLabel: 'Rejetées',
    color: 'bg-slate-600',
    icon: Ban
  },
};

// --- FILTRES SPÉCIAUX ---
export const SPECIAL_FILTERS = {
  ALL: { id: 'ALL', label: 'Toutes', icon: List },
  FAVORITES: { id: 'FAVORITES', label: 'Favoris', icon: Star },
  ERROR: { id: 'ERROR', label: 'Erreurs', icon: XCircle },
  SOLD: { id: 'SOLD', label: 'Vendues', icon: Tag }
};

// --- GROUPES POUR L'AFFICHAGE "TEMPÉRATURE" ---
export const RADAR_GROUP = ['PEPITE', 'FAST_FLIP', 'LUTHIER_PROJ', 'CASE_WIN', 'GOOD_DEAL'];
export const MARKET_GROUP = ['COLLECTION', 'FAIR'];
export const ARCHIVE_GROUP = ['BAD_DEAL', 'REJECTED_ITEM', 'REJECTED_SERVICE', 'INCOMPLETE_DATA', 'REJECTED', 'SOLD'];

// --- NOTE D'INTÉRÊT (moyenne des 5 scores IA) ---
// Utilisée pour trier les annonces par intérêt plutôt que par date,
// utile notamment pour départager les annonces qui ne sont pas des Pépites.
export const computeInterestScore = (aiAnalysis) => {
  if (!aiAnalysis) return null;
  const scores = [
    aiAnalysis.deal_score,
    aiAnalysis.authenticity_score,
    aiAnalysis.condition_score,
    aiAnalysis.liquidity_score,
    aiAnalysis.restoration_interest_score
  ].filter(s => typeof s === 'number');
  if (scores.length === 0) return null;
  return scores.reduce((sum, s) => sum + s, 0) / scores.length;
};

// --- ORDRE D'AFFICHAGE DES FILTRES DANS LA BARRE ---
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
  'SOLD',
  'ERROR'
];

// --- CONFIGURATION GLOBALE POUR ACCÈS FACILE ---
export const ALL_FILTERS_CONFIG = {
  ...NEW_VERDICTS,
  ...LEGACY_VERDICTS,
  ...SPECIAL_FILTERS,
  DEFAULT: {
    id: 'DEFAULT',
    label: 'Analyse...',
    color: 'bg-slate-400',
    icon: RefreshCw
  }
};
