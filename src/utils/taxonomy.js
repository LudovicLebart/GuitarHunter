import promptsData from '../../prompts.json';
import { formatTaxonomyLabel } from '../constants';

/**
 * Résolution et affichage de la taxonomie — source unique côté frontend.
 *
 * ⚠️ POURQUOI DEUX NORMALISATIONS DISTINCTES (bug trouvé le 2026-08-16)
 * L'ancienne implémentation normalisait un chemin complet avec le même helper que les libellés,
 * lequel supprime TOUS les caractères non alphanumériques — points compris. Conséquence :
 *   normalize("Guitare Electrique")  === "guitareelectrique"
 *   normalize("guitare.electrique")  === "guitareelectrique"   ← MÊME CLÉ
 * La feuille `etui_housse.Etui_Rigide.Guitare Electrique` (un étui) entrait donc en collision avec
 * la branche `guitare.electrique` (l'instrument). Les chemins complets étant testés en premier, tout
 * étui classé par son nom de feuille était résolu comme une vraie guitare électrique — pas seulement
 * mal affiché : mal filtré et mal compté. Le séparateur de chemin est désormais préservé
 * (`normalizePath`), il ne peut plus se confondre avec du texte de libellé.
 */

// Normalise UN segment : minuscules, sans accents, alphanumérique uniquement.
export const normalizeSegment = (str) => {
  if (!str) return '';
  return String(str)
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');
};

// Normalise un CHEMIN en préservant le séparateur '.', qui porte du sens.
export const normalizePath = (str) =>
  String(str || '').split('.').map(normalizeSegment).filter(Boolean).join('.');

const MASTER_TAXONOMY = promptsData.taxonomy_master || {};

// Clés courtes et branche `etui_housse` exclues de la recherche floue : voir le commentaire
// historique de findPathFuzzy (collision "cordes guitare" ⊃ "sg", feuilles d'étuis qui reprennent
// mot pour mot les noms d'instruments).
const FUZZY_MIN_KEY_LENGTH = 5;
const FUZZY_EXCLUDED_BRANCHES = ['etui_housse'];

// Branches dont les FEUILLES portent des noms génériques d'instruments ("Guitare Acoustique",
// "Guitare Electrique", "Basse") alors qu'elles désignent des ÉTUIS. Un nom nu appartenant à ces
// branches n'est jamais résolu : il est bien plus probable qu'il désigne l'instrument lui-même.
// Seul le chemin complet permet de classer un étui — c'est ce que le prompt exige désormais.
// Miroir de `backend/taxonomy.py::AMBIGUOUS_LEAF_BRANCHES`.
const AMBIGUOUS_LEAF_BRANCHES = ['etui_housse'];

/**
 * Index de la taxonomie :
 *  - `byPath`  : chemin normalisé (points conservés) → tableau de segments
 *  - `byLeaf`  : nom de feuille/branche normalisé → TOUS les chemins qui portent ce nom.
 *                Un tableau, pas une valeur unique : plusieurs branches partagent des homonymes
 *                (`Guitare Acoustique` est à la fois un étui et un instrument, `solid_body` existe
 *                sous `electrique` ET sous `basse`). L'ancienne map écrasait silencieusement les
 *                doublons — la dernière branche parcourue gagnait, sans que rien ne le signale.
 *  - `nodes`   : catalogue plat pour l'autocomplétion.
 */
const buildIndex = () => {
  const byPath = {};
  const byLeaf = {};
  const nodes = [];

  const register = (segments) => {
    const pathKey = normalizePath(segments.join('.'));
    byPath[pathKey] = segments;

    // Deux clés pour un même nœud : son nom de feuille, ET son chemin complet privé de ses points.
    // C'est le cœur du bug des étuis : "Guitare Electrique" est une feuille de `etui_housse`, mais
    // aussi la lecture naturelle du CHEMIN `guitare.electrique`. Les enregistrer sous la même clé
    // rend le nom nu détectable comme ambigu, quel que soit le sens voulu par l'IA — sans quoi on
    // ne fait que déplacer l'erreur (un étui devenait une guitare ; l'inverse arriverait ensuite).
    const keys = new Set([
      normalizeSegment(segments[segments.length - 1]),
      normalizePath(segments.join('.')).replace(/\./g, '')
    ]);
    keys.forEach(key => {
      if (!key) return;
      if (!byLeaf[key]) byLeaf[key] = [];
      byLeaf[key].push(segments);
    });

    nodes.push({
      path: segments.join('.'),
      label: formatTaxonomyLabel(segments[segments.length - 1]),
      breadcrumb: segments.slice(0, -1).map(formatTaxonomyLabel).join(' › '),
      depth: segments.length,
      labelNormalized: segments[segments.length - 1]
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
    });
  };

  const traverse = (node, currentPath) => {
    if (Array.isArray(node)) {
      node.forEach(item => register([...currentPath, item]));
    } else if (typeof node === 'object' && node !== null) {
      Object.keys(node).forEach(key => {
        const segments = [...currentPath, key];
        register(segments);
        traverse(node[key], segments);
      });
    }
  };

  traverse(MASTER_TAXONOMY, []);
  return { byPath, byLeaf, nodes };
};

