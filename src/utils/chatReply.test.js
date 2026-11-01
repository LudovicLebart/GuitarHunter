import { test } from 'node:test';
import assert from 'node:assert/strict';
import { joinReplyTexts } from './chatReply.js';

test('la réponse écrite avant l\'appel d\'outil est conservée avec le texte du tour de suite', () => {
    assert.equal(
        joinReplyTexts('Voici la réévaluation : 450 à 650 $.', 'Je t\'ai proposé 3 étapes.'),
        'Voici la réévaluation : 450 à 650 $.\n\nJe t\'ai proposé 3 étapes.',
    );
});

test('un tour de suite identique ou vide n\'ajoute rien', () => {
    assert.equal(joinReplyTexts('Réponse', 'Réponse', '  '), 'Réponse');
    assert.equal(joinReplyTexts('', 'Seulement le suivi'), 'Seulement le suivi');
});

test('sans aucun texte, une ligne générique est affichée', () => {
    assert.equal(joinReplyTexts('', undefined, null), "J'ai préparé une proposition ci-dessous.");
});
