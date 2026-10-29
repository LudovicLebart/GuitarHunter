import React from 'react';
import { ficheHref, splitFicheLinks } from '../utils/fiches';

// Texte d'une bulle de chat où SEULS les liens de fiches `[Titre](#fiche/<slug>)` deviennent cliquables (nouvel onglet : le
// chat et le plan de restauration restent ouverts). Le reste du texte du modèle est rendu tel quel, comme avant.
const FicheLinkText = ({ text }) => splitFicheLinks(text).map((part, i) => (
    typeof part === 'string'
        ? <React.Fragment key={i}>{part}</React.Fragment>
        : <a key={i} href={ficheHref(part.slug)} target="_blank" rel="noopener noreferrer"
            className="underline decoration-purple-300/50 text-purple-300 hover:text-purple-200 font-semibold">{part.title}</a>
));

export default FicheLinkText;
