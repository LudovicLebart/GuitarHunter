import React from 'react';
import { collectHeadings, parseBlocks, parseInline, safeUrl } from '../utils/markdown';

// Rendu React du Markdown minimal de `utils/markdown.js` (fiches techniques, réponses du chat). Aucun HTML brut n'est
// jamais interprété : tout texte est posé comme texte React ; les liens et images passent par `safeUrl` (pas de
// `javascript:`). Habillé pour le thème sombre de l'application.
//
// Props :
// - `text`          : le Markdown ;
// - `resolveHref`   : (href) => href — réécrit un lien (ex. `autre-fiche.md` → `#fiche/autre-fiche`) ;
// - `resolveImage`  : (src) => src  — réécrit la source d'une image (ex. `img/…` → dossier copié au build) ;
// - `isRouteHref`   : (href) => bool — un lien `#…` qui désigne une PAGE de l'application (ex. `#fiche/<slug>`) navigue
//                     normalement ; tout autre lien `#ancre` fait défiler vers le titre correspondant SANS toucher au hash
//                     (le hash sert à la navigation : le modifier ferait quitter la page) ;
// - `skipFirstH1`   : n'affiche pas le premier titre `# …` (la page l'affiche déjà dans son en-tête) ;
// - `className`     : classes du conteneur.

const identity = (value) => value;
const never = () => false;

