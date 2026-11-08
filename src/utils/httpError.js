/** Erreur d'une réponse HTTP non réussie de l'API. Le corps FastAPI `{"detail": …}` est lu une fois ici :
 *  - `detail` (texte lisible) : le `detail` s'il est un texte, ou son `message` s'il est `{code, message}` ;
 *  - `code` : le code machine éventuel (`daily_cap`…), à préférer à toute recherche dans le texte ;
 *  - `status`. Le message garde le texte brut quand le corps n'est pas lisible. */
export const buildHttpError = (method, path, status, bodyText) => {
  let detail = null;
  let code = null;
  try {
    const d = JSON.parse(bodyText)?.detail;
    if (typeof d === 'string') detail = d;
    else if (d && typeof d === 'object' && !Array.isArray(d)) {
      if (typeof d.message === 'string') detail = d.message;
      if (typeof d.code === 'string') code = d.code;
    }
  } catch { /* corps non JSON : message brut */ }
  const error = new Error(`apiService: ${method} ${path} a échoué (${status}) ${detail ?? bodyText}`);
  error.status = status;
  if (detail) error.detail = detail;
  if (code) error.code = code;
  return error;
};

/** Message affiché pour une commande refusée : le détail du serveur quand il existe (sans point final en double). */
export const commandRefusedMessage = (error) => {
  const detail = typeof error?.detail === 'string' ? error.detail.trim().replace(/[.\s]+$/, '') : '';
  if (detail) return `Commande non envoyée : ${detail.charAt(0).toLowerCase()}${detail.slice(1)}.`;
  if (error?.status === 429) return 'Commande non envoyée : trop de commandes sont déjà en attente, réessayez dans un moment.';
  if (error?.status === 422) return 'Commande non envoyée : commande refusée par le serveur.';
  return "Erreur lors de l'envoi de la commande.";
};
