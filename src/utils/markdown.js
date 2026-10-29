// Analyse Markdown MINIMALE et sans dépendance, pour afficher les fiches techniques de restauration (et, plus tard,
// les réponses du chat) : titres, listes (à puces, numérotées, à cocher, imbriquées), tableaux, citations, blocs de code,
// séparateurs, paragraphes ; en ligne : gras, italique, code, liens, images. Fonctions PURES (aucun React, aucun
// `import.meta`) : testées avec `node --test` (src/utils/markdown.test.js), rendues par `components/SimpleMarkdown.jsx`.
//
// Volontairement limité à ce que les fiches utilisent (voir docs/fiches/_GABARIT.md) : pas de HTML brut (jamais
// interprété : tout texte est rendu comme texte), pas de notes de bas de page, pas de listes de définitions.

// URL d'un lien : parenthèses tolérées si elles sont équilibrées sur un niveau (`Les_Paul_(guitare)`).
const URL_BODY = '(?:[^()\\s]|\\([^()\\s]*\\))+';
const URL_PATTERN = `(${URL_BODY})`;
const IMAGE_RE = new RegExp(`^!\\[([^\\]]*)\\]\\(${URL_PATTERN}(?:\\s+"[^"]*")?\\)`);
// Texte d'un lien : tout sauf `]`, ou une image (`[![schéma](img/x.jpg)](https://source)` = image cliquable).
const INLINE_IMAGE = `!\\[[^\\]]*\\]\\(${URL_BODY}\\)`;      // sans groupe capturant : le lien garde ses groupes 1 et 2
const LINK_RE = new RegExp(`^\\[((?:[^\\[\\]\\\\]|\\\\.|${INLINE_IMAGE})+)\\]\\(${URL_PATTERN}(?:\\s+"[^"]*")?\\)`);

/** Lien sûr à poser dans un `href` / `src`, ou null : http(s), mailto, ancre `#…` ou chemin relatif. Tout autre schéma
 *  (`javascript:`, `data:`, `vbscript:`…) est refusé. */
export const safeUrl = (url) => {
    const value = String(url || '').trim();
    if (!value) return null;
    const compact = value.replace(/[\u0000-\u001f\s]/g, '');
    if (/^[/\\]{2}/.test(compact)) return null;      // `//hôte/…` : URL protocole-relative = site tiers, jamais un chemin relatif
    const scheme = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(compact);
    if (!scheme) return value;                       // ancre ou chemin relatif
    return ['http', 'https', 'mailto'].includes(scheme[1].toLowerCase()) ? value : null;
};

const isWordChar = (ch) => !!ch && /[\p{L}\p{N}_]/u.test(ch);

/** Analyse les éléments en ligne d'un texte. Renvoie une liste de nœuds :
 *  {type:'text',value} | {type:'code',value} | {type:'bold'|'em',children} | {type:'link',href,children} |
 *  {type:'image',alt,src}. */
