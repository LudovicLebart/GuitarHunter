import test from 'node:test';
import assert from 'node:assert/strict';
import { createFichesLookup } from './fichesLookup.js';

const quiet = { warn: () => {} };

test('renvoie les fiches, avec la question et la limite transmises', async () => {
    const calls = [];
    const lookup = createFichesLookup(async (dealId, opts) => { calls.push([dealId, opts.q, opts.limit]); return [{ slug: 'a' }]; }, quiet);
    assert.deepEqual(await lookup('d1', 'truss rod coincé'), [{ slug: 'a' }]);
    assert.deepEqual(calls, [['d1', 'truss rod coincé', 4]]);
});

test('une réponse qui n’est pas une liste donne une liste vide', async () => {
    const lookup = createFichesLookup(async () => ({ detail: 'x' }), quiet);
    assert.deepEqual(await lookup('d', 'q'), []);
});

test('délai dépassé : liste vide, requête ANNULÉE, même si la requête ignore le signal', async () => {
    let aborted = false;
    const lookup = createFichesLookup((dealId, { signal }) => {
        signal.addEventListener('abort', () => { aborted = true; });
        return new Promise(() => {});                                   // ne répond jamais
    }, { timeoutMs: 20, ...quiet });
    const start = Date.now();
    assert.deepEqual(await lookup('d', 'q'), []);
    assert.ok(Date.now() - start < 500, 'ne reste pas bloqué');
    assert.equal(aborted, true);
});

test('disjoncteur : après un échec, aucune requête pendant la durée de repli, puis on réessaie', async () => {
    let clock = 1000;
    let calls = 0;
    let fail = true;
    const lookup = createFichesLookup(async () => { calls += 1; if (fail) throw new Error('panne'); return [{ slug: 'ok' }]; },
        { backoffMs: 60000, now: () => clock, ...quiet });
    assert.deepEqual(await lookup('d', 'q'), []);                       // échec → disjoncteur
    assert.deepEqual(await lookup('d', 'q'), []);                       // bloqué : aucune requête
    assert.equal(calls, 1);
    clock += 59999;
    assert.deepEqual(await lookup('d', 'q'), []);
    assert.equal(calls, 1);
    clock += 2; fail = false;                                           // repli écoulé
    assert.deepEqual(await lookup('d', 'q'), [{ slug: 'ok' }]);
    assert.equal(calls, 2);
});

test('un succès ne déclenche pas le disjoncteur', async () => {
    let calls = 0;
    const lookup = createFichesLookup(async () => { calls += 1; return []; }, quiet);
    await lookup('d', 'a'); await lookup('d', 'b'); await lookup('d', 'c');
    assert.equal(calls, 3);
});
