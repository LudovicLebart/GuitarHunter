import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search, ExternalLink, Guitar,
  AlertTriangle, RefreshCw, CheckCircle, XCircle,
  Activity, Settings, Clock,
  MapPin, Sparkles, TrendingUp, Plus, Trash2, ChevronLeft, ChevronRight, Ban, RotateCcw, Map as MapIcon, List, Heart, BrainCircuit
} from 'lucide-react';

// --- Configuration Firebase ---
import { initializeApp } from 'firebase/app';
import {
  getFirestore, collection, onSnapshot, doc, setDoc, deleteField, addDoc, deleteDoc, updateDoc
} from 'firebase/firestore';
import {
  getAuth, signInAnonymously, onAuthStateChanged
} from 'firebase/auth';

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

// --- VALEURS PAR DÉFAUT (MISES À JOUR) ---
const DEFAULT_PROMPT = `Tu es un luthier expert et un négociant de guitares chevronné pour le marché du Québec (MTL/QC).
Ton but : Analyser les photos pour protéger l'acheteur contre les arnaques et les mauvais prix.

TA MISSION D'ANALYSE :
1.  **REJET (REJECTED)** : Si l'objet n'est pas une guitare/basse (ex: ampli, pédale, jouet, montre, guitare de jeu video). 
2.  **Authentification** : Vérifie la forme de la tête (Headstock), le logo, le placement des boutons. Repère les 'Chibson' ou contrefaçons.
3.  **État** : Zoome sur les frettes (usure ?), le chevalet (oxydation ?), le manche (fissures ?).
4.  **Valeur** : Estime le prix de revente RÉALISTE au Québec (pas le prix neuf, le prix Kijiji/Marketplace).

FORMAT DE RÉPONSE ATTENDU (JSON) :
{
  "verdict": "GOOD_DEAL" | "FAIR" | "BAD_DEAL" | "REJECTED",
  "estimated_value": 1200,
  "confidence": 90,
  "reasoning": "Modèle 2018 authentique. Le prix demandé (800$) est bien sous la cote habituelle (1100$). Attention : légère scratch au dos.",
  "red_flags": ["Frettes très usées", "Bouton de volume non original"]
}`;

const DEFAULT_VERDICT_RULES = `- "GOOD_DEAL" : Le prix demandé est INFERIEUR à la valeur estimée.
- "FAIR" : Le prix demandé est PROCHE de la valeur estimée (à +/- 10%).
- "BAD_DEAL" : Le prix demandé est SUPERIEUR à la valeur estimée.
- "REJECTED" : L'objet n'est PAS ce que l'on recherche (ex: une montre guitare, un accessoire seul si on cherche une guitare, une guitare jouet, etc.).`;
const DEFAULT_REASONING_INSTRUCTION = "explication détaillée et complète justifiant le verdict par rapport au prix et à la valeur";

