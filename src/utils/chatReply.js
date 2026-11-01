// Réponse affichée d'un tour avec appels d'outils (2026-11-01) : texte écrit AVANT l'appel d'outil + texte(s) des tours de suite,
// sans doublon ni vide ; une seule ligne générique seulement s'il n'y a aucun texte du tout. Avant, seul le texte du dernier tour
// de suite (une ligne sur la proposition) était gardé : la réponse à la question posée en même temps était perdue.
export const joinReplyTexts = (...texts) => {
    const parts = [];
    for (const text of texts) {
        const trimmed = (text || '').trim();
        if (trimmed && !parts.includes(trimmed)) parts.push(trimmed);
    }
    return parts.join('\n\n') || "J'ai préparé une proposition ci-dessous.";
};