export const TAXONOMY_INDEX = buildIndex();
export const TAXONOMY_NODES = TAXONOMY_INDEX.nodes;

// Recherche floue : le chemin dont la clé textuelle est la plus longue (donc la plus spécifique)
// parmi celles contenues dans le texte. Dernier recours seulement — voir les exclusions ci-dessus.
const findPathFuzzy = (normalizedText) => {
  let bestKey = null;
  let bestPath = null;
  for (const [leafKey, paths] of Object.entries(TAXONOMY_INDEX.byLeaf)) {
    if (leafKey.length < FUZZY_MIN_KEY_LENGTH) continue;
    // Un nom ambigu (plusieurs nœuds distincts) ne peut pas être tranché par une recherche floue.
    const distinctPaths = [...new Set(paths.map(p => p.join('.')))];
    if (distinctPaths.length > 1) continue;
    const path = paths[0];
    if (path.length < 2) continue;
    if (FUZZY_EXCLUDED_BRANCHES.includes(path[0])) continue;
    if (normalizedText.includes(leafKey) && (!bestKey || leafKey.length > bestKey.length)) {
      bestKey = leafKey;
      bestPath = path;
    }
  }
  return bestPath;
};

/**
 * Résout la valeur `classification` renvoyée par l'IA en un chemin canonique.
 * Retourne `{ segments, ambiguous }` — `segments: null` si non résolue.
 * `ambiguous: true` signale un nom de feuille porté par plusieurs branches (ex: "Guitare
 * Acoustique") : impossible de trancher sans le chemin complet, donc volontairement NON résolu
 * plutôt que rattaché à une branche au hasard.
 */
export const resolveClassification = (classification) => {
  if (!classification) return { segments: null, ambiguous: false };

  // 1. Chemin complet exact (le format désormais exigé de l'IA)
  const asPath = normalizePath(classification);
  if (TAXONOMY_INDEX.byPath[asPath]) {
    return { segments: TAXONOMY_INDEX.byPath[asPath], ambiguous: false };
  }

  // 2. Nom de feuille seul (format historique, encore massivement présent en base).
  // Les candidats sont dédoublonnés : un même nœud est indexé sous plusieurs clés.
  const asLeaf = normalizeSegment(classification);
  const candidates = TAXONOMY_INDEX.byLeaf[asLeaf] || [];
  const distinct = [...new Set(candidates.map(c => c.join('.')))];
  if (distinct.length === 1) {
    const segments = distinct[0].split('.');
    if (AMBIGUOUS_LEAF_BRANCHES.includes(segments[0])) return { segments: null, ambiguous: true };
    return { segments, ambiguous: false };
  }
  if (distinct.length > 1) return { segments: null, ambiguous: true };

  // 3. Dernier recours : recherche floue sur du texte libre (ex: "Fender Stratocaster")
  const fuzzy = findPathFuzzy(asLeaf);
  return { segments: fuzzy || null, ambiguous: false };
};

// Chemin en dot-notation (ex: "guitare.acoustique_acier.formes_standard.Parlor"), ou null.
export const resolveClassificationPath = (classification) => {
  const { segments } = resolveClassification(classification);
  return segments ? segments.join('.') : null;
};

/**
 * Libellé lisible destiné à l'UI.
 * La branche racine est préfixée quand elle n'est PAS `guitare` — sans ça, un étui s'affiche
 * "Guitare Electrique" et se lit comme une guitare (symptôme signalé par l'utilisateur), et un
 * ampli "Combo Lampes" perd son contexte. Pour une guitare, la feuille seule suffit et reste
 * courte ("Parlor Standard"), ce qui préserve l'affichage actuel des cartes.
 * Une valeur non résolue est retournée telle quelle mais formatée — jamais de chemin technique
 * brut (`guitare.electrique.lespaul`) à l'écran.
 */
export const formatClassificationLabel = (classification) => {
  if (!classification) return null;
  const { segments } = resolveClassification(classification);

  if (!segments) {
    // Valeur inconnue de la taxonomie : on affiche au moins son dernier segment, proprement.
    const fallback = String(classification).split('.').pop();
    return formatTaxonomyLabel(fallback);
  }

  const leaf = formatTaxonomyLabel(segments[segments.length - 1]);
  if (segments.length > 1 && segments[0] !== 'guitare') {
    return `${formatTaxonomyLabel(segments[0])} › ${leaf}`;
  }
  return leaf;
};