// --- DICTIONNAIRE DE VILLES (COORDONNÉES APPROXIMATIVES) ---
// Utilisé pour placer les marqueurs sur la carte sans API de géocodage payante
const CITY_COORDINATES = {
  'montreal': { lat: 45.5017, lng: -73.5673 },
  'quebec': { lat: 46.8139, lng: -71.2080 },
  'laval': { lat: 45.5758, lng: -73.7531 },
  'gatineau': { lat: 45.4765, lng: -75.7013 },
  'longueuil': { lat: 45.5369, lng: -73.5105 },
  'sherbrooke': { lat: 45.4010, lng: -71.8824 },
  'levis': { lat: 46.8033, lng: -71.1779 },
  'trois-rivieres': { lat: 46.3430, lng: -72.5421 },
  'terrebonne': { lat: 45.6928, lng: -73.6330 },
  'saint-jean-sur-richelieu': { lat: 45.3057, lng: -73.2533 },
  'repentigny': { lat: 45.7397, lng: -73.4479 },
  'drummondville': { lat: 45.8833, lng: -72.4833 },
  'granby': { lat: 45.4000, lng: -72.7333 },
  'blainville': { lat: 45.6667, lng: -73.8833 },
  'saint-hyacinthe': { lat: 45.6333, lng: -72.9500 },
  'mirabel': { lat: 45.6500, lng: -74.0833 },
  'verdun': { lat: 45.4617, lng: -73.5669 },
  'lasalle': { lat: 45.4319, lng: -73.6336 },
  'lachine': { lat: 45.4419, lng: -73.6786 },
  'dorval': { lat: 45.4486, lng: -73.7367 },
  'pointe-claire': { lat: 45.4489, lng: -73.8167 },
  'kirkland': { lat: 45.4500, lng: -73.8667 },
  'beaconsfield': { lat: 45.4333, lng: -73.8667 },
  'baie-d\'urfé': { lat: 45.4167, lng: -73.9167 },
  'sainte-anne-de-bellevue': { lat: 45.4000, lng: -73.9500 },
  'senneville': { lat: 45.4167, lng: -73.9667 },
  'dollard-des-ormeaux': { lat: 45.4833, lng: -73.8167 },
  'pierrefonds': { lat: 45.4833, lng: -73.8667 },
  'roxboro': { lat: 45.5000, lng: -73.8167 },
  'sainte-geneviève': { lat: 45.4833, lng: -73.8667 },
  'île-bizard': { lat: 45.5000, lng: -73.8833 },
  'outremont': { lat: 45.5167, lng: -73.6000 },
  'westmount': { lat: 45.4833, lng: -73.6000 },
  'mont-royal': { lat: 45.5167, lng: -73.6500 },
  'côte-saint-luc': { lat: 45.4667, lng: -73.6667 },
  'hampstead': { lat: 45.4833, lng: -73.6333 },
  'montréal-ouest': { lat: 45.4500, lng: -73.6500 },
  'montréal-est': { lat: 45.6333, lng: -73.5000 },
  'anjou': { lat: 45.6000, lng: -73.5500 },
  'saint-léonard': { lat: 45.5833, lng: -73.6000 },
  'montréal-nord': { lat: 45.6000, lng: -73.6333 },
  'rivière-des-prairies': { lat: 45.6500, lng: -73.5833 },
  'pointe-aux-trembles': { lat: 45.6500, lng: -73.5000 },
  'brossard': { lat: 45.4667, lng: -73.4500 },
  'boucherville': { lat: 45.6000, lng: -73.4500 },
  'saint-bruno-de-montarville': { lat: 45.5333, lng: -73.3500 },
  'sainte-julie': { lat: 45.5833, lng: -73.3333 },
  'varennes': { lat: 45.6833, lng: -73.4333 },
  'verchères': { lat: 45.7667, lng: -73.3500 },
  'candiac': { lat: 45.3833, lng: -73.5167 },
  'la prairie': { lat: 45.4167, lng: -73.5000 },
  'sainte-catherine': { lat: 45.4000, lng: -73.5667 },
  'saint-constant': { lat: 45.3667, lng: -73.5667 },
  'châteauguay': { lat: 45.3667, lng: -73.7500 },
  'mercier': { lat: 45.3167, lng: -73.7500 },
  'beauharnois': { lat: 45.3167, lng: -73.8667 },
  'salaberry-de-valleyfield': { lat: 45.2500, lng: -74.1333 },
  'vaudreuil-dorion': { lat: 45.4000, lng: -74.0333 },
  'pincourt': { lat: 45.3833, lng: -73.9833 },
  'l\'île-perrot': { lat: 45.3833, lng: -73.9500 },
  'notre-dame-de-l\'île-perrot': { lat: 45.3667, lng: -73.9333 },
  'saint-lazare': { lat: 45.4000, lng: -74.1333 },
  'hudson': { lat: 45.4500, lng: -74.1500 },
  'rigaud': { lat: 45.4833, lng: -74.3000 },
  'saint-eustache': { lat: 45.5667, lng: -73.9000 },
  'deux-montagnes': { lat: 45.5333, lng: -73.8833 },
  'sainte-marthe-sur-le-lac': { lat: 45.5333, lng: -73.9333 },
  'pointe-calumet': { lat: 45.5167, lng: -73.9667 },
  'saint-joseph-du-lac': { lat: 45.5333, lng: -74.0000 },
  'oka': { lat: 45.4667, lng: -74.0833 },
  'boisbriand': { lat: 45.6167, lng: -73.8333 },
  'rosemère': { lat: 45.6333, lng: -73.8000 },
  'lorraine': { lat: 45.6500, lng: -73.7833 },
  'bois-des-filion': { lat: 45.6667, lng: -73.7500 },
  'sainte-thérèse': { lat: 45.6333, lng: -73.8333 },
  'mascouche': { lat: 45.7500, lng: -73.6000 },
  'l\'assomption': { lat: 45.8333, lng: -73.4167 },
  'charlemagne': { lat: 45.7167, lng: -73.4833 },
  'saint-sulpice': { lat: 45.8333, lng: -73.3500 },
  'lavaltrie': { lat: 45.8833, lng: -73.2833 },
  'lanoraie': { lat: 45.9500, lng: -73.2167 },
  'berthierville': { lat: 46.0833, lng: -73.1833 },
  'joliette': { lat: 46.0167, lng: -73.4333 },
  'notre-dame-des-prairies': { lat: 46.0500, lng: -73.4333 },
  'saint-charles-borromée': { lat: 46.0500, lng: -73.4667 },
  'saint-paul': { lat: 45.9500, lng: -73.4333 },
  'crabtree': { lat: 45.9667, lng: -73.4667 },
  'saint-lin-laurentides': { lat: 45.8500, lng: -73.7667 },
  'saint-calixte': { lat: 45.9500, lng: -73.8500 },
  'saint-hippolyte': { lat: 45.9167, lng: -74.0000 },
  'prévost': { lat: 45.8667, lng: -74.0833 },
  'saint-sauveur': { lat: 45.8833, lng: -74.1667 },
  'sainte-adèle': { lat: 45.9500, lng: -74.1333 },
  'val-david': { lat: 46.0333, lng: -74.2000 },
  'val-morin': { lat: 46.0167, lng: -74.2000 },
  'sainte-agathe-des-monts': { lat: 46.0500, lng: -74.2833 },
  'mont-tremblant': { lat: 46.1167, lng: -74.6000 },
  'saint-jérôme': { lat: 45.7833, lng: -74.0000 },
  'lachute': { lat: 45.6500, lng: -74.3333 },
  'brownsburg-chatham': { lat: 45.6667, lng: -74.4167 },
  'grenville': { lat: 45.6167, lng: -74.6000 },
  'hawkesbury': { lat: 45.6000, lng: -74.6000 },
  'saint-colomban': { lat: 45.7333, lng: -74.1333 },
  'gore': { lat: 45.7667, lng: -74.2500 },
  'mille-isles': { lat: 45.8000, lng: -74.1833 },
  'wentworth-nord': { lat: 45.8667, lng: -74.3833 },
  'morin-heights': { lat: 45.9000, lng: -74.2500 },
  'piedmont': { lat: 45.9000, lng: -74.1333 },
  'saint-adolphe-d\'howard': { lat: 45.9667, lng: -74.3333 },
  'saint-faustin-lac-carré': { lat: 46.1167, lng: -74.4833 },
  'mont-blanc': { lat: 46.1167, lng: -74.4833 },
  'labelle': { lat: 46.2833, lng: -74.7333 },
  'rivière-rouge': { lat: 46.4167, lng: -74.8833 },
  'mont-laurier': { lat: 46.5500, lng: -75.5000 },
  'ferme-neuve': { lat: 46.7000, lng: -75.4500 },
  'maniwaki': { lat: 46.3833, lng: -75.9667 },
  'chelsea': { lat: 45.5000, lng: -75.7833 },
  'cantley': { lat: 45.5500, lng: -75.7667 },
  'val-des-monts': { lat: 45.6500, lng: -75.6667 },
  'l\'ange-gardien': { lat: 45.6000, lng: -75.4333 },
  'buckingham': { lat: 45.5833, lng: -75.4167 },
  'masson-angers': { lat: 45.5333, lng: -75.4333 },
  'thurso': { lat: 45.6000, lng: -75.2500 },
  'papineauville': { lat: 45.6167, lng: -75.0167 },
  'montebello': { lat: 45.6500, lng: -74.9333 },
  'saint-andré-avellin': { lat: 45.7167, lng: -75.0500 },
  'chénéville': { lat: 45.8833, lng: -75.0500 },
  'lac-simon': { lat: 45.9333, lng: -75.0833 },
  'montpellier': { lat: 45.9167, lng: -75.1667 },
  'namur': { lat: 45.8833, lng: -74.9167 },
  'boileau': { lat: 45.9500, lng: -74.8333 },
  'amherst': { lat: 46.0333, lng: -74.8333 },
  'huberdeau': { lat: 45.9833, lng: -74.6333 },
  'arundel': { lat: 45.9667, lng: -74.6167 },
  'barkmere': { lat: 46.0333, lng: -74.5833 },
  'montcalm': { lat: 45.9667, lng: -74.5333 },
  'weir': { lat: 45.9500, lng: -74.5333 },
  'lac-des-seize-îles': { lat: 45.8833, lng: -74.4667 },
  'wentworth': { lat: 45.7500, lng: -74.3833 },
  'harrington': { lat: 45.7833, lng: -74.5833 },
  'grenville-sur-la-rouge': { lat: 45.6667, lng: -74.6833 },
  'pointe-fortune': { lat: 45.5500, lng: -74.3833 },
  'très-saint-rédempteur': { lat: 45.4333, lng: -74.3167 },
  'sainte-marthe': { lat: 45.4000, lng: -74.2833 },
  'sainte-justine-de-newton': { lat: 45.3500, lng: -74.3833 },
  'saint-télesphore': { lat: 45.2833, lng: -74.4167 },
  'saint-polycarpe': { lat: 45.3000, lng: -74.3000 },
  'saint-zotique': { lat: 45.2500, lng: -74.2333 },
  'les coteaux': { lat: 45.2667, lng: -74.2333 },
  'coteau-du-lac': { lat: 45.2833, lng: -74.1833 },
  'saint-clet': { lat: 45.3500, lng: -74.2167 },
  'les cèdres': { lat: 45.3000, lng: -74.0500 },
  'pointe-des-cascades': { lat: 45.3333, lng: -73.9667 },
  'terrasse-vaudreuil': { lat: 45.3833, lng: -73.9833 },
  'vaudreuil-sur-le-lac': { lat: 45.4167, lng: -74.0167 },
  'l\'île-cadieux': { lat: 45.4333, lng: -74.0167 },
  'saint-stanislas-de-kostka': { lat: 45.1833, lng: -74.1333 },
  'saint-étienne-de-beauharnois': { lat: 45.2500, lng: -73.9167 },
  'sainte-barbe': { lat: 45.1667, lng: -74.2000 },
  'saint-anicet': { lat: 45.0833, lng: -74.3667 },
  'dundee': { lat: 45.0167, lng: -74.5000 },
  'elgin': { lat: 45.0000, lng: -74.2500 },
  'hinchinbrooke': { lat: 45.0333, lng: -74.1667 },
  'huntingdon': { lat: 45.0833, lng: -74.1667 },
  'godmanchester': { lat: 45.0833, lng: -74.1500 },
  'ormstown': { lat: 45.1167, lng: -74.0500 },
  'franklin': { lat: 45.0333, lng: -73.9333 },
  'havelock': { lat: 45.0500, lng: -73.7667 },
  'saint-chrysostome': { lat: 45.1000, lng: -73.7500 },
  'très-saint-sacrement': { lat: 45.1667, lng: -73.8333 },
  'howick': { lat: 45.1833, lng: -73.8500 },
  'sainte-martine': { lat: 45.2500, lng: -73.8000 },
  'saint-urbain-premier': { lat: 45.2167, lng: -73.7333 },
  'sainte-clotilde': { lat: 45.1667, lng: -73.6833 },
  'hemmingford': { lat: 45.0500, lng: -73.5833 },
  'saint-bernard-de-lacolle': { lat: 45.0833, lng: -73.4167 },
  'lacolle': { lat: 45.0833, lng: -73.3667 },
  'saint-valentin': { lat: 45.1333, lng: -73.3167 },
  'saint-paul-de-l\'île-aux-noix': { lat: 45.1333, lng: -73.2667 },
  'henryville': { lat: 45.1333, lng: -73.1833 },
  'noyan': { lat: 45.0667, lng: -73.2000 },
  'clarenceville': { lat: 45.0667, lng: -73.2500 },
  'venise-en-québec': { lat: 45.0833, lng: -73.1333 },
  'saint-georges-de-clarenceville': { lat: 45.0667, lng: -73.2500 },
  'saint-sébastien': { lat: 45.1667, lng: -73.1333 },
  'pike river': { lat: 45.1167, lng: -73.0667 },
  'stanbridge station': { lat: 45.1167, lng: -73.0333 },
  'bedford': { lat: 45.1167, lng: -72.9833 },
  'notre-dame-de-stanbridge': { lat: 45.1833, lng: -73.0333 },
  'farnham': { lat: 45.2833, lng: -72.9667 },
  'sainte-brigide-d\'iberville': { lat: 45.3333, lng: -73.0500 },
  'mont-saint-grégoire': { lat: 45.3333, lng: -73.1500 },
  'saint-alexandre': { lat: 45.2333, lng: -73.1167 },
  'sainte-anne-de-sabrevois': { lat: 45.2167, lng: -73.2333 },
  'saint-blaise-sur-richelieu': { lat: 45.2167, lng: -73.2833 },
  'saint-cyprien-de-napierville': { lat: 45.1833, lng: -73.4000 },
  'napierville': { lat: 45.1833, lng: -73.4000 },
  'saint-jacques-le-mineur': { lat: 45.2833, lng: -73.4167 },
  'saint-michel': { lat: 45.2833, lng: -73.5667 },
  'saint-rémi': { lat: 45.2667, lng: -73.6167 },
  'saint-mathieu': { lat: 45.3167, lng: -73.5333 },
  'saint-philippe': { lat: 45.3500, lng: -73.4667 },
  'saint-basile-le-grand': { lat: 45.5333, lng: -73.2833 },
  'mcmasterville': { lat: 45.5500, lng: -73.2167 },
  'beloeil': { lat: 45.5667, lng: -73.2000 },
  'mont-saint-hilaire': { lat: 45.5667, lng: -73.1833 },
  'otterburn park': { lat: 45.5333, lng: -73.2000 },
  'saint-mathias-sur-richelieu': { lat: 45.4833, lng: -73.2667 },
  'richelieu': { lat: 45.4500, lng: -73.2500 },
  'chambly': { lat: 45.4500, lng: -73.2833 },
  'carignan': { lat: 45.4500, lng: -73.3333 },
  'saint-jean-baptiste': { lat: 45.5167, lng: -73.1167 },
  'saint-pie': { lat: 45.5167, lng: -72.9000 },
  'saint-dominique': { lat: 45.5500, lng: -72.8333 },
  'saint-valérien-de-milton': { lat: 45.5667, lng: -72.7167 },
  'roxton pond': { lat: 45.4833, lng: -72.6500 },
  'roxton falls': { lat: 45.5667, lng: -72.5167 },
  'acton vale': { lat: 45.6500, lng: -72.5667 },
  'upton': { lat: 45.6667, lng: -72.6667 },
  'saint-théodore-d\'acton': { lat: 45.6833, lng: -72.6000 },
  'saint-nazaire-d\'acton': { lat: 45.7500, lng: -72.6167 },
  'sainte-hélène-de-bagot': { lat: 45.7333, lng: -72.7333 },
  'saint-hugues': { lat: 45.8167, lng: -72.8833 },
  'saint-liboire': { lat: 45.6500, lng: -72.8667 },
  'sainte-rosalie': { lat: 45.6333, lng: -72.9000 },
  'saint-thomas-d\'aquin': { lat: 45.6167, lng: -73.0000 },
  'la présentation': { lat: 45.6667, lng: -73.0500 },
  'saint-jude': { lat: 45.7833, lng: -73.0333 },
  'saint-barnabé-sud': { lat: 45.7667, lng: -72.9333 },
  'saint-bernard-de-michaudville': { lat: 45.8167, lng: -73.0000 },
  'saint-louis': { lat: 45.8667, lng: -72.9833 },
  'saint-aimé': { lat: 45.9000, lng: -72.9500 },
  'saint-robert': { lat: 45.9667, lng: -73.0167 },
  'sainte-victoire-de-sorel': { lat: 45.9667, lng: -73.0833 },
  'saint-ours': { lat: 45.8833, lng: -73.1500 },
  'saint-roch-de-richelieu': { lat: 45.9167, lng: -73.1833 },
  'sorel-tracy': { lat: 46.0333, lng: -73.1167 },
  'saint-joseph-de-sorel': { lat: 46.0333, lng: -73.1333 },
  'sainte-anne-de-sorel': { lat: 46.0500, lng: -73.0667 },
  'yamaska': { lat: 46.0167, lng: -72.9167 },
  'saint-gérard-majella': { lat: 45.9833, lng: -72.8667 },
  'saint-david': { lat: 45.9667, lng: -72.8000 },
  'massueville': { lat: 45.9333, lng: -72.9333 },
  'saint-guillaume': { lat: 45.8833, lng: -72.7667 },
  'saint-bonaventure': { lat: 45.9333, lng: -72.6833 },
  'saint-pie-de-guire': { lat: 45.9333, lng: -72.6000 },
  'saint-françois-du-lac': { lat: 46.0667, lng: -72.8333 },
  'pierreville': { lat: 46.0667, lng: -72.8167 },
  'odanak': { lat: 46.0667, lng: -72.8167 },
  'baie-du-febvre': { lat: 46.1333, lng: -72.7167 },
  'nicolet': { lat: 46.2333, lng: -72.6167 },
  'grand-saint-esprit': { lat: 46.1667, lng: -72.5000 },
  'saint-célestin': { lat: 46.2167, lng: -72.4333 },
  'saint-wenceslas': { lat: 46.1667, lng: -72.3333 },
  'saint-léonard-d\'aston': { lat: 46.0833, lng: -72.3333 },
  'notre-dame-du-bon-conseil': { lat: 46.0000, lng: -72.3500 },
  'sainte-brigitte-des-saults': { lat: 46.0333, lng: -72.5000 },
  'saint-cyrille-de-wendover': { lat: 45.9333, lng: -72.4333 },
  'saint-lucien': { lat: 45.8333, lng: -72.4167 },
  'saint-félix-de-kingsey': { lat: 45.7833, lng: -72.2333 },
  'durham-sud': { lat: 45.6667, lng: -72.3333 },
  'lefebvre': { lat: 45.7000, lng: -72.4167 },
  'wickham': { lat: 45.7500, lng: -72.5167 },
  'l\'avenir': { lat: 45.7667, lng: -72.3333 },
  'saint-germain-de-grantham': { lat: 45.8333, lng: -72.5667 },
  'saint-majorique-de-grantham': { lat: 45.9000, lng: -72.5333 },
  'saint-eugène': { lat: 45.8167, lng: -72.6833 },
  'saint-edmond-de-grantham': { lat: 45.8667, lng: -72.6667 },
  'saint-joachim-de-courval': { lat: 45.9333, lng: -72.5667 },
  'saint-zéphirin-de-courval': { lat: 46.0500, lng: -72.6000 },
  'saint-elphège': { lat: 46.0833, lng: -72.6333 },
  'la visitation-de-yamaska': { lat: 46.1167, lng: -72.6000 },
  'saint-françois-xavier-de-brome': { lat: 45.2833, lng: -72.7167 },
  'brigham': { lat: 45.2833, lng: -72.7667 },
  'bromont': { lat: 45.3167, lng: -72.6500 },
  'lac-brome': { lat: 45.2167, lng: -72.5167 },
  'bolton-ouest': { lat: 45.2000, lng: -72.4500 },
  'sutton': { lat: 45.1000, lng: -72.6167 },
  'abercorn': { lat: 45.0333, lng: -72.6667 },
  'frelighsburg': { lat: 45.0500, lng: -72.8333 },
  'saint-armand': { lat: 45.0333, lng: -73.0500 },
  'dunham': { lat: 45.1333, lng: -72.8000 },
  'cowansville': { lat: 45.2000, lng: -72.7500 },
  'east farnham': { lat: 45.2333, lng: -72.7833 },
  'sainte-cécile-de-milton': { lat: 45.4833, lng: -72.7500 },
  'saint-alphonse-de-granby': { lat: 45.4000, lng: -72.8000 },
  'ange-gardien': { lat: 45.3500, lng: -72.9167 },
  'saint-paul-d\'abbotsford': { lat: 45.4333, lng: -72.8833 },
  'shefford': { lat: 45.3500, lng: -72.6000 },
  'waterloo': { lat: 45.3500, lng: -72.5167 },
  'warden': { lat: 45.3833, lng: -72.5000 },
  'saint-joachim-de-shefford': { lat: 45.4333, lng: -72.5667 },
  'sainte-anne-de-la-rochelle': { lat: 45.4167, lng: -72.4167 },
  'bonsecours': { lat: 45.4167, lng: -72.3000 },
  'lawrenceville': { lat: 45.4167, lng: -72.3667 },
  'valcourt': { lat: 45.5000, lng: -72.3167 },
  'maricourt': { lat: 45.5500, lng: -72.3000 },
  'racine': { lat: 45.4833, lng: -72.2333 },
  'melbourne': { lat: 45.5667, lng: -72.1667 },
  'richmond': { lat: 45.6667, lng: -72.1500 },
  'cleveland': { lat: 45.6667, lng: -72.1000 },
  'windsor': { lat: 45.5667, lng: -72.0000 },
  'saint-françois-xavier-de-brompton': { lat: 45.5167, lng: -72.0500 },
  'stoke': { lat: 45.5000, lng: -71.8167 },
  'ascot corner': { lat: 45.4500, lng: -71.7667 },
  'east angus': { lat: 45.4833, lng: -71.6667 },
  'westbury': { lat: 45.5000, lng: -71.6333 },
  'cookshire-eaton': { lat: 45.4167, lng: -71.6333 },
  'newport': { lat: 45.3667, lng: -71.4667 },
  'burt-harnett': { lat: 45.3667, lng: -71.4667 },
  'chartierville': { lat: 45.4333, lng: -71.2500 },
  'la patrie': { lat: 45.4000, lng: -71.2500 },
  'scotstown': { lat: 45.5333, lng: -71.2833 },
  'lingwick': { lat: 45.6167, lng: -71.3833 },
  'weedon': { lat: 45.7000, lng: -71.4667 },
  'dudswell': { lat: 45.6167, lng: -71.6333 },
  'bury': { lat: 45.5167, lng: -71.5000 },
  'saint-isidore-de-clifton': { lat: 45.2667, lng: -71.5167 },
  'saint-malo': { lat: 45.1833, lng: -71.5000 },
  'saint-venant-de-paquette': { lat: 45.1333, lng: -71.4667 },
  'east hereford': { lat: 45.0500, lng: -71.5000 },
  'saint-herménégilde': { lat: 45.1000, lng: -71.6833 },
  'dixville': { lat: 45.0833, lng: -71.7667 },
  'coaticook': { lat: 45.1333, lng: -71.8000 },
  'barnston-ouest': { lat: 45.1167, lng: -71.9333 },
  'stanstead-est': { lat: 45.0833, lng: -72.0500 },
  'stanstead': { lat: 45.0167, lng: -72.1000 },
  'ogden': { lat: 45.0333, lng: -72.1667 },
  'ayer\'s cliff': { lat: 45.1667, lng: -72.0500 },
  'hatley': { lat: 45.1833, lng: -71.9333 },
  'north hatley': { lat: 45.2667, lng: -71.9667 },
  'sainte-catherine-de-hatley': { lat: 45.2667, lng: -72.0500 },
  'magog': { lat: 45.2667, lng: -72.1500 },
  'austin': { lat: 45.1500, lng: -72.2667 },
  'saint-benoît-du-lac': { lat: 45.1667, lng: -72.2667 },
  'bolton-est': { lat: 45.2000, lng: -72.3500 },
  'saint-étienne-de-bolton': { lat: 45.2500, lng: -72.3500 },
  'stukely-sud': { lat: 45.3167, lng: -72.4167 },
  'eastman': { lat: 45.3000, lng: -72.3000 },
  'orford': { lat: 45.3667, lng: -72.1667 },
  'saint-denis-de-brompton': { lat: 45.4333, lng: -72.0833 },
  'val-joli': { lat: 45.5833, lng: -72.0333 },
  'saint-claude': { lat: 45.6667, lng: -71.9833 },
  'ulverton': { lat: 45.7167, lng: -72.2500 },
  'lisgar': { lat: 45.7167, lng: -72.2500 },
  'kingsbury': { lat: 45.5833, lng: -72.2833 },
  'val-racine': { lat: 45.4833, lng: -70.9500 },
  'hampden': { lat: 45.5333, lng: -71.3667 },
  'milan': { lat: 45.6000, lng: -71.1333 },
  'nantes': { lat: 45.6333, lng: -70.9833 },
  'lac-mégantic': { lat: 45.5833, lng: -70.8833 },
  'marston': { lat: 45.5500, lng: -70.9333 },
  'piopolis': { lat: 45.4500, lng: -70.9000 },
  'notre-dame-des-bois': { lat: 45.3833, lng: -71.0667 },
  'saint-augustin-de-woburn': { lat: 45.3833, lng: -70.8667 },
  'frontenac': { lat: 45.5333, lng: -70.8167 },
  'audet': { lat: 45.6667, lng: -70.7833 },
  'sainte-cécile-de-whitton': { lat: 45.7167, lng: -70.9333 },
  'lac-drolet': { lat: 45.7167, lng: -70.8500 },
  'saint-ludger': { lat: 45.7333, lng: -70.6833 },
  'saint-robert-bellarmin': { lat: 45.7167, lng: -70.5333 },
  'saint-gédéon-de-beauce': { lat: 45.8667, lng: -70.6333 },
  'saint-hilaire-de-dorset': { lat: 45.8667, lng: -70.8500 },
  'saint-évariste-de-forsyth': { lat: 45.9333, lng: -70.9333 },
  'la guadeloupe': { lat: 45.9500, lng: -70.9333 },
  'saint-honoré-de-shenley': { lat: 45.9667, lng: -70.8000 },
  'saint-martin': { lat: 45.9667, lng: -70.6500 },
  'saint-théophile': { lat: 45.9333, lng: -70.4667 },
  'saint-rené': { lat: 46.0667, lng: -70.5667 },
  'saint-côme-linière': { lat: 46.0667, lng: -70.5167 },
  'saint-georges': { lat: 46.1167, lng: -70.6667 },
  'saint-philibert': { lat: 46.1333, lng: -70.5667 },
  'saint-prosper': { lat: 46.2167, lng: -70.4833 },
  'saint-benjamin': { lat: 46.2833, lng: -70.5833 },
  'sainte-aurélie': { lat: 46.1833, lng: -70.3667 },
  'saint-zacharie': { lat: 46.1333, lng: -70.3667 },
  'sainte-rose-de-watford': { lat: 46.3167, lng: -70.4167 },
  'saint-louis-de-gonzague': { lat: 46.2667, lng: -70.3333 },
  'sainte-justine': { lat: 46.4167, lng: -70.3500 },
  'lac-etchemin': { lat: 46.4000, lng: -70.5167 },
  'saint-luc-de-bellechasse': { lat: 46.5000, lng: -70.4667 },
  'saint-magloire': { lat: 46.6000, lng: -70.2833 },
  'saint-camille-de-lellis': { lat: 46.5000, lng: -70.2000 },
  'sainte-sabine': { lat: 46.4833, lng: -70.3500 },
  'saint-odilon-de-cranbourne': { lat: 46.3167, lng: -70.6667 },
  'saint-joseph-de-beauce': { lat: 46.3000, lng: -70.8833 },
  'saint-joseph-des-érables': { lat: 46.3167, lng: -70.9000 },
  'saint-jules': { lat: 46.2667, lng: -70.9167 },
  'tring-jonction': { lat: 46.2667, lng: -70.9667 },
  'saint-frédéric': { lat: 46.3000, lng: -70.9667 },
  'vallée-jonction': { lat: 46.3667, lng: -70.9167 },
  'saints-anges': { lat: 46.4333, lng: -70.9000 },
  'frampton': { lat: 46.4667, lng: -70.8000 },
  'saint-malachie': { lat: 46.5333, lng: -70.7667 },
  'saint-léon-de-standon': { lat: 46.4833, lng: -70.6333 },
  'saint-nazaire-de-dorchester': { lat: 46.5500, lng: -70.6667 },
  'sainte-claire': { lat: 46.6000, lng: -70.8667 },
  'saint-anselme': { lat: 46.6333, lng: -70.9667 },
  'sainte-hénédine': { lat: 46.5500, lng: -70.9833 },
  'scott': { lat: 46.5000, lng: -71.0833 },
  'saint-bernard': { lat: 46.5000, lng: -71.1333 },
  'saint-lambert-de-lauzon': { lat: 46.5833, lng: -71.2167 },
  'saint-henri': { lat: 46.6833, lng: -71.0667 },
  'saint-gervais': { lat: 46.7167, lng: -70.9000 },
  'saint-lazare-de-bellechasse': { lat: 46.6667, lng: -70.8000 },
  'saint-damien-de-buckland': { lat: 46.6333, lng: -70.6667 },
  'buckland': { lat: 46.6167, lng: -70.5500 },
  'saint-philémon': { lat: 46.6833, lng: -70.4667 },
  'armagh': { lat: 46.7500, lng: -70.5833 },
  'saint-nerée-de-bellechasse': { lat: 46.7333, lng: -70.7333 },
  'saint-raphaël': { lat: 46.8000, lng: -70.7500 },
  'la durantaye': { lat: 46.8167, lng: -70.8667 },
  'saint-charles-de-bellechasse': { lat: 46.7833, lng: -70.9333 },
  'beaumont': { lat: 46.8333, lng: -71.0167 },
  'saint-michel-de-bellechasse': { lat: 46.8667, lng: -70.9167 },
  'saint-vallier': { lat: 46.8833, lng: -70.8167 },
  'berthier-sur-mer': { lat: 46.9333, lng: -70.7333 },
  'montmagny': { lat: 46.9833, lng: -70.5500 },
  'saint-pierre-de-la-rivière-du-sud': { lat: 46.9167, lng: -70.6333 },
  'saint-françois-de-la-rivière-du-sud': { lat: 46.9000, lng: -70.7167 },
  'notre-dame-du-rosaire': { lat: 46.8667, lng: -70.3833 },
  'cap-saint-ignace': { lat: 47.0333, lng: -70.4667 },
  'l\'islet': { lat: 47.1167, lng: -70.3667 },
  'saint-cyrille-de-l\'islet': { lat: 47.0333, lng: -70.2500 },
  'saint-marcel': { lat: 46.9333, lng: -70.0833 },
  'sainte-perpétue': { lat: 47.0500, lng: -69.9333 },
  'tourville': { lat: 47.0833, lng: -70.0500 },
  'saint-damase-de-l\'islet': { lat: 47.1833, lng: -70.1333 },
  'saint-jean-port-joli': { lat: 47.2167, lng: -70.2667 },
  'saint-aubert': { lat: 47.1667, lng: -70.2167 },
  'sainte-louise': { lat: 47.2833, lng: -70.1000 },
  'saint-roch-des-aulnaies': { lat: 47.3167, lng: -70.1000 },
  'sainte-anne-de-la-pocatière': { lat: 47.3500, lng: -70.0333 },
  'la pocatière': { lat: 47.3667, lng: -70.0333 },
  'saint-onésime-d\'ixworth': { lat: 47.2833, lng: -69.9500 },
  'saint-gabriel-lalemant': { lat: 47.4333, lng: -69.9667 },
  'mont-carmel': { lat: 47.4333, lng: -69.8500 },
  'rivière-ouelle': { lat: 47.4333, lng: -70.0167 },
  'saint-pacôme': { lat: 47.4000, lng: -69.9500 },
  'saint-denis-de-la-bouteillerie': { lat: 47.5000, lng: -69.9333 },
  'saint-philippe-de-néri': { lat: 47.4667, lng: -69.8833 },
  'kamouraska': { lat: 47.5667, lng: -69.8667 },
  'saint-pascal': { lat: 47.5333, lng: -69.8000 },
  'sainte-hélène-de-kamouraska': { lat: 47.5833, lng: -69.7333 },
  'saint-germain': { lat: 47.6167, lng: -69.8000 },
  'saint-andré': { lat: 47.6667, lng: -69.7333 },
  'saint-alexandre-de-kamouraska': { lat: 47.6833, lng: -69.6167 },
  'saint-joseph-de-kamouraska': { lat: 47.6000, lng: -69.6333 },
  'saint-bruno-de-kamouraska': { lat: 47.5333, lng: -69.7500 },
  'picard': { lat: 47.5333, lng: -69.7500 },
  'saint-athanase': { lat: 47.3833, lng: -69.4667 },
  'pohénégamook': { lat: 47.4667, lng: -69.2167 },
  'rivière-bleue': { lat: 47.4333, lng: -69.0500 },
  'saint-marc-du-lac-long': { lat: 47.6000, lng: -69.1667 },
  'saint-elzéar-de-témiscouata': { lat: 47.5333, lng: -69.1000 },
  'saint-louis-du-ha! ha!': { lat: 47.6667, lng: -69.0000 },
  'témiscouata-sur-le-lac': { lat: 47.6833, lng: -68.8833 },
  'saint-honoré-de-témiscouata': { lat: 47.7333, lng: -69.0333 },
  'saint-pierre-de-lamy': { lat: 47.7667, lng: -69.0833 },
  'saint-hubert-de-rivière-du-loup': { lat: 47.8167, lng: -69.1500 },
  'saint-antonin': { lat: 47.7667, lng: -69.4833 },
  'saint-modeste': { lat: 47.8333, lng: -69.4000 },
  'rivière-du-loup': { lat: 47.8333, lng: -69.5333 },
  'notre-dame-du-portage': { lat: 47.7667, lng: -69.6167 },
  'cacouna': { lat: 47.9167, lng: -69.5000 },
  'l\'isle-verte': { lat: 48.0167, lng: -69.3333 },
  'saint-paul-de-la-croix': { lat: 47.9667, lng: -69.2667 },
  'saint-épiphane': { lat: 47.9000, lng: -69.3167 },
  'saint-françois-xavier-de-viger': { lat: 47.9167, lng: -69.2500 },
  'saint-arsène': { lat: 47.9500, lng: -69.3833 },
  'saint-clément': { lat: 47.9333, lng: -69.0833 },
  'saint-cyprien': { lat: 47.8833, lng: -69.0167 },
  'sainte-rita': { lat: 47.9667, lng: -68.9500 },
  'saint-jean-de-dieu': { lat: 48.0167, lng: -69.0500 },
  'saint-médard': { lat: 48.0833, lng: -68.8667 },
  'saint-guy': { lat: 48.0667, lng: -68.8167 },
  'saint-éloi': { lat: 48.0500, lng: -69.2167 },
  'trois-pistoles': { lat: 48.1167, lng: -69.1667 },
  'notre-dame-des-neiges': { lat: 48.1000, lng: -69.1833 },
  'saint-mathieu-de-rioux': { lat: 48.1833, lng: -68.9833 },
  'saint-simon': { lat: 48.2167, lng: -68.8667 },
  'saint-fabien': { lat: 48.2833, lng: -68.8667 },
  'saint-eugène-de-ladrière': { lat: 48.2833, lng: -68.7000 },
  'saint-valérien': { lat: 48.2833, lng: -68.6000 },
  'le bic': { lat: 48.3667, lng: -68.7000 },
  'rimouski': { lat: 48.4500, lng: -68.5333 },
  'saint-anaclet-de-lessard': { lat: 48.4833, lng: -68.4167 },
  'sainte-luce': { lat: 48.5500, lng: -68.3833 },
  'sainte-flavie': { lat: 48.6000, lng: -68.2333 },
  'mont-joli': { lat: 48.5833, lng: -68.1833 },
  'saint-joseph-de-lepage': { lat: 48.5500, lng: -68.1333 },
  'price': { lat: 48.6000, lng: -68.1333 },
  'saint-octave-de-métis': { lat: 48.6167, lng: -68.0833 },
  'grand-métis': { lat: 48.6333, lng: -68.1333 },
  'métis-sur-mer': { lat: 48.6667, lng: -68.0333 },
  'baie-des-sables': { lat: 48.7167, lng: -67.8833 },
  'saint-ulric': { lat: 48.7833, lng: -67.6833 },
  'matane': { lat: 48.8333, lng: -67.5333 },
  'sainte-félicité': { lat: 48.8833, lng: -67.3333 },
  'grosses-roches': { lat: 48.9333, lng: -67.1667 },
  'les méchins': { lat: 49.0000, lng: -66.9667 },
  'saint-jean-de-cherbourg': { lat: 48.9167, lng: -67.2000 },
  'saint-adelme': { lat: 48.8667, lng: -67.1000 },
  'saint-rené-de-matane': { lat: 48.7667, lng: -67.4000 },
  'sainte-paule': { lat: 48.7167, lng: -67.5333 },
  'saint-léandre': { lat: 48.7500, lng: -67.6333 },
  'saint-damase': { lat: 48.6833, lng: -67.7667 },
  'saint-noël': { lat: 48.6000, lng: -67.8667 },
  'saint-moïse': { lat: 48.5667, lng: -67.8667 },
  'la rédemption': { lat: 48.4500, lng: -67.9333 },
  'saint-cléophas': { lat: 48.4333, lng: -67.8333 },
  'val-brillant': { lat: 48.5333, lng: -67.5500 },
  'sayabec': { lat: 48.5667, lng: -67.6333 },
  'amqui': { lat: 48.4667, lng: -67.4333 },
  'saint-alexandre-des-lacs': { lat: 48.4833, lng: -67.3333 },
  'lac-au-saumon': { lat: 48.4167, lng: -67.3333 },
  'saint-tharcisius': { lat: 48.4000, lng: -67.2333 },
  'saint-vianney': { lat: 48.5000, lng: -67.2333 },
  'albertville': { lat: 48.3333, lng: -67.3667 },
  'causapscal': { lat: 48.3500, lng: -67.2167 },
  'sainte-florence': { lat: 48.2667, lng: -67.2333 },
  'sainte-marguerite-marie': { lat: 48.3167, lng: -67.0833 },
  'saint-zénon-du-lac-humqui': { lat: 48.4333, lng: -67.5500 },
  'saint-léon-le-grand': { lat: 48.3833, lng: -67.5000 },
  'sainte-irène': { lat: 48.4667, lng: -67.5667 },
  'espritsaint': { lat: 48.3167, lng: -68.5667 },
  'la trinité-des-monts': { lat: 48.2667, lng: -68.4667 },
  'saint-narcisse-de-rimouski': { lat: 48.3000, lng: -68.4167 },
  'saint-marcellin': { lat: 48.3333, lng: -68.2833 },
  'saint-gabriel-de-rimouski': { lat: 48.4333, lng: -68.1333 },
  'saint-donat': { lat: 48.5000, lng: -68.2500 },
  'sainte-angèle-de-mérici': { lat: 48.5500, lng: -68.1333 },
  'padoue': { lat: 48.5833, lng: -68.0333 },
  'saint-charles-garnier': { lat: 48.4000, lng: -68.0333 },
  'les hauteurs': { lat: 48.3667, lng: -68.1000 },
  'cap-chat': { lat: 49.0833, lng: -66.6833 },
  'sainte-anne-des-monts': { lat: 49.1333, lng: -66.4833 },
  'la martre': { lat: 49.2000, lng: -66.1667 },
  'marsoui': { lat: 49.2167, lng: -66.0667 },
  'rivière-à-claude': { lat: 49.2167, lng: -65.9000 },
  'mont-saint-pierre': { lat: 49.2167, lng: -65.8000 },
  'saint-maxime-du-mont-louis': { lat: 49.2333, lng: -65.7333 },
  'sainte-madeleine-de-la-rivière-madeleine': { lat: 49.2500, lng: -65.3167 },
  'grande-vallée': { lat: 49.2167, lng: -65.1333 },
  'petite-vallée': { lat: 49.2167, lng: -65.0333 },
  'cloridorme': { lat: 49.1833, lng: -64.8333 },
  'gaspé': { lat: 48.8333, lng: -64.4833 },
  'murdochville': { lat: 48.9500, lng: -65.5000 },
  'percé': { lat: 48.5167, lng: -64.2167 },
  'sainte-thérèse-de-gaspé': { lat: 48.4167, lng: -64.4167 },
  'grande-rivière': { lat: 48.4000, lng: -64.5000 },
  'chandler': { lat: 48.3500, lng: -64.6833 },
  'port-daniel-gascons': { lat: 48.1833, lng: -64.9667 },
  'shigawake': { lat: 48.1000, lng: -65.0833 },
  'saint-godefroi': { lat: 48.0667, lng: -65.1167 },
  'hope town': { lat: 48.0500, lng: -65.1833 },
  'hope': { lat: 48.0333, lng: -65.2000 },
  'paspébiac': { lat: 48.0333, lng: -65.2500 },
  'new carlisle': { lat: 48.0000, lng: -65.3333 },
  'bonaventure': { lat: 48.0500, lng: -65.4833 },
  'saint-siméon': { lat: 48.0667, lng: -65.5667 },
  'caplan': { lat: 48.1167, lng: -65.7333 },
  'new richmond': { lat: 48.1667, lng: -65.8667 },
  'cascapédia-saint-jules': { lat: 48.2000, lng: -65.9333 },
  'maria': { lat: 48.1667, lng: -65.9833 },
  'carleton-sur-mer': { lat: 48.1000, lng: -66.1333 },
  'nouvelle': { lat: 48.1333, lng: -66.3167 },
  'escuminac': { lat: 48.1000, lng: -66.4667 },
  'pointe-à-la-croix': { lat: 48.0167, lng: -66.7167 },
  'ristigouche-partie-sud-est': { lat: 48.0000, lng: -66.7833 },
  'matapédia': { lat: 47.9833, lng: -66.9333 },
  'saint-andré-de-restigouche': { lat: 48.0667, lng: -66.9167 },
  'saint-alexis-de-matapédia': { lat: 47.9667, lng: -67.0500 },
  'saint-françois-d\'assise': { lat: 48.0000, lng: -67.0833 },
  'l\'ascension-de-patapédia': { lat: 47.9833, lng: -67.2333 },
  'tadoussac': { lat: 48.1500, lng: -69.7167 },
  'sacré-coeur': { lat: 48.2333, lng: -69.8000 },
  'les bergeronnes': { lat: 48.2500, lng: -69.5500 },
  'les escoumins': { lat: 48.3500, lng: -69.4000 },
  'longue-rive': { lat: 48.5500, lng: -69.2500 },
  'portneuf-sur-mer': { lat: 48.6167, lng: -69.1000 },
  'forestville': { lat: 48.7333, lng: -69.0833 },
  'colombier': { lat: 48.8167, lng: -68.8833 },
  'betsiamites': { lat: 48.9333, lng: -68.6500 },
  'ragueneau': { lat: 49.0500, lng: -68.5500 },
  'chute-aux-outardes': { lat: 49.1167, lng: -68.4000 },
  'pointe-aux-outardes': { lat: 49.0500, lng: -68.4167 },
  'pointe-lebel': { lat: 49.1667, lng: -68.2000 },
  'baie-comeau': { lat: 49.2167, lng: -68.1500 },
  'franquelin': { lat: 49.2833, lng: -67.9000 },
  'godbout': { lat: 49.3167, lng: -67.6000 },
  'baie-trinité': { lat: 49.4167, lng: -67.3000 },
  'port-cartier': { lat: 50.0333, lng: -66.8667 },
  'sept-îles': { lat: 50.2000, lng: -66.3833 },
  'uashat': { lat: 50.2167, lng: -66.4000 },
  'maliotenam': { lat: 50.2167, lng: -66.2333 },
  'rivière-au-tonnerre': { lat: 50.2667, lng: -64.7833 },
  'mingan': { lat: 50.2833, lng: -64.0333 },
  'longue-pointe-de-mingan': { lat: 50.2667, lng: -64.1333 },
  'havre-saint-pierre': { lat: 50.2333, lng: -63.6000 },
  'baie-johan-beetz': { lat: 50.2833, lng: -62.8000 },
  'aguanish': { lat: 50.2167, lng: -62.0833 },
  'natashquan': { lat: 50.1833, lng: -61.8167 },
  'pointe-natashquan': { lat: 50.1333, lng: -61.8000 },
  'côte-nord-du-golfe-du-saint-laurent': { lat: 50.5000, lng: -59.5000 },
  'blanc-sablon': { lat: 51.4167, lng: -57.1333 },
  'bonne-espérance': { lat: 51.4000, lng: -57.6667 },
  'gros-mécatina': { lat: 50.8000, lng: -59.1000 },
  'fermont': { lat: 52.7833, lng: -67.0833 },
  'schefferville': { lat: 54.8000, lng: -66.8167 },
  'kawawachikamach': { lat: 54.8500, lng: -66.7667 },
  'l\'île-d\'anticosti': { lat: 49.5000, lng: -63.0000 },
  'port-menier': { lat: 49.8167, lng: -64.3500 },
  'les îles-de-la-madeleine': { lat: 47.3833, lng: -61.8667 },
  'grosse-île': { lat: 47.6333, lng: -61.5167 },
  'chibougamau': { lat: 49.9167, lng: -74.3667 },
  'chapais': { lat: 49.7833, lng: -74.8500 },
  'lebel-sur-quévillon': { lat: 49.0500, lng: -76.9667 },
  'matagami': { lat: 49.7500, lng: -77.6333 },
  'eeyou istchee baie-james': { lat: 52.0000, lng: -76.0000 },
  'chisasibi': { lat: 53.7833, lng: -78.9000 },
  'wemindji': { lat: 53.0000, lng: -78.8167 },
  'eastmain': { lat: 52.2333, lng: -78.5167 },
  'waskaganish': { lat: 51.4667, lng: -78.7500 },
  'nemaska': { lat: 51.5667, lng: -76.1333 },
  'waswanipi': { lat: 49.7333, lng: -75.9500 },
  'mistissini': { lat: 50.4167, lng: -73.8667 },
  'oujé-bougoumou': { lat: 49.9333, lng: -74.8167 },
  'whapmagoostui': { lat: 55.2833, lng: -77.7667 },
  'rouyn-noranda': { lat: 48.2333, lng: -79.0167 },
  'val-d\'or': { lat: 48.1000, lng: -77.7833 },
  'amos': { lat: 48.5667, lng: -78.1167 },
  'la sarre': { lat: 48.8000, lng: -79.2000 },
  'macamic': { lat: 48.7500, lng: -79.0500 },
  'palmarolle': { lat: 48.6667, lng: -79.2000 },
  'dupuy': { lat: 48.8667, lng: -79.3167 },
  'clerval': { lat: 48.8667, lng: -79.4167 },
  'normétal': { lat: 48.9833, lng: -79.3667 },
  'sainte-hélène-de-mancebourg': { lat: 48.7833, lng: -79.3333 },
  'gallichan': { lat: 48.6000, lng: -79.3000 },
  'roquemaure': { lat: 48.6000, lng: -79.3833 },
  'rapide-danseur': { lat: 48.5500, lng: -79.3000 },
  'taschereau': { lat: 48.6667, lng: -78.6833 },
  'authier': { lat: 48.7333, lng: -78.8500 },
  'authier-nord': { lat: 48.8333, lng: -78.8667 },
  'poularies': { lat: 48.6833, lng: -78.9833 },
  'chazel': { lat: 48.8333, lng: -79.0333 },
  'sainte-germaine-boulé': { lat: 48.6667, lng: -79.1000 },
  'saint-lambert': { lat: 48.9333, lng: -79.1667 },
  'clermont': { lat: 48.9667, lng: -79.2333 },
  'val-saint-gilles': { lat: 49.0167, lng: -79.2667 },
  'saint-félix-de-dalquier': { lat: 48.6000, lng: -78.0500 },
  'saint-dominique-du-rosaire': { lat: 48.7000, lng: -78.0167 },
  'berry': { lat: 48.8167, lng: -78.2333 },
  'trécesson': { lat: 48.6000, lng: -78.3833 },
  'launay': { lat: 48.6500, lng: -78.5333 },
  'sainte-gertrude-manneville': { lat: 48.5667, lng: -78.3667 },
  'preissac': { lat: 48.4000, lng: -78.3500 },
  'saint-mathieu-d\'harricana': { lat: 48.5000, lng: -78.1833 },
  'la motte': { lat: 48.3167, lng: -78.1167 },
  'saint-marc-de-figuery': { lat: 48.4333, lng: -78.0500 },
  'landrienne': { lat: 48.5500, lng: -77.9667 },
  'barraute': { lat: 48.4333, lng: -77.6333 },
  'la corne': { lat: 48.3500, lng: -77.8667 },
  'champneuf': { lat: 48.7333, lng: -77.5667 },
  'rochebaucourt': { lat: 48.6833, lng: -77.5000 },
  'la morandière': { lat: 48.6333, lng: -77.6500 },
  'belcourt': { lat: 48.4000, lng: -77.4833 },
  'senneterre': { lat: 48.3833, lng: -77.2333 },
  'malartic': { lat: 48.1333, lng: -78.1333 },
  'd\'alembert': { lat: 48.3833, lng: -79.0167 },
  'mont-brun': { lat: 48.3167, lng: -78.8333 },
  'cléricy': { lat: 48.3500, lng: -78.8333 },
  'destor': { lat: 48.4667, lng: -78.9167 },
  'mcwatters': { lat: 48.2167, lng: -78.9167 },
  'arnfield': { lat: 48.2000, lng: -79.2333 },
  'beaudry': { lat: 48.1333, lng: -79.0167 },
  'bellecombe': { lat: 48.0500, lng: -79.0833 },
  'montbeillard': { lat: 48.0333, lng: -79.2167 },
  'rollet': { lat: 47.9333, lng: -79.2333 },
  'cloutier': { lat: 47.9667, lng: -79.0833 },
  'évain': { lat: 48.2167, lng: -79.1000 },
  'cadillac': { lat: 48.2167, lng: -78.5000 },
  'lorrainville': { lat: 47.3500, lng: -79.3500 },
  'duhamel-ouest': { lat: 47.3667, lng: -79.4667 },
  'ville-marie': { lat: 47.3333, lng: -79.4333 },
  'saint-bruno-de-guigues': { lat: 47.4667, lng: -79.4333 },
  'laverlochère-angliers': { lat: 47.4167, lng: -79.3000 },
  'fugèreville': { lat: 47.4000, lng: -79.2000 },
  'latulipe-et-gaboury': { lat: 47.4167, lng: -79.0333 },
  'belleterre': { lat: 47.3833, lng: -78.7000 },
  'béarn': { lat: 47.3000, lng: -79.2333 },
  'saint-eugène-de-guigues': { lat: 47.4833, lng: -79.2833 },
  'notre-dame-du-nord': { lat: 47.6000, lng: -79.4833 },
  'nédelec': { lat: 47.6667, lng: -79.4167 },
  'rémigny': { lat: 47.7667, lng: -79.2333 },
  'guérin': { lat: 47.6167, lng: -79.2333 },
  'moffet': { lat: 47.5333, lng: -78.9667 },
  'laforce': { lat: 47.5333, lng: -78.8333 },
  'winneway': { lat: 47.6000, lng: -78.6000 },
  'kipawa': { lat: 46.7833, lng: -78.9833 },
  'témiscaming': { lat: 46.7167, lng: -79.1000 },
  'hunter\'s point': { lat: 46.9833, lng: -78.8000 },
  'wolf lake': { lat: 46.8333, lng: -78.7167 },
  'kebaowek': { lat: 46.7833, lng: -78.9667 },
  'timiskaming': { lat: 47.3167, lng: -79.4667 },
  'alma': { lat: 48.5500, lng: -71.6500 },
  'saguenay': { lat: 48.4167, lng: -71.0667 },
  'chicoutimi': { lat: 48.4333, lng: -71.0667 },
  'jonquière': { lat: 48.4167, lng: -71.2500 },
  'la baie': { lat: 48.3333, lng: -70.8833 },
  'laterrière': { lat: 48.3167, lng: -71.1333 },
  'canton-tremblay': { lat: 48.4833, lng: -71.0500 },
  'shipshaw': { lat: 48.4833, lng: -71.2000 },
  'lac-kénogami': { lat: 48.3667, lng: -71.3667 },
  'saint-honoré': { lat: 48.5333, lng: -71.0500 },
  'saint-david-de-falardeau': { lat: 48.6333, lng: -71.0833 },
  'sainte-rose-du-nord': { lat: 48.3833, lng: -70.5333 },
  'saint-fulgence': { lat: 48.4500, lng: -70.9000 },
  'saint-félix-d\'otis': { lat: 48.2833, lng: -70.6167 },
  'ferland-et-boilleau': { lat: 48.1833, lng: -70.8000 },
  'l\'anse-saint-jean': { lat: 48.2333, lng: -70.2000 },
  'rivière-éternité': { lat: 48.2833, lng: -70.3333 },
  'petit-saguenay': { lat: 48.2167, lng: -70.0667 },
  'saint-charles-de-bourget': { lat: 48.5000, lng: -71.4167 },
  'saint-ambroise': { lat: 48.5500, lng: -71.3167 },
  'bégin': { lat: 48.6833, lng: -71.3333 },
  'larouche': { lat: 48.4500, lng: -71.5333 },
  'saint-nazaire': { lat: 48.5833, lng: -71.5500 },
  'labrecque': { lat: 48.6667, lng: -71.5000 },
  'lamarches': { lat: 48.6833, lng: -71.4667 },
  'l\'ascension-de-notre-seigneur': { lat: 48.6833, lng: -71.6333 },
  'saint-henri-de-taillon': { lat: 48.6667, lng: -71.8000 },
  'sainte-monique': { lat: 48.7333, lng: -71.8500 },
  'saint-ludger-de-milot': { lat: 48.8333, lng: -71.7333 },
  'saint-bruno': { lat: 48.4667, lng: -71.6500 },
  'hébertville': { lat: 48.3833, lng: -71.6833 },
  'hébertville-station': { lat: 48.4333, lng: -71.6667 },
  'métabetchouan-lac-à-la-croix': { lat: 48.4333, lng: -71.8667 },
  'desbiens': { lat: 48.4167, lng: -71.9500 },
  'chambord': { lat: 48.4333, lng: -72.0667 },
  'saint-andré-du-lac-saint-jean': { lat: 48.3167, lng: -71.9667 },
  'saint-françois-de-sales': { lat: 48.3167, lng: -72.1667 },
  'lac-bouchette': { lat: 48.2500, lng: -72.1833 },
  'roberval': { lat: 48.5167, lng: -72.2333 },
  'sainte-hedwidge': { lat: 48.5167, lng: -72.3333 },
  'saint-prime': { lat: 48.5833, lng: -72.3333 },
  'saint-félicien': { lat: 48.6500, lng: -72.4500 },
  'la doré': { lat: 48.7000, lng: -72.6333 },
  'normandin': { lat: 48.8333, lng: -72.5333 },
  'saint-thomas-didyme': { lat: 48.9167, lng: -72.6667 },
  'saint-edmond-les-plaines': { lat: 48.9333, lng: -72.4667 },
  'girardville': { lat: 49.0000, lng: -72.5500 },
  'albanel': { lat: 48.8833, lng: -72.4167 },
  'dolbeau-mistassini': { lat: 48.8833, lng: -72.2333 },
  'sainte-jeanne-d\'arc': { lat: 48.8833, lng: -72.0833 },
  'péribonka': { lat: 48.7667, lng: -72.0500 },
  'sainte-élisabeth-de-proulx': { lat: 48.8667, lng: -72.0000 },
  'saint-stanislas': { lat: 48.9333, lng: -72.1333 },
  'notre-dame-de-lorette': { lat: 48.9500, lng: -72.2667 },
  'mashteuiatsh': { lat: 48.5667, lng: -72.2333 },
  'shawinigan': { lat: 46.5667, lng: -72.7500 },
  'grand-mère': { lat: 46.6167, lng: -72.6833 },
  'shawinigan-sud': { lat: 46.5333, lng: -72.7333 },
  'saint-georges-de-champlain': { lat: 46.6333, lng: -72.6500 },
  'lac-à-la-tortue': { lat: 46.6000, lng: -72.6167 },
  'saint-jean-des-piles': { lat: 46.6833, lng: -72.7333 },
  'saint-gérard-des-laurentides': { lat: 46.5833, lng: -72.8000 },
  'saint-boniface': { lat: 46.4833, lng: -72.8167 },
  'saint-étienne-des-grès': { lat: 46.4333, lng: -72.7667 },
  'charette': { lat: 46.4500, lng: -72.9167 },
  'saint-élie-de-caxton': { lat: 46.4833, lng: -72.9667 },
  'saint-mathieu-du-parc': { lat: 46.6000, lng: -72.9333 },
  'saint-roch-de-mékinac': { lat: 46.8167, lng: -72.7667 },
  'sainte-thècle': { lat: 46.8167, lng: -72.5000 },
  'saint-tite': { lat: 46.7333, lng: -72.5667 },
  'hérouxville': { lat: 46.6667, lng: -72.6000 },
  'grandes-piles': { lat: 46.6833, lng: -72.7167 },
  'saint-séverin': { lat: 46.6333, lng: -72.5333 },
  'saint-adelphe': { lat: 46.7333, lng: -72.4333 },
  'lac-aux-sables': { lat: 46.8667, lng: -72.4000 },
  'notre-dame-de-montauban': { lat: 46.9000, lng: -72.3333 },
  'trois-rives': { lat: 47.0000, lng: -72.6667 },
  'la tuque': { lat: 47.4333, lng: -72.7833 },
  'la bostonnais': { lat: 47.5167, lng: -72.6833 },
  'lac-édouard': { lat: 47.6500, lng: -72.2667 },
  'parent': { lat: 47.9167, lng: -74.6167 },
  'wemotaci': { lat: 47.9000, lng: -73.7833 },
  'obedjiwan': { lat: 48.6667, lng: -74.9333 },
  'coucoucache': { lat: 47.6667, lng: -73.0000 },
  'bécancour': { lat: 46.3333, lng: -72.4333 },
  'sainte-angèle-de-laval': { lat: 46.3333, lng: -72.5167 },
  'saint-grégoire': { lat: 46.2667, lng: -72.5167 },
  'gentilly': { lat: 46.4000, lng: -72.2667 },
  'sainte-gertrude': { lat: 46.3333, lng: -72.3500 },
  'précieux-sang': { lat: 46.3000, lng: -72.4000 },
  'saint-sylvère': { lat: 46.1833, lng: -72.2167 },
  'saint-pierre-les-becquets': { lat: 46.5000, lng: -72.2000 },
  'deschaillons-sur-saint-laurent': { lat: 46.5667, lng: -72.1000 },
  'parisville': { lat: 46.5333, lng: -72.0333 },
  'fortierville': { lat: 46.4667, lng: -72.0000 },
  'sainte-sophie-de-lévrard': { lat: 46.4333, lng: -72.1167 },
  'sainte-marie-de-blandford': { lat: 46.3333, lng: -72.1667 },
  'lemieux': { lat: 46.3000, lng: -72.0667 },
  'manseau': { lat: 46.3667, lng: -71.9667 },
  'sainte-françoise': { lat: 46.4167, lng: -71.9500 },
  'sainte-cécile-de-lévrard': { lat: 46.4333, lng: -72.0500 },
  'saint-samuel': { lat: 46.2667, lng: -72.2000 },
  'saint-valère': { lat: 46.1667, lng: -72.0667 },
  'saint-rosaire': { lat: 46.1333, lng: -72.1000 },
  'victoriaville': { lat: 46.0500, lng: -71.9667 },
  'arthabaska': { lat: 46.0333, lng: -71.9500 },
  'saint-christophe-d\'arthabaska': { lat: 46.0167, lng: -71.9333 },
  'warwick': { lat: 45.9500, lng: -71.9833 },
  'kingsey falls': { lat: 45.8500, lng: -72.0500 },
  'tingwick': { lat: 45.8833, lng: -71.9500 },
  'saint-rémi-de-tingwick': { lat: 45.8333, lng: -71.8667 },
  'saint-albert': { lat: 46.0000, lng: -72.0833 },
  'sainte-élisabeth-de-warwick': { lat: 45.9833, lng: -72.0833 },
  'sainte-séraphine': { lat: 45.9333, lng: -72.1167 },
  'sainte-clotilde-de-horton': { lat: 45.9833, lng: -72.2333 },
  'notre-dame-de-ham': { lat: 45.8667, lng: -71.8000 },
  'ham-nord': { lat: 45.9000, lng: -71.6500 },
  'saints-martyrs-canadiens': { lat: 45.8333, lng: -71.6167 },
  'saint-norbert-d\'arthabaska': { lat: 46.0667, lng: -71.8333 },
  'sainte-hélène-de-chester': { lat: 46.0333, lng: -71.7333 },
  'chesterville': { lat: 45.9667, lng: -71.7667 },
  'saint-louis-de-blandford': { lat: 46.2500, lng: -71.9500 },
  'princeville': { lat: 46.1667, lng: -71.8833 },
  'plessisville': { lat: 46.2167, lng: -71.7667 },
  'laurierville': { lat: 46.3333, lng: -71.7167 },
  'notre-dame-de-lourdes': { lat: 46.3167, lng: -71.8000 },
  'villeroy': { lat: 46.3833, lng: -71.8667 },
  'val-alain': { lat: 46.4167, lng: -71.7333 },
  'lyster': { lat: 46.3667, lng: -71.6000 },
  'sainte-sophie-d\'halifax': { lat: 46.1500, lng: -71.7000 },
  'saint-ferdinand': { lat: 46.1000, lng: -71.5667 },
  'saint-pierre-baptiste': { lat: 46.2000, lng: -71.6000 },
  'inverness': { lat: 46.2667, lng: -71.5167 }
};

