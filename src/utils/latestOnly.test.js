import test from 'node:test';
import assert from 'node:assert/strict';
import { latestOnly } from './latestOnly.js';

const deferred = () => {
  let resolve; let reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
};

test('une réponse ancienne arrivée après une plus récente est ignorée', async () => {
  const first = deferred();
  const second = deferred();
  const queue = [first, second];
  const got = [];
  const run = latestOnly(() => queue.shift().promise, (v) => got.push(v), () => got.push('erreur'));
  const a = run();
  const b = run();
  second.resolve('récent');
  await b;
  first.resolve('ancien');
  await a;
  assert.deepEqual(got, ['récent']);
});

test("après close(), ni la réponse ni l'erreur ne sont émises", async () => {
  const d = deferred();
  const got = [];
  const run = latestOnly(() => d.promise, (v) => got.push(v), () => got.push('erreur'));
  const p = run();
  run.close();
  d.reject(new Error('x'));
  await p;
  assert.deepEqual(got, []);
});

test('une erreur de la lecture la plus récente est transmise', async () => {
  const got = [];
  const run = latestOnly(async () => { throw new Error('x'); }, () => got.push('ok'), (e) => got.push(e.message));
  await run();
  assert.deepEqual(got, ['x']);
});
