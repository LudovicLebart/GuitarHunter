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
    year_unknown: 'Année inconnue (non écrite dans l\'annonce)',
    battery_unknown: 'Capacité de batterie inconnue',
    battery_24_possible: 'Batterie 24 kWh possible',
    battery_24_replaced: 'Batterie 24 kWh remplacée (preuve à demander)',
    detail_unavailable: 'Fiche de l\'annonce illisible',
    ai_unsupported_claim: 'IA : un fait sans preuve dans l\'annonce a été écarté',
    ai_conflict: 'IA : contredite par les règles (les règles sont retenues)',
    ai_polarity_corrected: 'IA : sens d\'un fait corrigé par le code d\'après sa citation (ex. « jamais accidentée »)',
    ai_accident_mentioned: 'Accident ou dommage mentionné (lu par l\'IA)',
    photo_km_mismatch: 'Kilométrage d\'une photo différent de celui de l\'annonce',
};
/** Libellé d'un drapeau ; `accident:<mot>` -> « Mot d'alerte : <mot> » ; un drapeau inconnu est affiché tel quel. */
export const flagLabel = (flag) => {
    const f = String(flag || '');
    if (f.startsWith('accident:')) return `Mot d'alerte : ${f.slice('accident:'.length)}`;
    return FLAG_LABELS[f] || f;
};

