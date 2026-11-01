import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DEAL_CONTEXT_HEADER, historyHasDealContext } from './dealContext.js';

test('un historique vide n\'a pas le contexte de l\'annonce', () => {
    assert.equal(historyHasDealContext([]), false);
    assert.equal(historyHasDealContext(undefined), false);
});

test('le contexte est reconnu dans un tour utilisateur de l\'historique rejoué', () => {
    const history = [
        { role: 'user', parts: [{ text: `${DEAL_CONTEXT_HEADER}\nTitre : Guitare\n\nQuestion` }, { text: '[Photo 1/3 …]' }] },
        { role: 'model', parts: [{ text: 'Réponse' }] },
    ];
    assert.equal(historyHasDealContext(history), true);
});

test('une conversation dont le premier tour est parti sans contexte le réclame encore', () => {
    const history = [
        { role: 'user', parts: [{ text: 'Prépare le plan de restauration' }] },
        { role: 'model', parts: [{ text: 'Je n\'ai pas la fiche.' }] },
    ];
    assert.equal(historyHasDealContext(history), false);
});

test('le texte du modèle qui cite le contexte ne compte pas', () => {
    assert.equal(historyHasDealContext([{ role: 'model', parts: [{ text: DEAL_CONTEXT_HEADER }] }]), false);
});
