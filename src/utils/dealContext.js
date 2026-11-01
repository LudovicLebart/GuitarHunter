// Première ligne du contexte d'annonce envoyé au modèle (voir buildDealContextText dans geminiChatService.js).
export const DEAL_CONTEXT_HEADER = "Contexte de l'annonce (déjà analysée par Guitar Hunter AI) :";

// Le modèle a-t-il DÉJÀ vu le contexte de l'annonce dans l'historique rejoué (`[{role, parts}]`, déjà alterné par
// sanitizeHistory) ? Sert à décider s'il faut l'envoyer avec le prochain message (2026-11-01) : « premier message » ne suffit
// pas, car une conversation dont le tout premier tour est parti sans contexte (échec, ancienne version) ne le recevrait jamais.
export const historyHasDealContext = (history = []) => history.some((turn) => turn.role === 'user'
    && (turn.parts || []).some((part) => typeof part?.text === 'string' && part.text.includes(DEAL_CONTEXT_HEADER)));
