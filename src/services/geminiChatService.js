import { getGenerativeModel, Schema } from 'firebase/ai';
import { ai } from './firebase';
import { RESTORATION_CATEGORIES, RESTORATION_STATUS_LABELS } from '../constants/restorationPlan';
import { NEW_VERDICTS } from '../constants';

// Modèle par défaut si analysisConfig.expertModel n'est pas encore chargé — aligné sur
// GEMINI_MODELS["default_expert"] (config.py), le même modèle que le Tier 3 Expert Pro du
// pipeline d'analyse, pour une continuité de "personnalité"/capacité entre l'analyse
// automatique et la conversation.
export const DEFAULT_CHAT_MODEL = 'gemini-3.1-pro-preview';

// Filet de sécurité (2026-08-23, Plan 1 tokens) — la consigne de concision dans SYSTEM_INSTRUCTION
// est la règle de fond, ce plafond n'intervient qu'en cas de dérive (le modèle ignore la consigne
// sur un tour donné). Volontairement large : le système invite explicitement à développer sur
// demande ("raconte-moi l'histoire de cette guitare...") — un plafond trop bas (1024, valeur
// initiale corrigée en revue) tronquait en plein milieu de phrase une réponse détaillée pourtant
// légitime, et le texte tronqué est ce qui finit persisté en dur dans l'historique Firestore.
const MAX_OUTPUT_TOKENS = 4096;

const SYSTEM_INSTRUCTION = [
    "Tu es l'assistant conversationnel de Guitar Hunter AI, spécialisé dans l'évaluation de guitares,",
    "amplis, étuis et matériel musical d'occasion.",
    "L'utilisateur discute d'une annonce déjà analysée automatiquement (le contexte et l'analyse IA",
    "existante te sont fournis dans le premier message). Poursuis la conversation naturellement :",
    "réponds à ses questions, challenge ou affine l'analyse existante si les photos jointes",
    "suggèrent autre chose (déformation du manche, décollement de chevalet, corrosion, etc.),",
    "et reste concret et direct. Réponds en français.",
    "Sois concis par défaut : réponses courtes et claires, sans détailler ni développer sauf si",
    "l'utilisateur le demande explicitement (ex: \"raconte-moi l'histoire de cette guitare\",",
    "\"explique-moi ceci en détail\").",
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
    const itemRefs = buildRestorationItemRefs(items);
    const lines = itemRefs.map(({ item, ref }, index) => {
        const cost = item.status === 'done' ? (item.actualCost ?? item.estimatedCost) : item.estimatedCost;
        return `${index + 1}. [${RESTORATION_STATUS_LABELS[item.status] || item.status}] ${item.label}${cost != null ? ` (${cost}$)` : ''} [ref: ${ref}]`;
    });
    const doneCount = items.filter(i => i.status === 'done').length;
    const remaining = items
        .filter(i => i.status !== 'done' && i.status !== 'skipped')
        .reduce((sum, i) => sum + (i.estimatedCost || 0), 0);
    const spent = items
        .filter(i => i.status === 'done')
        .reduce((sum, i) => sum + (i.actualCost ?? i.estimatedCost ?? 0), 0);
    return [
        "Plan de restauration actuel de cette annonce (checklist tenue par l'utilisateur, mise à jour au fil de la conversation), dans l'ordre actuel :",
        ...lines,
        `Résumé : ${doneCount}/${items.length} terminées, reste ~${remaining}$ estimés, dépensé à date : ${spent}$.`,
        "Le [ref: ...] de chaque étape est son identifiant exact à recopier tel quel dans ordered_item_refs si l'utilisateur demande de réordonner — jamais le numéro affiché, qui ne sert qu'à la lecture.",
    ].join('\n');
};

// Identifiants courts et stables dérivés de l'id Firestore de chaque item — jamais l'id complet
// (superflu, alourdit inutilement le contexte) ni un numéro de position (change à chaque
// réordonnancement, donc inutilisable comme référence dans un tour suivant). Longueur étendue par
// paliers de 2 uniquement en cas de collision (plans avec beaucoup d'étapes) — 6 caractères
// suffisent dans l'immense majorité des cas.
const MIN_REF_LENGTH = 6;
export const buildRestorationItemRefs = (items) => {
    let length = MIN_REF_LENGTH;
    while (length < 20) {
        const refs = items.map(i => i.id.slice(0, length));
        if (new Set(refs).size === refs.length) break;
        length += 2;
    }
    return items.map(item => ({ item, ref: item.id.slice(0, length) }));
};