// Verdict calculé EN CODE (backend/leaf/verdict.py), jamais par l'IA.
export const VERDICTS = {
    CANDIDAT_FORT: { label: 'Candidat fort', style: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
    A_VERIFIER: { label: 'À vérifier', style: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
    BATTERIE_DOUTEUSE: { label: 'Batterie douteuse', style: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
    TROP_CHER: { label: 'Trop cher', style: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
    INCOMPLET: { label: 'Infos incomplètes', style: 'bg-slate-700/50 text-slate-300 border-slate-600' },
};
export const verdictInfo = (code) => VERDICTS[code] || null;

// Faits extraits par l'IA (niveau 2) : seuls les faits PROUVÉS par une citation de l'annonce sont stockés.
export const AI_FACT_LABELS = {
    soh_pct: 'SOH annoncé', battery_replaced: 'Batterie de traction remplacée', accident_mentioned: 'Accident ou dommage mentionné',
    heat_pump: 'Pompe à chaleur', winter_tires: 'Pneus d\'hiver', chademo: 'Charge rapide CHAdeMO', charging_cable: 'Câble de recharge',
};
export const CONFIDENCE_LABELS = { high: 'confiance élevée', medium: 'confiance moyenne', low: 'confiance faible' };
/** Lignes affichables [{ key, label, value, evidence, confidence }] des faits de `analysis.ai`, dans l'ordre de AI_FACT_LABELS. */
export const aiFactLines = (ai) => Object.entries(AI_FACT_LABELS)
    .filter(([key]) => ai?.facts?.[key] && ai.facts[key].value != null)
    .map(([key, label]) => {
        const f = ai.facts[key];
        return { key, label, value: typeof f.value === 'number' ? `${f.value} %` : (f.value ? 'Oui' : 'Non'), evidence: f.evidence || '',
            confidence: CONFIDENCE_LABELS[f.confidence] || CONFIDENCE_LABELS.low, corrected: f.corrected === true };
    });
export const AI_PROVIDERS = [['local', 'Qwen local (Dell)'], ['gemini', 'Gemini Flash']];

export const WINTER_LABELS = { ok: 'Suffisante', juste: 'Juste', insuffisant: 'Insuffisante', inconnu: 'Inconnue' };
/** « 75–110 km » (autonomie hivernale estimée) ou null si inconnue. */
export const winterRange = (analysis) => {
    const w = analysis?.winter_fit;
    return w && w.low_km != null && w.high_km != null ? `${w.low_km}–${w.high_km} km` : null;
};
export const winterVerdict = (analysis) => analysis?.winter_fit?.verdict || 'inconnu';

// Tris de la liste. `key` : valeur numérique à comparer (null = inconnue, TOUJOURS rangée en dernier, quel que soit le sens) ; `dir` : sens naturel
// (« asc » = le plus petit d'abord). Le bouton de sens de la page inverse l'ordre sans jamais remonter les valeurs inconnues.
const VERDICT_RANK = { CANDIDAT_FORT: 0, A_VERIFIER: 1, INCOMPLET: 2, TROP_CHER: 3, BATTERIE_DOUTEUSE: 4 };
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : (v != null && v !== '' && Number.isFinite(Number(v)) ? Number(v) : null));
const time = (v) => { const t = Date.parse(v || ''); return Number.isFinite(t) ? t : null; };
export const SORTS = {
    price: { label: 'Prix', key: (d) => num(d.price), dir: 'asc' },
    km: { label: 'Kilométrage', key: (d) => num(d.km), dir: 'asc' },
    year: { label: 'Année', key: (d) => num(d.year), dir: 'desc' },
    recent: { label: 'Date : nouvelles d\'abord', key: (d) => time(d.first_seen_at), dir: 'desc' },
    updated: { label: 'Dernière modification', key: (d) => time(d.timestamp), dir: 'desc' },
    drop: { label: 'Baisse de prix', key: (d) => (num(d.price_drop_amount) > 0 ? num(d.price_drop_amount) : null), dir: 'desc' },
    favorite: { label: 'Favoris d\'abord', key: (d) => (d.is_favorite ? 0 : 1), dir: 'asc', then: 'price' },
    verdict: { label: 'Verdict (meilleurs d\'abord)', key: (d) => (d.verdict in VERDICT_RANK ? VERDICT_RANK[d.verdict] : null), dir: 'asc', then: 'price' },
    soh: { label: 'SOH annoncé', key: (d) => num(d.soh_announced), dir: 'desc' },
    winter: { label: 'Autonomie hivernale', key: (d) => num(d.analysis?.winter_fit?.high_km), dir: 'desc' },
};
export const SORT_KEYS = Object.keys(SORTS);

/** Comparateur du tri `sort` (clé inconnue = prix). `reverse` inverse le sens naturel ; les valeurs inconnues restent en dernier dans les deux sens. */
export const compareBy = (sort, reverse = false) => {
    const spec = SORTS[sort] || SORTS.price;
    const sign = (spec.dir === 'desc' ? -1 : 1) * (reverse ? -1 : 1);
    const tie = spec.then && SORTS[spec.then] ? compareBy(spec.then) : null;
    return (a, b) => {
        const x = spec.key(a);
        const y = spec.key(b);
        if (x === null && y === null) return tie ? tie(a, b) : 0;
        if (x === null) return 1;
        if (y === null) return -1;
        return x === y ? (tie ? tie(a, b) : 0) : (x - y) * sign;
    };
};

const normalize = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** Filtre (favoris seulement, recherche texte sans accents) puis tri. N'altère pas la liste d'origine. */
/** Doublons probables MASQUABLES : une annonce marquée `duplicate_of` dont l'originale est bien dans la liste (sinon on la garde : ne jamais faire
 *  disparaître une annonce parce que son original est masqué, rejeté ou vendu). */
export const hiddenDuplicateIds = (deals) => {
    const present = new Set((deals || []).map((d) => d.id));
    return new Set((deals || []).filter((d) => d.duplicate_of && d.duplicate_of !== d.id && present.has(d.duplicate_of)).map((d) => d.id));
};
/** { idOriginal: nombre de doublons } (seulement ceux dont l'original est présent), pour afficher « +2 doublons » sur la carte. */
export const duplicateCounts = (deals) => {
    const hidden = hiddenDuplicateIds(deals);
    const counts = {};
    for (const d of deals || []) if (hidden.has(d.id)) counts[d.duplicate_of] = (counts[d.duplicate_of] || 0) + 1;
    return counts;
};

export const filterAndSortDeals = (deals, { favoritesOnly = false, query = '', sort = 'price', reverse = false, hideDuplicates = false } = {}) => {
    const q = normalize(query).trim();
    const sorter = compareBy(sort, reverse);
    const filtered = (deals || []).filter((d) => (!favoritesOnly || d.is_favorite)
        && (!q || normalize(`${d.title} ${d.location} ${d.trim} ${d.year}`).includes(q)));
    // Les doublons se décident APRÈS les autres filtres : une copie dont l'original est filtré (ex. « favoris seulement ») reste affichée.
    const duplicates = hideDuplicates ? hiddenDuplicateIds(filtered) : new Set();
    return filtered.filter((d) => !duplicates.has(d.id)).sort(sorter);
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
export const LEAF_SOURCES = [['kijiji', 'Kijiji Autos'], ['autohebdo', 'AutoHebdo'], ['facebook', 'Facebook Marketplace (navigateur, expérimental)']];

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
    aiEnabled: !!cfg?.analysis?.enabled,
    aiMax: String(cfg?.analysis?.max_calls_per_day ?? 30),
    aiExpertMax: String(cfg?.analysis?.max_expert_per_day ?? 5),
    aiPhotoMax: String(cfg?.analysis?.max_photo_calls_per_day ?? 20),
    aiProviders: Object.fromEntries(AI_PROVIDERS.map(([key]) => [key, (cfg?.analysis?.providers || ['local', 'gemini']).includes(key)])),
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
    const aiMax = toInt(form.aiMax);
    const aiExpertMax = toInt(form.aiExpertMax);
    const aiPhotoMax = toInt(form.aiPhotoMax);
    const aiProviders = AI_PROVIDERS.map(([key]) => key).filter((key) => form.aiProviders?.[key]);
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
    if (!(aiMax >= 1 && aiMax <= 500)) errors.push('Analyses IA par jour : de 1 à 500.');
    if (!(aiExpertMax >= 1 && aiExpertMax <= 50)) errors.push('Analyses approfondies par jour : de 1 à 50.');
    if (!(aiPhotoMax >= 1 && aiPhotoMax <= 200)) errors.push('Lectures de photos par jour : de 1 à 200.');
    if (aiProviders.length === 0) errors.push('Analyse IA : choisissez au moins un fournisseur.');
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
            analysis: { enabled: !!form.aiEnabled, max_calls_per_day: aiMax, max_expert_per_day: aiExpertMax, max_photo_calls_per_day: aiPhotoMax, providers: aiProviders },
        },
    };
};

// --- Analyse approfondie (Expert, niveau 3) : avis stocké dans `analysis.expert`.
export const WORTH_LABELS = {
    oui: { label: 'À visiter', style: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
    'peut-etre': { label: 'Peut-être', style: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
    non: { label: 'À éviter', style: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
};
/** Avis de l'Expert prêt à afficher, ou null. Les listes absentes deviennent [] ; un « à visiter » inconnu devient « peut-être ». */
export const expertView = (expert) => {
    if (!expert || typeof expert.opinion !== 'string' || !expert.opinion) return null;
    return {
        opinion: expert.opinion,
        worth: WORTH_LABELS[expert.worth_visiting] || WORTH_LABELS['peut-etre'],
        questions: Array.isArray(expert.seller_questions) ? expert.seller_questions : [],
        inspection: Array.isArray(expert.inspection_points) ? expert.inspection_points : [],
        risks: Array.isArray(expert.risks) ? expert.risks : [],
        ceiling: expert.price_ceiling && Number.isFinite(expert.price_ceiling.amount) ? expert.price_ceiling : null,
        model: expert.model || '', at: expert.at || '',
    };
};
/** Texte à copier pour envoyer les questions au vendeur (une par ligne, numérotées). */
export const questionsText = (questions) => (questions || []).map((q, i) => `${i + 1}. ${q}`).join('\n');

/** Lectures faites sur les PHOTOS (`analysis.photos`) : SOH et capacité lus sur une capture, avec le numéro de la photo (à partir de 1) et la
 *  transcription recopiée. Toujours présentés comme « à confirmer » : un fait lu sur photo n'est jamais une preuve. */
export const photoFactLines = (photos) => {
    const labels = { soh_photo: ['SOH lu sur photo', (v) => `${v} %`], ahr_photo: ['Capacité lue sur photo', (v) => `${v} Ah`] };
    return Object.entries(labels).filter(([key]) => photos?.facts?.[key] && Number.isFinite(photos.facts[key].value)).map(([key, [label, fmt]]) => {
        const f = photos.facts[key];
        return { key, label, value: fmt(f.value), photo: Number.isInteger(f.photo) ? f.photo : null, evidence: f.evidence || '' };
    });
};

// --- Prompts de l'IA (éditeur « avancé » des réglages) : `null` = prompt par défaut du bot.
export const PROMPT_LABELS = {
    extract: ['Lecture du texte de l\'annonce (niveau 2)', 'Règles données au modèle pour extraire les faits du texte. Le format JSON et la preuve par citation restent imposés.'],
    photo: ['Lecture des photos (captures LeafSpy)', 'Consigne de recopie des chiffres lisibles sur les images. La forme de la réponse est imposée par un schéma strict.'],
    expert: ['Analyse approfondie (Expert)', 'Consigne de l\'Expert. Le format JSON, la règle des photos et les garde-fous (citations, prix plafond, question LeafSpy) restent imposés.'],
};
export const MAX_PROMPT_CHARS = 8000;
/** Texte du formulaire -> valeur à envoyer : vide ou identique au défaut = null (le défaut du bot s'applique et suit ses mises à jour). */
export const promptToValue = (text, defaultText) => {
    const t = String(text ?? '').trim();
    return !t || t === String(defaultText ?? '').trim() ? null : t;
};
/** Messages d'erreur du formulaire des prompts ([] si valide). */
export const validatePrompts = (texts) => Object.keys(PROMPT_LABELS)
    .filter((key) => String(texts?.[key] ?? '').length > MAX_PROMPT_CHARS)
    .map((key) => `${PROMPT_LABELS[key][0]} : ${MAX_PROMPT_CHARS} caractères au plus.`);
