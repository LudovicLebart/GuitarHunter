import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  Search, ExternalLink, Guitar,
  AlertTriangle, RefreshCw, CheckCircle, XCircle,
  Activity, Settings, Clock,
  MapPin, Sparkles, TrendingUp, Plus, Trash2, ChevronLeft, ChevronRight, Ban, RotateCcw, Map as MapIcon, List, Heart, BrainCircuit, Gem, Maximize2, X
} from 'lucide-react';

// --- Configuration Firebase ---
import { initializeApp } from 'firebase/app';
import {
  getFirestore, collection, onSnapshot, doc, setDoc, deleteField, addDoc, deleteDoc, updateDoc
} from 'firebase/firestore';
import {
  getAuth, signInAnonymously, onAuthStateChanged
} from 'firebase/auth';

// --- Import des prompts centralisés ---
import promptsData from './prompts.json';
import CITY_COORDINATES from './city_coordinates.json';

// --- CONFIGURATION FIREBASE (Extraite de ton code) ---
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

// --- CONSTANTES ---
const PYTHON_APP_ID = "c_5d118e719dbddbfc_index.html-217";
const PYTHON_USER_ID = "00737242777130596039";
const appId = PYTHON_APP_ID;

// --- VALEURS PAR DÉFAUT (MISES À JOUR DEPUIS JSON) ---

const DEFAULT_PROMPT = promptsData.system_prompt;
const DEFAULT_VERDICT_RULES = promptsData.verdict_rules;
const DEFAULT_REASONING_INSTRUCTION = promptsData.reasoning_instruction;
const DEFAULT_USER_PROMPT = promptsData.user_prompt;

// --- COMPOSANTS UTILITAIRES ---

