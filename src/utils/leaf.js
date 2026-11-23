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

// --- Photos : l'annonce ne donne qu'UNE taille, les deux sources en servent plusieurs selon l'URL (vérifié en réel
// le 2026-11-23). Kijiji : `?rule=kijijica-<largeur>-jpg` (200, 640 et 1600 existent ; 1920 renvoie 404). AutoHebdo
// (images AutoScout24) : `/<L>x<H>.webp` (360x270, 720x540 et 1280x960). Toute autre URL est rendue telle quelle.
const IMAGE_SIZES = {
    thumb: { kijiji: 200, autoscout: '360x270' },
    medium: { kijiji: 640, autoscout: '720x540' },
    large: { kijiji: 1600, autoscout: '1280x960' },
};
const KIJIJI_RULE_RE = /([?&]rule=kijijica-)\d+(-jpg)/;
const AUTOSCOUT_SIZE_RE = /\/\d+x\d+\.webp$/;

/** URL de la photo dans la taille demandée (`thumb`, `medium` ou `large`). */
export const leafImageUrl = (url, size = 'medium') => {
    const u = String(url || '');
    const wanted = IMAGE_SIZES[size] || IMAGE_SIZES.medium;
    if (u.includes('media.kijiji.ca') && KIJIJI_RULE_RE.test(u)) return u.replace(KIJIJI_RULE_RE, `$1${wanted.kijiji}$2`);
    if (u.includes('pictures.autoscout24.net') && AUTOSCOUT_SIZE_RE.test(u)) return u.replace(AUTOSCOUT_SIZE_RE, `/${wanted.autoscout}.webp`);
    return u;
};
/** Photos d'une annonce dans une taille, sans doublon (la liste et la fiche peuvent répéter une photo), `https` seulement. */
export const leafImages = (urls, size = 'medium') => {
    const out = [];
    for (const raw of urls || []) {
        if (typeof raw !== 'string' || !raw.startsWith('https://')) continue;
        const u = leafImageUrl(raw, size);
        if (!out.includes(u)) out.push(u);
    }
    return out;
};

// --- Réglages de recherche (panneau de la page Leaf) : le formulaire manipule des chaînes, l'API attend des nombres.
export const LEAF_SOURCES = [['kijiji', 'Kijiji Autos'], ['autohebdo', 'AutoHebdo']];

export const configToForm = (cfg) => ({
    enabled: !!cfg?.enabled,
    frequency: String(cfg?.scan?.frequency ?? 120),
    minPrice: String(cfg?.scan?.min_price ?? 1500),
    maxPrice: String(cfg?.scan?.max_price ?? 7500),
    maxKm: String(cfg?.scan?.max_km ?? 150000),
    pages: String(cfg?.scan?.pages ?? 2),
    years: (cfg?.scan?.years || [2016, 2017, 2018]).join(', '),
    sources: Object.fromEntries(LEAF_SOURCES.map(([key]) => [key, (cfg?.scan?.sources || []).includes(key)])),
    readDetails: cfg?.scan?.read_details !== false,
    homeName: cfg?.scan?.home?.name || '',
    lat: String(cfg?.scan?.home?.latitude ?? ''),
    lon: String(cfg?.scan?.home?.longitude ?? ''),
    radius: String(cfg?.scan?.radius_km ?? 150),
    notifyEnabled: cfg?.notify?.enabled !== false,
    notifyNew: cfg?.notify?.new !== false,
    notifyDrop: cfg?.notify?.price_drop !== false,
});

const toInt = (s) => (/^\s*-?\d+\s*$/.test(String(s)) ? parseInt(s, 10) : NaN);
const toNum = (s) => (String(s).trim() !== '' && Number.isFinite(Number(s)) ? Number(s) : NaN);

/** { errors: [message…], body } — `body` est le corps de `PUT /leaf/config` (mêmes bornes que le serveur ; le serveur revalide). */
export const validateLeafForm = (form) => {
    const errors = [];
    const frequency = toInt(form.frequency);
    const minPrice = toInt(form.minPrice);
    const maxPrice = toInt(form.maxPrice);
    const maxKm = toInt(form.maxKm);
    const pages = toInt(form.pages);
    const radius = toInt(form.radius);
    const years = String(form.years).split(/[\s,;]+/).filter(Boolean).map(toInt);
    const sources = LEAF_SOURCES.map(([key]) => key).filter((key) => form.sources?.[key]);
    const lat = toNum(form.lat);
    const lon = toNum(form.lon);
    if (!(frequency >= 60 && frequency <= 1440)) errors.push('Fréquence : entre 60 et 1 440 minutes.');
    if (!(minPrice >= 0)) errors.push('Prix minimum : un nombre positif.');
    if (!(maxPrice >= 0)) errors.push('Prix maximum : un nombre positif.');
    else if (minPrice >= 0 && maxPrice < minPrice) errors.push('Le prix maximum doit être au moins égal au prix minimum.');
    if (!(maxKm >= 1)) errors.push('Kilométrage maximum : un nombre positif.');
    if (!(pages >= 1 && pages <= 3)) errors.push('Pages Kijiji : de 1 à 3.');
    if (years.length === 0 || years.some((y) => !(y >= 2010 && y <= 2030))) errors.push('Années : une liste entre 2010 et 2030 (ex. 2016, 2017, 2018).');
    if (sources.length === 0) errors.push('Choisissez au moins une source.');
    if (!(lat >= -90 && lat <= 90) || !(lon >= -180 && lon <= 180)) errors.push('Ville de référence : latitude et longitude valides.');
    if (!(radius >= 1 && radius <= 2000)) errors.push('Rayon : de 1 à 2 000 km.');
    if (errors.length) return { errors, body: null };
    const home = { latitude: lat, longitude: lon };
    if (String(form.homeName).trim()) home.name = String(form.homeName).trim().slice(0, 80);
    return {
        errors,
        body: {
            enabled: !!form.enabled,
            scan: {
                frequency, min_price: minPrice, max_price: maxPrice, max_km: maxKm, pages, years: [...new Set(years)].sort(),
                sources, read_details: !!form.readDetails, home, radius_km: radius,
            },
            notify: { enabled: !!form.notifyEnabled, new: !!form.notifyNew, price_drop: !!form.notifyDrop },
        },
    };
};