export const parseInline = (text) => {
    const source = String(text ?? '');
    const nodes = [];
    let buffer = '';
    const flush = () => { if (buffer) { nodes.push({ type: 'text', value: buffer }); buffer = ''; } };
    let i = 0;
    while (i < source.length) {
        const rest = source.slice(i);
        const ch = source[i];
        let m;
        if (ch === '\\' && i + 1 < source.length && /[\\`*_{}[\]()#+\-.!|>~]/.test(source[i + 1])) {   // caractère échappé
            buffer += source[i + 1]; i += 2; continue;
        }
        if (ch === '`' && (m = /^`([^`]+)`/.exec(rest))) {
            flush(); nodes.push({ type: 'code', value: m[1] }); i += m[0].length; continue;
        }
        if (ch === '!' && (m = IMAGE_RE.exec(rest))) {
            flush(); nodes.push({ type: 'image', alt: m[1], src: m[2] }); i += m[0].length; continue;
        }
        if (ch === '[' && (m = LINK_RE.exec(rest))) {
            flush(); nodes.push({ type: 'link', href: m[2], children: parseInline(m[1]) }); i += m[0].length; continue;
        }
        if (ch === '*' && rest.startsWith('**') && (m = /^\*\*(?=\S)(.+?)(?<=\S)\*\*/.exec(rest))) {
            flush(); nodes.push({ type: 'bold', children: parseInline(m[1]) }); i += m[0].length; continue;
        }
        if ((ch === '*' || ch === '_') && !rest.startsWith(ch + ch)) {
            const before = source[i - 1];
            const open = ch === '_' ? !isWordChar(before) : true;        // `snake_case` n'est pas de l'italique
            m = open && new RegExp(`^\\${ch}(?=\\S)([^${ch === '*' ? '*' : '_'}]+?)(?<=\\S)\\${ch}`).exec(rest);
            if (m && (ch === '*' || !isWordChar(source[i + m[0].length]))) {
                flush(); nodes.push({ type: 'em', children: parseInline(m[1]) }); i += m[0].length; continue;
            }
        }
        buffer += ch; i += 1;
    }
    flush();
    return nodes;
};

const splitCells = (line) => {
    let body = line.trim();
    if (body.startsWith('|')) body = body.slice(1);
    if (body.endsWith('|') && !body.endsWith('\\|')) body = body.slice(0, -1);
    return body.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'));
};
const TABLE_SEPARATOR_RE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;
const LIST_ITEM_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
// Séquence fermante ATX (`## Titre ##`) seulement si elle est précédée d'une espace : « Accordage en C# » garde son `#`.
const HEADING_RE = /^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
const FENCE_RE = /^\s*```\s*([\w-]*)\s*$/;
const HR_RE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const alignOf = (cell) => (cell.startsWith(':') && cell.endsWith(':') ? 'center' : cell.endsWith(':') ? 'right' : cell.startsWith(':') ? 'left' : null);

const startsBlock = (line, next) => (
    HEADING_RE.test(line) || FENCE_RE.test(line) || HR_RE.test(line) || /^\s*>/.test(line) || LIST_ITEM_RE.test(line)
    || (line.includes('|') && next !== undefined && TABLE_SEPARATOR_RE.test(next) && next.includes('-'))
);

/** Analyse les blocs d'un texte. Renvoie une liste de blocs :
 *  {type:'heading',level,text} | {type:'paragraph',text} | {type:'hr'} | {type:'code',lang,text} |
 *  {type:'quote',blocks} | {type:'table',header,align,rows} |
 *  {type:'list',ordered,start,items:[{checked,text,children}]} (`checked` = null | true | false ; `start` = premier
 *  numéro d'une liste numérotée, null sinon). */
export const parseBlocks = (text) => {
    const lines = String(text ?? '').replace(/\r\n?/g, '\n').split('\n');
    const blocks = [];
    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        if (!line.trim()) { i += 1; continue; }

        let m = FENCE_RE.exec(line);
        if (m) {
            const code = [];
            i += 1;
            while (i < lines.length && !FENCE_RE.test(lines[i])) { code.push(lines[i]); i += 1; }
            i += 1;                                                  // fence fermante (ou fin du texte)
            blocks.push({ type: 'code', lang: m[1] || null, text: code.join('\n') });
            continue;
        }
        if ((m = HEADING_RE.exec(line))) { blocks.push({ type: 'heading', level: m[1].length, text: m[2] }); i += 1; continue; }
        if (HR_RE.test(line)) { blocks.push({ type: 'hr' }); i += 1; continue; }

        if (/^\s*>/.test(line)) {
            const quoted = [];
            while (i < lines.length && /^\s*>/.test(lines[i])) { quoted.push(lines[i].replace(/^\s*>\s?/, '')); i += 1; }
            blocks.push({ type: 'quote', blocks: parseBlocks(quoted.join('\n')) });
            continue;
        }

        if (line.includes('|') && i + 1 < lines.length && lines[i + 1].includes('-') && TABLE_SEPARATOR_RE.test(lines[i + 1])) {
            const header = splitCells(line);
            const align = splitCells(lines[i + 1]).map(alignOf);
            const rows = [];
            i += 2;
            while (i < lines.length && lines[i].trim() && lines[i].includes('|')) { rows.push(splitCells(lines[i])); i += 1; }
            blocks.push({ type: 'table', header, align, rows });
            continue;
        }

        if ((m = LIST_ITEM_RE.exec(line))) {
            const baseIndent = m[1].length;
            const ordered = /\d/.test(m[2]);
            const start = ordered ? parseInt(m[2], 10) : null;
            const isSibling = (l) => {
                const it = LIST_ITEM_RE.exec(l || '');
                return !!it && it[1].length === baseIndent && /\d/.test(it[2]) === ordered;
            };
            const items = [];
            while (i < lines.length && isSibling(lines[i])) {
                let content = LIST_ITEM_RE.exec(lines[i])[3];
                let checked = null;
                const box = /^\[( |x|X)\]\s+(.*)$/.exec(content);
                if (box) { checked = box[1] !== ' '; content = box[2]; }
                i += 1;
                // Corps de l'élément : lignes plus indentées que la puce, lignes vides comprises tant que la suite est encore
                // indentée (bloc de code, image seule, sous-liste, second paragraphe).
                const body = [];
                while (i < lines.length) {
                    if (!lines[i].trim()) {
                        let j = i;
                        while (j < lines.length && !lines[j].trim()) j += 1;
                        if (j < lines.length && /^\s*/.exec(lines[j])[0].length > baseIndent) { while (i < j) { body.push(''); i += 1; } continue; }
                        break;
                    }
                    if (/^\s*/.exec(lines[i])[0].length <= baseIndent) break;
                    body.push(lines[i]); i += 1;
                }
                let children = [];
                if (body.length) {
                    const indent = Math.min(...body.filter((l) => l.trim()).map((l) => /^\s*/.exec(l)[0].length));
                    children = parseBlocks(body.map((l) => l.slice(indent)).join('\n'));
                    // Un premier paragraphe prolonge le texte de l'élément (retour à la ligne) ; le reste reste en blocs.
                    if (body[0] !== '' && children[0]?.type === 'paragraph') content += ` ${children.shift().text}`;   // pas après une ligne vide : c'est un vrai second paragraphe
                }
                items.push({ checked, text: content, children });
                // Éléments d'une même liste séparés par des lignes vides : toujours UNE liste (numérotation continue).
                let j = i;
                while (j < lines.length && !lines[j].trim()) j += 1;
                if (j > i && isSibling(lines[j])) i = j;
            }
            blocks.push({ type: 'list', ordered, start, items });
            continue;
        }

        const paragraph = [line.trim()];
        i += 1;
        while (i < lines.length && lines[i].trim() && !startsBlock(lines[i], lines[i + 1])) { paragraph.push(lines[i].trim()); i += 1; }
        blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
    }
    return blocks;
};

const nodesToText = (nodes) => nodes.map((n) => (
    n.type === 'text' || n.type === 'code' ? n.value : n.type === 'image' ? n.alt : nodesToText(n.children || []))).join('');

/** Texte brut d'un titre (sans marques de gras, code, lien…) — sert à fabriquer l'ancre d'une section. */
export const plainText = (text) => nodesToText(parseInline(text));

/** Ancre d'un titre : minuscules, sans accents, mots séparés par des tirets (« 2. Mesurer le relief » → « 2-mesurer-le-relief »). */
export const slugifyHeading = (text) => plainText(text)
    .normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

/** Tous les titres d'un texte, DANS L'ORDRE du document (y compris ceux imbriqués dans citations et listes), avec une
 *  ancre UNIQUE : un titre répété reçoit `-2`, `-3`… Source commune du rendu (`id` des titres) et du sommaire (liens). */
export const collectHeadings = (blocks) => {
    const found = [];
    const walk = (list) => list.forEach((b) => {
        if (b.type === 'heading') found.push({ level: b.level, text: b.text });
        else if (b.type === 'quote') walk(b.blocks);
        else if (b.type === 'list') b.items.forEach((it) => walk(it.children));
    });
    walk(blocks);
    const seen = new Map();
    return found.map((h) => {
        const base = slugifyHeading(h.text) || 'section';
        const n = (seen.get(base) || 0) + 1;
        seen.set(base, n);
        return { ...h, id: n === 1 ? base : `${base}-${n}` };
    });
};
