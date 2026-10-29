import test from 'node:test';
import assert from 'node:assert/strict';
import { collectHeadings, parseBlocks, parseInline, plainText, safeUrl, slugifyHeading } from './markdown.js';

const text = (nodes) => nodes.map((n) => n.value ?? '').join('');

test('inline : gras, italique, code', () => {
    const nodes = parseInline('un **gras**, un *italique*, du `code` et snake_case');
    assert.deepEqual(nodes.map((n) => n.type), ['text', 'bold', 'text', 'em', 'text', 'code', 'text']);
    assert.equal(nodes[1].children[0].value, 'gras');
    assert.equal(nodes[5].value, 'code');
    assert.equal(nodes.at(-1).value, ' et snake_case');          // pas d'italique dans un mot
});

test('inline : lien, URL à parenthèses, image', () => {
    const [link] = parseInline('[Les Paul](https://fr.wikipedia.org/wiki/Les_Paul_(guitare))');
    assert.equal(link.type, 'link');
    assert.equal(link.href, 'https://fr.wikipedia.org/wiki/Les_Paul_(guitare)');
    const [img] = parseInline('![relief mesuré](img/reglage-action/01-relief.jpg)');
    assert.deepEqual(img, { type: 'image', alt: 'relief mesuré', src: 'img/reglage-action/01-relief.jpg' });
    const nested = parseInline('[**gras** dans un lien](autre.md)')[0];
    assert.equal(nested.children[0].type, 'bold');
});

test('inline : jamais de HTML interprété, caractères échappés, crochets orphelins', () => {
    assert.deepEqual(parseInline('<script>alert(1)</script>'), [{ type: 'text', value: '<script>alert(1)</script>' }]);
    assert.equal(text(parseInline('2 \\* 3 \\* 4')), '2 * 3 * 4');
    assert.equal(text(parseInline('crochet [seul et (parenthèse)')), 'crochet [seul et (parenthèse)');
    assert.equal(text(parseInline('3 * 4 et 5 * 6')), '3 * 4 et 5 * 6');   // pas d'italique entre espaces
});

test('safeUrl : refuse les schémas dangereux, accepte http(s), mailto, ancres et chemins relatifs', () => {
    for (const bad of ['javascript:alert(1)', ' JaVaScRiPt:alert(1)', 'java\nscript:alert(1)', 'data:text/html;base64,AAA', 'vbscript:x', '']) {
        assert.equal(safeUrl(bad), null, JSON.stringify(bad));
    }
    for (const good of ['https://stewmac.com/a', 'http://x.org', 'mailto:a@b.c', '#fiche/neck-reset', 'img/a/b.jpg', '../x', 'autre.md']) {
        assert.equal(safeUrl(good), good, good);
    }
});

test('blocs : titres, paragraphes joints, séparateur', () => {
    const blocks = parseBlocks('# Titre\n\nune ligne\nsuite de la ligne\n\n---\n\n### Sous-titre ###');
    assert.deepEqual(blocks.map((b) => b.type), ['heading', 'paragraph', 'hr', 'heading']);
    assert.equal(blocks[0].level, 1);
    assert.equal(blocks[1].text, 'une ligne suite de la ligne');
    assert.deepEqual([blocks[3].level, blocks[3].text], [3, 'Sous-titre']);
});

test('blocs : listes à puces, numérotées et à cocher', () => {
    const [ul, ol, todo] = parseBlocks('- un\n- deux\n\n1. premier\n2. second\n\n- [ ] à faire\n- [x] fait');
    assert.equal(ul.ordered, false);
    assert.deepEqual(ul.items.map((i) => i.text), ['un', 'deux']);
    assert.equal(ol.ordered, true);
    assert.deepEqual(todo.items.map((i) => [i.checked, i.text]), [[false, 'à faire'], [true, 'fait']]);
});

test('blocs : liste imbriquée et suite de ligne dans un élément', () => {
    const [list] = parseBlocks('- parent\n  suite du parent\n  - enfant a\n  - enfant b\n- autre');
    assert.equal(list.items.length, 2);
    assert.equal(list.items[0].text, 'parent suite du parent');
    assert.deepEqual(list.items[0].children[0].items.map((i) => i.text), ['enfant a', 'enfant b']);
});

test('blocs : tableau avec alignements et cellules inégales', () => {
    const [table] = parseBlocks('| Instrument | Grave | Aigu |\n|:--|--:|:-:|\n| Électrique | 1,6 à 2,0 mm | 1,2 à 1,6 mm |\n| Acoustique | 2,4 mm | 1,6 mm |');
    assert.equal(table.type, 'table');
    assert.deepEqual(table.header, ['Instrument', 'Grave', 'Aigu']);
    assert.deepEqual(table.align, ['left', 'right', 'center']);
    assert.equal(table.rows.length, 2);
    assert.equal(table.rows[0][1], '1,6 à 2,0 mm');
});

test('blocs : citation, bloc de code fermé ou non', () => {
    const [quote] = parseBlocks('> Résumé sur\n> deux lignes\n>\n> - et une liste');
    assert.equal(quote.type, 'quote');
    assert.deepEqual(quote.blocks.map((b) => b.type), ['paragraph', 'list']);
    const [code] = parseBlocks('```bash\npython seed.py --dry-run\n```');
    assert.deepEqual([code.type, code.lang, code.text], ['code', 'bash', 'python seed.py --dry-run']);
    assert.equal(parseBlocks('```\nnon fermé')[0].text, 'non fermé');
});

