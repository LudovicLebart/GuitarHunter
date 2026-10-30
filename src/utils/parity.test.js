import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { RESTORATION_CATEGORIES } from '../constants/restorationPlan.js';
import { FICHE_SLUG_RE, STATUT_LABELS } from './fiches.js';

// Parité Python ↔ JavaScript : ces valeurs sont définies des deux côtés (le chargeur Python valide ce que l'API sert et que
// le site affiche). Rien ne les relie à l'exécution : ce test lit les sources Python et échoue dès qu'elles divergent.
const read = (path) => fs.readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8');
const pythonSet = (source, name) => {
    const m = new RegExp(`^${name} = \\{([^}]*)\\}`, 'm').exec(source);
    assert.ok(m, `${name} introuvable côté Python`);
    return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort();
};

test('catégories : le chargeur Python et le plan de restauration (JS) acceptent les mêmes', () => {
    assert.deepEqual(pythonSet(read('backend/scripts/seed_guitar_fiches.py'), 'CATEGORIES'), [...RESTORATION_CATEGORIES].sort());
});

test('statuts : le chargeur Python et les libellés du site (JS) couvrent les mêmes', () => {
    assert.deepEqual(pythonSet(read('backend/scripts/seed_guitar_fiches.py'), 'STATUTS'), Object.keys(STATUT_LABELS).sort());
});

test('slug : même motif côté serveur (guitar_knowledge.FICHE_SLUG_RE) et côté site', () => {
    const m = /^FICHE_SLUG_RE = re\.compile\(r"([^"]+)"\)/m.exec(read('backend/guitar_knowledge.py'));
    assert.ok(m, 'FICHE_SLUG_RE introuvable côté Python');
    assert.equal(FICHE_SLUG_RE.source, `^${m[1]}$`);
});
