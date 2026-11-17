import test from 'node:test';
import assert from 'node:assert/strict';
import { combineWithProvisional, joinTiers, combinedEtag } from './indexTiers.js';

test('provisoire : le lot live frais prime, le reste vient de ce qu\'on savait déjà', () => {
    const provisional = { a: { v: 'ancien' }, b: { v: 'archive-ancienne' } };
    const live = { a: { v: 'frais' }, c: { v: 'nouveau' } };
    assert.deepEqual(combineWithProvisional(provisional, live), { a: { v: 'frais' }, b: { v: 'archive-ancienne' }, c: { v: 'nouveau' } });
});

test('provisoire : sans cache ni lecture précédente, seulement le lot live', () => {
    assert.deepEqual(combineWithProvisional(null, { a: 1 }), { a: 1 });
});

test('définitif : les deux lots, et une annonce disparue de l\'archive ne survit pas', () => {
    assert.deepEqual(joinTiers({ a: 1 }, { b: 2 }), { a: 1, b: 2 });
    assert.deepEqual(joinTiers({ a: 'live' }, { a: 'archive', b: 2 }), { a: 'live', b: 2 });
});

test('ETag combiné : nul dès qu\'un des deux manque', () => {
    assert.equal(combinedEtag('W/"1"', 'W/"2"'), 'W/"1"|W/"2"');
    assert.equal(combinedEtag('W/"1"', null), null);
    assert.equal(combinedEtag(null, 'W/"2"'), null);
});