// Résout une proposition de réordonnancement (refs bruts renvoyés par Gemini) contre l'état
// RÉEL et courant du plan (`liveItems`) — jamais l'état capturé au moment du tour de chat, qui a
// pu changer entretemps (ajout/suppression manuelle, autre proposition appliquée). Utilisé à la
// fois pour l'aperçu affiché dans la carte de proposition (recalculé à chaque rendu) ET au moment
// de l'application (revalidé avec l'état alors courant) — c'est ce double usage qui garantit
// qu'aucun réordonnancement partiel/incohérent ne peut jamais être écrit, plutôt qu'un contrôle par
// horodatage (`updatedAt` d'un item est justement modifié par un réordonnancement, et sujet au
// décalage horloge client/serveur — écarté après revue).
export const resolveRestorationReorderProposal = (rawRefs, liveItems) => {
    if (!Array.isArray(rawRefs) || !liveItems?.length || rawRefs.length !== liveItems.length) {
        return { valid: false };
    }
    const itemRefs = buildRestorationItemRefs(liveItems);
    const refToItem = new Map(itemRefs.map(({ item, ref }) => [ref, item]));
    const seen = new Set();
    const orderedItems = [];
    for (const ref of rawRefs) {
        const item = refToItem.get(ref);
        if (!item || seen.has(item.id)) return { valid: false };
        seen.add(item.id);
        orderedItems.push(item);
    }
    if (seen.size !== liveItems.length) return { valid: false };
    return { valid: true, orderedItems, orderedItemIds: orderedItems.map(i => i.id) };
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

// Retourne `{parts, urls}` (jamais juste `parts`, 2026-08-23) — `urls` reste ALIGNÉ index-à-index
// avec `parts` même quand une photo échoue au chargement (filtrée en même temps que sa part, pas
// après coup) : useDealChat.js::sendMessage a besoin de l'URL d'origine de chaque part conservée
// pour poser son ref (`d-<hash>`, voir buildPhotoRefIndex) dans le placeholder persisté — un simple
// index recalculé après un `.filter(Boolean)` désaligné aurait pu associer le ref de la mauvaise
// photo dès qu'une seule échouait au chargement.
export const buildDealImageParts = async (deal) => {
    const urls = (deal.storageImageUrls || deal.imageUrls || []).filter(Boolean);
    const results = await Promise.all(urls.map(async (url) => {
        try {
            return { url, part: await fetchImageAsInlinePart(url) };
        } catch (e) {
            console.error('Erreur chargement image pour le chat:', url, e);
            return null;
        }
    }));
    const kept = results.filter(Boolean);
    return { parts: kept.map(r => r.part), urls: kept.map(r => r.url) };
};

// Refs courts et stables pour les photos (2026-08-23, Plan 1 tokens, Lot C/D) — même philosophie
// que buildRestorationItemRefs plus haut : jamais un index de position (`storageImageUrls` est
// réécrit intégralement côté backend à chaque ré-analyse — un index périmé résoudrait
// silencieusement vers la MAUVAISE photo, un ref périmé échoue proprement). Deux familles dans un
// même espace de noms préfixé, jamais confondues entre elles ni avec les refs du plan de
// restauration (slices hex nues, sans préfixe) :
// - `d-<hash>` : photo de l'annonce, hash du pathname de son URL Storage (stable même si l'URL
//   change de token de signature) — toujours disponible quel que soit l'état de la conversation,
//   jamais dépendante de ce qui est persisté dans l'historique du chat.
// - `c-<messageId6>-<partIndex>` : photo jointe par l'utilisateur en cours de conversation, encore
//   pleinement persistée en Firestore (le correctif du Lot B n'a élidé QUE les photos de
//   l'annonce à l'écriture, jamais celles-ci).
const REF_HASH_MIN_LENGTH = 6;

const fnv1aHash = (str) => {
    let hash = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
        hash ^= str.charCodeAt(i);
        hash = Math.imul(hash, 0x01000193);
    }
    return (hash >>> 0).toString(36);
};

