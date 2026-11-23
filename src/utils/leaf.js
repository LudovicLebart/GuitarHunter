// Leaf Hunter : routes, libellés, tri/filtre PURS (aucun React, aucun `import.meta`), testés avec `node --test`
// (src/utils/leaf.test.js). Les annonces viennent de l'API (`/leaf/*`, voir apiService.js) ; navigation par le hash de l'URL
// (`#leaf`, `#leaf/<id>`), sans routeur, comme les fiches.

export const LEAF_HREF = '#leaf';
export const leafDealHref = (id) => `#leaf/${id}`;

const LEAF_HASH_RE = /^#leaf(?:\/([A-Za-z0-9_-]{1,120}))?$/;
/** `#leaf` -> { view: 'list' } ; `#leaf/<id>` -> { view: 'detail', id } ; sinon null. */
export const parseLeafHash = (hash) => {
    const m = LEAF_HASH_RE.exec(String(hash || ''));
    if (!m) return null;
    return m[1] ? { view: 'detail', id: m[1] } : { view: 'list' };
};

export const formatPrice = (n) => (typeof n === 'number' && Number.isFinite(n) ? `${Math.round(n).toLocaleString('fr-CA')} $` : '—');
export const formatKm = (n) => (typeof n === 'number' && Number.isFinite(n) ? `${Math.round(n).toLocaleString('fr-CA')} km` : 'km ?');

export const FLAG_LABELS = {
    soh_unknown: 'SOH inconnu (à mesurer avec LeafSpy)',
    km_unknown: 'Kilométrage inconnu',
    battery_unknown: 'Capacité de batterie inconnue',
    battery_24_possible: 'Batterie 24 kWh possible',
    battery_24_replaced: 'Batterie 24 kWh remplacée (preuve à demander)',
    detail_unavailable: 'Fiche de l\'annonce illisible',
};
/** Libellé d'un drapeau ; `accident:<mot>` -> « Mot d'alerte : <mot> » ; un drapeau inconnu est affiché tel quel. */
export const flagLabel = (flag) => {
    const f = String(flag || '');
    if (f.startsWith('accident:')) return `Mot d'alerte : ${f.slice('accident:'.length)}`;
    return FLAG_LABELS[f] || f;
};

export const WINTER_LABELS = { ok: 'Suffisante', juste: 'Juste', insuffisant: 'Insuffisante', inconnu: 'Inconnue' };
/** « 75–110 km » (autonomie hivernale estimée) ou null si inconnue. */
export const winterRange = (analysis) => {
    const w = analysis?.winter_fit;
    return w && w.low_km != null && w.high_km != null ? `${w.low_km}–${w.high_km} km` : null;
};
export const winterVerdict = (analysis) => analysis?.winter_fit?.verdict || 'inconnu';

export const SORTS = {
    price: { label: 'Prix', cmp: (a, b) => (a.price ?? Infinity) - (b.price ?? Infinity) },
    km: { label: 'Kilométrage', cmp: (a, b) => (a.km ?? Infinity) - (b.km ?? Infinity) },
    year: { label: 'Année', cmp: (a, b) => (b.year ?? 0) - (a.year ?? 0) },
    recent: { label: 'Récentes', cmp: (a, b) => String(b.first_seen_at || '').localeCompare(String(a.first_seen_at || '')) },
};

const normalize = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** Filtre (favoris seulement, recherche texte sans accents) puis tri. N'altère pas la liste d'origine. */
export const filterAndSortDeals = (deals, { favoritesOnly = false, query = '', sort = 'price' } = {}) => {
    const q = normalize(query).trim();
    const sorter = (SORTS[sort] || SORTS.price).cmp;
    return (deals || [])
        .filter((d) => (!favoritesOnly || d.is_favorite)
            && (!q || normalize(`${d.title} ${d.location} ${d.trim} ${d.year}`).includes(q)))
        .slice()
        .sort(sorter);
};

/** Évolution du prix : { first, last, delta } (delta < 0 = baisse), ou null s'il n'y a pas assez de points. */
export const priceTrend = (history) => {
    const prices = (history || []).map((h) => Number(h.price)).filter(Number.isFinite);
    if (prices.length < 2) return null;
    const first = prices[0];
    const last = prices[prices.length - 1];
    return { first, last, delta: last - first };
};

export const CHECKLIST_ITEMS = [
    ['leafspy', 'Lecture LeafSpy : SOH et barres de capacité'],
    ['carfax', 'Rapport Carfax / historique d\'accidents'],
    ['battery_proof', 'Preuve du remplacement de batterie (si 24 kWh remplacée)'],
    ['chademo', 'Port CHAdeMO et charge rapide testés'],
    ['heat_pump', 'Pompe à chaleur / chauffage confirmés'],
    ['winter_tires', 'Pneus d\'hiver inclus ou à prévoir'],
    ['cable', 'Câble de recharge fourni'],
    ['test_drive', 'Essai routier fait'],
];
export const checklistProgress = (checklist) => {
    const done = CHECKLIST_ITEMS.filter(([key]) => checklist?.[key] === true).length;
    return { done, total: CHECKLIST_ITEMS.length };
};
