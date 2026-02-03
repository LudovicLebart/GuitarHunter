import React, { useState, useEffect, useRef } from 'react';
import CITY_COORDINATES from '../../city_coordinates.json';

const MapView = ({ deals, onDealSelect }) => {
  const mapRef = useRef(null);
  const [map, setMap] = useState(null);
  const markersRef = useRef([]);
  const [isApiLoaded, setIsApiLoaded] = useState(false);

  // Fonction pour obtenir les coordonnées d'une ville (avec jitter)
  const getCoordinates = (location) => {
    if (!location) return null;
    
    // Nettoyage du nom de la ville (ex: "Laval, QC" -> "laval")
    const cleanLoc = location.toLowerCase().split(',')[0].trim();
    
    // Recherche dans le dictionnaire
    let coords = CITY_COORDINATES[cleanLoc];
    
    // Si pas trouvé, on essaie de trouver une correspondance partielle
    if (!coords) {
        const key = Object.keys(CITY_COORDINATES).find(k => cleanLoc.includes(k));
        if (key) coords = CITY_COORDINATES[key];
    }

    // Fallback sur Montréal si inconnu
    if (!coords) coords = CITY_COORDINATES['montreal'];

    // Ajout d'un "jitter" (décalage aléatoire) pour éviter la superposition exacte
    // +/- 0.01 degrés correspond à environ +/- 1km
    const jitter = 0.02; 
    return {
      lat: coords.lat + (Math.random() - 0.5) * jitter,
      lng: coords.lng + (Math.random() - 0.5) * jitter
    };
  };

  // Chargement du script Google Maps
  useEffect(() => {
    // Si l'API est déjà chargée
    if (window.google && window.google.maps) {
      setIsApiLoaded(true);
      return;
    }

    // Vérifie si le script est déjà dans le DOM
    const existingScript = document.querySelector('script[src*="maps.googleapis.com"]');
    if (existingScript) {
      // Si le script existe mais window.google n'est pas encore là, on attend
      if (!window.initMap) {
         window.initMap = () => setIsApiLoaded(true);
      }
      return;
    }

    // Handler d'erreur d'authentification Google Maps
    window.gm_authFailure = () => {
      console.error("Google Maps Auth Failure");
      alert("Erreur Google Maps : Accès bloqué.\n\nCauses probables :\n1. Restrictions HTTP (Referrer) sur la clé API (ajoutez http://localhost:*).\n2. API 'Maps JavaScript API' non activée.\n\nVérifiez la console Google Cloud.");
    };

    // Injection du script
    const script = document.createElement('script');
    // Ajout de v=weekly et libraries=marker (pour le futur)
    script.src = `https://maps.googleapis.com/maps/api/js?key=${import.meta.env.VITE_GOOGLE_MAPS_API_KEY}&callback=initMap&v=weekly`;
    script.async = true;
    script.defer = true;
    
    window.initMap = () => {
       setIsApiLoaded(true);
    };
    
    document.head.appendChild(script);

    return () => {
      // Cleanup si nécessaire
      // window.initMap = null; 
    };
  }, []);

  // Initialisation de la carte une fois l'API chargée
  useEffect(() => {
    if (isApiLoaded && !map && mapRef.current && window.google) {
      const newMap = new window.google.maps.Map(mapRef.current, {
        center: { lat: 45.5017, lng: -73.5673 }, // Montréal par défaut
        zoom: 9,
        styles: [
            {
                "featureType": "all",
                "elementType": "geometry",
                "stylers": [{ "color": "#f5f5f5" }]
            },
            {
                "featureType": "water",
                "elementType": "geometry",
                "stylers": [{ "color": "#c9c9c9" }]
            },
            {
                "featureType": "water",
                "elementType": "labels.text.fill",
                "stylers": [{ "color": "#9e9e9e" }]
            }
        ],
        disableDefaultUI: true,
        zoomControl: true,
      });
      setMap(newMap);
    }
  }, [isApiLoaded, map]);

  // Mise à jour des marqueurs
  useEffect(() => {
    if (!map || !deals || !window.google) return;

    // Nettoyage des anciens marqueurs
    markersRef.current.forEach(marker => marker.setMap(null));
    markersRef.current = [];

    deals.forEach(deal => {
      const coords = getCoordinates(deal.location);
      if (coords) {
        // Couleur du marqueur selon le verdict
        let markerColor = '#64748b'; // Slate (Default)
        if (deal.aiAnalysis?.verdict === 'PEPITE') markerColor = '#facc15'; // Yellow
        else if (deal.aiAnalysis?.verdict === 'GOOD_DEAL') markerColor = '#10b981'; // Emerald
        else if (deal.aiAnalysis?.verdict === 'FAIR') markerColor = '#3b82f6'; // Blue
        else if (deal.aiAnalysis?.verdict === 'BAD_DEAL') markerColor = '#f43f5e'; // Rose

        // Création d'une icône SVG personnalisée
        const svgMarker = {
            path: "M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z",
            fillColor: markerColor,
            fillOpacity: 1,
            strokeWeight: 1,
            strokeColor: "#ffffff",
            rotation: 0,
            scale: 1.5,
            anchor: new window.google.maps.Point(12, 22),
        };

        const marker = new window.google.maps.Marker({
          position: coords,
          map: map,
          title: deal.title,
          icon: svgMarker
        });

        marker.addListener("click", () => {
          onDealSelect(deal);
        });

        markersRef.current.push(marker);
      }
    });
  }, [map, deals, onDealSelect]);

  return <div ref={mapRef} className="w-full h-[600px] rounded-3xl shadow-sm border border-slate-200 overflow-hidden" />;
};

export default MapView;
