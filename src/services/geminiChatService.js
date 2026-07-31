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

// Parts image gs:// (Cloud Storage for Firebase) — lues directement par Gemini côté serveur,
// sans téléchargement/encodage base64 côté client. Nécessite storageImageGsUris (backend,
// 2026-07-31) ; absent sur les annonces créées avant cette date (repli : pas de photo jointe).
export const buildDealImageParts = (deal) => {
    const gsUris = deal.storageImageGsUris || [];
    return gsUris.filter(Boolean).map(fileUri => ({
        fileData: { fileUri, mimeType: 'image/jpeg' },
    }));
};

export const getDealChatModel = (modelName = DEFAULT_CHAT_MODEL) => {
    if (!ai) throw new Error("Firebase AI Logic n'est pas initialisé (voir src/services/firebase.js).");
    return getGenerativeModel(ai, {
        model: modelName,
        systemInstruction: SYSTEM_INSTRUCTION,
    });
};
