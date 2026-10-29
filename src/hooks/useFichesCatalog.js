import { useEffect, useState } from 'react';
import { fetchFiches } from '../services/apiService';

// Catalogue des fiches techniques (liste sans corps), partagé par tous les composants et le chat : UNE requête, gardée
// 5 minutes en mémoire. Un échec n'est jamais mis en cache (la requête suivante réessaie) et ne casse rien : sans
// catalogue, l'interface fonctionne comme avant (pas de sélecteur de fiche, pas de lien enrichi).
const TTL_MS = 5 * 60 * 1000;
let cache = { at: 0, promise: null };

export const getFichesCatalog = () => {
    if (cache.promise && Date.now() - cache.at < TTL_MS) return cache.promise;
    const promise = fetchFiches().catch((error) => {
        if (cache.promise === promise) cache = { at: 0, promise: null };
        throw error;
    });
    cache = { at: Date.now(), promise };
    return promise;
};

/** `{ fiches, loaded }` : `loaded` est vrai quand le catalogue a bien été reçu (même vide). */
export const useFichesCatalog = () => {
    const [state, setState] = useState({ fiches: [], loaded: false });
    useEffect(() => {
        let cancelled = false;
        getFichesCatalog()
            .then((fiches) => { if (!cancelled) setState({ fiches, loaded: true }); })
            .catch(() => { if (!cancelled) setState({ fiches: [], loaded: false }); });
        return () => { cancelled = true; };
    }, []);
    return state;
};
