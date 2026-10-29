import React from 'react';
import { ficheHref, splitFicheLinks } from '../utils/fiches';

// Texte d'une bulle de chat où SEULS les liens de fiches `[Titre](#fiche/<slug>)` vers une fiche CONNUE deviennent cliquables
// (nouvel onglet : le chat et le plan de restauration restent ouverts). `knownSlugs` = fiches du catalogue + fiches données au
// modèle dans la conversation : un lien inventé par le modèle s'affiche comme son simple titre, jamais comme un lien mort.
// Le reste du texte du modèle est rendu tel quel, comme avant.
const FicheLinkText = ({ text, knownSlugs }) => splitFicheLinks(text).map((part, i) => {
    if (typeof part === 'string') return <React.Fragment key={i}>{part}</React.Fragment>;
    if (!knownSlugs?.has(part.slug)) return <React.Fragment key={i}>{part.title}</React.Fragment>;
    return (
        <a key={i} href={ficheHref(part.slug)} target="_blank" rel="noopener noreferrer"
            className="underline decoration-purple-300/50 text-purple-300 hover:text-purple-200 font-semibold">{part.title}</a>
    );
});

export default FicheLinkText;