test('un paragraphe s’arrête devant un tableau, une liste ou un titre', () => {
    const blocks = parseBlocks('Voici :\n- a\npuis\n## T\n| a | b |\n|---|---|\n| 1 | 2 |');
    assert.deepEqual(blocks.map((b) => b.type), ['paragraph', 'list', 'paragraph', 'heading', 'table']);
});

test('ancres de titres', () => {
    assert.equal(slugifyHeading('2. Mesurer le relief du manche (diagnostic : faut-il ?)'), '2-mesurer-le-relief-du-manche-diagnostic-faut-il');
    assert.equal(slugifyHeading('Pièges et **erreurs** courantes'), 'pieges-et-erreurs-courantes');
    assert.equal(plainText('un [lien](x.md) et `code`'), 'un lien et code');
});

test('une vraie fiche se découpe sans perdre de section', () => {
    const fiche = '# Titre\n\n> Résumé\n\n## Étapes\n\n### 1. Un\n\nTexte avec **gras**.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## Vérifications finales\n\n- [ ] contrôle\n\n## Sources et liens\n\n- [StewMac : x](https://stewmac.com/x) : note\n';
    const types = parseBlocks(fiche).map((b) => b.type);
    assert.deepEqual(types, ['heading', 'quote', 'heading', 'heading', 'paragraph', 'table', 'heading', 'list', 'heading', 'list']);
});

test('image cliquable : [![alt](img)](url) est un lien dont le texte est une image', () => {
    const [link] = parseInline('[![schéma](img/x.jpg)](https://source.example/page)');
    assert.equal(link.type, 'link');
    assert.equal(link.href, 'https://source.example/page');
    assert.deepEqual(link.children, [{ type: 'image', alt: 'schéma', src: 'img/x.jpg' }]);
    const nodes = parseInline('avant [![a](i.png)](https://x.org) après [lien](y.md)');
    assert.deepEqual(nodes.map((n) => n.type), ['text', 'link', 'text', 'link']);
    assert.equal(nodes[3].href, 'y.md');                                  // les groupes du second lien ne sont pas décalés
});

test('safeUrl : une URL protocole-relative (//hôte) est refusée', () => {
    for (const bad of ['//tracker.example/p.png', '\\\\hote\\partage', '/ /x']) assert.equal(safeUrl(bad), null, bad);
    assert.equal(safeUrl('/chemin/absolu.png'), '/chemin/absolu.png');
});

test('titres : « C# » garde son dièse, la séquence fermante précédée d’une espace est retirée', () => {
    const blocks = parseBlocks('## Accordage en C#\n\n## Piège n°1 ##\n\n### Fin #\n\n#hashtag');
    assert.equal(blocks[0].text, 'Accordage en C#');
    assert.equal(blocks[1].text, 'Piège n°1');
    assert.equal(blocks[2].text, 'Fin');
    assert.equal(blocks[3].type, 'paragraph');                            // `#hashtag` (sans espace) n'est pas un titre
    assert.equal(slugifyHeading(blocks[0].text), 'accordage-en-c');
});

test('liste numérotée séparée par des lignes vides : UNE liste, numéro de départ conservé', () => {
    const [list, ...rest] = parseBlocks('1. A\n\n2. B\n\n3. C');
    assert.equal(rest.length, 0);
    assert.deepEqual([list.ordered, list.start, list.items.map((i) => i.text)], [true, 1, ['A', 'B', 'C']]);
    const [from3] = parseBlocks('3. trois\n4. quatre');
    assert.equal(from3.start, 3);
    assert.equal(parseBlocks('- a\n- b')[0].start, null);
    // deux listes réellement distinctes (texte entre les deux) restent deux listes
    assert.equal(parseBlocks('- a\n\npuis un paragraphe\n\n- b').filter((b) => b.type === 'list').length, 2);
    // une liste à puces ne se fond pas dans une liste numérotée voisine
    assert.deepEqual(parseBlocks('1. a\n\n- b').map((b) => b.type), ['list', 'list']);
});

test('élément de liste : bloc de code, image seule et second paragraphe restent des blocs', () => {
    const [list] = parseBlocks('- Étape\n  ```bash\n  python seed.py\n  ```\n- Suite\n  ![schéma](img/x.jpg)\n- Fin\n\n  Second paragraphe de Fin');
    const [etape, suite, fin] = list.items;
    assert.equal(etape.text, 'Étape');
    assert.deepEqual([etape.children[0].type, etape.children[0].text], ['code', 'python seed.py']);
    assert.equal(suite.text, 'Suite ![schéma](img/x.jpg)');                // une image seule prolonge le texte de l'élément
    assert.deepEqual(parseInline(suite.text).map((n) => n.type), ['text', 'image']);
    assert.equal(fin.children[0].text, 'Second paragraphe de Fin');
    assert.equal(list.items.length, 3);
});

test('collectHeadings : ancres uniques dans l’ordre du document, titres imbriqués compris', () => {
    const blocks = parseBlocks('# Notes\n\n## Notes\n\n## Notes\n\n> ## Dans une citation\n\n## Dans une citation');
    assert.deepEqual(collectHeadings(blocks).map((h) => h.id), ['notes', 'notes-2', 'notes-3', 'dans-une-citation', 'dans-une-citation-2']);
    assert.equal(collectHeadings(parseBlocks('## !!!'))[0].id, 'section');
});
