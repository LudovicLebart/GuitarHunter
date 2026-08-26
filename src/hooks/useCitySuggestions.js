import { useEffect, useRef, useState } from 'react';
import { calculateDistanceKm, minDistanceToCities } from '../utils/geo';

// Photon (photon.komoot.io, basé sur OpenStreetMap) plutôt que Nominatim directement depuis le
// navigateur : la politique d'usage de Nominatim interdit explicitement l'autocomplete
// (recherche à chaque frappe) sans self-hosting, et ce projet n'a pas de serveur HTTP pour faire
// proxy (main.py est un worker qui lit des commandes Firestore, pas une API) — voir discussion
// 2026-08-26 (JOURNAL.md) pour le détail du choix.
const PHOTON_URL = 'https://photon.komoot.io/api/';
const DEBOUNCE_MS = 400;
const MIN_QUERY_LENGTH = 2;

/**
 * Suggestions de villes en direct pour l'ajout d'une NOUVELLE ville (pas déjà dans le catalogue
 * partagé) — l'utilisateur choisit visuellement la bonne parmi plusieurs homonymes possibles,
 * plutôt qu'un algorithme qui devine (source du bug "Saint-Lambert" géocodé en France, voir
 * JOURNAL.md 2026-08-25/26). Reclassées par distance à la position GPS réelle de l'utilisateur
 * quand elle est disponible (plus pertinent que les villes déjà configurées, qui peuvent être
 * ailleurs — utilisateur en déplacement), sinon repli sur la distance à la ville la plus proche
 * déjà configurée (jamais un filtre qui exclut — juste un tri, une ville légitimement lointaine
 * reste visible en tapant plus précis, ex: ajouter ", France").
 */
export const useCitySuggestions = (query, existingCities) => {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);
  const requestIdRef = useRef(0);
  // Géolocalisation demandée une seule fois par instance du sélecteur (pas à l'ouverture du
  // panneau de config entier, seulement à la première recherche) — jamais bloquant : un refus, une
  // erreur ou un navigateur sans support retombe silencieusement sur le tri par ville configurée.
  const geoRequestedRef = useRef(false);
  const userPositionRef = useRef(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmed = (query || '').trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      setLoading(false);
      return undefined;
    }

    if (!geoRequestedRef.current) {
      geoRequestedRef.current = true;
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (pos) => { userPositionRef.current = { latitude: pos.coords.latitude, longitude: pos.coords.longitude }; },
          () => { userPositionRef.current = null; },
          { timeout: 5000, maximumAge: 300000 }
        );
      }
    }

    const requestId = ++requestIdRef.current;
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ q: trimmed, limit: '8', lang: 'fr' });
        // Biais géographique demandé à Photon lui-même (paramètres `lat`/`lon` de son API) plutôt
        // que de se contenter de retrier les 8 résultats déjà choisis par SON classement par
        // pertinence globale (population/notoriété) — sans ça, une ville proche mais peu connue
        // peut ne jamais figurer dans les 8 résultats bruts, quel que soit notre tri côté client.
        const pos = userPositionRef.current;
        if (pos) {
          params.set('lat', String(pos.latitude));
          params.set('lon', String(pos.longitude));
        }
        const res = await fetch(`${PHOTON_URL}?${params.toString()}`);
        if (!res.ok) throw new Error(`Photon a répondu ${res.status}`);
        const data = await res.json();
        if (requestId !== requestIdRef.current) return; // réponse obsolète (frappe plus récente)

        const candidates = (data.features || [])
          .filter(f => f.geometry?.coordinates?.length === 2)
          .map(f => {
            const props = f.properties || {};
            const [longitude, latitude] = f.geometry.coordinates;
            return {
              name: props.name,
              state: props.state || null,
              country: props.country || null,
              // Indice de région transmis au backend pour choisir la bonne suggestion Facebook
              // (voir city_finder.py) — état/province d'abord, pays en repli.
              regionHint: props.state || props.country || null,
              latitude,
              longitude,
              displayLabel: [props.name, props.state, props.country].filter(Boolean).join(', '),
            };
          })
          .filter(c => c.name && c.latitude != null && c.longitude != null);

        const distanceTo = (c) => {
          const pos = userPositionRef.current;
          return pos
            ? calculateDistanceKm(pos.latitude, pos.longitude, c.latitude, c.longitude)
            : minDistanceToCities(c.latitude, c.longitude, existingCities);
        };
        candidates.sort((a, b) => distanceTo(a) - distanceTo(b));

        setSuggestions(candidates);
      } catch (e) {
        console.error('Erreur de recherche de ville (Photon):', e);
        if (requestId === requestIdRef.current) setSuggestions([]);
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(debounceRef.current);
  }, [query, existingCities]);

  return { suggestions, loading };
};
