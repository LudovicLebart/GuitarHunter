import { useEffect, useState } from 'react';
import { auth } from '../services/firebase';
import { fetchFiches } from '../services/apiService';

// Catalogue des fiches techniques (liste sans corps), partagé par tous les composants et le chat : UNE requête, gardée
// 5 minutes en mémoire ET rattachée à l'utilisateur connecté (un autre compte ne reçoit jamais le cache du précédent). Un échec
// n'est jamais mis en cache et ne casse rien : sans catalogue, l'interface fonctionne comme avant (pas de sélecteur de fiche) ;
// le hook réessaie tout seul (5 s, 15 s, 45 s) puis s'arrête — un remontage ou `reload()` repart de zéro.
const TTL_MS = 5 * 60 * 1000;
const RETRY_DELAYS_MS = [5000, 15000, 45000];
let cache = { uid: null, at: 0, promise: null };

export const resetFichesCatalog = () => { cache = { uid: null, at: 0, promise: null }; };

export const getFichesCatalog = () => {
    const uid = auth?.currentUser?.uid ?? null;
    if (cache.promise && cache.uid === uid && Date.now() - cache.at < TTL_MS) return cache.promise;
    const promise = fetchFiches().catch((error) => {
        if (cache.promise === promise) resetFichesCatalog();
        throw error;
    });
    cache = { uid, at: Date.now(), promise };
    return promise;
};

/** `{ fiches, loaded, reload }` : `loaded` est vrai quand le catalogue a bien été reçu (même vide). */
export const useFichesCatalog = () => {
    const [state, setState] = useState({ fiches: [], loaded: false });
    const [attempt, setAttempt] = useState(0);
    const [nonce, setNonce] = useState(0);
    useEffect(() => {
        let cancelled = false;
        let timer;
        getFichesCatalog()
            .then((fiches) => { if (!cancelled) setState({ fiches, loaded: true }); })
            .catch(() => {
                if (cancelled) return;
                setState({ fiches: [], loaded: false });
                if (attempt < RETRY_DELAYS_MS.length) timer = setTimeout(() => { if (!cancelled) setAttempt((n) => n + 1); }, RETRY_DELAYS_MS[attempt]);
            });
        return () => { cancelled = true; clearTimeout(timer); };
    }, [attempt, nonce]);
    return { ...state, reload: () => { resetFichesCatalog(); setAttempt(0); setNonce((n) => n + 1); } };
};
