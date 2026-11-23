// Classement des échecs d'un appel du chat (extrait de useDealChat.js pour être testable). Mêmes valeurs que
// `llm_usage.classify_error` côté backend, avec le code HTTP en plus quand il est connu (`customErrorData.status`).

// Heuristique (2026-08-23) : un échec avec tools actifs signale-t-il VRAIMENT que le modèle ne supporte pas le function
// calling (désactivation durable), ou une erreur transitoire quelconque (réseau, 503, timeout) ? Pas 'invalid' ni 'not
// allowed' : toute erreur de schéma de tool ou de signature de réflexion les contient sans que le modèle en soit incapable.
export const looksLikeToolsUnsupportedError = (error) => {
    const haystack = `${error?.message || ''} ${error?.code || ''}`.toLowerCase();
    const mentionsTools = haystack.includes('function') || haystack.includes('tool');
    const mentionsRejection = haystack.includes('not support') || haystack.includes('unsupported') || haystack.includes('not enabled');
    return mentionsTools && mentionsRejection;
};

export const classifyChatError = (error) => {
    const text = `${error?.name || ''} ${error?.code || ''} ${error?.message || ''}`.toLowerCase();
    if (error?.name === 'AbortError' || text.includes('timeout') || text.includes('timed out')) return 'timeout';
    if (looksLikeToolsUnsupportedError(error)) return 'tools_rejected';
    // Plafond de dépense du jour : l'API le signale par un code (`daily_cap`), il ne se lève pas en attendant.
    if (error?.code === 'daily_cap') return 'daily_cap';
    const status = error?.customErrorData?.status;
    if (status) return `http_${status}`;
    if (text.includes('failed to fetch') || text.includes('network')) return 'connection';
    return 'other';
};

/** Échec transitoire : une seule nouvelle tentative à l'identique (429 hors plafond du jour, 5xx, réseau). */
export const isTransientChatError = (kind) => kind === 'connection' || kind === 'http_429' || /^http_5\d\d$/.test(kind);

/** Échec sans nouvelle tentative ni repli : annulation/délai (peut-être déjà facturé), clé absente (424), crédit épuisé
 *  (402), plafond du jour. */
export const isFinalChatError = (kind) => ['timeout', 'http_424', 'http_402', 'daily_cap'].includes(kind);
