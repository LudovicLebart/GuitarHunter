/**
 * Clé canonique et libellé d'affichage d'une ville — miroir de `backend/cities.py`.
 *
 * La même ville arrivait dans les statistiques sous plusieurs graphies (`Montréal, QC`,
 * `montreal`, `St-Jean-sur-Richelieu,QC`) et y était donc comptée plusieurs fois. Deux
 * producteurs écrivent deux formats : Facebook la chaîne scrapée telle quelle, Kijiji la clé
 * normalisée de la ville configurée (minuscules, sans accents).
 *
 * Deux notions à ne pas confondre :
 *  - la CLÉ (`normalizeCityKey`) regroupe — insensible aux accents, casse, tirets, abréviations
 *    Saint/St et région ;
 *  - le LIBELLÉ (`pickBestLabel`) affiche — on garde la graphie la plus riche rencontrée
 *    (accents + région), format « Ville, RÉGION » qui distingue les homonymes (`Paris, IDF`).
 */

/**
 * Clé de regroupement. Reproduit exactement `ListingParser.normalize_city_name` (Python) :
 * partie avant la virgule, minuscules, tirets/points → espaces, St→Saint, Ste→Sainte, accents
 * retirés. Toute divergence entre les deux ferait regrouper différemment le backend et l'UI.
 */
export const normalizeCityKey = (raw) => {
  if (!raw) return '';
  let name = String(raw).split(',')[0].trim().toLowerCase();
  name = name.replace(/-/g, ' ').replace(/\./g, ' ');
  name = name
    .split(/\s+/)
    .filter(Boolean)
    .map(word => (word === 'st' ? 'saint' : word === 'ste' ? 'sainte' : word))
    .join(' ');
  return name.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
};

/**
 * Note la « richesse » d'une graphie : région présente, puis accents/majuscules, puis longueur.
 * Miroir de `backend/cities.py::score_label`.
 */
export const scoreLabel = (raw) => {
  if (!raw) return [0, 0, 0];
  const text = String(raw);
  const hasRegion = text.includes(',') && text.split(',').slice(1).join(',').trim() ? 1 : 0;
  const hasDiacriticsOrCase = /[A-Z]/.test(text) || /[^\x00-\x7F]/.test(text) ? 1 : 0;
  return [hasRegion, hasDiacriticsOrCase, text.length];
};

const compareLabels = (a, b) => {
  const [ra, da, la] = scoreLabel(a);
  const [rb, db, lb] = scoreLabel(b);
  // Décroissant sur le score, puis alphabétique décroissant — déterministe, donc stable d'un
  // rendu à l'autre (sinon le libellé d'une ville pourrait changer au gré de l'ordre des deals).
  return (rb - ra) || (db - da) || (lb - la) || String(b).localeCompare(String(a));
};

/** Choisit la graphie à afficher parmi celles observées pour une même ville. */
export const pickBestLabel = (labels) => {
  const candidates = (labels || []).filter(l => l && String(l).trim());
  if (candidates.length === 0) return null;
  return [...candidates].sort(compareLabels)[0];
};

/**
 * Regroupe une liste de valeurs `location` brutes par clé canonique.
 * Retourne `{ key → { label, values } }` : le libellé retenu pour l'affichage et toutes les
 * graphies qu'il recouvre (utile pour un diagnostic ou un tooltip).
 */
export const buildCityLabelMap = (locations) => {
  const groups = {};
  (locations || []).forEach(raw => {
    const key = normalizeCityKey(raw);
    if (!key) return;
    if (!groups[key]) groups[key] = { label: null, values: [] };
    groups[key].values.push(raw);
  });
  Object.values(groups).forEach(group => {
    group.label = pickBestLabel(group.values);
  });
  return groups;
};
