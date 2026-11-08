/** Échappe un texte pour l'insérer dans un gabarit HTML (InfoWindow de la carte) : `&`, `<`, `>`, `"` et `'`. */
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
