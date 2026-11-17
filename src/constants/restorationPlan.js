// Valeurs fermées du plan de restauration (guitar_deals/{dealId}/restorationPlan/{itemId}) —
// module dédié pour être importable à la fois par l'UI (RestorationPlanPanel.jsx), la validation
// des propositions IA (geminiChatService.js, useDealChat.js) et l'injection de contexte dans le
// chat, sans dupliquer la liste à trois endroits.

export const RESTORATION_CATEGORY_LABELS = {
    evaluation: 'Diagnostic et évaluation',
    reglage: 'Réglage et setup',
    manche: 'Manche et frettes',
    structurel: 'Structure et bois',
    finition: 'Finition et cosmétique',
    electronique: 'Électronique',
    quincaillerie: 'Quincaillerie',
    'lutherie-base': 'Techniques de base',
    autre: 'Autre',
};

// Catégories proposées (fiches, étapes, chat).
export const RESTORATION_CATEGORIES = Object.keys(RESTORATION_CATEGORY_LABELS);

// Valeurs d'avant le 2026-11-17, encore présentes sur des étapes déjà enregistrées : affichables, jamais proposées.
const LEGACY_CATEGORY_LABELS = { cosmetique: 'Finition et cosmétique' };

export const restorationCategoryLabel = (c) => RESTORATION_CATEGORY_LABELS[c] || LEGACY_CATEGORY_LABELS[c] || c;

export const RESTORATION_STATUS_LABELS = {
    pending: 'À faire',
    waiting: 'En attente',
    in_progress: 'En cours',
    done: 'Terminé',
    skipped: 'Ignoré',
};

export const RESTORATION_STATUSES = Object.keys(RESTORATION_STATUS_LABELS);