const pathnameOf = (url) => {
    try { return new URL(url).pathname; } catch { return url; }
};

// Génère `length` caractères en enchaînant des hash SALÉS (`pathname#0`, `pathname#1`, ...) jusqu'à
// atteindre la longueur voulue — correctif (2026-08-23, trouvé en revue) : `fnv1aHash` seule
// renvoie une chaîne de longueur FIXE (≤7 caractères en base36 pour un hash 32 bits) ; la tronquer
// avec `.slice(0, length)` pour `length > 7` renvoyait systématiquement la même chaîne, rendant la
// boucle de retry sur collision (ci-dessous) inopérante au-delà de la première tentative — deux
// photos dont le hash colliderait sur les 6 premiers caractères auraient silencieusement partagé le
// même ref, la seconde écrasant la première dans l'index.
const hashPhotoRef = (pathname, length) => {
    let out = '';
    let salt = 0;
    while (out.length < length) {
        out += fnv1aHash(`${pathname}#${salt}`).padStart(7, '0');
        salt++;
    }
    return out.slice(0, length);
};

export const buildPhotoRefIndex = (deal, messages) => {
    const refToLocation = new Map();
    const locationToRef = new Map(); // clé: `deal:${url}` ou `chat:${messageId}:${partIndex}`

    const dealUrls = (deal?.storageImageUrls || deal?.imageUrls || []).filter(Boolean);
    dealUrls.forEach((url) => {
        let length = REF_HASH_MIN_LENGTH;
        let ref;
        do {
            ref = `d-${hashPhotoRef(pathnameOf(url), length)}`;
            length += 2;
        } while (refToLocation.has(ref) && refToLocation.get(ref).url !== url && length < 20);
        refToLocation.set(ref, { kind: 'deal', url });
        locationToRef.set(`deal:${url}`, ref);
    });

    (messages || []).forEach((message) => {
        if (message.role !== 'user') return;
        // Duplique volontairement la logique de rétrocompatibilité de
        // useDealChat.js::getAttachedImagePartIndices plutôt que de l'importer — ce module ne doit
        // jamais dépendre de useDealChat.js (import circulaire, c'est l'inverse aujourd'hui).
        const indices = message.attachedImagePartIndices
            ?? (message.attachedImagePartIndex != null ? [message.attachedImagePartIndex] : []);
        indices.forEach((partIndex) => {
            if (!message.parts?.[partIndex]?.inlineData) return; // déjà élidé ou absent
            const ref = `c-${(message.id || '').slice(0, 6)}-${partIndex}`;
            refToLocation.set(ref, { kind: 'chat', messageId: message.id, partIndex });
            locationToRef.set(`chat:${message.id}:${partIndex}`, ref);
        });
    });

    return { refToLocation, locationToRef };
};

// Résout des refs (venant d'un appel `request_photo_review`) en parts `inlineData` réelles —
// toujours contre l'index construit depuis l'état COURANT (deal + messages), jamais mis en cache,
// pour ne jamais servir une photo qui n'existe plus. `missing` couvre 3 cas distincts (ref inconnu,
// photo chat introuvable/déjà élidée par ailleurs, fetch Storage en échec) — jamais avalé
// silencieusement : le modèle doit savoir qu'il ne les a pas eues plutôt que de répondre comme s'il
// les avait vues.
export const resolvePhotoRefs = async (refs, photoRefIndex, messages) => {
    const parts = [];
    const missing = [];
    for (const ref of refs) {
        const location = photoRefIndex.refToLocation.get(ref);
        if (!location) { missing.push(ref); continue; }
        if (location.kind === 'chat') {
            const message = (messages || []).find(m => m.id === location.messageId);
            const inlineData = message?.parts?.[location.partIndex]?.inlineData;
            if (!inlineData) { missing.push(ref); continue; }
            parts.push({ inlineData });
        } else {
            try {
                parts.push(await fetchImageAsInlinePart(location.url));
            } catch (e) {
                console.error('Erreur récupération photo rappelée:', location.url, e);
                missing.push(ref);
            }
        }
    }
    return { parts, missing };
};

