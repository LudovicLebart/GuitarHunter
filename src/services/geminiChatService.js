import { getGenerativeModel } from 'firebase/ai';
import { ai } from './firebase';

// Modèle par défaut si analysisConfig.expertModel n'est pas encore chargé — aligné sur
// GEMINI_MODELS["default_expert"] (config.py), le même modèle que le Tier 3 Expert Pro du
// pipeline d'analyse, pour une continuité de "personnalité"/capacité entre l'analyse
// automatique et la conversation.
export const DEFAULT_CHAT_MODEL = 'gemini-3.1-pro-preview';

const SYSTEM_INSTRUCTION = [
    "Tu es l'assistant conversationnel de Guitar Hunter AI, spécialisé dans l'évaluation de guitares,",
    "amplis, étuis et matériel musical d'occasion.",
    "L'utilisateur discute d'une annonce déjà analysée automatiquement (le contexte et l'analyse IA",
    "existante te sont fournis dans le premier message). Poursuis la conversation naturellement :",
    "réponds à ses questions, challenge ou affine l'analyse existante si les photos jointes",
    "suggèrent autre chose (déformation du manche, décollement de chevalet, corrosion, etc.),",
    "et reste concret et direct. Réponds en français.",
].join(' ');

// Construit le contexte texte (annonce + analyse IA déjà produite) injecté avant la première
// question de l'utilisateur. Les photos sont jointes séparément (voir buildDealImageParts) —
// pas besoin d'y faire référence par lien ici, contrairement à l'ancien prompt presse-papier.
export const buildDealContextText = (deal) => {
    const a = deal.aiAnalysis || {};
    const lines = [
        "Contexte de l'annonce (déjà analysée par Guitar Hunter AI) :",
        `Titre : ${deal.title || 'N/A'}`,
        `Prix demandé : ${deal.price != null ? `${deal.price}$` : 'N/A'}`,
    ];
    if (deal.location) lines.push(`Localisation : ${deal.location}`);
    if (deal.description) lines.push(`Description : ${deal.description}`);

    const specs = [
        a.brand && `Marque : ${a.brand}`,
        a.model_name && `Modèle : ${a.model_name}`,
        a.production_year && `Année : ${a.production_year}`,
        a.country_of_origin && `Pays : ${a.country_of_origin}`,
        a.color && `Couleur : ${a.color}`,
    ].filter(Boolean);
    if (specs.length) lines.push('', 'Identification IA :', ...specs);

    if (a.verdict) lines.push('', `Verdict IA : ${a.verdict}`);
    if (a.summary) lines.push(`Résumé IA : ${a.summary}`);
    if (a.estimated_value != null) lines.push(`Valeur estimée : ${a.estimated_value}$`);
    if (a.resale_potential != null) lines.push(`Potentiel de revente : ${a.resale_potential}$`);
    if (a.estimated_gross_margin != null) lines.push(`Marge brute estimée : ${a.estimated_gross_margin}$`);

    return lines.join('\n');
};

// Parts image en base64 (inlineData) — 2026-08-01, correctif : le backend Firebase AI Logic
// configuré ici est le Gemini Developer API (`GoogleAIBackend`), qui ne supporte PAS les URIs
// gs:///le File API via le SDK Firebase AI Logic (confirmé en test réel : erreur 400 "Referencing
// Google Cloud Storage files directly is not supported") — contrairement à Vertex AI, vérifié
// initialement mais qui ne s'applique pas au backend réellement configuré. `storageImageGsUris`
// (backend, 2026-07-31) reste en base pour une éventuelle migration future vers Vertex AI, mais
// n'est plus utilisé ici : chaque image est téléchargée depuis son URL HTTPS publique
// (`storageImageUrls`) puis encodée en base64 côté navigateur.
//
// Redimensionnement côté navigateur (2026-08-01) : les photos Marketplace peuvent être en haute
// résolution (plusieurs Mo chacune) ; envoyées telles quelles en base64 (×1.33 la taille), une
// annonce à 8-10 photos peut dépasser ce que la requête peut transporter de façon fiable,
// observé en test réel ("Failed to fetch" générique côté navigateur sur l'appel generateContent).
// Repasser par un canvas (max 1024px de long côté, JPEG 80%) reste léger tout en gardant assez de
// détail pour repérer un défaut visuel — même principe que `_download_and_optimize_image()` côté
// backend (PIL), simplement appliqué ici côté client.
const MAX_IMAGE_DIMENSION = 1024;
const JPEG_QUALITY = 0.8;

// Redimensionnement/compression partagé — utilisé aussi bien pour les photos de l'annonce
// (fetch depuis leur URL publique) que pour une photo jointe par l'utilisateur depuis le chat
// (2026-08-01, File venant directement d'un <input type="file">).
const blobToInlinePart = async (blob) => {
    const bitmap = await createImageBitmap(blob);
    const scale = Math.min(1, MAX_IMAGE_DIMENSION / Math.max(bitmap.width, bitmap.height));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.getContext('2d').drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();

    const dataUrl = canvas.toDataURL('image/jpeg', JPEG_QUALITY);
    return { inlineData: { data: dataUrl.split(',')[1], mimeType: 'image/jpeg' } };
};

const fetchImageAsInlinePart = async (url) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    return blobToInlinePart(blob);
};

// Photo(s) jointe(s) par l'utilisateur depuis le chat (prise sur place ou choisies dans sa
// galerie — plusieurs à la fois depuis 2026-08-22). Résilient par photo (même principe que
// buildDealImageParts ci-dessus) : un fichier corrompu/non décodable ne doit pas faire échouer
// tout l'envoi si les autres photos du même message sont valides.
export const filesToInlineParts = async (files) => {
    const parts = await Promise.all(files.map(async (file) => {
        try {
            return await blobToInlinePart(file);
        } catch (e) {
            console.error('Erreur préparation photo jointe:', file?.name, e);
            return null;
        }
    }));
    return parts.filter(Boolean);
};

export const buildDealImageParts = async (deal) => {
    const urls = (deal.storageImageUrls || deal.imageUrls || []).filter(Boolean);
    const parts = await Promise.all(urls.map(async (url) => {
        try {
            return await fetchImageAsInlinePart(url);
        } catch (e) {
            console.error('Erreur chargement image pour le chat:', url, e);
            return null;
        }
    }));
    return parts.filter(Boolean);
};

export const getDealChatModel = (modelName = DEFAULT_CHAT_MODEL) => {
    if (!ai) throw new Error("Firebase AI Logic n'est pas initialisé (voir src/services/firebase.js).");
    return getGenerativeModel(ai, {
        model: modelName,
        systemInstruction: SYSTEM_INSTRUCTION,
    });
};
