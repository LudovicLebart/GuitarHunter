import test from 'node:test';
import assert from 'node:assert/strict';
import { INDEX_MAX_AUTO_RETRIES, INDEX_RETRY_DELAYS_MS, nextIndexRetryDelayMs, shouldReportIndexError, shouldRetryIndex } from './retryBackoff.js';

test('attente croissante puis plafonnée', () => {
  const d = [1, 2, 3, 4, 5, 6, 50].map((n) => nextIndexRetryDelayMs(n, () => 0.5));
  assert.deepEqual(d, [...INDEX_RETRY_DELAYS_MS, 30000, 30000]);
});

test('l\'aléa reste dans ±20 %', () => {
  assert.equal(nextIndexRetryDelayMs(3, () => 0), 6400);
  assert.equal(nextIndexRetryDelayMs(3, () => 1), 9600);
});

test('un attempt invalide retombe sur la première attente', () => {
  assert.equal(nextIndexRetryDelayMs(0, () => 0.5), 1000);
});

test('premier échec silencieux, page cachée silencieuse', () => {
  assert.equal(shouldReportIndexError(1, false), false);
  assert.equal(shouldReportIndexError(2, false), true);
  assert.equal(shouldReportIndexError(5, true), false);
});

test('on ne relance que les pannes passagères', () => {
  assert.equal(shouldRetryIndex(new Error('expiré'), 1), true);          // pas de status : réseau / délai
  for (const status of [500, 502, 503, 408, 429]) assert.equal(shouldRetryIndex({ status }, 1), true);
  for (const status of [400, 401, 403, 404]) assert.equal(shouldRetryIndex({ status }, 1), false);
});

test('les relances automatiques sont plafonnées', () => {
  assert.equal(shouldRetryIndex(new Error('x'), INDEX_MAX_AUTO_RETRIES), true);
  assert.equal(shouldRetryIndex(new Error('x'), INDEX_MAX_AUTO_RETRIES + 1), false);
});

test("l'erreur est montrée tout de suite quand on ne relancera pas", () => {
  assert.equal(shouldReportIndexError(1, false, false), true);
  assert.equal(shouldReportIndexError(1, true, false), false);
});
