import test from 'node:test';
import assert from 'node:assert/strict';
import { DELTA_MAX_IDS, chooseIndexRefresh, deltaIdFromMessage, mergeIndexDelta } from './indexDelta.js';

test('fusion : met à jour, ajoute et retire les ids absents de la réponse', () => {
  const map = { a: { id: 'a', v: 1 }, b: { id: 'b', v: 1 }, c: { id: 'c', v: 1 } };
  const next = mergeIndexDelta(map, ['a', 'b', 'd'], [{ id: 'a', v: 2 }, { id: 'd', v: 1 }]);
  assert.deepEqual(next, { a: { id: 'a', v: 2 }, c: { id: 'c', v: 1 }, d: { id: 'd', v: 1 } });
  assert.equal(map.b.v, 1); // l'index courant n'est pas muté
});

test('mode de lecture', () => {
  assert.equal(chooseIndexRefresh({ hasIndex: false, fullNeeded: false, pendingCount: 3 }), 'full');
  assert.equal(chooseIndexRefresh({ hasIndex: true, fullNeeded: true, pendingCount: 3 }), 'full');
  assert.equal(chooseIndexRefresh({ hasIndex: true, fullNeeded: false, pendingCount: 0 }), 'full');
  assert.equal(chooseIndexRefresh({ hasIndex: true, fullNeeded: false, pendingCount: DELTA_MAX_IDS + 1 }), 'full');
  assert.equal(chooseIndexRefresh({ hasIndex: true, fullNeeded: false, pendingCount: 3 }), 'delta');
});

test('id exploitable seulement pour une notification simple', () => {
  assert.equal(deltaIdFromMessage({ id: '123' }), '123');
  assert.equal(deltaIdFromMessage({ type: 'bulk' }), null);
  assert.equal(deltaIdFromMessage({ id: 5 }), null);
  assert.equal(deltaIdFromMessage(undefined), null);
});
