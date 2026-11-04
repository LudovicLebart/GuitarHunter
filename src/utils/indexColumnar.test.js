import test from 'node:test';
import assert from 'node:assert/strict';
import { decodeIndexRows } from './indexColumnar.js';

test('reconstruit les objets de l\'ancien format, valeurs nulles et imbriquées comprises', () => {
  const payload = {
    cols: ['id', 'price', 'ai_analysis', 'storage_image_urls', 'sold_at'],
    rows: [['a', 10.5, { verdict: 'GOOD_DEAL', scores: [1, null] }, ['u'], null], ['b', null, null, [], null]],
  };
  assert.deepEqual(decodeIndexRows(payload), [
    { id: 'a', price: 10.5, ai_analysis: { verdict: 'GOOD_DEAL', scores: [1, null] }, storage_image_urls: ['u'], sold_at: null },
    { id: 'b', price: null, ai_analysis: null, storage_image_urls: [], sold_at: null },
  ]);
});

test('liste vide et ancien format (tableau) acceptés', () => {
  assert.deepEqual(decodeIndexRows({ cols: [], rows: [] }), []);
  const legacy = [{ id: 'x' }];
  assert.equal(decodeIndexRows(legacy), legacy);
});

test('format inattendu : erreur claire', () => {
  assert.throws(() => decodeIndexRows({ foo: 1 }), /illisible/);
  assert.throws(() => decodeIndexRows(null), /illisible/);
});