// --- COMPOSANTS UTILITAIRES ---
const VerdictBadge = ({ verdict }) => {
  const configs = {
    'GOOD_DEAL': { label: 'Excellente Affaire', color: 'bg-emerald-500', icon: <Sparkles size={12}/> },
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

  if (!images || images.length === 0) {
    return (
      <div className="w-full h-full bg-slate-100 flex items-center justify-center text-slate-400">
        <Guitar size={48} className="opacity-20" />
      </div>
    );
  }

  const nextImage = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex((prev) => (prev + 1) % images.length);
  };

  const prevImage = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex((prev) => (prev - 1 + images.length) % images.length);
  };

  return (
    <div className="relative w-full h-full group">
      <img
        src={images[currentIndex]}
        className="w-full h-full object-cover transition-transform duration-700"
        alt={`${title} - ${currentIndex + 1}`}
      />
      
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
  );
};

// --- NOUVEAU COMPOSANT EXTRAIT ---
const DealCard = React.memo(({ deal, filterType, onRetry, onReject, onToggleFavorite }) => {
  return (
    <div className={`group bg-white rounded-[2rem] shadow-sm border border-slate-200 overflow-hidden flex flex-col md:flex-row hover:shadow-2xl hover:shadow-blue-500/5 transition-all duration-500 animate-in fade-in slide-in-from-bottom-4 ${deal.status === 'rejected' ? 'opacity-50' : ''}`}>
      {/* Image Section */}
      <div className="md:w-80 h-64 md:h-auto overflow-hidden relative">
        <ImageGallery images={deal.imageUrls || [deal.imageUrl]} title={deal.title} />
        <div className="absolute top-4 left-4 z-10">
          <VerdictBadge verdict={deal.aiAnalysis?.verdict} />
        </div>
        {/* Overlay gradient */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent pointer-events-none" />
      </div>

      {/* Content Section */}
      <div className="flex-1 p-6 md:p-8 flex flex-col">
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
            <p className="text-slate-600 text-sm font-medium italic leading-relaxed">
              "{deal.aiAnalysis?.reasoning || "Analyse de l'état et de la valeur en cours par l'intelligence artificielle..."}"
            </p>
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
        if (deal.aiAnalysis?.verdict === 'GOOD_DEAL') markerColor = '#10b981'; // Emerald
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
  const [scanConfig, setScanConfig] = useState({
      maxAds: 5, frequency: 60, location: 'montreal', distance: 60, minPrice: 0, maxPrice: 10000, searchQuery: "electric guitar"
  });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCleaning, setIsCleaning] = useState(false);
  
  // New City Form State
  const [newCityName, setNewCityName] = useState('');
  const [newCityId, setNewCityId] = useState('');

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
      await saveConfig({
        prompt: DEFAULT_PROMPT,
        verdictRules: DEFAULT_VERDICT_RULES,
        reasoningInstruction: DEFAULT_REASONING_INSTRUCTION
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
              {['ALL', 'FAVORITES', 'GOOD_DEAL', 'FAIR', 'BAD_DEAL', 'REJECTED', 'ERROR'].map((type) => (
                <button
                  key={type}
                  onClick={() => setFilterType(type)}
                  className={`px-4 py-2 rounded-2xl text-xs font-bold whitespace-nowrap transition-all ${filterType === type ? 'bg-blue-600 text-white shadow-md' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                >
                  {type === 'ALL' ? 'Toutes' : type === 'FAVORITES' ? 'Favoris' : type === 'GOOD_DEAL' ? 'Bonnes Affaires' : type === 'FAIR' ? 'Prix Juste' : type === 'BAD_DEAL' ? 'Trop Cher' : type === 'REJECTED' ? 'Rejetées' : 'Erreurs'}
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
          className="fixed inset-0 bg-black/80 z-50 flex flex-col items-center justify-center overflow-hidden animate-in fade-in backdrop-blur-sm"
          onClick={() => setSelectedDealFromMap(null)}
        >
          {/* Controls Bar */}
          <div 
            className="absolute top-6 z-50 flex items-center gap-4"
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
            className="relative transition-transform duration-200 ease-out origin-center" 
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