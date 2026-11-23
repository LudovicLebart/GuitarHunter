import test from 'node:test';
import assert from 'node:assert/strict';
import {
    CHECKLIST_ITEMS, checklistProgress, filterAndSortDeals, flagLabel, formatKm, formatPrice, leafDealHref, parseLeafHash,
    priceTrend, winterRange, winterVerdict,
} from './leaf.js';

test('parseLeafHash : liste, détail, ou rien', () => {
    assert.deepEqual(parseLeafHash('#leaf'), { view: 'list' });
    assert.deepEqual(parseLeafHash('#leaf/leaf_kijiji_123'), { view: 'detail', id: 'leaf_kijiji_123' });
    assert.equal(parseLeafHash('#fiches'), null);
    assert.equal(parseLeafHash('#leafy'), null);
    assert.equal(parseLeafHash('#leaf/a/b'), null);
    assert.equal(parseLeafHash(''), null);
    assert.equal(parseLeafHash(undefined), null);
});

test('leafDealHref est relu par parseLeafHash', () => {
    assert.deepEqual(parseLeafHash(leafDealHref('leaf_autohebdo_9')), { view: 'detail', id: 'leaf_autohebdo_9' });
});

test('formatPrice / formatKm : valeurs inconnues explicites', () => {
    assert.match(formatPrice(6000), /6\s?000 \$/);
    assert.equal(formatPrice(null), '—');
    assert.match(formatKm(90000), /90\s?000 km/);
    assert.equal(formatKm(undefined), 'km ?');
});

test('flagLabel : connu, accident:<mot>, inconnu affiché tel quel', () => {
    assert.match(flagLabel('soh_unknown'), /LeafSpy/);
    assert.equal(flagLabel('accident:reconstruit'), "Mot d'alerte : reconstruit");
    assert.equal(flagLabel('autre_chose'), 'autre_chose');
});

test('winterRange / winterVerdict', () => {
    assert.equal(winterRange({ winter_fit: { low_km: 75, high_km: 110, verdict: 'ok' } }), '75–110 km');
    assert.equal(winterRange({ winter_fit: { low_km: null, high_km: null } }), null);
    assert.equal(winterRange(null), null);
    assert.equal(winterVerdict({ winter_fit: { verdict: 'juste' } }), 'juste');
    assert.equal(winterVerdict({}), 'inconnu');
});

const DEALS = [
    { id: 'a', title: '2017 Leaf SV', location: 'Québec', trim: 'SV', year: 2017, price: 6000, km: 90000, is_favorite: false, first_seen_at: '2026-11-01' },
    { id: 'b', title: '2016 Leaf S', location: 'Sherbrooke', trim: 'S', year: 2016, price: 5000, km: 120000, is_favorite: true, first_seen_at: '2026-11-03' },
    { id: 'c', title: '2018 Leaf SL', location: 'Montréal', trim: 'SL', year: 2018, price: null, km: null, is_favorite: false, first_seen_at: '2026-11-02' },
];

test('filterAndSortDeals : tri par prix (inconnu en dernier), km, année, récentes', () => {
    assert.deepEqual(filterAndSortDeals(DEALS).map((d) => d.id), ['b', 'a', 'c']);
    assert.deepEqual(filterAndSortDeals(DEALS, { sort: 'km' }).map((d) => d.id), ['a', 'b', 'c']);
    assert.deepEqual(filterAndSortDeals(DEALS, { sort: 'year' }).map((d) => d.id), ['c', 'a', 'b']);
    assert.deepEqual(filterAndSortDeals(DEALS, { sort: 'recent' }).map((d) => d.id), ['b', 'c', 'a']);
    assert.deepEqual(filterAndSortDeals(DEALS, { sort: 'inconnu' }).map((d) => d.id), ['b', 'a', 'c']);
});

test('filterAndSortDeals : favoris, recherche sans accents, liste d\'origine intacte', () => {
    assert.deepEqual(filterAndSortDeals(DEALS, { favoritesOnly: true }).map((d) => d.id), ['b']);
    assert.deepEqual(filterAndSortDeals(DEALS, { query: 'QUEBEC' }).map((d) => d.id), ['a']);
    assert.deepEqual(filterAndSortDeals(DEALS, { query: 'montreal' }).map((d) => d.id), ['c']);
    assert.deepEqual(filterAndSortDeals(DEALS, { query: 'zzz' }), []);
    assert.deepEqual(DEALS.map((d) => d.id), ['a', 'b', 'c']);
    assert.deepEqual(filterAndSortDeals(null), []);
});

