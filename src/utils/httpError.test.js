import test from 'node:test';
import assert from 'node:assert/strict';
import { buildHttpError, commandRefusedMessage } from './httpError.js';

test('un detail texte est repris tel quel', () => {
  const e = buildHttpError('POST', '/commands', 429, '{"detail":"Trop de commandes en attente : patiente."}');
  assert.equal(e.status, 429);
  assert.equal(e.detail, 'Trop de commandes en attente : patiente.');
  assert.equal(e.code, undefined);
});

test('un detail {code, message} donne le code machine et le texte', () => {
  const e = buildHttpError('POST', '/deals/1/chat', 429, '{"detail":{"code":"daily_cap","message":"Plafond de 2 $ atteint."}}');
  assert.equal(e.code, 'daily_cap');
  assert.match(e.message, /Plafond de 2 \$ atteint\./);
});

test('un corps non JSON ou une liste de validation garde le texte brut', () => {
  assert.match(buildHttpError('GET', '/x', 500, 'Internal Server Error').message, /Internal Server Error/);
  const e = buildHttpError('POST', '/commands', 422, '{"detail":[{"msg":"x"}]}');
  assert.equal(e.detail, undefined);
});

test('le message de commande refusée : pas de double point, détail citant des guillemets échappés', () => {
  const e = buildHttpError('POST', '/commands', 429, '{"detail":"Trop de commandes en attente : patiente le temps qu\'elles soient traitées."}');
  assert.equal(commandRefusedMessage(e), "Commande non envoyée : trop de commandes en attente : patiente le temps qu'elles soient traitées.");
  const q = buildHttpError('POST', '/commands', 422, '{"detail":"Type \\"X\\" inconnu."}');
  assert.equal(commandRefusedMessage(q), 'Commande non envoyée : type "X" inconnu.');
});

test('sans détail, repli par statut', () => {
  assert.match(commandRefusedMessage({ status: 429 }), /trop de commandes/);
  assert.match(commandRefusedMessage({ status: 422 }), /refusée/);
  assert.equal(commandRefusedMessage({ status: 500 }), "Erreur lors de l'envoi de la commande.");
});
