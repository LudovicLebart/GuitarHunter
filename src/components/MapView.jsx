import React, { useState, useEffect, useRef } from 'react';
import CITY_COORDINATES from '../../backend/resources/city_coordinates.json';

// Mapping des couleurs pour Google Maps (Hexadécimal requis)
const VERDICT_COLORS = {
  // V2
  PEPITE: '#facc15',       // Yellow 400
  FAST_FLIP: '#10b981',    // Emerald 500
  LUTHIER_PROJ: '#f97316', // Orange 500
  CASE_WIN: '#0ea5e9',     // Sky 500
  COLLECTION: '#3b82f6',   // Blue 500
  BAD_DEAL: '#f43f5e',     // Rose 500
  REJECTED_ITEM: '#475569', // Slate 600
  REJECTED_SERVICE: '#475569', // Slate 600
  INCOMPLETE_DATA: '#94a3b8', // Slate 400

  // Legacy
  GOOD_DEAL: '#10b981',    // Emerald 500
  FAIR: '#3b82f6',         // Blue 500
  REJECTED: '#475569',     // Slate 600

  // Default
  DEFAULT: '#64748b'       // Slate 500
};

const MapView = ({ deals, onDealSelect, selectedDealId }) => {
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

    const bounds = new window.google.maps.LatLngBounds();
    let hasValidCoords = false;

    // Création d'une InfoWindow partagée globale (pour n'en avoir qu'une seule ouverte à la fois)
    const infoWindow = new window.google.maps.InfoWindow();

    // Listener sur domready pour brancher l'événement de clic sur la popup elle-même
    window.google.maps.event.addListener(infoWindow, 'domready', () => {
      const el = document.getElementById('info-window-card');
      if (el) {
        el.onclick = () => {
          const dealId = el.getAttribute('data-id');
          const d = deals.find(x => x.id === dealId);
          if (d) {
            onDealSelect(d);
            infoWindow.close();
          }
        };
      }
    });

    deals.forEach(deal => {
      let coords;
      // Priorité aux coordonnées GPS précises si elles existent
      if (deal.latitude && deal.longitude) {
        coords = { lat: deal.latitude, lng: deal.longitude };
      } else {
        // Sinon, fallback sur la localisation par nom de ville
        coords = getCoordinates(deal.location);
      }

      if (coords) {
        // Couleur du marqueur selon le verdict
        const verdict = deal.aiAnalysis?.verdict || 'DEFAULT';
        const markerColor = VERDICT_COLORS[verdict] || VERDICT_COLORS.DEFAULT;

        // Création d'une icône SVG personnalisée, agrandie si c'est le marqueur sélectionné
        const isSelected = selectedDealId === deal.id;
        const svgMarker = {
          path: "M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z",
          fillColor: markerColor,
          fillOpacity: 1,
          strokeWeight: isSelected ? 2 : 1,
          strokeColor: "#ffffff",
          rotation: 0,
          scale: isSelected ? 2.0 : 1.5,
          anchor: new window.google.maps.Point(12, 22),
        };

        const marker = new window.google.maps.Marker({
          position: coords,
          map: map,
          title: deal.title,
          icon: svgMarker
        });

        // Contenu HTML de l'InfoWindow enrichi et Dark Mode
        const imageSrc = deal.storageImageUrls?.[0] || deal.imageUrls?.[0];
        const placeholderImg = "https://via.placeholder.com/150?text=No+Image";

        const price = deal.price || 0;
        const estValue = deal.aiAnalysis?.estimated_value || 0;
        const margin = estValue > 0 ? estValue - (deal.aiAnalysis?.net_guitar_cost || price) : 0;
        const marginColor = margin > 0 ? '#10b981' : (margin < 0 ? '#f43f5e' : '#64748b');

        // Remplacement de la condition par le score du Deal ou le statut IA
        const score = deal.aiAnalysis?.deal_score;
        const scoreDisplay = score ? `${score}/10` : (deal.aiAnalysis?.verdict || 'Analyse en attente');

        const contentStr = `
          <div id="info-window-card" data-id="${deal.id}" style="width: 240px; font-family: ui-sans-serif, system-ui, sans-serif; cursor: pointer;">
            <div style="height: 140px; width: 100%; background: #1e293b; position: relative;">
              <img src="${imageSrc || placeholderImg}" style="width: 100%; height: 100%; object-fit: cover;" alt="Deal" />
              <div style="position: absolute; bottom: 8px; right: 8px; background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(4px); color: #10b981; font-weight: 900; font-size: 15px; padding: 4px 10px; border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.2); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);">
                $${price}
              </div>
            </div>
            <div style="padding: 12px 16px;">
              <h3 style="font-size: 14px; font-weight: 700; color: #f8fafc; margin: 0 0 10px 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.4;">
                ${deal.title}
              </h3>
              
              <div style="display: flex; flex-direction: column; gap: 6px; font-size: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="color: #94a3b8;">Score Deal (IA)</span>
                  <span style="color: #60a5fa; font-weight: 600;">${scoreDisplay}</span>
                </div>
                ${estValue > 0 ? `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="color: #94a3b8;">Valeur Est.</span>
                  <span style="color: #e2e8f0; font-weight: 600;">$${estValue}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="color: #94a3b8;">Marge potentielle</span>
                  <span style="color: ${marginColor}; font-weight: 700;">${margin > 0 ? '+' : ''}$${margin}</span>
                </div>
                ` : `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="color: #94a3b8;">Analyse</span>
                  <span style="color: #cbd5e1; font-weight: 600;">Non évaluable</span>
                </div>
                `}
              </div>
            </div>
          </div>
        `;

        marker.addListener("mouseover", () => {
          infoWindow.setContent(contentStr);
          infoWindow.open({
            anchor: marker,
            map,
            shouldFocus: false,
          });
        });

        marker.addListener("click", () => {
          onDealSelect(deal);
        });

        markersRef.current.push(marker);
        bounds.extend(coords);
        hasValidCoords = true;
      }
    });

    if (hasValidCoords) {
      map.fitBounds(bounds);

      // Empêcher un zoom excessif (ex: un seul marqueur)
      const listener = window.google.maps.event.addListener(map, "idle", () => {
        if (map.getZoom() > 12) map.setZoom(12);
        window.google.maps.event.removeListener(listener);
      });
    }
  }, [map, deals, onDealSelect, selectedDealId]);

  return (
    <>
      <style>{`
        /* Overrides for Google Maps InfoWindow to match Slate-900 */
        .gm-style .gm-style-iw-c {
          background-color: #0f172a !important;
          border: 1px solid #334155 !important;
          box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.8) !important;
          padding: 0 !important;
          border-radius: 12px !important;
        }
        .gm-style .gm-style-iw-t::after {
          background: #0f172a !important;
          box-shadow: -2px 2px 3px 0 rgba(0, 0, 0, 0.4) !important;
        }
        .gm-ui-hover-effect { 
          top: 0 !important; 
          right: 0 !important; 
          background: rgba(15, 23, 42, 0.8) !important; 
          border-radius: 0 12px 0 12px !important; 
          padding: 6px !important;
        }
        .gm-ui-hover-effect span {
          width: 20px !important;
          height: 20px !important;
          margin: 0 !important;
          filter: invert(1) !important;
        }
        .gm-style-iw-d { overflow: hidden !important; max-height: none !important; }
      `}</style>
      <div ref={mapRef} className="w-full h-[600px] rounded-3xl shadow-sm border border-slate-800 overflow-hidden" />
    </>
  );
};

export default MapView;
