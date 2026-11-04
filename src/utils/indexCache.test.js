import test from 'node:test';
import assert from 'node:assert/strict';
import { INDEX_CACHE_MAX_AGE_MS, INDEX_CACHE_VERSION, hashShape, loadIndexCache, saveIndexCache, usableIndexCache } from './indexCache.js';

const rec = (over = {}) => ({ version: INDEX_CACHE_VERSION, uid: 'u1', shape: 'S', savedAt: 1000, map: { a: { id: 'a' } }, ...over });

test('enregistrement valide : la carte est rendue', () => {
  assert.deepEqual(usableIndexCache(rec(), 'u1', 'S', 2000), { a: { id: 'a' } });
});

test('ignoré : autre utilisateur, autre version, trop ancien, incomplet', () => {
  assert.equal(usableIndexCache(rec(), 'u2', 'S', 2000), null);
  assert.equal(usableIndexCache(rec(), 'u1', 'AUTRE', 2000), null); // dealFromRow a changé
  assert.equal(usableIndexCache(rec({ version: INDEX_CACHE_VERSION + 1 }), 'u1', 'S', 2000), null);
  assert.equal(usableIndexCache(rec(), 'u1', 'S', 1000 + INDEX_CACHE_MAX_AGE_MS + 1), null);
  assert.equal(usableIndexCache(rec({ map: null }), 'u1', 'S', 2000), null);
  assert.equal(usableIndexCache(rec({ savedAt: 'hier' }), 'u1', 'S', 2000), null);
  assert.equal(usableIndexCache(undefined, 'u1', 'S', 2000), null);
});

test('sans IndexedDB (Node) : aucune erreur, simplement pas de cache', async () => {
  assert.equal(await loadIndexCache('u1', 'S'), null);
  await saveIndexCache('u1', 'S', { a: 1 });
});

test('hashShape : stable pour un même code, différent si le code change', () => {
  assert.equal(hashShape('function f(r){return r.a}'), hashShape('function f(r){return r.a}'));
  assert.notEqual(hashShape('function f(r){return r.a}'), hashShape('function f(r){return r.b}'));
});

// IndexedDB minimal en mémoire : exerce le vrai chemin openDb/run (transaction, oncomplete, création du store).
function installFakeIndexedDb() {
  const data = new Map();
  globalThis.indexedDB = {
    open() {
      const req = {};
      setTimeout(() => {
        req.result = {
          close() {},
          createObjectStore() {},
          transaction() {
            const tx = {};
            const done = () => setTimeout(() => tx.oncomplete && tx.oncomplete(), 0);
            tx.objectStore = () => ({
              get: (k) => { const r = { result: data.get(k) }; done(); return r; },
              put: (v, k) => { data.set(k, structuredClone(v)); done(); return {}; },
              delete: (k) => { data.delete(k); done(); return {}; },
            });
            return tx;
          },
        };
        if (req.onupgradeneeded) req.onupgradeneeded();
        if (req.onsuccess) req.onsuccess();
      }, 0);
      return req;
    },
  };
  return () => { delete globalThis.indexedDB; };
}

test('aller-retour réel : sauvegarde puis lecture, refusés pour un autre utilisateur ou une autre forme', async () => {
  const uninstall = installFakeIndexedDb();
  try {
    await saveIndexCache('u1', 'S', { a: { id: 'a' } });
    assert.deepEqual(await loadIndexCache('u1', 'S'), { a: { id: 'a' } });
    assert.equal(await loadIndexCache('u2', 'S'), null);
    assert.equal(await loadIndexCache('u1', 'T'), null);
  } finally { uninstall(); }
});
