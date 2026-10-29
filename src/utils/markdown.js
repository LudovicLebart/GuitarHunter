// Analyse Markdown MINIMALE et sans dépendance, pour afficher les fiches techniques de restauration (et, plus tard,
// les réponses du chat) : titres, listes (à puces, numérotées, à cocher, imbriquées), tableaux, citations, blocs de code,
// séparateurs, paragraphes ; en ligne : gras, italique, code, liens, images. Fonctions PURES (aucun React, aucun
// `import.meta`) : testées avec `node --test` (src/utils/markdown.test.js), rendues par `components/SimpleMarkdown.jsx`.
//
// Volontairement limité à ce que les fiches utilisent (voir docs/fiches/_GABARIT.md) : pas de HTML brut (jamais
// interprété : tout texte est rendu comme texte), pas de notes de bas de page, pas de listes de définitions.

// URL d'un lien : parenthèses tolérées si elles sont équilibrées sur un niveau (`Les_Paul_(guitare)`).
const URL_PATTERN = '((?:[^()\\s]|\\([^()\\s]*\\))+)';
const IMAGE_RE = new RegExp(`^!\\[([^\\]]*)\\]\\(${URL_PATTERN}(?:\\s+"[^"]*")?\\)`);
const LINK_RE = new RegExp(`^\\[((?:[^\\]\\\\]|\\\\.)+)\\]\\(${URL_PATTERN}(?:\\s+"[^"]*")?\\)`);

/** Lien sûr à poser dans un `href` / `src`, ou null : http(s), mailto, ancre `#…` ou chemin relatif. Tout autre schéma
 *  (`javascript:`, `data:`, `vbscript:`…) est refusé. */
export const safeUrl = (url) => {
    const value = String(url || '').trim();
    if (!value) return null;
    const scheme = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(value.replace(/[\u0000-\u001f\s]/g, ''));
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
const HEADING_RE = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
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
 *  {type:'list',ordered,items:[{checked,text,children}]} (`checked` = null | true | false). */
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
            const items = [];
            while (i < lines.length) {
                const itemMatch = LIST_ITEM_RE.exec(lines[i]);
                if (!itemMatch || itemMatch[1].length !== baseIndent || /\d/.test(itemMatch[2]) !== ordered) break;
                let content = itemMatch[3];
                let checked = null;
                const box = /^\[( |x|X)\]\s+(.*)$/.exec(content);
                if (box) { checked = box[1] !== ' '; content = box[2]; }
                i += 1;
                const nested = [];
                while (i < lines.length) {                           // lignes plus indentées = suite de l'élément / sous-liste
                    const next = lines[i];
                    if (!next.trim()) break;
                    const indent = /^\s*/.exec(next)[0].length;
                    if (indent <= baseIndent) break;
                    nested.push(next.slice(Math.min(indent, baseIndent + 2)));
                    i += 1;
                }
                let children = [];
                const firstList = nested.findIndex((l) => LIST_ITEM_RE.test(l));
                if (firstList === -1) {                              // simple suite de l'élément (retour à la ligne)
                    if (nested.length) content += ` ${nested.map((l) => l.trim()).join(' ')}`;
                } else {                                             // sous-liste (le texte qui la précède prolonge l'élément)
                    if (firstList > 0) content += ` ${nested.slice(0, firstList).map((l) => l.trim()).join(' ')}`;
                    children = parseBlocks(nested.slice(firstList).join('\n'));
                }
                items.push({ checked, text: content, children });
            }
            blocks.push({ type: 'list', ordered, items });
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
