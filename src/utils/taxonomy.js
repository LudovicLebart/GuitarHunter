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

// Branche des contenants, dont CERTAINES feuilles portent des noms génériques d'instruments
// ("Guitare Acoustique", "Guitare Electrique") tout en désignant des étuis. Un tel nom nu n'est
// jamais résolu : il est bien plus probable qu'il désigne l'instrument lui-même.
// ⚠️ Restreint le 2026-08-16 après l'audit en production : la règle bloquait auparavant TOUTE
// feuille de la branche, y compris des termes d'étui purs sans ambiguïté ("Housse_Souple",
// "Gigbag Standard", "ATA Road Case") — ≈19 annonces correctement classées rendues invisibles.
// Miroir de `backend/taxonomy.py::CONTAINER_BRANCHES`.
const CONTAINER_BRANCHES = ['etui_housse'];

// Segments minimum d'un chemin partiel accepté pour une réparation par suffixe.
const MIN_PARTIAL_PATH_SEGMENTS = 2;

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

// Racines désignant des objets (guitare, amplificateur…), hors contenants — déduites de la
// taxonomie plutôt que codées en dur.
const INSTRUMENT_ROOTS = [...new Set(
  Object.values(TAXONOMY_INDEX.byPath)
    .map(segments => segments[0])
    .filter(root => !CONTAINER_BRANCHES.includes(root))
    .map(normalizeSegment)
)];

/**
 * Étend un chemin INCOMPLET vers l'unique chemin canonique qui s'y termine.
 * L'IA produit régulièrement des chemins presque bons : racine oubliée
 * (`electrique.solid_body.Double_Cut.SG`), niveau intermédiaire sauté, ou racine obsolète
 * (`accessoire_etui.protection.…`). Tous désignent une seule catégorie sans ambiguïté.
 * Miroir de `backend/taxonomy.py::_repair_partial_path`.
 */
const repairPartialPath = (classification) => {
  let segments = normalizePath(classification).split('.').filter(Boolean);
  const canonicalPaths = Object.values(TAXONOMY_INDEX.byPath);

  while (segments.length >= MIN_PARTIAL_PATH_SEGMENTS) {
    const suffix = `.${segments.join('.')}`;
    const matches = [...new Set(
      canonicalPaths
        .filter(path => normalizePath(path.join('.')).endsWith(suffix))
        .map(path => path.join('.'))
    )];
    if (matches.length === 1) return matches[0].split('.');
    if (matches.length > 1) return null; // Plusieurs cibles : on ne devine pas.
    segments = segments.slice(1);        // Racine inventée/obsolète : on la retire.
  }
  return null;
};

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
    // Feuille d'un contenant : refusée seulement si son nom commence par un nom de famille
    // d'instrument. Les termes d'étui purs passent normalement.
    if (CONTAINER_BRANCHES.includes(segments[0])) {
      const leafKey = normalizeSegment(segments[segments.length - 1]);
      if (INSTRUMENT_ROOTS.some(root => leafKey.startsWith(root))) {
        return { segments: null, ambiguous: true };
      }
    }
    return { segments, ambiguous: false };
  }
  if (distinct.length > 1) return { segments: null, ambiguous: true };

  // Chemin incomplet (racine oubliée, niveau sauté, racine obsolète) : extensible sans ambiguïté.
  const repaired = repairPartialPath(classification);
  if (repaired) return { segments: repaired, ambiguous: false };

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
