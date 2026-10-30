import test from 'node:test';
import assert from 'node:assert/strict';
import {
    FICHES_HREF, buildFichesContextText, ficheHref, fichesForCategory, filterFiches, groupByCategory, needsWarning, parseFicheHash,
    pickAllowedFicheSlug, resolveFicheHref, resolveFicheImage, safeUrl, splitFicheLinks, fichesSharedInMessages, splitFicheHistory,
    categoryForFiche,
} from './fiches.js';

test('filterFiches : cherche aussi dans les alias (sans accents ni casse)', () => {
    const fiches = [
        { slug: 'debloquer-truss-rod', titre: 'Débloquer un truss rod coincé', resume: '', categorie: 'reglage', aliases: ['écrou qui ne tourne pas', 'truss rod grippé'] },
        { slug: 'neck-reset', titre: 'Neck reset', resume: '', categorie: 'structurel', aliases: [] },
        { slug: 'sans-alias', titre: 'Autre', categorie: 'autre' },
    ];
    assert.deepEqual(filterFiches(fiches, { query: 'GRIPPE' }).map((f) => f.slug), ['debloquer-truss-rod']);
    assert.deepEqual(filterFiches(fiches, { query: 'ecrou tourne' }).map((f) => f.slug), ['debloquer-truss-rod']);
    assert.deepEqual(filterFiches(fiches, { query: 'neck' }).map((f) => f.slug), ['neck-reset']);
    assert.equal(filterFiches(fiches, { query: 'introuvable' }).length, 0);
});

test('categoryForFiche : la catégorie de la fiche si elle est connue, sinon null', () => {
    const categories = ['structurel', 'reglage', 'autre'];
    assert.equal(categoryForFiche({ categorie: 'reglage' }, categories), 'reglage');
    assert.equal(categoryForFiche({ categorie: 'inconnue' }, categories), null);
    assert.equal(categoryForFiche(null, categories), null);
    assert.equal(categoryForFiche({ categorie: 'reglage' }), null);
});

test('splitFicheHistory : la dernière section « Historique des révisions » est séparée du corps', () => {
    const md = '# T\n\n## Étapes\n\ntexte\n\n## Sources et liens\n\n- a\n\n## Historique des révisions\n\n| Date | Changement |\n|---|---|\n| 2026-10-30 | Création |\n';
    const { main, history } = splitFicheHistory(md);
    assert.ok(main.includes('## Sources et liens') && !main.includes('Historique des révisions'));
    assert.ok(main.endsWith('- a\n'));
    assert.ok(history.startsWith('| Date | Changement |') && history.includes('Création'));
    assert.ok(!history.includes('##'));
});

test('splitFicheHistory : sans historique, historique non final, ou dans un bloc de code : rien n\'est séparé', () => {
    const sans = '# T\n\n## Étapes\n\ntexte\n';
    assert.deepEqual(splitFicheHistory(sans), { main: sans, history: '' });
    const milieu = '# T\n\n## Historique des révisions\n\n| a |\n\n## Annexe\n\ntexte\n';
    assert.deepEqual(splitFicheHistory(milieu), { main: milieu, history: '' });
    const code = '# T\n\n## Étapes\n\n```\n## Historique des révisions\n```\n';
    assert.deepEqual(splitFicheHistory(code), { main: code, history: '' });
    // fences mêlées : ``` imbriqué dans ~~~, ou 4 backticks contenant un bloc ``` : le titre dans le bloc ne compte pas
    const melee = '# T\n\n~~~\n```\n## Historique des révisions\n~~~\n\n## Historique des révisions\n\n| a |\n';
    const coupe = splitFicheHistory(melee);
    assert.ok(coupe.main.includes('~~~\n```\n## Historique') && coupe.history === '| a |');
    const quatre = '# T\n\n````\n```\n## Historique des révisions\n```\n````\n';
    assert.deepEqual(splitFicheHistory(quatre), { main: quatre, history: '' });
    assert.deepEqual(splitFicheHistory(''), { main: '', history: '' });
    assert.deepEqual(splitFicheHistory(null), { main: '', history: '' });
});

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
    assert.equal(resolveFicheImage('//tracker.example/p.png', '/'), '');            // protocole-relatif = site tiers
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

