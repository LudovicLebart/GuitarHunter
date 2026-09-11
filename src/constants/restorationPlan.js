// Valeurs fermées du plan de restauration (guitar_deals/{dealId}/restorationPlan/{itemId}) —
// module dédié pour être importable à la fois par l'UI (RestorationPlanPanel.jsx), la validation
// des propositions IA (geminiChatService.js, useDealChat.js) et l'injection de contexte dans le
// chat, sans dupliquer la liste à trois endroits.

export const RESTORATION_CATEGORY_LABELS = {
    structurel: 'Structurel',
    cosmetique: 'Cosmétique',
    electronique: 'Électronique',
    quincaillerie: 'Quincaillerie',
    reglage: 'Réglage',
    autre: 'Autre',
};

export const RESTORATION_CATEGORIES = Object.keys(RESTORATION_CATEGORY_LABELS);

export const RESTORATION_STATUS_LABELS = {
    pending: 'À faire',
    waiting: 'En attente',
    in_progress: 'En cours',
    done: 'Terminé',
    skipped: 'Ignoré',
};

export const RESTORATION_STATUSES = Object.keys(RESTORATION_STATUS_LABELS);
