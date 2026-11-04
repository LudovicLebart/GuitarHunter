/**
 * Synchronisation incrémentale de l'index des annonces (2026-11-03).
 *
 * Le serveur notifie déjà l'id de chaque annonce modifiée ; le client relisait pourtant les ~8 400 annonces
 * (16 Mo) à chaque notification. Il ne demande désormais que les ids notifiés (`GET /deals/index?ids=`) et les
 * fusionne ici. Un id demandé mais absent de la réponse n'est plus visible (supprimé, retiré du fil) : on le retire.
 */

/** Au-delà, une relecture complète coûte moins cher que plusieurs lectures incrémentales (le serveur envoie `bulk` à 50). */
export const DELTA_MAX_IDS = 50;

/** Relecture complète de sécurité : suppressions et frais de restauration ne notifient pas encore (voir le plan). */
export const FULL_REFRESH_INTERVAL_MS = 10 * 60 * 1000;

/** `map` : index courant {id: annonce}. `requestedIds` : ids demandés. `deals` : annonces reçues (déjà mappées, avec `id`). */
export const mergeIndexDelta = (map, requestedIds, deals) => {
  const next = { ...map };
  for (const id of requestedIds) delete next[id];
  for (const deal of deals) next[deal.id] = deal;
  return next;
};

/** Mode de la prochaine lecture : 'full' ou 'delta'. */
export const chooseIndexRefresh = ({ hasIndex, fullNeeded, pendingCount }) => {
  if (!hasIndex || fullNeeded || pendingCount === 0 || pendingCount > DELTA_MAX_IDS) return 'full';
  return 'delta';
};

/** Une notification WS porte-t-elle un id exploitable en incrémental ? (`bulk`, "ready", message sans id => non) */
export const deltaIdFromMessage = (msg) => (msg && msg.type !== 'bulk' && typeof msg.id === 'string' && msg.id ? msg.id : null);