// Function calling (2026-08-22, Lot B ; réordonnancement ajouté 2026-08-23 après réévaluation du
// risque par Opus) — deux fonctions : l'AJOUT d'une étape, et le RÉORDONNANCEMENT complet de la
// checklist (jamais la modification/suppression d'une étape existante par id, retiré du périmètre
// après revue — id périmés jamais nettoyables une fois rejoués dans l'historique, risque d'écraser
// une édition manuelle faite entre-temps dans le panneau). Le réordonnancement porte toujours sur
// l'ORDRE COMPLET (jamais un delta/déplacement relatif) — plus simple à valider entièrement contre
// l'état courant (voir resolveRestorationReorderProposal) qu'une séquence de mouvements relatifs.
const RESTORATION_FUNCTION_DECLARATIONS = [
    {
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
    },
    {
        name: 'propose_restoration_reorder',
        description: "Propose un NOUVEL ORDRE COMPLET pour les étapes du plan de restauration, uniquement quand l'utilisateur le demande explicitement (ex: \"priorise le réglage avant le reste\", \"remets le cosmétique en dernier\"). Ne jamais appeler spontanément. Doit inclure TOUTES les étapes actuelles du plan, chacune une seule fois, en utilisant leur [ref: ...] exact tel que donné dans le contexte du plan.",
        parameters: Schema.object({
            properties: {
                ordered_item_refs: Schema.array({
                    items: Schema.string({ description: "Le [ref: ...] exact d'une étape, tel que fourni dans le contexte du plan." }),
                    description: "La liste COMPLÈTE des refs d'étapes, dans le nouvel ordre proposé.",
                }),
                justification: Schema.string({ description: 'Pourquoi ce nouvel ordre est proposé.' }),
            },
            optionalProperties: [],
        }),
    },
];

// Rappel de photo (2026-08-23, Plan 1 tokens, Lot D) — indépendante de propose_restoration_step/
// propose_restoration_reorder (jamais gatée sur `isPurchased`, voir getDealChatModel plus bas) :
// les vieilles photos jointes par l'utilisateur sont élidées de l'historique rejoué à chaque tour
// (voir useDealChat.js::elideOldChatPhotos) pour réduire le coût en tokens ; cette fonction permet
// à Gemini de les revoir explicitement, seulement les refs pertinentes, seulement quand il en a
// vraiment besoin — jamais un simple bouton "tout renvoyer".
const PHOTO_RECALL_FUNCTION_DECLARATIONS = [{
    name: 'request_photo_review',
    description: "Redemande à voir une ou plusieurs photos précises qui ne sont plus affichées dans la conversation (remplacées par un placeholder texte portant leur ref) OU une photo de l'annonce d'origine, quand tu as réellement besoin de les revoir pour répondre correctement — jamais par réflexe, jamais toutes les photos d'un coup si seules certaines sont pertinentes à la question posée.",
    parameters: Schema.object({
        properties: {
            photo_refs: Schema.array({
                items: Schema.string({ description: "Le ref exact d'une photo (ex: \"d-7f3a91\" ou \"c-a1b2c3-0\"), tel que donné dans le placeholder ou le contexte." }),
                description: 'Les refs des photos à revoir — seulement celles nécessaires, jamais une liste large "au cas où".',
            }),
            reason: Schema.string({ description: 'Ce que tu cherches à vérifier sur ces photos précises.' }),
        },
        optionalProperties: [],
    }),
}];

const PHOTO_RECALL_SYSTEM_INSTRUCTION_ADDENDUM = [
    "Certaines photos jointes plus tôt dans cette conversation ne sont plus affichées ici (remplacées",
    "par un texte '[Photo ... ref: ...]') pour alléger la conversation — leur contenu reste dans ce",
    "que tu as déjà dit à leur sujet. Si tu as VRAIMENT besoin de revoir une photo précise (pas juste",
    "t'y référer), appelle request_photo_review avec son ref exact — jamais spontanément, jamais",
    "plusieurs photos non pertinentes à la fois.",
].join(' ');

