import test from 'node:test';
import assert from 'node:assert/strict';
import {
    FICHES_HREF, ficheHref, filterFiches, groupByCategory, needsWarning, parseFicheHash, resolveFicheHref, resolveFicheImage,
} from './fiches.js';

test('parseFicheHash : liste, détail, formes tolérées, rejets', () => {
    assert.deepEqual(parseFicheHash('#fiches'), { name: 'list' });
    assert.deepEqual(parseFicheHash('#/fiches'), { name: 'list' });
    assert.deepEqual(parseFicheHash('#fiche/neck-reset'), { name: 'detail', slug: 'neck-reset' });
    assert.deepEqual(parseFicheHash('#/fiche/reglage-truss-rod'), { name: 'detail', slug: 'reglage-truss-rod' });
    for (const bad of ['', '#', '#accueil', '#fiche/', '#fiche/A', '#fiche/a_b', '#fiche/a/b', '#fiche/%E0%A4%A', '#fiche/' + 'a'.repeat(81), null, undefined]) {
        assert.equal(parseFicheHash(bad), null, String(bad));
    }
    assert.equal(parseFicheHash(FICHES_HREF).name, 'list');
    assert.equal(parseFicheHash(ficheHref('neck-reset')).slug, 'neck-reset');
});

test('resolveFicheHref : renvois entre fiches réécrits, le reste intact', () => {
    assert.equal(resolveFicheHref('reglage-truss-rod.md'), '#fiche/reglage-truss-rod');
    assert.equal(resolveFicheHref('./neck-reset.md#etapes'), '#fiche/neck-reset');
    for (const same of ['https://stewmac.com/a', '#ancre', 'Autre Fiche.md', '../x.md', 'img/a.jpg', 'mailto:a@b.c']) {
        assert.equal(resolveFicheHref(same), same, same);
    }
});

test('resolveFicheImage : chemin relatif vers les images du build, URL absolue intacte, pas de remontée', () => {
    assert.equal(resolveFicheImage('img/reglage-action/01-relief.jpg', '/GuitarHunter/'), '/GuitarHunter/fiches/img/reglage-action/01-relief.jpg');
    assert.equal(resolveFicheImage('./img/a/b.jpg', '/GuitarHunter'), '/GuitarHunter/fiches/img/a/b.jpg');
    assert.equal(resolveFicheImage('https://exemple.com/x.jpg', '/'), 'https://exemple.com/x.jpg');
    assert.equal(resolveFicheImage('/absolu.jpg', '/'), '/absolu.jpg');
    assert.equal(resolveFicheImage('img/../../secret.jpg', '/'), '');
});

const FICHES = [
    { slug: 'reglage-action', titre: "Ajuster l'action", resume: 'Hauteur des cordes au-dessus des frettes', categorie: 'reglage', statut: 'brouillon', confidence: 'sourced' },
    { slug: 'reglage-truss-rod', titre: 'Ajuster le truss rod', resume: 'Courbure du manche', categorie: 'reglage', statut: 'validee', confidence: 'sourced' },
    { slug: 'neck-reset', titre: 'Neck reset', resume: 'Réinclinaison du manche', categorie: 'structurel', statut: 'validee', confidence: 'single_source' },
];

test('filterFiches : catégorie, mots (sans accents ni casse), combinaison', () => {
    assert.equal(filterFiches(FICHES, {}).length, 3);
    assert.deepEqual(filterFiches(FICHES, { categorie: 'structurel' }).map((f) => f.slug), ['neck-reset']);
    assert.deepEqual(filterFiches(FICHES, { query: 'REINCLINAISON' }).map((f) => f.slug), ['neck-reset']);
    assert.deepEqual(filterFiches(FICHES, { query: 'ajuster manche' }).map((f) => f.slug), ['reglage-truss-rod']);
    assert.deepEqual(filterFiches(FICHES, { categorie: 'reglage', query: 'neck' }), []);
    assert.deepEqual(filterFiches(null, { query: 'x' }), []);
});

test('groupByCategory : ordre donné, catégories inconnues à la fin', () => {
    const groups = groupByCategory([...FICHES, { slug: 'x', titre: 'X', categorie: 'autre' }], ['structurel', 'reglage']);
    assert.deepEqual(groups.map(([c]) => c), ['structurel', 'reglage', 'autre']);
    assert.equal(groups[1][1].length, 2);
});

test('needsWarning : brouillon, en révision ou source unique', () => {
    assert.equal(needsWarning(FICHES[0]), true);                      // brouillon
    assert.equal(needsWarning(FICHES[1]), false);                     // validée et sourcée
    assert.equal(needsWarning(FICHES[2]), true);                      // validée mais source unique
    assert.equal(needsWarning({ statut: 'en_revision', confidence: 'sourced' }), true);
});
