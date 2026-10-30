import React from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSlug from 'rehype-slug';
import { safeUrl } from '../utils/fiches';

// Rendu Markdown (fiches techniques) par `react-markdown` + `remark-gfm` (tableaux, cases à cocher) + `rehype-slug` (ancres des
// titres), habillé pour le thème sombre. Aucun HTML brut n'est jamais interprété (pas de `rehype-raw`) : tout texte est posé comme
// texte React ; les liens et images passent par `safeUrl` (pas de `javascript:`, de `data:` ni de `//hôte`).
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
const cx = (...names) => names.filter(Boolean).join(' ');

// Fait défiler vers le titre dont l'`id` est l'ancre du lien, sans changer l'URL.
const scrollToAnchor = (event, href) => {
    event.preventDefault();
    let id = href.slice(1);
    try { id = decodeURIComponent(id); } catch { /* %-encodage invalide : on cherche l'id tel quel */ }
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const HEADINGS = {
    h1: 'text-2xl font-black text-white mt-6 mb-2',
    h2: 'text-lg font-black text-white mt-8 mb-2 pb-1 border-b border-slate-800',
    h3: 'text-base font-bold text-blue-300 mt-5 mb-1',
    h4: 'text-sm font-bold text-slate-200 mt-4 mb-1 uppercase tracking-wide',
    h5: 'text-sm font-bold text-slate-300 mt-3 mb-1',
    h6: 'text-xs font-bold text-slate-400 mt-3 mb-1 uppercase tracking-wide',
};
const heading = (tag) => ({ node, className, ...props }) => React.createElement(tag, { ...props, className: cx(HEADINGS[tag], 'scroll-mt-20') });

// `node` (arbre syntaxique) n'est jamais posé sur un élément DOM.
const buildComponents = ({ isRouteHref }) => ({
    h1: heading('h1'), h2: heading('h2'), h3: heading('h3'), h4: heading('h4'), h5: heading('h5'), h6: heading('h6'),
    a: ({ node, href, children }) => {
        if (!href) return <>{children}</>;                                // lien refusé par safeUrl : texte seul
        const external = /^https?:/i.test(href);
        const inPage = href.startsWith('#') && href.length > 1 && !isRouteHref(href);
        return (
            <a href={href} className="text-blue-400 underline decoration-blue-400/40 underline-offset-2 hover:text-blue-300"
                {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                {...(inPage ? { onClick: (e) => scrollToAnchor(e, href) } : {})}>
                {children}
            </a>
        );
    },
    img: ({ node, src, alt }) => (src
        ? <img src={src} alt={alt || ''} loading="lazy" className="inline-block max-w-full max-h-[28rem] my-2 rounded-xl border border-slate-700" />
        : <span className="text-slate-500 italic">{alt}</span>),
    strong: ({ node, ...props }) => <strong {...props} className="font-bold text-slate-100" />,
    em: ({ node, ...props }) => <em {...props} className="italic" />,
    hr: () => <hr className="border-slate-800 my-4" />,
    blockquote: ({ node, ...props }) => <blockquote {...props} className="border-l-4 border-blue-500/50 bg-slate-800/40 rounded-r-xl pl-4 pr-3 py-2 text-slate-300 space-y-2" />,
    pre: ({ node, ...props }) => <pre {...props} className="overflow-x-auto rounded-xl bg-slate-950 border border-slate-800 p-3 text-xs text-slate-200 font-mono [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-slate-200" />,
    code: ({ node, ...props }) => <code {...props} className={cx(props.className, 'px-1.5 py-0.5 rounded bg-slate-800 text-amber-300 text-[0.85em] font-mono')} />,
    ul: ({ node, className, ...props }) => <ul {...props} className={cx(className?.includes('contains-task-list') ? 'list-none pl-0' : 'list-disc pl-6', 'space-y-1 marker:text-blue-400')} />,
    ol: ({ node, className, ...props }) => <ol {...props} className={cx(className?.includes('contains-task-list') ? 'list-none pl-0' : 'list-decimal pl-6', 'space-y-1 marker:text-blue-400')} />,
    li: ({ node, className, ...props }) => <li {...props} className={cx(className, className?.includes('task-list-item') && 'flex items-start gap-2')} />,
    input: ({ node, ...props }) => <input {...props} className="mt-1 accent-blue-500" />,
    table: ({ node, ...props }) => (
        <div className="overflow-x-auto rounded-xl border border-slate-700"><table {...props} className="w-full text-sm border-collapse" /></div>
    ),
    thead: ({ node, ...props }) => <thead {...props} className="bg-slate-800 text-slate-200" />,
    tr: ({ node, ...props }) => <tr {...props} className="border-t border-slate-800 first:border-t-0" />,
    th: ({ node, ...props }) => <th {...props} className="px-3 py-2 font-bold text-left" />,
    td: ({ node, ...props }) => <td {...props} className="px-3 py-2 align-top" />,
});

const SimpleMarkdown = ({ text, resolveHref = identity, resolveImage = identity, isRouteHref = never, skipFirstH1 = false, className = '' }) => {
    if (!text) return null;
    const source = skipFirstH1 ? text.replace(/^\s*#[ \t]+[^\n]*\n?/, '') : text;
    const urlTransform = (url, key) => safeUrl(key === 'src' ? resolveImage(url) : resolveHref(url)) || '';
    return (
        <div className={cx('space-y-3 text-slate-300 text-sm leading-relaxed', className)}>
            <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]} urlTransform={urlTransform} components={buildComponents({ isRouteHref })}>
                {source}
            </Markdown>
        </div>
    );
};

export default SimpleMarkdown;
