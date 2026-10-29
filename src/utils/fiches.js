// Fiches techniques de restauration : routes, liens et filtres PURS (aucun React, aucun `import.meta`), testés avec
// `node --test` (src/utils/fiches.test.js). Les fiches sont servies par l'API (`/fiches`, voir apiService.js) ;
// la navigation se fait par le hash de l'URL (`#fiches`, `#fiche/<slug>`), sans routeur.

// Même format que `guitar_knowledge.valid_fiche_slug` côté serveur : une fiche listée est toujours consultable.
export const FICHE_SLUG_RE = /^[a-z0-9][a-z0-9-]{0,79}$/;

export const FICHES_HREF = '#fiches';
export const ficheHref = (slug) => `#fiche/${slug}`;

/** Route demandée par le hash de l'URL : null (pas une page de fiches), {name:'list'} ou {name:'detail', slug}.
 *  Un slug mal formé n'ouvre rien (null) plutôt qu'une page d'erreur. */
export const parseFicheHash = (hash) => {
    const value = String(hash || '').replace(/^#\/?/, '');
    if (value === 'fiches') return { name: 'list' };
    const m = /^fiche\/([^/?#]+)$/.exec(value);
    if (!m) return null;
    let slug;
    try { slug = decodeURIComponent(m[1]); } catch { return null; }
    return FICHE_SLUG_RE.test(slug) ? { name: 'detail', slug } : null;
};

/** Lien d'un corps de fiche : `autre-fiche.md` (renvoi entre fiches) devient `#fiche/autre-fiche` ; le reste est inchangé. */
export const resolveFicheHref = (href) => {
    const m = /^(?:\.\/)?([a-z0-9][a-z0-9-]*)\.md(?:#.*)?$/.exec(String(href || ''));
    return m && FICHE_SLUG_RE.test(m[1]) ? ficheHref(m[1]) : href;
};

/** Source d'une image d'un corps de fiche : un chemin relatif (`img/<slug>/01-nom.jpg`) pointe vers les images copiées
 *  au build dans `<base>fiches/…` ; une URL absolue (http, `/…`) est laissée telle quelle. `base` = `import.meta.env.BASE_URL`. */
export const resolveFicheImage = (src, base = '/') => {
    const value = String(src || '');
    if (/^[/\\]{2}/.test(value)) return '';                              // `//hôte/…` : site tiers, jamais une image de la fiche
    if (/^([a-z][a-z0-9+.-]*:|\/)/i.test(value)) return value;
    const clean = value.replace(/^(\.\/)+/, '');
    if (clean.split('/').includes('..')) return '';                       // jamais de remontée de dossier
    return `${base.endsWith('/') ? base : `${base}/`}fiches/${clean}`;
};

export const STATUT_LABELS = { brouillon: 'Brouillon', en_revision: 'En révision', validee: 'Validée' };
export const CONFIDENCE_LABELS = { sourced: 'Sourcée', single_source: 'Source unique' };
export const CONFIDENCE_HINTS = {
    sourced: 'Au moins deux éditeurs indépendants citent cette information.',
    single_source: "Un seul éditeur est cité : à recouper avant de s'y fier.",
};
export const STATUT_HINTS = {
    brouillon: "Rédigée, pas encore relue par l'atelier : valeurs et procédure à confirmer.",
    en_revision: 'En cours de relecture.',
    validee: "Relue et confirmée par l'atelier.",
};
/** Une fiche mérite un avertissement tant qu'elle n'est pas validée ou qu'elle repose sur une seule source. */
export const needsWarning = (fiche) => fiche?.statut !== 'validee' || fiche?.confidence === 'single_source';

export const difficultyLabel = (d) => (Number.isInteger(d) && d >= 1 && d <= 5 ? `${d}/5` : null);

const fold = (text) => String(text || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** Filtre la liste : catégorie exacte (vide = toutes) et mots de `query` tous présents dans titre, résumé ou slug (sans
 *  tenir compte des accents ni de la casse). */
export const filterFiches = (fiches, { categorie = '', query = '' } = {}) => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    return (fiches || []).filter((f) => {
        if (categorie && f.categorie !== categorie) return false;
        const haystack = fold(`${f.titre} ${f.resume || ''} ${f.slug}`);
        return words.every((w) => haystack.includes(w));
    });
};

/** Regroupe par catégorie en gardant l'ordre `order` (les catégories inconnues passent à la fin). */
export const groupByCategory = (fiches, order = []) => {
    const groups = new Map();
    for (const f of fiches) {
        if (!groups.has(f.categorie)) groups.set(f.categorie, []);
        groups.get(f.categorie).push(f);
    }
    const rank = (c) => (order.indexOf(c) === -1 ? order.length : order.indexOf(c));
    return [...groups.entries()].sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]));
};
