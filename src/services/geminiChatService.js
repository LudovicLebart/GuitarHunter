import { getGenerativeModel, Schema } from 'firebase/ai';
import { ai } from './firebase';
import { RESTORATION_CATEGORIES, RESTORATION_STATUS_LABELS } from '../constants/restorationPlan';

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

// Contexte du plan de restauration (2026-08-22, Lot B) — injecté dans `parts` (jamais affiché,
// voir displayText) à CHAQUE tour utilisateur tant que le plan n'est pas vide, pas seulement au
// premier message : le plan évolue au fil des sessions (ajouts manuels dans le panneau, étapes
// cochées), donc son état doit rester à jour pour que Gemini puisse répondre à "qu'est-ce qu'il
// reste avant que ce soit revendable" et éviter de reproposer une étape déjà là. `items` vient du
// hook useRestorationPlan (mêmes objets que le panneau, jamais un id à référencer ici : Lot B ne
// couvre que l'AJOUT d'étapes, jamais leur modification par l'IA — voir propose_restoration_step).
export const buildRestorationPlanContextText = (items) => {
    if (!items?.length) return null;
    const lines = items.map(item => {
        const cost = item.status === 'done' ? (item.actualCost ?? item.estimatedCost) : item.estimatedCost;
        return `- [${RESTORATION_STATUS_LABELS[item.status] || item.status}] ${item.label}${cost != null ? ` (${cost}$)` : ''}`;
    });
    const doneCount = items.filter(i => i.status === 'done').length;
    const remaining = items
        .filter(i => i.status !== 'done' && i.status !== 'skipped')
        .reduce((sum, i) => sum + (i.estimatedCost || 0), 0);
    const spent = items
        .filter(i => i.status === 'done')
        .reduce((sum, i) => sum + (i.actualCost ?? i.estimatedCost ?? 0), 0);
    return [
        "Plan de restauration actuel de cette annonce (checklist tenue par l'utilisateur, mise à jour au fil de la conversation) :",
        ...lines,
        `Résumé : ${doneCount}/${items.length} terminées, reste ~${remaining}$ estimés, dépensé à date : ${spent}$.`,
    ].join('\n');
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

// Function calling (2026-08-22, Lot B) — une seule fonction, volontairement limitée à l'AJOUT
// d'une étape. La mise à jour d'une étape existante par id a été retirée du périmètre après revue
// (id périmés jamais nettoyables une fois rejoués dans l'historique, risque d'écraser une édition
// manuelle faite entre-temps dans le panneau) — l'utilisateur modifie/supprime toujours lui-même
// dans RestorationPlanPanel.jsx, Gemini ne fait que proposer des ajouts.
const RESTORATION_FUNCTION_DECLARATIONS = [{
    name: 'propose_restoration_step',
    description: "Propose d'ajouter une NOUVELLE étape au plan de restauration de cette annonce. Ne sert jamais à modifier ou marquer terminée une étape existante. À utiliser uniquement quand la conversation fait émerger un défaut concret ou une tâche de restauration précise à faire, jamais spontanément ni à chaque tour.",
    parameters: Schema.object({
        properties: {
            label: Schema.string({ description: 'Description courte de l\'étape (ex: "Recoller le binding décollé").' }),
            category: Schema.enumString({ enum: RESTORATION_CATEGORIES, description: "Catégorie de l'étape." }),
            estimated_cost: Schema.number({ description: 'Coût estimé en dollars, si évaluable à ce stade. Omettre si inconnu — ne jamais deviner un chiffre arbitraire.' }),
            justification: Schema.string({ description: 'Pourquoi cette étape est proposée — résumé du constat fait dans la conversation.' }),
        },
        optionalProperties: ['estimated_cost'],
    }),
}];

const RESTORATION_SYSTEM_INSTRUCTION_ADDENDUM = [
    "Cette annonce a été achetée par l'utilisateur, qui restaure la guitare avant de la revendre — un",
    "plan de restauration structuré (checklist) lui est associé, dont l'état actuel t'est donné en",
    "contexte au fil de la conversation. Tu peux appeler propose_restoration_step pour proposer",
    "d'ajouter une nouvelle étape à cette checklist, mais uniquement quand la conversation fait",
    "émerger un défaut concret ou une tâche de restauration précise, jamais spontanément. Ne propose",
    "jamais de modifier ou marquer terminée une étape déjà dans la checklist — l'utilisateur gère",
    "lui-même l'avancement dans son panneau ; contente-toi d'en discuter s'il te le demande.",
].join(' ');

// Valide/normalise les arguments bruts d'un appel `propose_restoration_step` avant affichage —
// jamais seulement avant application : Gemini peut halluciner une catégorie hors liste ou un
// coût aberrant, une proposition invalide doit être silencieusement écartée plutôt que rendue
// avec un bouton Appliquer qui écrirait n'importe quoi.
export const validateRestorationStepProposal = (args) => {
    if (!args || typeof args !== 'object') return null;
    const label = typeof args.label === 'string' ? args.label.trim().slice(0, 200) : '';
    if (!label) return null;
    const category = RESTORATION_CATEGORIES.includes(args.category) ? args.category : 'autre';
    const estimatedCost = Number.isFinite(args.estimated_cost) && args.estimated_cost >= 0 && args.estimated_cost < 100000
        ? args.estimated_cost
        : null;
    const justification = typeof args.justification === 'string' ? args.justification.trim().slice(0, 500) : '';
    return { label, category, estimatedCost, justification };
};

// `withRestorationTools` (2026-08-22) : gaté par l'appelant sur `deal.isPurchased` (jamais ici) —
// voir useDealChat.js::sendMessage, qui reconstruit la session si ce statut change en cours de
// conversation. `tools`/l'addendum système ne sont ajoutés que dans ce cas, comportement du chat
// inchangé à zéro risque pour toute annonce non achetée.
export const getDealChatModel = (modelName = DEFAULT_CHAT_MODEL, { withRestorationTools = false } = {}) => {
    if (!ai) throw new Error("Firebase AI Logic n'est pas initialisé (voir src/services/firebase.js).");
    return getGenerativeModel(ai, {
        model: modelName,
        systemInstruction: withRestorationTools ? `${SYSTEM_INSTRUCTION} ${RESTORATION_SYSTEM_INSTRUCTION_ADDENDUM}` : SYSTEM_INSTRUCTION,
        ...(withRestorationTools ? { tools: [{ functionDeclarations: RESTORATION_FUNCTION_DECLARATIONS }] } : {}),
    });
};
