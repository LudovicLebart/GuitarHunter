import { useEffect, useState } from 'react';
import { parseLeafHash } from '../utils/leaf';

/** Route Leaf Hunter demandée par le hash de l'URL (`#leaf`, `#leaf/<id>`), ou null. Réagit à `hashchange`. */
export const useLeafRoute = () => {
    const [route, setRoute] = useState(() => parseLeafHash(window.location.hash));
    useEffect(() => {
        const onChange = () => setRoute(parseLeafHash(window.location.hash));
        window.addEventListener('hashchange', onChange);
        return () => window.removeEventListener('hashchange', onChange);
    }, []);
    return route;
};
