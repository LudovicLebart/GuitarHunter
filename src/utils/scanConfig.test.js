import test from 'node:test';
import assert from 'node:assert/strict';
import { sanitizeScanNumbers, mergeServerScanConfig } from './scanConfig.js';

test('un champ numérique vidé reprend la valeur du serveur, jamais 0', () => {
  const out = sanitizeScanNumbers({ frequency: '', max_ads: 5, distance: 0 }, { frequency: 60, max_ads: 5 });
  assert.equal(out.frequency, 60);
  assert.equal(out.distance, 0);
});

test('sans valeur connue, le champ vidé est retiré', () => {
  assert.equal('frequency' in sanitizeScanNumbers({ frequency: '' }, null), false);
});

test('une saisie non enregistrée résiste à une mise à jour du serveur', () => {
  const known = { frequency: 60, max_price: 150 };
  const local = { frequency: 30, max_price: 150 }; // frequency en cours de saisie
  const out = mergeServerScanConfig(local, { frequency: 60, max_price: 200 }, known);
  assert.equal(out.frequency, 30);
  assert.equal(out.max_price, 200);
});

test('sans valeur connue, tout vient du serveur', () => {
  assert.deepEqual(mergeServerScanConfig({ a: 1 }, { a: 2 }, null), { a: 2 });
});
