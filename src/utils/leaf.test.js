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
