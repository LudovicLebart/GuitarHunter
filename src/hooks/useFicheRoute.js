import { useEffect, useState } from 'react';
import { parseFicheHash } from '../utils/fiches';

/** Route « fiches » demandée par le hash de l'URL (`#fiches`, `#fiche/<slug>`), ou null. Réagit à `hashchange` : un lien
 *  `<a href="#fiche/…">` suffit pour naviguer, sans routeur. */
export const useFicheRoute = () => {
    const [route, setRoute] = useState(() => parseFicheHash(window.location.hash));
    useEffect(() => {
        const onChange = () => setRoute(parseFicheHash(window.location.hash));
        window.addEventListener('hashchange', onChange);
        return () => window.removeEventListener('hashchange', onChange);
    }, []);
    return route;
};