// Requalification d'annonce via le chat (2026-08-27, Lot 2 du plan CHAT_GALLERY_REQUALIFICATION_PLAN.md,
// implémenté après le Lot 1 galerie) — indépendante d'`isPurchased` (contrairement aux outils de
// restauration ci-dessous) : un désaccord factuel sur l'identification/le verdict peut survenir sur
// n'importe quelle annonce discutée, pas seulement celles achetées. L'application réelle patche
// directement `aiAnalysis` (voir `firestoreService.js::applyManualAnalysisOverrides`), pas de nouvel
// appel Gemini — une 1ère version passait par une ré-analyse complète (`retryDealAnalysis`), abandonnée
// le 2026-08-27 (2e revue Opus) : lente (repaie 1 à 3 appels Gemini déjà faits) et pas fiable (l'IA
// peut reconverger sur l'analyse d'origine au lieu de suivre la correction). Les champs sont déjà
// validés/bornés côté client (voir `validateDealRequalificationProposal` ci-dessous) avant même
// l'affichage du bouton Appliquer — aucune ré-inférence IA n'est nécessaire pour les écrire.
const VERDICT_ENUM = Object.keys(NEW_VERDICTS);
const FINISH_APPLICATION_ENUM = ['Peinture opaque', 'Vernis/Laque transparente', 'Teinture', 'Naturel/Brut', 'Inconnue'];
const FINISH_TEXTURE_ENUM = ['Brillant', 'Satiné/Soyeux', 'Mat', 'Inconnue'];

// Libellés affichés dans la carte de proposition (avant/après).
export const REQUALIFICATION_FIELD_LABELS = {
    verdict: 'Verdict',
    deal_score: 'Score Attractivité/Prix',
    authenticity_score: 'Score Fiabilité/Contrefaçon',
    condition_score: 'Score État',
    liquidity_score: 'Score Liquidité',
    restoration_interest_score: 'Score Intérêt de restauration',
    brand: 'Marque',
    model_name: 'Modèle',
    production_year: 'Année de production',
    country_of_origin: 'Pays de fabrication',
    color: 'Couleur',
    finish_application: "Type d'application de la finition",
    finish_texture: 'Brillance de la finition',
    neck_scale_length: "Longueur d'échelle du manche",
};

const REQUALIFICATION_FUNCTION_DECLARATIONS = [{
    name: 'propose_deal_requalification',
    description: "Propose une correction du verdict, des scores ou des caractéristiques identifiées de CETTE annonce, uniquement en cas de désaccord FACTUEL réel révélé par la conversation (ex: une photo jointe montre un défaut non vu par l'analyse initiale, une caractéristique mal identifiée, un verdict qui ne tient plus compte d'un élément discuté). N'inclus QUE les champs dont la valeur doit réellement changer, jamais un champ déjà correct. Jamais spontanément, jamais pour une simple question ou un avis sans fait nouveau.",
    parameters: Schema.object({
        properties: {
            verdict: Schema.enumString({ enum: VERDICT_ENUM, description: 'Nouveau verdict, si à corriger.' }),
            deal_score: Schema.number({ description: 'Nouveau score Attractivité/Prix, de 0 à 10, si à corriger.' }),
            authenticity_score: Schema.number({ description: 'Nouveau score Fiabilité/Contrefaçon, de 0 à 10, si à corriger.' }),
            condition_score: Schema.number({ description: 'Nouveau score État, de 0 à 10, si à corriger.' }),
            liquidity_score: Schema.number({ description: 'Nouveau score Liquidité, de 0 à 10, si à corriger.' }),
            restoration_interest_score: Schema.number({ description: 'Nouveau score Intérêt de restauration, de 0 à 10, si à corriger.' }),
            brand: Schema.string({ description: 'Nouvelle marque, si à corriger.' }),
            model_name: Schema.string({ description: 'Nouveau modèle, si à corriger.' }),
            production_year: Schema.string({ description: "Nouvelle année ou décennie de production (ex: \"2010s\", \"1994\"), si à corriger." }),
            country_of_origin: Schema.string({ description: 'Nouveau pays de fabrication, si à corriger.' }),
            color: Schema.string({ description: 'Nouvelle couleur, si à corriger.' }),
            finish_application: Schema.enumString({ enum: FINISH_APPLICATION_ENUM, description: "Nouveau type d'application de la finition, si à corriger." }),
            finish_texture: Schema.enumString({ enum: FINISH_TEXTURE_ENUM, description: 'Nouvelle brillance de la finition, si à corriger.' }),
            neck_scale_length: Schema.string({ description: "Nouvelle longueur d'échelle du manche (ex: 25.5\"), si à corriger." }),
            justification: Schema.string({ description: 'Pourquoi cette correction, en te basant sur ce qui a été dit dans la conversation.' }),
        },
        optionalProperties: [
            'verdict', 'deal_score', 'authenticity_score', 'condition_score', 'liquidity_score',
            'restoration_interest_score', 'brand', 'model_name', 'production_year', 'country_of_origin',
            'color', 'finish_application', 'finish_texture', 'neck_scale_length',
        ],
    }),
}];