test('fichesForCategory : la catégorie de l’étape d’abord, sans cacher les autres', () => {
    const { same, others } = fichesForCategory(FICHES, 'reglage');
    assert.deepEqual(same.map((f) => f.slug), ['reglage-action', 'reglage-truss-rod']);
    assert.deepEqual(others.map((f) => f.slug), ['neck-reset']);
    assert.deepEqual(fichesForCategory(null, 'x'), { same: [], others: [] });
});

test('splitFicheLinks : seuls les liens de fiches valides deviennent des liens', () => {
    assert.deepEqual(splitFicheLinks('Voir [Ajuster le truss rod](#fiche/reglage-truss-rod) pour la marche à suivre.'),
        ['Voir ', { title: 'Ajuster le truss rod', slug: 'reglage-truss-rod' }, ' pour la marche à suivre.']);
    assert.deepEqual(splitFicheLinks('[A](#fiche/a-1) puis [B](#fiche/b-2)').filter((p) => typeof p !== 'string').map((p) => p.slug), ['a-1', 'b-2']);
    for (const bad of ['[x](#fiche/A_B)', '[x](https://exemple.org)', '[x](#fiches)', '[x](javascript:alert(1))', 'texte **gras** et `code`']) {
        assert.deepEqual(splitFicheLinks(bad), [bad], bad);                 // texte inchangé
    }
    assert.deepEqual(splitFicheLinks(null), []);
    assert.deepEqual(splitFicheLinks(''), []);
});

test('buildFichesContextText : une ligne par fiche, statut et confiance visibles, pas de corps', () => {
    assert.equal(buildFichesContextText([]), null);
    assert.equal(buildFichesContextText(undefined), null);
    const text = buildFichesContextText([{ ...FICHES[0], resume: 'x '.repeat(200) }, FICHES[2]]);
    const lines = text.split('\n');
    assert.ok(lines[1].includes('[slug: reglage-action]') && lines[1].includes('Brouillon') && lines[1].includes('Sourcée'));
    assert.ok(lines[2].includes('Source unique'));
    assert.ok(lines[1].length < 300, 'résumé coupé');
    assert.match(text, /\[Titre\]\(#fiche\/<slug>\)/);
    assert.match(text, /jamais un lien ou un slug inventé/);
});

test('pickAllowedFicheSlug : seulement une fiche réellement fournie au modèle', () => {
    const allowed = new Set(['reglage-action']);
    assert.equal(pickAllowedFicheSlug('reglage-action', allowed), 'reglage-action');
    for (const bad of ['inventee', '', null, undefined, 3, 'REGLAGE-ACTION']) assert.equal(pickAllowedFicheSlug(bad, allowed), null, String(bad));
    assert.equal(pickAllowedFicheSlug('reglage-action', undefined), null);
});

test('fichesSharedInMessages : relit les fiches déjà décrites dans les messages utilisateur seulement', () => {
    const block = buildFichesContextText([FICHES[0], FICHES[1]]);
    const history = [
        { role: 'user', parts: [{ text: `${block}\n\nMa question` }, { inlineData: {} }] },
        { role: 'model', parts: [{ text: 'Réponse citant [slug: neck-reset] en passant' }] },        // le modèle n'est pas une source
        { role: 'user', parts: [{ text: 'Sans fiche' }] },
    ];
    assert.deepEqual([...fichesSharedInMessages(history)].sort(), ['reglage-action', 'reglage-truss-rod']);
    assert.equal(fichesSharedInMessages(null).size, 0);
    assert.equal(fichesSharedInMessages([{ role: 'user' }, null]).size, 0);
    assert.equal(fichesSharedInMessages([{ role: 'user', parts: [{ text: '[slug: A_B] [slug: ok-1]' }] }]).has('ok-1'), true);
    assert.equal(fichesSharedInMessages([{ role: 'user', parts: [{ text: '[slug: A_B]' }] }]).size, 0);
});

test('safeUrl : refuse les schémas dangereux et les URL protocole-relatives, accepte le reste', () => {
    for (const bad of ['javascript:alert(1)', ' JaVaScRiPt:alert(1)', 'java\nscript:alert(1)', 'data:text/html;base64,AAA', 'vbscript:x', '',
        '//tracker.example/p.png', '\\\\hote\\partage', '/ /x']) {
        assert.equal(safeUrl(bad), null, JSON.stringify(bad));
    }
    for (const good of ['https://stewmac.com/a', 'http://x.org', 'mailto:a@b.c', '#fiche/neck-reset', 'img/a/b.jpg', '../x', 'autre.md', '/chemin/absolu.png']) {
        assert.equal(safeUrl(good), good, good);
    }
});
