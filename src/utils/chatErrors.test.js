import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyChatError, isTransientChatError, isFinalChatError } from './chatErrors.js';

const httpError = (status, extra = {}) => Object.assign(new Error(`échec (${status})`), { customErrorData: { status }, ...extra });

test('le plafond du jour est reconnu par son code, pas par le texte', () => {
  const cap = httpError(429, { code: 'daily_cap' });
  assert.equal(classifyChatError(cap), 'daily_cap');
  assert.equal(isFinalChatError('daily_cap'), true);
  assert.equal(isTransientChatError('daily_cap'), false);
});

test("un autre 429 (flux simultanés, quota) reste transitoire et se relance", () => {
  const kind = classifyChatError(httpError(429));
  assert.equal(kind, 'http_429');
  assert.equal(isTransientChatError(kind), true);
  assert.equal(isFinalChatError(kind), false);
});

test('424 et 402 ne sont ni relancés ni repliés', () => {
  assert.equal(isFinalChatError(classifyChatError(httpError(424))), true);
  assert.equal(isFinalChatError(classifyChatError(httpError(402))), true);
});

test('5xx et coupure réseau sont transitoires, un délai dépassé est final', () => {
  assert.equal(isTransientChatError(classifyChatError(httpError(503))), true);
  assert.equal(isTransientChatError(classifyChatError(new Error('Failed to fetch'))), true);
  assert.equal(isFinalChatError(classifyChatError(Object.assign(new Error('x'), { name: 'AbortError' }))), true);
});