const REQUALIFICATION_SYSTEM_INSTRUCTION_ADDENDUM = [
    "Cette annonce a déjà été analysée automatiquement (verdict, scores, identification donnés en",
    "contexte). Si la conversation révèle un désaccord FACTUEL réel avec cette analyse (une photo",
    "montre un défaut ou un détail non vu, une caractéristique mal identifiée), tu peux appeler",
    "propose_deal_requalification pour proposer une correction — jamais spontanément, jamais pour une",
    "simple question ou un avis sans fait nouveau. N'inclus dans l'appel QUE les champs dont la valeur",
    "doit changer. La correction n'est jamais appliquée automatiquement : l'utilisateur voit une carte",
    "avant/après et doit cliquer sur Appliquer — ne la re-propose pas si elle a déjà été traitée",
    "(appliquée ou ignorée), signalé le cas échéant dans le contexte.",
].join(' ');

// Valide/normalise les arguments bruts d'un appel `propose_deal_requalification` — même principe que
// validateRestorationStepProposal (Gemini peut halluciner une valeur hors énumération ou un score
// aberrant) : un champ invalide est silencieusement écarté plutôt que rendu avec un bouton Appliquer
// qui écrirait n'importe quoi. Retourne `null` si AUCUN champ valide ne subsiste (rien à proposer).
const SCORE_FIELDS = ['deal_score', 'authenticity_score', 'condition_score', 'liquidity_score', 'restoration_interest_score'];
const STRING_FIELDS = ['brand', 'model_name', 'production_year', 'country_of_origin', 'color', 'neck_scale_length'];

export const validateDealRequalificationProposal = (args) => {
    if (!args || typeof args !== 'object') return null;
    const fields = {};
    if (VERDICT_ENUM.includes(args.verdict)) fields.verdict = args.verdict;
    for (const key of SCORE_FIELDS) {
        const value = args[key];
        if (Number.isFinite(value) && value >= 0 && value <= 10) fields[key] = value;
    }
    for (const key of STRING_FIELDS) {
        const value = args[key];
        if (typeof value === 'string' && value.trim()) fields[key] = value.trim().slice(0, 100);
    }
    if (FINISH_APPLICATION_ENUM.includes(args.finish_application)) fields.finish_application = args.finish_application;
    if (FINISH_TEXTURE_ENUM.includes(args.finish_texture)) fields.finish_texture = args.finish_texture;
    if (!Object.keys(fields).length) return null;
    const justification = typeof args.justification === 'string' ? args.justification.trim().slice(0, 500) : '';
    return { fields, justification };
};

