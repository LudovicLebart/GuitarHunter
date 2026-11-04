// Cache IndexedDB du dernier index des annonces (2026-11-04, PERF_API_INDEX_PLAN M3) : à l'ouverture de l'app la liste
// s'affiche tout de suite depuis le disque, pendant que la lecture complète (souvent un 304, voir M2) se fait en arrière-plan.
// Prudence : le cache n'est qu'un affichage provisoire. Il n'alimente jamais la synchronisation incrémentale (la première
// lecture réseau est toujours complète) et il est ignoré s'il est d'un autre utilisateur, trop ancien ou d'une autre
// version de forme des objets (`INDEX_CACHE_VERSION` : à incrémenter quand `dealFromRow` change de forme).
// Toute erreur IndexedDB (navigation privée, quota, API absente) est avalée : l'app fonctionne alors sans cache.
export const INDEX_CACHE_VERSION = 1;
export const INDEX_CACHE_MAX_AGE_MS = 7 * 24 * 3600 * 1000;
const DB_NAME = 'guitarhunter-cache';
const STORE = 'kv';
const KEY = 'dealsIndex';

// Validité d'un enregistrement lu (pure, testable sans IndexedDB).
export function usableIndexCache(record, uid, now = Date.now()) {
  if (!record || record.version !== INDEX_CACHE_VERSION || record.uid !== uid) return null;
  if (typeof record.savedAt !== 'number' || now - record.savedAt > INDEX_CACHE_MAX_AGE_MS) return null;
  if (!record.map || typeof record.map !== 'object') return null;
  return record.map;
}

function openDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') { reject(new Error('IndexedDB indisponible')); return; }
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function run(mode, fn) {
  return openDb().then((db) => new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = fn(tx.objectStore(STORE));
    tx.oncomplete = () => { db.close(); resolve(request?.result); };
    tx.onerror = tx.onabort = () => { db.close(); reject(tx.error); };
  }));
}

export async function loadIndexCache(uid) {
  try {
    return usableIndexCache(await run('readonly', (s) => s.get(KEY)), uid);
  } catch { return null; }
}

export async function saveIndexCache(uid, map) {
  try {
    await run('readwrite', (s) => s.put({ version: INDEX_CACHE_VERSION, uid, savedAt: Date.now(), map }, KEY));
  } catch { /* cache facultatif */ }
}

export async function clearIndexCache() {
  try { await run('readwrite', (s) => s.delete(KEY)); } catch { /* cache facultatif */ }
}