test('priceTrend : baisse, hausse, pas assez de points', () => {
    assert.deepEqual(priceTrend([{ price: 6200 }, { price: '6000' }]), { first: 6200, last: 6000, delta: -200 });
    assert.equal(priceTrend([{ price: 6000 }]), null);
    assert.equal(priceTrend(null), null);
});

test('checklistProgress : ne compte que les « true » connus', () => {
    assert.deepEqual(checklistProgress({ leafspy: true, carfax: false, inconnu: true }), { done: 1, total: CHECKLIST_ITEMS.length });
    assert.deepEqual(checklistProgress(null), { done: 0, total: CHECKLIST_ITEMS.length });
});

import { configToForm, leafImageUrl, leafImages, validateLeafForm } from './leaf.js';

test('leafImageUrl : tailles Kijiji et AutoHebdo, autres URL intactes', () => {
    const k = 'https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/ae/ae58?rule=kijijica-200-jpg';
    assert.equal(leafImageUrl(k, 'large'), 'https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/ae/ae58?rule=kijijica-1600-jpg');
    assert.equal(leafImageUrl(k, 'medium'), k.replace('-200-', '-640-'));
    assert.equal(leafImageUrl(k, 'thumb'), k);
    const a = 'https://prod.pictures.autoscout24.net/listing-images/abc_def.jpg/120x90.webp';
    assert.equal(leafImageUrl(a, 'large'), 'https://prod.pictures.autoscout24.net/listing-images/abc_def.jpg/1280x960.webp');
    assert.equal(leafImageUrl(a, 'medium'), a.replace('120x90', '720x540'));
    assert.equal(leafImageUrl('https://exemple.invalide/p.jpg', 'large'), 'https://exemple.invalide/p.jpg');
    assert.equal(leafImageUrl('https://media.kijiji.ca/sans-regle.jpg', 'large'), 'https://media.kijiji.ca/sans-regle.jpg');
    assert.equal(leafImageUrl(null), '');
});

test('leafImages : sans doublon, https seulement, taille appliquée', () => {
    const k = (n) => `https://media.kijiji.ca/api/v1/x/images/${n}?rule=kijijica-200-jpg`;
    assert.deepEqual(leafImages([k('a'), k('a'), k('b'), 'http://non-https.invalide/x.jpg', 3, null], 'large'),
        [k('a').replace('-200-', '-1600-'), k('b').replace('-200-', '-1600-')]);
    assert.deepEqual(leafImages(null), []);
});

const CFG = { enabled: true, scan: { frequency: 180, min_price: 2000, max_price: 6500, max_km: 130000, pages: 2, years: [2017, 2018],
    sources: ['kijiji'], read_details: true, home: { latitude: 45.5333, longitude: -73.35, name: 'Saint-Bruno' }, radius_km: 90 },
    notify: { enabled: true, new: false, price_drop: true } };

test('configToForm puis validateLeafForm : aller-retour sans perte', () => {
    const { errors, body } = validateLeafForm(configToForm(CFG));
    assert.deepEqual(errors, []);
    assert.deepEqual(body, { ...CFG, scan: { ...CFG.scan } });
});

test('validateLeafForm : refuse les valeurs hors bornes avec un message par problème', () => {
    const bad = (patch) => validateLeafForm({ ...configToForm(CFG), ...patch });
    assert.match(bad({ frequency: '5' }).errors[0], /Fréquence/);
    assert.match(bad({ pages: '9' }).errors[0], /Pages/);
    assert.match(bad({ minPrice: '9000' }).errors.join(' '), /prix maximum/);
    assert.match(bad({ years: '1999, abc' }).errors[0], /Années/);
    assert.match(bad({ sources: { kijiji: false, autohebdo: false } }).errors[0], /source/);
    assert.match(bad({ lat: '200' }).errors[0], /latitude/);
    assert.match(bad({ lat: '' }).errors[0], /latitude/);
    assert.match(bad({ radius: '0' }).errors[0], /Rayon/);
    assert.equal(bad({ frequency: '5' }).body, null);
    assert.equal(bad({}).errors.length, 0);
});

test('validateLeafForm : années dédupliquées et triées, nom de ville facultatif', () => {
    const { body } = validateLeafForm({ ...configToForm(CFG), years: '2018 2016, 2018', homeName: '  ' });
    assert.deepEqual(body.scan.years, [2016, 2018]);
    assert.equal('name' in body.scan.home, false);
});

test('configToForm : valeurs par défaut si la configuration est vide', () => {
    const f = configToForm(null);
    assert.equal(f.frequency, '120');
    assert.equal(f.enabled, false);
    assert.deepEqual(f.sources, { kijiji: false, autohebdo: false, facebook: false });
});