// Fait défiler vers le titre dont l'`id` est l'ancre du lien, sans changer l'URL.
const scrollToAnchor = (event, href) => {
    event.preventDefault();
    let id = href.slice(1);
    try { id = decodeURIComponent(id); } catch { /* %-encodage invalide : on cherche l'id tel quel */ }
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const renderInline = (nodes, ctx, keyPrefix = '') => nodes.map((node, i) => {
    const key = `${keyPrefix}${i}`;
    switch (node.type) {
        case 'text': return <React.Fragment key={key}>{node.value}</React.Fragment>;
        case 'code': return <code key={key} className="px-1.5 py-0.5 rounded bg-slate-800 text-amber-300 text-[0.85em] font-mono">{node.value}</code>;
        case 'bold': return <strong key={key} className="font-bold text-slate-100">{renderInline(node.children, ctx, `${key}.`)}</strong>;
        case 'em': return <em key={key} className="italic">{renderInline(node.children, ctx, `${key}.`)}</em>;
        case 'link': {
            const href = safeUrl(ctx.resolveHref(node.href));
            const content = renderInline(node.children, { ...ctx, insideLink: true }, `${key}.`);
            if (!href) return <React.Fragment key={key}>{content}</React.Fragment>;
            const external = /^https?:/i.test(href);
            const inPageAnchor = href.startsWith('#') && href.length > 1 && !ctx.isRouteHref(href);
            return (
                <a key={key} href={href} className="text-blue-400 underline decoration-blue-400/40 underline-offset-2 hover:text-blue-300"
                    {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                    {...(inPageAnchor ? { onClick: (e) => scrollToAnchor(e, href) } : {})}>
                    {content}
                </a>
            );
        }
        case 'image': {
            const src = safeUrl(ctx.resolveImage(node.src));
            if (!src) return <span key={key} className="text-slate-500 italic">{node.alt}</span>;
            const img = <img src={src} alt={node.alt} loading="lazy" className="max-w-full max-h-[28rem] rounded-xl border border-slate-700" />;
            // Dans un lien (image cliquable), l'image n'ouvre pas son propre lien : pas d'`<a>` imbriqué.
            if (ctx.insideLink) return <React.Fragment key={key}>{img}</React.Fragment>;
            return <a key={key} href={src} target="_blank" rel="noopener noreferrer" className="block my-2">{img}</a>;
        }
        default: return null;
    }
});

const HEADING_CLASSES = {
    1: 'text-2xl font-black text-white mt-6 mb-2',
    2: 'text-lg font-black text-white mt-8 mb-2 pb-1 border-b border-slate-800',
    3: 'text-base font-bold text-blue-300 mt-5 mb-1',
    4: 'text-sm font-bold text-slate-200 mt-4 mb-1 uppercase tracking-wide',
    5: 'text-sm font-bold text-slate-300 mt-3 mb-1',
    6: 'text-xs font-bold text-slate-400 mt-3 mb-1 uppercase tracking-wide',
};
const ALIGN_CLASSES = { left: 'text-left', center: 'text-center', right: 'text-right' };

const renderBlocks = (blocks, ctx, keyPrefix = '') => blocks.map((block, i) => {
    const key = `${keyPrefix}${i}`;
    switch (block.type) {
        case 'heading': {
            const { id } = ctx.headings[ctx.state.heading++];        // même ordre que `collectHeadings` : ancres uniques
            if (block.level === 1 && ctx.skipFirstH1 && !ctx.state.skipped) { ctx.state.skipped = true; return null; }
            const Tag = `h${block.level}`;
            return <Tag key={key} id={id} className={`${HEADING_CLASSES[block.level]} scroll-mt-20`}>{renderInline(parseInline(block.text), ctx, `${key}.`)}</Tag>;
        }
        case 'paragraph': return <p key={key}>{renderInline(parseInline(block.text), ctx, `${key}.`)}</p>;
        case 'hr': return <hr key={key} className="border-slate-800 my-4" />;
        case 'code': return <pre key={key} className="overflow-x-auto rounded-xl bg-slate-950 border border-slate-800 p-3 text-xs text-slate-200 font-mono"><code>{block.text}</code></pre>;
        case 'quote': return <blockquote key={key} className="border-l-4 border-blue-500/50 bg-slate-800/40 rounded-r-xl pl-4 pr-3 py-2 text-slate-300 space-y-2">{renderBlocks(block.blocks, ctx, `${key}.`)}</blockquote>;
        case 'table': return (
            <div key={key} className="overflow-x-auto rounded-xl border border-slate-700">
                <table className="w-full text-sm border-collapse">
                    <thead className="bg-slate-800 text-slate-200">
                        <tr>{block.header.map((cell, c) => <th key={c} className={`px-3 py-2 font-bold ${ALIGN_CLASSES[block.align[c]] || 'text-left'}`}>{renderInline(parseInline(cell), ctx, `${key}.h${c}.`)}</th>)}</tr>
                    </thead>
                    <tbody>
                        {block.rows.map((row, r) => (
                            <tr key={r} className="border-t border-slate-800">
                                {block.header.map((_, c) => <td key={c} className={`px-3 py-2 align-top ${ALIGN_CLASSES[block.align[c]] || 'text-left'}`}>{renderInline(parseInline(row[c] ?? ''), ctx, `${key}.${r}.${c}.`)}</td>)}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
        case 'list': {
            const Tag = block.ordered ? 'ol' : 'ul';
            const marker = block.ordered ? 'list-decimal' : 'list-disc';
            const start = block.ordered && block.start > 1 ? { start: block.start } : {};
            return (
                <Tag key={key} {...start} className={`${block.items.some((it) => it.checked !== null) ? 'list-none pl-0' : `${marker} pl-6`} space-y-1 marker:text-blue-400`}>
                    {block.items.map((item, n) => (
                        <li key={n} className={item.checked !== null ? 'flex items-start gap-2' : undefined}>
                            {item.checked !== null && <input type="checkbox" checked={item.checked} readOnly disabled className="mt-1 accent-blue-500" />}
                            <span>
                                {renderInline(parseInline(item.text), ctx, `${key}.${n}.`)}
                                {item.children.length > 0 && <div className="mt-1 space-y-1">{renderBlocks(item.children, ctx, `${key}.${n}.c`)}</div>}
                            </span>
                        </li>
                    ))}
                </Tag>
            );
        }
        default: return null;
    }
});

const SimpleMarkdown = ({ text, resolveHref = identity, resolveImage = identity, isRouteHref = never, skipFirstH1 = false, className = '' }) => {
    if (!text) return null;
    const blocks = parseBlocks(text);
    const ctx = { resolveHref, resolveImage, isRouteHref, skipFirstH1, headings: collectHeadings(blocks), state: { skipped: false, heading: 0 } };
    return (
        <div className={`space-y-3 text-slate-300 text-sm leading-relaxed ${className}`}>
            {renderBlocks(blocks, ctx)}
        </div>
    );
};

export default SimpleMarkdown;
