import test from 'node:test';
import assert from 'node:assert/strict';
import { INDEX_CACHE_MAX_AGE_MS, INDEX_CACHE_VERSION, loadIndexCache, saveIndexCache, usableIndexCache } from './indexCache.js';

const rec = (over = {}) => ({ version: INDEX_CACHE_VERSION, uid: 'u1', savedAt: 1000, map: { a: { id: 'a' } }, ...over });

test('enregistrement valide : la carte est rendue', () => {
  assert.deepEqual(usableIndexCache(rec(), 'u1', 2000), { a: { id: 'a' } });
});

test('ignoré : autre utilisateur, autre version, trop ancien, incomplet', () => {
  assert.equal(usableIndexCache(rec(), 'u2', 2000), null);
  assert.equal(usableIndexCache(rec({ version: INDEX_CACHE_VERSION + 1 }), 'u1', 2000), null);
  assert.equal(usableIndexCache(rec(), 'u1', 1000 + INDEX_CACHE_MAX_AGE_MS + 1), null);
  assert.equal(usableIndexCache(rec({ map: null }), 'u1', 2000), null);
  assert.equal(usableIndexCache(rec({ savedAt: 'hier' }), 'u1', 2000), null);
  assert.equal(usableIndexCache(undefined, 'u1', 2000), null);
});

test('sans IndexedDB (Node) : aucune erreur, simplement pas de cache', async () => {
  assert.equal(await loadIndexCache('u1'), null);
  await saveIndexCache('u1', { a: 1 });
});
