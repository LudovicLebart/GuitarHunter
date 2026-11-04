/**
 * Relance après l'échec d'une lecture de l'index des annonces (2026-11-03).
 *
 * Avant : une lecture échouée (délai de 20 s, coupure réseau, redémarrage de l'API) affichait un
 * bandeau rouge et RIEN ne la relançait — l'écran restait vide jusqu'à la prochaine notification
 * WebSocket. Attente croissante, plafonnée, avec une part d'aléa (`jitter`) pour que tous les
 * clients déconnectés par un redémarrage de l'API ne reviennent pas au même instant.
 */
export const INDEX_RETRY_DELAYS_MS = [1000, 3000, 8000, 20000, 30000];

/** `attempt` : nombre d'échecs consécutifs déjà subis (1 = premier échec). `random` injectable pour les tests. */
export const nextIndexRetryDelayMs = (attempt, random = Math.random) => {
  const idx = Math.min(Math.max(attempt, 1), INDEX_RETRY_DELAYS_MS.length) - 1;
  const base = INDEX_RETRY_DELAYS_MS[idx];
  return Math.round(base * (0.8 + random() * 0.4));
};

/** Au-delà, on cesse de relancer : seules une notification WebSocket ou le retour au premier plan relisent encore. */
export const INDEX_MAX_AUTO_RETRIES = 10;

/** Relancer seulement une panne passagère : réseau/délai (pas de `status`), 5xx, 408, 429. Un 4xx (401, 403, 404...)
 *  ne se réparera pas seul — le relancer toutes les 30 s ne ferait que charger un serveur déjà en peine. */
export const shouldRetryIndex = (error, consecutiveFailures) => {
  if (consecutiveFailures > INDEX_MAX_AUTO_RETRIES) return false;
  const status = error?.status;
  if (typeof status !== 'number') return true;
  return status >= 500 || status === 408 || status === 429;
};

/** Le 1er échec est relancé en silence (un nouvel essai ouvre une connexion neuve, ce qui règle un socket
 *  mort après une veille) ; l'erreur n'est montrée qu'à partir du 2e, ou tout de suite si on ne relancera pas,
 *  et jamais si la page était cachée. */
export const shouldReportIndexError = (consecutiveFailures, pageHidden, willRetry = true) =>
  !pageHidden && (consecutiveFailures >= 2 || !willRetry);
