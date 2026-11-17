/**
 * Index des annonces en deux lots (2026-11-17, `GET /deals/index?tier=live|archive`, voir deals_repo.py).
 *
 * `live` : ce que l'écran d'accueil affiche (~200 annonces : radar, favoris, achats, analyses en cours) ; `archive` : vendu,
 * rejeté, trop cher… (~95 % des lignes), lu ensuite en arrière-plan. Les deux lots sont disjoints (partition testée côté serveur).
 */

/**
 * Index à afficher dès que le lot `live` est arrivé : les annonces `live` toutes fraîches, plus ce qu'on savait déjà
 * (cache disque ou lecture précédente) pour les autres — provisoire, remplacé quand le lot `archive` arrive.
 * `provisional` peut être nul (premier chargement sans cache) : l'index ne contient alors que le lot `live`.
 */
export const combineWithProvisional = (provisional, liveMap) => ({ ...(provisional || {}), ...liveMap });

/** Index définitif : les deux lots, disjoints (en cas de chevauchement transitoire, `live` prime). */
export const joinTiers = (liveMap, archiveMap) => ({ ...archiveMap, ...liveMap });

/** Les lectures de lot ne portent pas toutes un ETag ; sans les deux, on ne sait pas si le contenu a changé. */
export const combinedEtag = (liveEtag, archiveEtag) => (liveEtag && archiveEtag ? `${liveEtag}|${archiveEtag}` : null);