// Nouveau composant pour le rendu Markdown simplifié
const SimpleMarkdown = ({ text }) => {
  if (!text) return null;

  // Découpe le texte par ligne
  const lines = text.split('\n');

  return (
    <div className="space-y-2 text-slate-600 text-sm font-medium leading-relaxed">
      {lines.map((line, index) => {
        const trimmedLine = line.trim();
        
        // Gestion des titres (###)
        if (trimmedLine.startsWith('###')) {
          return (
            <h3 key={index} className="text-blue-800 font-bold text-base mt-3 mb-1 uppercase tracking-wide">
              {trimmedLine.replace(/^###\s*/, '')}
            </h3>
          );
        }
        
        // Gestion des listes à puces (-)
        if (trimmedLine.startsWith('- ')) {
          return (
            <div key={index} className="flex items-start gap-2 ml-2">
              <span className="text-blue-400 mt-1.5">•</span>
              <span>
                {parseBold(trimmedLine.replace(/^- /, ''))}
              </span>
            </div>
          );
        }

        // Paragraphe standard (avec gestion du gras)
        if (trimmedLine.length > 0) {
           return (
             <p key={index}>
               {parseBold(trimmedLine)}
             </p>
           );
        }

        return null; // Ligne vide
      })}
    </div>
  );
};

// Fonction helper pour parser le gras (**texte**)
const parseBold = (text) => {
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="text-slate-800 font-bold">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
};


const VerdictBadge = ({ verdict }) => {
  const configs = {
    'PEPITE': { label: 'Pépite !', color: 'bg-yellow-400', icon: <Gem size={12}/> },
    'GOOD_DEAL': { label: 'Bonne Affaire', color: 'bg-emerald-500', icon: <Sparkles size={12}/> },
    'FAIR': { label: 'Prix Correct', color: 'bg-blue-500', icon: <CheckCircle size={12}/> },
    'BAD_DEAL': { label: 'Trop Cher', color: 'bg-rose-500', icon: <AlertTriangle size={12}/> },
    'REJECTED': { label: 'Rejeté', color: 'bg-slate-600', icon: <Ban size={12}/> },
    'ERROR': { label: 'Erreur Analyse', color: 'bg-rose-600', icon: <XCircle size={12}/> },
    'DEFAULT': { label: 'Analyse...', color: 'bg-slate-400', icon: <RefreshCw size={12} className="animate-spin"/> }
  };
  const config = configs[verdict] || configs.DEFAULT;
  return (
    <span className={`${config.color} text-white px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest shadow-lg flex items-center gap-1.5`}>
      {config.icon} {config.label}
    </span>
  );
};

const DebugStatus = ({ label, status, details }) => (
  <div className="flex items-start gap-2 text-[10px] font-mono mb-2 p-2 bg-slate-50 rounded-lg border border-slate-100">
    <div className="mt-0.5">
      {status === 'loading' && <RefreshCw size={12} className="animate-spin text-blue-500" />}
      {status === 'success' && <CheckCircle size={12} className="text-emerald-500" />}
      {status === 'error' && <XCircle size={12} className="text-rose-500" />}
      {status === 'pending' && <div className="w-3 h-3 rounded-full border-2 border-slate-300" />}
    </div>
    <div className="flex-1">
      <div className={`font-bold uppercase ${status === 'error' ? 'text-rose-600' : 'text-slate-600'}`}>{label}</div>
      {details && <p className="text-slate-400 leading-tight mt-0.5 break-all">{details}</p>}
    </div>
  </div>
);

const ImageGallery = ({ images, title }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFullScreen, setIsFullScreen] = useState(false);

  // Gestion du scroll body quand le plein écran est actif
  useEffect(() => {
    if (isFullScreen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isFullScreen]);

  // Gestion des touches clavier
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isFullScreen) return;
      if (e.key === 'Escape') setIsFullScreen(false);
      if (e.key === 'ArrowRight') nextImage(e);
      if (e.key === 'ArrowLeft') prevImage(e);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullScreen, currentIndex, images]);

  if (!images || images.length === 0) {
    return (
      <div className="w-full h-full bg-slate-100 flex items-center justify-center text-slate-400">
        <Guitar size={48} className="opacity-20" />
      </div>
    );
  }

  const nextImage = (e) => {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    setCurrentIndex((prev) => (prev + 1) % images.length);
  };

  const prevImage = (e) => {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    setCurrentIndex((prev) => (prev - 1 + images.length) % images.length);
  };

  const toggleFullScreen = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsFullScreen(!isFullScreen);
  };

  return (
    <>
      {/* Mode Normal */}
      <div className="relative w-full h-full group cursor-pointer" onClick={toggleFullScreen}>
        <img
          src={images[currentIndex]}
          className="w-full h-full object-contain transition-transform duration-700"
          alt={`${title} - ${currentIndex + 1}`}
        />
        
        {/* Bouton Expand au survol */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 text-white p-1.5 rounded-lg">
            <Maximize2 size={16} />
        </div>

        {images.length > 1 && (
          <>
            <button 
              onClick={prevImage}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <ChevronLeft size={20} />
            </button>
            <button 
              onClick={nextImage}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <ChevronRight size={20} />
            </button>
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
              {images.map((_, idx) => (
                <div 
                  key={idx} 
                  className={`w-1.5 h-1.5 rounded-full ${idx === currentIndex ? 'bg-white' : 'bg-white/50'}`}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Mode Plein Écran */}
      {isFullScreen && createPortal(
        <div className="fixed inset-0 z-[9999] bg-black/95 flex items-center justify-center animate-in fade-in duration-200" onClick={() => setIsFullScreen(false)}>
            <div className="relative w-full h-full flex items-center justify-center p-4" onClick={(e) => e.stopPropagation()}>
                <img
                    src={images[currentIndex]}
                    className="max-w-full max-h-full object-contain shadow-2xl"
                    alt={`${title} - Fullscreen`}
                />

                {images.length > 1 && (
                    <>
                        <button 
                            onClick={prevImage}
                            className="absolute left-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
                        >
                            <ChevronLeft size={48} />
                        </button>
                        <button 
                            onClick={nextImage}
                            className="absolute right-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
                        >
                            <ChevronRight size={48} />
                        </button>
                        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex gap-2">
                            {images.map((_, idx) => (
                                <div 
                                    key={idx} 
                                    className={`w-2 h-2 rounded-full transition-all ${idx === currentIndex ? 'bg-white scale-125' : 'bg-white/30'}`}
                                />
                            ))}
                        </div>
                    </>
                )}
            </div>

            <button 
                onClick={(e) => {
                   e.stopPropagation();
                   setIsFullScreen(false);
                }}
                className="absolute top-4 right-4 z-50 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
            >
                <X size={32} />
            </button>
        </div>,
        document.body
      )}
    </>
  );
};

// --- NOUVEAU COMPOSANT POUR SECTION RÉDUCTIBLE ---
const CollapsibleSection = ({ title, children }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mt-4 border-t border-slate-200 pt-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex justify-between items-center w-full text-left text-sm font-bold text-slate-600 hover:text-blue-600 transition-colors"
      >
        <span>{title}</span>
        <ChevronRight
          size={16}
          className={`transform transition-transform duration-200 ${
            isOpen ? 'rotate-90' : ''
          }`}
        />
      </button>
      {isOpen && <div className="mt-2 animate-in fade-in">{children}</div>}
    </div>
  );
};

// --- NOUVEAU COMPOSANT EXTRAIT ---
const DealCard = React.memo(({ deal, filterType, onRetry, onReject, onToggleFavorite }) => {
  return (
    <div className={`group bg-white rounded-[2rem] shadow-sm border border-slate-200 flex flex-col md:flex-row items-start hover:shadow-2xl hover:shadow-blue-500/5 transition-all duration-500 animate-in fade-in slide-in-from-bottom-4 ${deal.status === 'rejected' ? 'opacity-50' : ''}`}>
      {/* Image Section */}
      <div className="md:w-80 md:sticky md:top-24 self-start shrink-0 relative bg-slate-100 md:rounded-l-[2rem] rounded-t-[2rem] md:rounded-tr-none overflow-hidden">
        {/* On force une hauteur minimale pour que le sticky fonctionne bien visuellement */}
        <div className="h-64 md:h-80 w-full">
            <ImageGallery images={deal.imageUrls || [deal.imageUrl]} title={deal.title} />
        </div>
        <div className="absolute top-4 left-4 z-10 pointer-events-none">
          <VerdictBadge verdict={deal.aiAnalysis?.verdict} />
        </div>
        {/* Overlay gradient */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent pointer-events-none" />
      </div>

      {/* Content Section */}
      <div className="flex-1 p-6 md:p-8 flex flex-col w-full md:rounded-r-[2rem] rounded-b-[2rem] md:rounded-bl-none overflow-hidden">
        <div className="flex justify-between items-start gap-4 mb-4">
          <div>
            <div className="flex items-center gap-2 text-blue-600 font-bold text-[10px] uppercase tracking-widest mb-1">
              <MapPin size={10} /> {deal.location || 'Québec'}
            </div>
            <h2 className="text-2xl font-black text-slate-800 leading-tight group-hover:text-blue-600 transition-colors uppercase tracking-tight">{deal.title}</h2>
          </div>
          <div className="text-right flex flex-col items-end">
            <div className="bg-slate-900 text-white px-4 py-2 rounded-2xl shadow-xl">
              <span className="block text-[8px] font-black uppercase text-slate-400 tracking-tighter">Prix Demandé</span>
              <span className="text-2xl font-black tabular-nums">{deal.price} $</span>
            </div>
            {deal.aiAnalysis?.estimated_value && deal.status !== 'rejected' && (
              <div className="mt-2 text-emerald-600 flex items-center gap-1 font-bold text-xs bg-emerald-50 px-2 py-1 rounded-lg">
                <TrendingUp size={12} /> Val. Est: {deal.aiAnalysis.estimated_value}$
              </div>
            )}
            {deal.aiAnalysis?.estimated_value_after_repair > 0 && deal.status !== 'rejected' && (
              <div className="mt-1 text-purple-600 flex items-center gap-1 font-bold text-xs bg-purple-50 px-2 py-1 rounded-lg">
                <Activity size={12} /> Val. Revente: {deal.aiAnalysis.estimated_value_after_repair}$
              </div>
            )}
          </div>
        </div>

        {/* AI Insights */}
        <div className="relative mb-6">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-100 rounded-full" />
          <div className="pl-5 py-1">
            <div className="flex items-center gap-1.5 text-blue-600 mb-2">
              <Sparkles size={14} />
              <span className="text-[10px] font-black uppercase tracking-widest">Analyse Gemini Flash</span>
            </div>
            
            <div className="mt-2">
              {deal.aiAnalysis?.reasoning ? (
                (() => {
                  const reasoningText = deal.aiAnalysis.reasoning;
                  const summaryMatch = reasoningText.match(/### RÉSUMÉ\n([\s\S]*?)(?=\n###|$)/);
                  const summary = summaryMatch ? summaryMatch[1].trim() : reasoningText;
                  
                  const detailsMatch = reasoningText.match(/(### (?!RÉSUMÉ)[\s\S]*)/);
                  const details = detailsMatch ? detailsMatch[1].trim() : null;

                  return (
                    <>
                      <SimpleMarkdown text={summary} />
                      {details && (
                        <CollapsibleSection title="Voir l'analyse détaillée">
                          <SimpleMarkdown text={details} />
                        </CollapsibleSection>
                      )}
                    </>
                  );
                })()
              ) : (
                <p className="text-slate-400 italic text-sm">Analyse de l'état et de la valeur en cours par l'intelligence artificielle...</p>
              )}
            </div>

          </div>
        </div>

        {/* Meta & Action */}
        <div className="mt-auto pt-6 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2 text-slate-400 text-[10px] font-bold">
              <Clock size={14} />
              <span className="uppercase tracking-widest">
                {deal.timestamp?.seconds ? new Date(deal.timestamp.seconds * 1000).toLocaleString() : 'Juste maintenant'}
              </span>
            </div>
            {deal.aiAnalysis?.confidence && (
              <div className="flex items-center gap-2">
                <div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full" style={{width: `${deal.aiAnalysis.confidence}%`}} />
                </div>
                <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Confiance {deal.aiAnalysis.confidence}%</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Bouton Favori */}
            <button
                onClick={() => onToggleFavorite(deal.id, deal.isFavorite)}
                className={`flex items-center gap-2 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-sm ${deal.isFavorite ? 'bg-rose-100 text-rose-600' : 'bg-slate-100 text-slate-400 hover:text-rose-400'}`}
                title={deal.isFavorite ? "Retirer des favoris" : "Ajouter aux favoris"}
            >
                <Heart size={14} fill={deal.isFavorite ? "currentColor" : "none"} />
            </button>

            {/* CORRECTIF: Bouton Relancer Analyse (toujours visible si non rejeté) */}
            {deal.status !== 'rejected' && (
                <button
                    onClick={() => onRetry(deal.id)}
                    disabled={deal.status === 'retry_analysis'}
                    className={`flex items-center gap-2 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-sm ${deal.status === 'retry_analysis' ? 'bg-amber-100 text-amber-600 cursor-wait' : 'bg-slate-100 text-slate-400 hover:text-amber-500'}`}
                    title="Relancer l'analyse"
                >
                    <RefreshCw size={14} className={deal.status === 'retry_analysis' ? "animate-spin" : ""} />
                </button>
            )}

            {deal.status !== 'rejected' && (
              <button
                onClick={() => onReject(deal.id)}
                className="flex items-center gap-2 bg-slate-100 hover:bg-rose-600 hover:text-white text-slate-600 px-3 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all group/btn shadow-sm"
                title="Rejeter l'annonce"
              >
                <Ban size={14} />
              </button>
            )}
            <a
              href={deal.link}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 bg-slate-100 hover:bg-blue-600 hover:text-white text-slate-600 px-6 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all group/btn shadow-sm"
            >
              Voir sur Facebook <ExternalLink size={14} className="group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5 transition-transform" />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
});

// --- COMPOSANT CARTE ---
const MapView = ({ deals, onDealSelect }) => {
  const mapRef = React.useRef(null);
  const [map, setMap] = React.useState(null);
  const markersRef = React.useRef([]);
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
      // Note: Idéalement on devrait s'attacher à l'event load du script existant, 
      // mais ici on va simplement vérifier périodiquement ou attendre que initMap soit appelé
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

    const infoWindow = new window.google.maps.InfoWindow();

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

        // Contenu de l'infowindow
        const contentString = `
          <div style="font-family: sans-serif; width: 200px;">
            <h3 style="font-weight: bold; margin-bottom: 5px;">${deal.title}</h3>
            <p style="font-size: 14px; font-weight: bold; color: #2563eb;">${deal.price} $</p>
            <p style="font-size: 12px; color: #64748b;">${deal.location || 'Localisation inconnue'}</p>
            <a href="${deal.link}" target="_blank" style="display: block; margin-top: 8px; color: #2563eb; text-decoration: none; font-size: 12px;">Voir l'annonce</a>
          </div>
        `;

        marker.addListener("click", () => {
          // infoWindow.setContent(contentString);
          // infoWindow.open(map, marker);
          onDealSelect(deal);
        });

        markersRef.current.push(marker);
      }
    });
  }, [map, deals, onDealSelect]);

  return <div ref={mapRef} className="w-full h-[600px] rounded-3xl shadow-sm border border-slate-200 overflow-hidden" />;
};


const App = () => {
  const [user, setUser] = useState(null);
  const [deals, setDeals] = useState([]);
  const [cities, setCities] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  // UI States
  const [showConfig, setShowConfig] = useState(false);
  const [viewMode, setViewMode] = useState('LIST'); // 'LIST' ou 'MAP'
  const [selectedDealFromMap, setSelectedDealFromMap] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(0.85); // 85% par défaut
  const [isReanalyzingAll, setIsReanalyzingAll] = useState(false); // New state for UI feedback

  // Filter States
  const [filterType, setFilterType] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Config States
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [verdictRules, setVerdictRules] = useState(DEFAULT_VERDICT_RULES);
  const [reasoningInstruction, setReasoningInstruction] = useState(DEFAULT_REASONING_INSTRUCTION);
  const [userPrompt, setUserPrompt] = useState(DEFAULT_USER_PROMPT);
  const [scanConfig, setScanConfig] = useState({
      maxAds: 5, frequency: 60, location: 'montreal', distance: 60, minPrice: 0, maxPrice: 10000, searchQuery: "electric guitar"
  });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCleaning, setIsCleaning] = useState(false);
  
  // New City Form State
  const [newCityName, setNewCityName] = useState('');
  const [newCityId, setNewCityId] = useState('');

  // New Specific URL Scan State
  const [specificUrl, setSpecificUrl] = useState('');
  const [isScanningUrl, setIsScanningUrl] = useState(false);

  // Diagnostic State
  const [diag, setDiag] = useState({
    auth: { status: 'loading', msg: 'Connexion...' },
    userDoc: { status: 'pending', msg: 'En attente' },
    collection: { status: 'pending', msg: 'En attente' }
  });

  // 1. Auth Init
  useEffect(() => {
    const initAuth = async () => {
      try {
        await signInAnonymously(auth);
        setDiag(prev => ({ ...prev, auth: { status: 'success', msg: 'Authentifié' } }));
      } catch (err) {
        setDiag(prev => ({ ...prev, auth: { status: 'error', msg: err.message } }));
        setError(`Auth Error: ${err.message}`);
      }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  // 2. User Config & Diag Sync (Real-time)
  useEffect(() => {
    if (!user) return;
    const userDocRef = doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID);
    
    const unsubscribe = onSnapshot(userDocRef, (docSnap) => {
      if (docSnap.exists()) {
        setDiag(prev => ({ ...prev, userDoc: { status: 'success', msg: 'Dossier Python trouvé' } }));
        const data = docSnap.data();
        
        // Synchronise le prompt et la config depuis Firestore
        if (data.prompt) setPrompt(data.prompt);
        if (data.verdictRules) setVerdictRules(data.verdictRules);
        if (data.reasoningInstruction) setReasoningInstruction(data.reasoningInstruction);
        if (data.userPrompt) setUserPrompt(data.userPrompt);
        if (data.scanConfig) setScanConfig(prev => ({ ...prev, ...data.scanConfig }));

        // Gère l'erreur de scan envoyée par le bot
        if (data.scanError) {
          setError(data.scanError);
        } else {
          // Si l'erreur a été résolue (champ supprimé), on nettoie le message d'erreur
          if (error && error.startsWith("Ville")) {
             setError(null);
          }
        }

      } else {
        setDiag(prev => ({ ...prev, userDoc: { status: 'error', msg: "Dossier Python introuvable" } }));
      }
    }, (e) => {
      setDiag(prev => ({ ...prev, userDoc: { status: 'error', msg: e.message } }));
    });

    return () => unsubscribe();
  }, [user, error]);

  // 3. Firestore Deals Sync
  useEffect(() => {
    if (!user) return;
    const collectionRef = collection(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'guitar_deals');
    const unsubscribe = onSnapshot(collectionRef, (snapshot) => {
      const dealsData = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      dealsData.sort((a, b) => (b.timestamp?.seconds || 0) - (a.timestamp?.seconds || 0));
      setDeals(dealsData);
      setLoading(false);
      setDiag(prev => ({ ...prev, collection: { status: 'success', msg: `${snapshot.size} annonces` } }));
    }, (err) => {
      setError(err.message);
      setLoading(false);
    });
    return () => unsubscribe();
  }, [user]);

  // 4. Firestore Cities Sync
  useEffect(() => {
    if (!user) return;
    const citiesRef = collection(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'cities');
    const unsubscribe = onSnapshot(citiesRef, (snapshot) => {
      const citiesData = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      setCities(citiesData);
    });
    return () => unsubscribe();
  }, [user]);

  // Actions
  const saveConfig = useCallback(async (newVal) => {
    try {
      const userDocRef = doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID);
      await setDoc(userDocRef, newVal, { merge: true });
    } catch (e) { setError("Erreur de sauvegarde"); }
  }, []);

  const handleManualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    // On efface l'ancienne erreur avant de relancer
    await saveConfig({ forceRefresh: Date.now(), scanError: deleteField() });
    setTimeout(() => setIsRefreshing(false), 5000);
  }, [saveConfig]);

  const handleManualCleanup = useCallback(async () => {
    setIsCleaning(true);
    await saveConfig({ forceCleanup: Date.now() });
    setTimeout(() => setIsCleaning(false), 5000);
  }, [saveConfig]);

  const handleResetDefaults = useCallback(async () => {
    if (window.confirm("Voulez-vous vraiment réinitialiser les paramètres du bot aux valeurs par défaut ?")) {
      setPrompt(DEFAULT_PROMPT);
      setVerdictRules(DEFAULT_VERDICT_RULES);
      setReasoningInstruction(DEFAULT_REASONING_INSTRUCTION);
      setUserPrompt(DEFAULT_USER_PROMPT);
      await saveConfig({
        prompt: DEFAULT_PROMPT,
        verdictRules: DEFAULT_VERDICT_RULES,
        reasoningInstruction: DEFAULT_REASONING_INSTRUCTION,
        userPrompt: DEFAULT_USER_PROMPT
      });
    }
  }, [saveConfig]);

  const handleAddCity = useCallback(async () => {
    if (!newCityName || !newCityId) return;
    try {
      const citiesRef = collection(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'cities');
      await addDoc(citiesRef, {
        name: newCityName,
        id: newCityId,
        createdAt: new Date()
      });
      setNewCityName('');
      setNewCityId('');
    } catch (e) {
      setError("Erreur ajout ville: " + e.message);
    }
  }, [newCityName, newCityId]);

  const handleDeleteCity = useCallback(async (docId) => {
    try {
      await deleteDoc(doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'cities', docId));
    } catch (e) {
      setError("Erreur suppression ville");
    }
  }, []);

  const handleRejectDeal = useCallback(async (dealId) => {
    try {
      const dealDocRef = doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'guitar_deals', dealId);
      await updateDoc(dealDocRef, {
        status: 'rejected',
        'aiAnalysis.verdict': 'REJECTED'
      });
    } catch (e) {
      setError("Erreur lors du rejet de l'annonce.");
    }
  }, []);

  const handleRetryAnalysis = useCallback(async (dealId) => {
    try {
      const dealDocRef = doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'guitar_deals', dealId);
      await updateDoc(dealDocRef, {
        status: 'retry_analysis',
        'aiAnalysis.verdict': 'DEFAULT',
        'aiAnalysis.reasoning': 'Analyse relancée...'
      });
    } catch (e) {
      setError("Erreur lors de la demande de ré-analyse.");
    }
  }, []);

  const handleToggleFavorite = useCallback(async (dealId, currentStatus) => {
    try {
      const dealDocRef = doc(db, 'artifacts', appId, 'users', PYTHON_USER_ID, 'guitar_deals', dealId);
      await updateDoc(dealDocRef, {
        isFavorite: !currentStatus
      });
    } catch (e) {
      setError("Erreur lors de la mise à jour des favoris.");
    }
  }, []);

  const handleRelaunchAll = useCallback(async () => {
    if (window.confirm("⚠️ ATTENTION : Voulez-vous vraiment relancer l'analyse IA pour TOUTES les annonces ?\n\nCela peut prendre plusieurs minutes et consommer beaucoup de quota API.")) {
        setIsReanalyzingAll(true);
        try {
            await saveConfig({ forceReanalyzeAll: Date.now() });
            setTimeout(() => setIsReanalyzingAll(false), 5000); // Reset visual state after 5s
        } catch (e) {
            setError("Erreur lors de la demande de ré-analyse globale.");
            setIsReanalyzingAll(false);
        }
    }
  }, [saveConfig]);

  const handleScanSpecificUrl = useCallback(async () => {
    if (!specificUrl) return;
    setIsScanningUrl(true);
    try {
      await saveConfig({ scanSpecificUrl: specificUrl });
      setSpecificUrl(''); // Clear input after sending
      setTimeout(() => setIsScanningUrl(false), 5000); // Reset button state
    } catch (e) {
      setError("Erreur lors de la demande de scan d'URL.");
      setIsScanningUrl(false);
    }
  }, [specificUrl, saveConfig]);

  // Memoized Filtered List
  const filteredDeals = useMemo(() => {
    return deals.filter(deal => {
      const analysis = deal.aiAnalysis || {};
      const verdict = analysis.verdict || 'PENDING';
      const status = deal.status;
      const reasoning = analysis.reasoning || ""; // Vide si pas de raisonnement

      // Détection stricte des erreurs / analyses incomplètes
      // 1. Pas d'analyse du tout
      // 2. Verdict 'DEFAULT' ou 'PENDING' ou 'ERROR'
      // 3. Raisonnement vide (ce qui provoque l'affichage du texte par défaut)
      // 4. Raisonnement contenant des mots clés d'erreur explicites
      const isError = 
        !deal.aiAnalysis || 
        verdict === 'DEFAULT' || 
        verdict === 'ERROR' ||
        !reasoning || // Raisonnement vide = Erreur/En attente
        reasoning.includes("Erreur") ||
        reasoning.includes("Analyse IA impossible");

      if (filterType === 'ERROR') {
        // Dans l'onglet erreur, on veut voir tout ce qui a échoué, sauf si c'est déjà rejeté (poubelle)
        return isError && status !== 'rejected';
      }

      if (filterType === 'REJECTED') {
        return status === 'rejected';
      }

      if (filterType === 'FAVORITES') {
        return deal.isFavorite;
      }
      
      // Pour les autres filtres (ALL, GOOD_DEAL, etc.)
      // On exclut les annonces rejetées
      if (status === 'rejected') {
        return false;
      }

      // Si on filtre par type (ex: GOOD_DEAL), on doit s'assurer que ce n'est PAS une erreur déguisée
      // Si l'utilisateur veut voir les GOOD_DEAL, il ne veut pas voir celles qui ont un verdict GOOD_DEAL mais pas de raisonnement.
      if (filterType !== 'ALL' && isError) {
          return false; 
      }

      const matchesType = filterType === 'ALL' || verdict === filterType;
      const matchesSearch = deal.title?.toLowerCase().includes(searchQuery.toLowerCase());

      return matchesType && matchesSearch;
    });
  }, [deals, filterType, searchQuery]);

  return (
    <div className="min-h-screen bg-[#F8FAFC] font-sans text-slate-900 selection:bg-blue-100">

      {/* NAVBAR */}
      <nav className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-2 rounded-xl text-white shadow-lg shadow-blue-200">
              <Guitar size={24} />
            </div>
            <div>
              <h1 className="text-lg font-black tracking-tight text-slate-800">GUITAR HUNTER <span className="text-blue-600">AI</span></h1>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest leading-none">Scraper & Gemini Evaluator</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
                onClick={handleManualCleanup}
                disabled={isCleaning}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${isCleaning ? 'bg-slate-100 text-slate-400' : 'bg-amber-50 text-amber-600 hover:bg-amber-100 shadow-sm border border-amber-100'}`}
            >
              <Trash2 size={14} className={isCleaning ? "animate-bounce" : ""} />
              <span className="hidden sm:inline">{isCleaning ? 'Vérification...' : 'Vérifier Stocks'}</span>
            </button>
            <button
                onClick={handleManualRefresh}
                disabled={isRefreshing}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${isRefreshing ? 'bg-slate-100 text-slate-400' : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100 shadow-sm border border-emerald-100'}`}
            >
              <RefreshCw size={14} className={isRefreshing ? "animate-spin" : ""} />
              <span className="hidden sm:inline">{isRefreshing ? 'Scan en cours...' : 'Scanner maintenant'}</span>
            </button>
            <button
              onClick={() => setShowConfig(!showConfig)}
              className="p-2 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors"
            >
              <Settings size={20} />
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 py-8 grid grid-cols-1 lg:grid-cols-4 gap-8">

        {/* SIDEBAR - CONTROLS & STATUS */}
        <aside className="lg:col-span-1 space-y-6">

          {/* Status Card */}
          <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-200">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Système</h3>
              <div className="flex items-center gap-1.5 bg-emerald-50 text-emerald-600 px-2 py-1 rounded-lg text-[9px] font-bold">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> LIVE
              </div>
            </div>
            <div className="space-y-1">
              <DebugStatus label="Auth" status={diag.auth.status} details={diag.auth.msg} />
              <DebugStatus label="Engine" status={diag.userDoc.status} details="Python Bot Connected" />
              <DebugStatus label="Database" status={diag.collection.status} details={diag.collection.msg} />
            </div>
          </div>

          {/* Config Card (Si ouvert) */}
          {showConfig && (
            <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-200 space-y-4 animate-in fade-in slide-in-from-top-4 duration-300">
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Paramètres</h3>

              {/* SECTION 1: FACEBOOK SEARCH */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-blue-600 mb-2">
                  <Search size={14} />
                  <span className="text-[10px] font-black uppercase tracking-widest">Recherche Facebook</span>
                </div>
                
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Lieu</label>
                    <select
                      value={scanConfig.location}
                      onChange={(e) => setScanConfig({...scanConfig, location: e.target.value})}
                      onBlur={() => saveConfig({ scanConfig })}
                      className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="" disabled>Choisir une ville</option>
                      {cities.map(city => (
                        <option key={city.id} value={city.name}>{city.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Dist (km)</label>
                    <input type="number" value={scanConfig.distance} onChange={(e) => setScanConfig({...scanConfig, distance: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Min Price</label>
                    <input type="number" value={scanConfig.minPrice} onChange={(e) => setScanConfig({...scanConfig, minPrice: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Max Price</label>
                    <input type="number" value={scanConfig.maxPrice} onChange={(e) => setScanConfig({...scanConfig, maxPrice: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Max Ads</label>
                    <input type="number" value={scanConfig.maxAds} onChange={(e) => setScanConfig({...scanConfig, maxAds: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                  <div>
                    <label className="text-[9px] font-bold text-slate-400 uppercase">Fréquence (min)</label>
                    <input type="number" value={scanConfig.frequency} onChange={(e) => setScanConfig({...scanConfig, frequency: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                  </div>
                </div>
                
                <div>
                  <label className="text-[9px] font-bold text-slate-400 uppercase">Search Query</label>
                  <input type="text" value={scanConfig.searchQuery} onChange={(e) => setScanConfig({...scanConfig, searchQuery: e.target.value})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
                </div>

                {/* New Specific URL Scan Section */}
                <div className="pt-3 border-t border-slate-100">
                  <label className="text-[9px] font-bold text-slate-400 uppercase">Scan d'URL Spécifique</label>
                  <div className="flex gap-2 mt-1">
                    <input
                      type="text"
                      placeholder="Coller l'URL de l'annonce Facebook..."
                      value={specificUrl}
                      onChange={(e) => setSpecificUrl(e.target.value)}
                      className="flex-grow p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs"
                    />
                    <button
                      onClick={handleScanSpecificUrl}
                      disabled={!specificUrl || isScanningUrl}
                      className="bg-blue-500 text-white px-3 py-2 rounded-lg text-xs font-bold hover:bg-blue-600 disabled:bg-slate-300 flex items-center justify-center"
                    >
                      {isScanningUrl ? <RefreshCw size={14} className="animate-spin" /> : <Search size={14} />}
                    </button>
                  </div>
                </div>

              </div>

              {/* SECTION 2: GESTION DES VILLES (Déplacé ici) */}
              <div className="pt-4 border-t border-slate-100">
                <label className="text-[9px] font-bold text-slate-400 uppercase block mb-2">Villes Autorisées</label>
                
                <div className="space-y-2 mb-3 max-h-40 overflow-y-auto">
                  {cities.map(city => (
                    <div key={city.id} className="flex items-center justify-between bg-slate-50 p-2 rounded-lg text-xs">
                      <div>
                        <span className="font-bold block">{city.name}</span>
                        <span className="text-[9px] text-slate-400 font-mono">{city.id}</span>
                      </div>
                      <button onClick={() => handleDeleteCity(city.id)} className="text-rose-400 hover:text-rose-600 p-1">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                  {cities.length === 0 && <p className="text-[10px] text-slate-400 italic">Aucune ville configurée.</p>}
                </div>

                <div className="flex gap-2">
                  <input 
                    type="text" 
                    placeholder="Nom (ex: Montreal)" 
                    value={newCityName}
                    onChange={(e) => setNewCityName(e.target.value)}
                    className="w-1/2 p-2 bg-slate-50 border border-slate-200 rounded-lg text-[10px]"
                  />
                  <input 
                    type="text" 
                    placeholder="ID Facebook" 
                    value={newCityId}
                    onChange={(e) => setNewCityId(e.target.value)}
                    className="w-1/2 p-2 bg-slate-50 border border-slate-200 rounded-lg text-[10px]"
                  />
                </div>
                <button
                  onClick={handleAddCity}
                  disabled={!newCityName || !newCityId}
                  className="w-full mt-2 bg-blue-50 text-blue-600 py-2 rounded-xl text-[10px] font-bold uppercase hover:bg-blue-100 disabled:opacity-50 flex items-center justify-center gap-1"
                >
                  <Plus size={12} /> Ajouter Ville
                </button>
              </div>

              {/* SECTION 3: AI BOT CONFIG */}
              <div className="space-y-3 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-purple-600">
                    <Sparkles size={14} />
                    <span className="text-[10px] font-black uppercase tracking-widest">Intelligence Artificielle</span>
                  </div>
                  <button 
                    onClick={handleResetDefaults}
                    className="text-[9px] font-bold text-slate-400 hover:text-blue-600 flex items-center gap-1 transition-colors"
                    title="Réinitialiser aux valeurs par défaut"
                  >
                    <RotateCcw size={10} /> Reset
                  </button>
                </div>

                <button
                    onClick={handleRelaunchAll}
                    disabled={isReanalyzingAll}
                    className={`w-full mb-4 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${isReanalyzingAll ? 'bg-purple-100 text-purple-600' : 'bg-purple-50 text-purple-600 hover:bg-purple-100 border border-purple-100'}`}
                >
                    <BrainCircuit size={16} className={isReanalyzingAll ? "animate-pulse" : ""} />
                    {isReanalyzingAll ? 'Demande envoyée...' : 'Relancer TOUTES les analyses'}
                </button>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Prompt Gemini</label>
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onBlur={() => saveConfig({ prompt })}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24 italic"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Prompt Utilisateur (Template)</label>
                  <textarea
                    value={userPrompt}
                    onChange={(e) => setUserPrompt(e.target.value)}
                    onBlur={() => saveConfig({ userPrompt })}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24 italic"
                    placeholder="Utilisez {title}, {price}, {description} comme placeholders."
                  />
                </div>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Règles de Verdict</label>
                  <textarea
                    value={verdictRules}
                    onChange={(e) => setVerdictRules(e.target.value)}
                    onBlur={() => saveConfig({ verdictRules })}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Instruction de Raisonnement</label>
                  <textarea
                    value={reasoningInstruction}
                    onChange={(e) => setReasoningInstruction(e.target.value)}
                    onBlur={() => saveConfig({ reasoningInstruction })}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24"
                  />
                </div>
              </div>

            </div>
          )}
        </aside>

        {/* MAIN FEED */}
        <main className="lg:col-span-3 space-y-6">

          {/* SEARCH & FILTERS BAR */}
          <div className="bg-white p-4 rounded-3xl shadow-sm border border-slate-200 flex flex-wrap gap-4 items-center justify-between">
            <div className="flex-1 min-w-[200px] relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type="text"
                placeholder="Rechercher par modèle..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>
            
            {/* Toggle View Mode */}
            <div className="flex bg-slate-100 p-1 rounded-2xl">
                <button
                    onClick={() => setViewMode('LIST')}
                    className={`p-2 rounded-xl transition-all ${viewMode === 'LIST' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    <List size={18} />
                </button>
                <button
                    onClick={() => setViewMode('MAP')}
                    className={`p-2 rounded-xl transition-all ${viewMode === 'MAP' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    <MapIcon size={18} />
                </button>
            </div>

            <div className="flex items-center gap-2 overflow-x-auto pb-1 w-full lg:w-auto">
              {['ALL', 'FAVORITES', 'PEPITE', 'GOOD_DEAL', 'FAIR', 'BAD_DEAL', 'REJECTED', 'ERROR'].map((type) => (
                <button
                  key={type}
                  onClick={() => setFilterType(type)}
                  className={`px-4 py-2 rounded-2xl text-xs font-bold whitespace-nowrap transition-all ${filterType === type ? 'bg-blue-600 text-white shadow-md' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                >
                  {type === 'ALL' ? 'Toutes' : type === 'FAVORITES' ? 'Favoris' : type === 'PEPITE' ? 'Pépites' : type === 'GOOD_DEAL' ? 'Bonnes Affaires' : type === 'FAIR' ? 'Prix Juste' : type === 'BAD_DEAL' ? 'Trop Cher' : type === 'REJECTED' ? 'Rejetées' : 'Erreurs'}
                </button>
              ))}
            </div>
          </div>

          {/* CONTENT AREA (LIST OR MAP) */}
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center bg-white rounded-3xl border border-slate-200">
              <RefreshCw className="text-blue-600 animate-spin mb-4" size={40} />
              <p className="text-slate-400 font-bold uppercase tracking-widest text-xs">Synchronisation Firestore...</p>
            </div>
          ) : filteredDeals.length === 0 ? (
            <div className="py-20 flex flex-col items-center justify-center bg-white rounded-3xl border border-dashed border-slate-200">
              <div className="bg-slate-50 p-6 rounded-full mb-4">
                <Search className="text-slate-200" size={48} />
              </div>
              <h3 className="text-lg font-black text-slate-400 uppercase tracking-tight italic">Aucun trésor trouvé</h3>
              <p className="text-slate-400 text-xs mt-1">Ajustez vos filtres ou lancez un scan manuel</p>
            </div>
          ) : viewMode === 'MAP' ? (
             <MapView deals={filteredDeals} onDealSelect={setSelectedDealFromMap} />
          ) : (
            <div className="grid grid-cols-1 gap-6">
              {filteredDeals.map((deal) => (
                <DealCard
                  key={deal.id}
                  deal={deal}
                  filterType={filterType}
                  onRetry={handleRetryAnalysis}
                  onReject={handleRejectDeal}
                  onToggleFavorite={handleToggleFavorite}
                />
              ))}
            </div>
          )}
        </main>
      </div>

      {/* ERROR TOAST */}
      {error && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-10">
          <div className="bg-rose-600 text-white px-6 py-4 rounded-2xl shadow-2xl shadow-rose-200 flex items-center gap-4">
            <AlertTriangle size={24} />
            <div>
              <p className="font-black uppercase text-[10px] tracking-widest leading-none mb-1 opacity-80">Erreur Détectée</p>
              <p className="text-sm font-bold">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="ml-4 hover:bg-white/20 p-1 rounded-lg transition-colors">
              <XCircle size={20} />
            </button>
          </div>
        </div>
      )}

      {/* MODAL FOR MAP DEAL */}
      {selectedDealFromMap && (
        <div 
          className="fixed inset-0 bg-black/80 z-50 flex flex-col items-center overflow-y-auto animate-in fade-in backdrop-blur-sm pt-24 pb-12"
          onClick={() => setSelectedDealFromMap(null)}
        >
          {/* Controls Bar */}
          <div 
            className="fixed top-6 z-50 flex items-center gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-slate-900/90 text-white px-4 py-2 rounded-full flex items-center gap-3 shadow-2xl border border-white/10">
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Zoom</span>
                <input 
                type="range" 
                min="0.5" 
                max="1.1" 
                step="0.1" 
                value={zoomLevel} 
                onChange={(e) => setZoomLevel(parseFloat(e.target.value))}
                className="w-24 accent-blue-500 h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer"
                />
                <span className="text-[10px] font-mono w-8 text-right text-blue-400">{Math.round(zoomLevel * 100)}%</span>
            </div>

            <button 
              onClick={() => setSelectedDealFromMap(null)}
              className="bg-white text-slate-900 rounded-full p-2.5 shadow-2xl hover:bg-rose-500 hover:text-white transition-all"
            >
              <XCircle size={20} />
            </button>
          </div>

          {/* Scalable Content */}
          <div 
            className="relative transition-transform duration-200 ease-out origin-top"
            style={{ 
              transform: `scale(${zoomLevel})`,
              width: '100%',
              maxWidth: '60rem', // un peu plus large pour compenser le scale down
              padding: '1rem'
            }}
            onClick={(e) => e.stopPropagation()}
          >
             <DealCard
                key={selectedDealFromMap.id}
                deal={selectedDealFromMap}
                filterType={filterType}
                onRetry={handleRetryAnalysis}
                onReject={handleRejectDeal}
                onToggleFavorite={handleToggleFavorite}
              />
          </div>
        </div>
      )}
    </div>
  );
};

export default App;