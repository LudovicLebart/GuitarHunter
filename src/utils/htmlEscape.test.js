import test from 'node:test';
import assert from 'node:assert/strict';
import { esc } from './htmlEscape.js';

test('esc neutralise les balises et les guillemets', () => {
  assert.equal(esc('<img src=x onerror="a()">'), '&lt;img src=x onerror=&quot;a()&quot;&gt;');
  assert.equal(esc("l'ami & co"), 'l&#39;ami &amp; co');
});

test('esc accepte null, undefined et les nombres', () => {
  assert.equal(esc(null), '');
  assert.equal(esc(undefined), '');
  assert.equal(esc(12.5), '12.5');
});