// Persona "luthier / vendeur référent" (2026-08-23, Plan 2) — actif dès `isPurchased`, pour TOUT
// message sur cette annonce (message tapé librement ou envoyé via un bouton de prompt prédéfini,
// aucune différence : le persona est porté par la session Gemini elle-même, pas par le contenu du
// message). Remplace l'ancienne posture générique par une identité double — restaurateur ET
// revendeur — cohérente avec ce que l'utilisateur fait réellement à ce stade (restaurer PUIS
// revendre), plutôt qu'un simple assistant qui répond à des questions ponctuelles.
const RESTORATION_PERSONA_ADDENDUM = [
    "Cette annonce a été achetée par l'utilisateur, qui restaure la guitare avant de la revendre.",
    "Dans ce contexte, adopte la posture d'un luthier-restaurateur expérimenté ET d'un vendeur",
    "référent qui connaît le marché de l'occasion — pas un assistant générique qui répond à des",
    "questions isolées. Concrètement : donne des avis tranchés et concrets (pas de \"ça dépend\" sans",
    "trancher quand tu as assez d'éléments), pense à l'ordre de faisabilité des étapes et signale",
    "explicitement quand une étape risque d'en abîmer une autre (ex: finition avant réglage du",
    "manche), et garde en tête l'impact sur la marge de revente (le prix d'achat et les coûts du plan",
    "de restauration te sont donnés en contexte) sans qu'on ait besoin de te le redemander à chaque",
    "fois. Tu peux terminer une réponse par UNE suggestion courte de prochaine étape logique quand",
    "c'est pertinent, mais jamais un tour de conversation entier consacré à ça, et jamais si la",
    "question posée n'appelle pas ce genre de suivi.",
].join(' ');

const RESTORATION_SYSTEM_INSTRUCTION_ADDENDUM = [
    RESTORATION_PERSONA_ADDENDUM,
    "Un plan de restauration structuré (checklist) est associé à cette annonce, dont l'état actuel",
    "t'est donné en contexte au fil de la conversation, avec un [ref: ...] par étape. Tu peux appeler",
    "propose_restoration_step pour proposer d'ajouter une nouvelle étape à cette checklist, mais",
    "uniquement quand la conversation fait émerger un défaut concret ou une tâche de restauration",
    "précise, jamais spontanément. Tu peux appeler propose_restoration_reorder pour proposer un",
    "nouvel ordre complet des étapes, mais UNIQUEMENT quand l'utilisateur le demande explicitement —",
    "jamais spontanément, jamais pour ajouter/retirer/modifier le contenu d'une étape — et toujours en",
    "reprenant TOUTES les étapes actuelles avec leur [ref: ...] exact, jamais leur numéro affiché. Ne",
    "propose jamais de modifier ou marquer terminée une étape déjà dans la checklist — l'utilisateur",
    "gère lui-même l'avancement dans son panneau ; contente-toi d'en discuter s'il te le demande.",
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
// conversation. `withPhotoRecall` (2026-08-23) : PAS gaté sur `isPurchased` — l'essentiel du gain
// d'élision de photos porte sur les annonces non achetées (la majorité des conversations), donc
// cette fonction doit rester disponible indépendamment du plan de restauration. Les deux jeux de
// tools/addenda se composent librement (aucun, l'un, l'autre, ou les deux) ; comportement du chat
// inchangé à zéro risque quand les deux sont `false`.
export const getDealChatModel = (modelName = DEFAULT_CHAT_MODEL, { withRestorationTools = false, withPhotoRecall = false, withRequalification = false } = {}) => {
    if (!ai) throw new Error("Firebase AI Logic n'est pas initialisé (voir src/services/firebase.js).");
    const functionDeclarations = [
        ...(withPhotoRecall ? PHOTO_RECALL_FUNCTION_DECLARATIONS : []),
        ...(withRestorationTools ? RESTORATION_FUNCTION_DECLARATIONS : []),
        ...(withRequalification ? REQUALIFICATION_FUNCTION_DECLARATIONS : []),
    ];
    const systemInstruction = [
        SYSTEM_INSTRUCTION,
        withPhotoRecall ? PHOTO_RECALL_SYSTEM_INSTRUCTION_ADDENDUM : null,
        withRestorationTools ? RESTORATION_SYSTEM_INSTRUCTION_ADDENDUM : null,
        withRequalification ? REQUALIFICATION_SYSTEM_INSTRUCTION_ADDENDUM : null,
    ].filter(Boolean).join(' ');
    return getGenerativeModel(ai, {
        model: modelName,
        systemInstruction,
        generationConfig: { maxOutputTokens: MAX_OUTPUT_TOKENS },
        ...(functionDeclarations.length ? { tools: [{ functionDeclarations }] } : {}),
    });
};
