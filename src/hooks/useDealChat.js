import { useState, useEffect, useCallback, useRef } from 'react';
import {
    onDealChatUpdate, addDealChatMessage, addImageToDealGallery, markChatMessageAddedToGallery,
    addRestorationItem, markChatMessageRestorationProposalStatus, reorderRestorationItems,
} from '../services/firestoreService';
import {
    getDealChatModel, buildDealContextText, buildDealImageParts, filesToInlineParts,
    buildRestorationPlanContextText, validateRestorationStepProposal, resolveRestorationReorderProposal,
    buildPhotoRefIndex, resolvePhotoRefs,
} from '../services/geminiChatService';
import { base64ToBlob, uploadChatPhotoToDealStorage } from '../services/storageService';

// Rétrocompatibilité (2026-08-22) — un message de chat écrit avant le support multi-photos ne
// porte que les champs singuliers `attachedImagePartIndex`/`addedToGalleryUrl`. Ces deux fonctions
// sont le SEUL endroit qui connaît l'équivalence avec les nouveaux champs pluriels
// (`attachedImagePartIndices`/`addedToGalleryUrls`) — réutilisées aussi bien par l'affichage
// (DealChatPanel) que par les gardes anti-double-ajout (ici et dans DealChatPanel), pour ne
// jamais les faire diverger (une des deux avait été oubliée lors du passage au multi-photos).
export const getAttachedImagePartIndices = (message) =>
    message.attachedImagePartIndices
        ?? (message.attachedImagePartIndex != null ? [message.attachedImagePartIndex] : []);

export const getAddedToGalleryUrl = (message, partIndex) =>
    message.addedToGalleryUrls?.[partIndex]
        ?? (message.attachedImagePartIndex === partIndex ? message.addedToGalleryUrl : undefined);

// État (appliquée/ignorée) d'une proposition de restauration portée par un message (2026-08-22,
// Lot B) — persisté sur le message (voir markChatMessageRestorationProposalStatus), pas en état
// React local, pour qu'un reload ne réactive jamais un bouton déjà cliqué.
export const getRestorationProposalState = (message, index) => message.restorationProposalStates?.[index];

// Reconstruit un historique garanti alterné (user, model, user, model, ...) à partir de la liste
// brute Firestore, qui peut contenir des tours 'user' isolés (appel Gemini jamais résolu — ex.
// écriture interrompue avant le correctif d'appariement systématique, ou deux écritures aux
// timestamps trop proches pour que `orderBy('createdAt')` reflète l'ordre réel). Ne garde que les
// paires strictement consécutives (user suivi immédiatement de model) ; tout tour 'user' isolé,
// où qu'il soit dans la liste, est ignoré plutôt que de casser l'appel à l'API.
const sanitizeHistory = (msgs) => {
    const history = [];
    for (let i = 0; i < msgs.length; i++) {
        if (msgs[i].role !== 'user') continue;
        const next = msgs[i + 1];
        if (next && next.role === 'model') {
            history.push({ role: 'user', parts: msgs[i].parts });
            history.push({ role: 'model', parts: next.parts });
            i++; // le tour 'model' vient d'être consommé
        }
    }
    return history;
};

const MAX_RESTORATION_ADD_PROPOSALS_PER_TURN = 5;
// Un seul réordonnancement affiché par tour — en proposer plusieurs dans le même tour n'a pas de
// sens produit (chacun porte déjà l'ordre COMPLET de la checklist, le second écraserait le premier).
const MAX_RESTORATION_REORDER_PROPOSALS_PER_TURN = 1;

// Extrait les propositions de restauration (ajout/réordonnancement) d'un tableau de function calls
// — factorisé (2026-08-23, Lot D) car désormais appelé depuis 3 chemins distincts dans sendMessage
// (tour normal, tour rejoué après rappel de photo, rappel de photo invalide) : jamais dupliquer
// cette logique pour ne pas risquer de la faire diverger entre les chemins.
const buildRestorationProposalsFromCalls = (calls) => {
    const addProposals = calls
        .filter(call => call.name === 'propose_restoration_step')
        .slice(0, MAX_RESTORATION_ADD_PROPOSALS_PER_TURN)
        .map(call => validateRestorationStepProposal(call.args))
        .filter(Boolean)
        .map(p => ({ type: 'add', ...p }));
    const reorderProposals = calls
        .filter(call => call.name === 'propose_restoration_reorder')
        .slice(0, MAX_RESTORATION_REORDER_PROPOSALS_PER_TURN)
        .map(call => {
            const refs = Array.isArray(call.args?.ordered_item_refs) ? call.args.ordered_item_refs.filter(r => typeof r === 'string') : null;
            if (!refs?.length) return null;
            const justification = typeof call.args.justification === 'string' ? call.args.justification.trim().slice(0, 500) : '';
            return { type: 'reorder', orderedItemRefs: refs, justification };
        })
        .filter(Boolean);
    return [...addProposals, ...reorderProposals];
};

// Budget en nombre d'images (pas en nombre de tours), 2026-08-23, Plan 1 tokens, Lot C — parcouru
// de la fin vers le début, granularité tour entier (jamais la moitié d'un tour élidée). Le tour le
// plus récent portant une image est TOUJOURS gardé même s'il dépasse le budget à lui seul.
const MAX_HISTORY_IMAGES = 6;
// Plafond du nombre de photos effectivement rappelées en un seul appel `request_photo_review`
// (2026-08-23, Lot D) — un modèle qui en redemande 10 d'un coup annulerait le gain de l'élision.
const MAX_RECALLED_PHOTOS_PER_TURN = 3;

// Élision non-mutante des VIEILLES photos jointes par l'utilisateur en cours de conversation
// (2026-08-23, Plan 1 tokens, Lot C) — ne porte JAMAIS sur les photos de l'annonce elles-mêmes :
// depuis le correctif du Lot B, celles-ci ne sont plus jamais persistées en `inlineData` dans le
// premier message, rien à élider de leur côté (toujours recomposées à la demande via
// `request_photo_review`, résolues directement depuis `deal.storageImageUrls`, jamais depuis
// l'historique du chat). `sanitizeHistory` pousse `parts` PAR RÉFÉRENCE aux objets du listener
// Firestore temps réel, réutilisés tels quels par `DealChatPanel`/`addPhotoToGallery` pour
// l'affichage des vignettes et le bouton "Ajouter à la galerie" — une élision qui muterait ces
// objets en place casserait silencieusement l'UI. Cette fonction ne mute jamais `msgs`, produit des
// objets/tableaux neufs, et remplace une part `inlineData` par une part `text` AU MÊME INDEX
// (jamais une part retirée) pour que les index déjà persistés (`attachedImagePartIndices`) restent
// valides.
const elideOldChatPhotos = (msgs, photoRefIndex) => {
    let budget = MAX_HISTORY_IMAGES;
    let mostRecentImageTurnKept = false;
    const result = new Array(msgs.length);
    for (let i = msgs.length - 1; i >= 0; i--) {
        const msg = msgs[i];
        const imageIndices = getAttachedImagePartIndices(msg).filter(idx => msg.parts?.[idx]?.inlineData);
        if (!imageIndices.length) { result[i] = msg; continue; }
        if (budget > 0 || !mostRecentImageTurnKept) {
            budget -= imageIndices.length;
            mostRecentImageTurnKept = true;
            result[i] = msg;
            continue;
        }
        result[i] = {
            ...msg,
            parts: msg.parts.map((part, partIndex) => {
                if (!imageIndices.includes(partIndex)) return part;
                const ref = photoRefIndex.locationToRef.get(`chat:${msg.id}:${partIndex}`);
                return {
                    text: ref
                        ? `[Photo jointe précédemment — non affichée ici pour alléger la conversation. ref: ${ref} — rappelle-la avec request_photo_review si tu as vraiment besoin de la revoir.]`
                        : "[Photo jointe précédemment — déjà décrite dans la conversation ci-dessus.]",
                };
            }),
        };
    }
    return result;
};

// Enrobe `sanitizeHistory` sans la modifier (sa logique d'appariement user/model est déjà
// éprouvée) — `elide` n'est activé que si le rappel de photo est réellement disponible côté modèle
// (élision ⇔ capacité de rappel : sinon le modèle serait rendu aveugle sans aucun moyen de
// compenser, voir sendMessage).
const buildApiHistory = (msgs, { elide, photoRefIndex }) =>
    sanitizeHistory(elide ? elideOldChatPhotos(msgs, photoRefIndex) : msgs);

// `chatToolsRef` (2026-08-23, Plan 1 tokens, Lot D) — cesse d'être un booléen : `withPhotoRecall`
// (jamais gaté sur `isPurchased`) et `withRestorationTools` (gaté sur `isPurchased`) varient
// indépendamment, un simple booléen raterait une transition où l'un change mais pas l'autre.
const toolsSignature = (withPhotoRecall, withRestorationTools) =>
    `${withPhotoRecall ? 'p' : '-'}${withRestorationTools ? 'r' : '-'}`;

// Heuristique (2026-08-23, Plan 1 tokens, Lot B) — décide si un échec de `chat.sendMessage()` avec
// tools actifs signale VRAIMENT que le modèle configuré ne supporte pas le function calling (auquel
// cas désactiver durablement, `toolsUnsupportedRef`), ou si c'est une erreur transitoire quelconque
// (réseau, 503, timeout) qui ne doit désactiver les tools que pour CE tour. Avant ce correctif,
// n'importe quelle erreur pendant un tour avec tools actifs rendait `toolsUnsupportedRef` collant
// pour le reste de la session (`useRef`, jamais remis à `false`) — bénin en soi, mais devient
// critique avec le rappel de photos (Lot D) : une simple coupure réseau éteindrait alors la
// capacité de Gemini à revoir des photos élidées pour le reste de la conversation. Best-effort —
// à ajuster si un cas réel révèle un texte d'erreur différent (jamais vérifiable en environnement
// de dev, sans accès Gemini/Firebase).
const looksLikeToolsUnsupportedError = (error) => {
    const haystack = `${error?.message || ''} ${error?.code || ''}`.toLowerCase();
    const mentionsTools = haystack.includes('function') || haystack.includes('tool');
    const mentionsRejection = haystack.includes('support') || haystack.includes('invalid') || haystack.includes('not allowed');
    return mentionsTools && mentionsRejection;
};

// Instrumentation temporaire (2026-08-23, Plan 1 tokens, Lot B) — pas de UI, juste la console, pour
// mesurer le vrai coût en tokens avant de juger de l'effet des optimisations suivantes (Lot C/D) au
// lieu de le supposer. `cachedContentTokenCount` reflète le caching implicite déjà appliqué par
// Gemini sur les préfixes stables (historique) — une partie du coût "rejoué à chaque tour" est déjà
// amortie automatiquement, à regarder avant de conclure sur le gain réel d'une élision.
const logTokenUsage = (label, response) => {
    const u = response?.usageMetadata;
    if (!u) return;
    console.log(`[tokens] ${label} — prompt=${u.promptTokenCount ?? '?'} cached=${u.cachedContentTokenCount ?? 0} réponse=${u.candidatesTokenCount ?? '?'} total=${u.totalTokenCount ?? '?'}`);
};

// Filet de sécurité Firestore (2026-08-23, Plan 1 tokens, Lot B) — limite dure de 1 Mo/document,
// jamais vérifiée jusqu'ici. Purement diagnostique (ne bloque rien) : le vrai correctif est de ne
// plus persister les photos de l'annonce en base64 (voir persistedParts dans sendMessage), ce seuil
// n'existe que pour repérer un futur cas qui y échapperait quand même (ex: beaucoup de grosses
// photos jointes par l'utilisateur lui-même, jamais élidées à l'écriture).
const FIRESTORE_DOC_SIZE_WARNING_BYTES = 900_000;

// Gère une session de chat Gemini (Firebase AI Logic) pour une annonce donnée. L'historique est
// la source de vérité Firestore (guitar_deals/{dealId}/chat) — la session Gemini en mémoire
// (chatRef) est reconstruite à chaque mise à jour pour permettre de reprendre après un rechargement
// de page, mais l'appel en cours utilise toujours la référence capturée avant l'écriture Firestore
// du tour utilisateur pour éviter toute course entre les deux.
//
// `restorationItems` (optionnel, 2026-08-22, Lot B) : items du plan de restauration (même
// tableau que `useRestorationPlan`, monté dans DealAnalysisModal.jsx — pas ici, ce hook n'écrit
// jamais dans la sous-collection lui-même hors application d'une proposition IA) — utilisé pour
// injecter le contexte du plan dans chaque tour tant que l'annonce est achetée.
export const useDealChat = (deal, user, modelName, restorationItems) => {
    const [messages, setMessages] = useState([]);
    const [loading, setLoading] = useState(true);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState(null);
    const chatRef = useRef(null);
    // Ce que `chatRef.current` porte RÉELLEMENT (signature `toolsSignature`, voir plus haut) —
    // comparé à la config voulue avant chaque envoi (voir sendMessage) ; tenu à jour par l'effet
    // ci-dessous à chaque nouveau message aussi, donc un rebuild dans sendMessage ne devrait
    // déclencher que si aucun message Firestore n'a encore fait passer ce ref par la config
    // courante (ex. juste après avoir basculé "Acheté" sans qu'aucun nouveau message n'ait encore
    // été échangé).
    const chatToolsRef = useRef('');
    // Toujours à jour (réaffecté à chaque rendu) — sans lui, le callback du listener Firestore
    // ci-dessous verrait le statut Acheté capturé au moment où l'effet a tourné pour la dernière
    // fois (déps `[deal?.id, user, modelName]`, jamais `isPurchased`), pas le statut réel au
    // moment où un nouveau message arrive.
    const dealRef = useRef(deal);
    dealRef.current = deal;
    // Un modèle qui ne supporte pas le function calling rejette l'appel à l'envoi, pas à la
    // construction (voir plus bas) — mémorisé pour ne pas repayer l'échec à chaque message une
    // fois détecté sur cette session.
    const toolsUnsupportedRef = useRef(false);

    useEffect(() => {
        if (!deal?.id || !user) return;
        setLoading(true);
        const unsubscribe = onDealChatUpdate(deal.id, (msgs) => {
            setMessages(msgs);
            setLoading(false);
            try {
                const withRestorationTools = !!dealRef.current?.isPurchased && !toolsUnsupportedRef.current;
                const withPhotoRecall = !toolsUnsupportedRef.current;
                const model = getDealChatModel(modelName, { withRestorationTools, withPhotoRecall });
                const photoRefIndex = buildPhotoRefIndex(dealRef.current, msgs);
                chatRef.current = model.startChat({ history: buildApiHistory(msgs, { elide: withPhotoRecall, photoRefIndex }) });
                chatToolsRef.current = toolsSignature(withPhotoRecall, withRestorationTools);
            } catch (e) {
                console.error('Erreur initialisation session Gemini:', e);
                setError(e.message);
            }
        }, (e) => { setError(e.message); setLoading(false); }, user.uid);
        return () => unsubscribe();
    }, [deal?.id, user, modelName]);

    // `imageFiles` (optionnel, 2026-08-01, tableau depuis 2026-08-22) : photo(s) jointe(s) depuis
    // le chat (prises sur place ou choisies dans la galerie) — envoyer un message avec des images
    // seules (sans texte) est permis.
    const sendMessage = useCallback(async (text, imageFiles) => {
        const trimmed = (text || '').trim();
        const files = imageFiles?.length ? imageFiles : null;
        if ((!trimmed && !files) || !deal?.id || !user || sending || !chatRef.current) return;

        const withRestorationTools = !!deal.isPurchased && !toolsUnsupportedRef.current;
        const withPhotoRecall = !toolsUnsupportedRef.current;
        // Index de refs construit une seule fois pour ce tour, réutilisé pour l'élision de
        // l'historique ET pour résoudre un éventuel appel `request_photo_review` plus bas — toujours
        // depuis l'état COURANT (`deal`/`messages`), jamais mis en cache entre deux tours.
        const photoRefIndex = buildPhotoRefIndex(deal, messages);
        if (chatToolsRef.current !== toolsSignature(withPhotoRecall, withRestorationTools)) {
            try {
                chatRef.current = getDealChatModel(modelName, { withRestorationTools, withPhotoRecall })
                    .startChat({ history: buildApiHistory(messages, { elide: withPhotoRecall, photoRefIndex }) });
                chatToolsRef.current = toolsSignature(withPhotoRecall, withRestorationTools);
            } catch (e) {
                console.error('Erreur reconstruction de session Gemini (tools):', e);
            }
        }
        const chat = chatRef.current; // capturé avant toute écriture Firestore (voir note ci-dessus)
        setSending(true);
        setError(null);

        const isFirstMessage = messages.length === 0;

        // filesToInlineParts() peut échouer (fichier corrompu/non décodable) — contrairement à
        // buildDealImageParts() qui avale déjà ses propres erreurs par image. Sans ce try/catch,
        // une exception ici court-circuite le reste de la fonction et laisse `sending` bloqué à
        // `true` pour toujours (le seul `setSending(false)` atteignable est plus bas).
        let uploadedParts, dealImages;
        try {
            [uploadedParts, dealImages] = await Promise.all([
                files ? filesToInlineParts(files) : Promise.resolve([]),
                isFirstMessage ? buildDealImageParts(deal) : Promise.resolve({ parts: [], urls: [] }),
            ]);
        } catch (e) {
            console.error('Erreur préparation des photos jointes:', e);
            setError("Impossible de préparer les photos jointes. Réessaie ou envoie sans photo.");
            setSending(false);
            return;
        }

        // Contexte invisible (dans `parts`, jamais `displayText`) injecté à CHAQUE tour tant que
        // l'annonce est achetée et le plan non vide — pas seulement au premier message : le plan
        // évolue au fil des sessions (voir buildRestorationPlanContextText).
        const restorationContextText = deal.isPurchased ? buildRestorationPlanContextText(restorationItems) : null;
        const contextBlocks = [
            isFirstMessage ? buildDealContextText(deal) : null,
            restorationContextText,
        ].filter(Boolean);

        const firstMessageText = contextBlocks.length
            ? [...contextBlocks, trimmed].filter(Boolean).join('\n\n')
            : trimmed;
        const dealImageParts = dealImages.parts;
        const parts = [
            ...(firstMessageText ? [{ text: firstMessageText }] : []),
            ...dealImageParts,
            ...uploadedParts,
        ];

        // Référence les index des photos jointes dans `parts` plutôt que de dupliquer leur base64
        // (uploadedParts, quand présentes, sont toujours ajoutées en dernier ci-dessus) — évite de
        // stocker/retransmettre deux fois les mêmes données image par message.
        const attachedImagePartIndices = uploadedParts.length
            ? Array.from({ length: uploadedParts.length }, (_, i) => parts.length - uploadedParts.length + i)
            : undefined;

        // Variante PERSISTÉE (2026-08-23, Plan 1 tokens, Lot B, étendue Lot D) — les photos de
        // l'annonce (dealImageParts, non vides seulement au premier message) ne sont jamais
        // dupliquées en base64 dans Firestore : reconstructibles à tout moment depuis
        // `deal.storageImageUrls`. Sans ce correctif, une annonce à beaucoup de photos (8-10 en
        // 1024px/JPEG 80%, encodées en base64) peut dépasser la limite Firestore de 1 Mo/document et
        // faire échouer l'écriture du tout premier message. L'appel à l'API ci-dessous continue
        // d'utiliser `parts` (les vraies images) — ce correctif ne change QUE ce qui est écrit en
        // base. Le placeholder porte le `ref` (`d-<hash>`, voir buildPhotoRefIndex) de chaque photo
        // — sans lui, un historique reconstruit plus tard n'aurait aucun moyen de dire à Gemini
        // quoi demander pour la revoir via `request_photo_review`. `dealImages.urls` reste ALIGNÉ
        // index-à-index avec `dealImageParts` même si une photo a échoué au chargement (filtrées
        // ensemble dans buildDealImageParts) — jamais un recalcul d'index séparé qui risquerait de
        // poser le ref de la mauvaise photo.
        const dealImageStart = firstMessageText ? 1 : 0;
        const persistedParts = dealImageParts.length
            ? parts.map((part, i) => {
                if (i < dealImageStart || i >= dealImageStart + dealImageParts.length) return part;
                const url = dealImages.urls[i - dealImageStart];
                const ref = photoRefIndex.locationToRef.get(`deal:${url}`);
                return {
                    text: `[Photo ${i - dealImageStart + 1}/${dealImageParts.length} de l'annonce d'origine — non dupliquée ici.${ref ? ` ref: ${ref} — rappelle-la avec request_photo_review si besoin.` : ' Déjà disponible dans la galerie de l\'annonce.'}]`,
                };
            })
            : parts;

        const persistedSize = JSON.stringify(persistedParts).length;
        if (persistedSize > FIRESTORE_DOC_SIZE_WARNING_BYTES) {
            console.warn(`Message de chat volumineux (${(persistedSize / 1024).toFixed(0)} Ko) — risque de dépassement de la limite Firestore (1 Mo/document).`);
        }

        try {
            await addDealChatMessage(deal.id, 'user', persistedParts, trimmed, user.uid, attachedImagePartIndices);
        } catch (e) {
            console.error('Erreur sauvegarde message utilisateur:', e);
            setError("Impossible d'envoyer le message.");
            setSending(false);
            return;
        }

        try {
            let result;
            try {
                result = await chat.sendMessage(parts);
                logTokenUsage('tour principal', result.response);
            } catch (sendError) {
                // Le rejet d'un modèle qui ne supporte pas le function calling arrive ICI (pas à
                // la construction du modèle) — on retente une fois sans tools depuis le même
                // historique assaini, sans re-persister le tour utilisateur déjà écrit ci-dessus
                // (sinon doublon cassant l'alternance user/model requise par sanitizeHistory).
                // Désactivation DURABLE (`toolsUnsupportedRef`, désactive withRestorationTools ET
                // withPhotoRecall pour le reste de la session) seulement si l'erreur ressemble
                // vraiment à un rejet du function calling (voir looksLikeToolsUnsupportedError) —
                // toute autre erreur (réseau, 503, timeout) ne fait un repli que pour CE tour, les
                // tools restent actifs pour les suivants (bug trouvé en revue : avant ce correctif,
                // n'importe quelle erreur transitoire éteignait les tools pour le reste de la
                // session, sans aucun signal).
                if (withRestorationTools || withPhotoRecall) {
                    const sticky = looksLikeToolsUnsupportedError(sendError);
                    console.error(`Échec avec function calling actif, repli sans tools ${sticky ? '(désactivés durablement — modèle sans support détecté)' : '(ponctuel, tools restent actifs pour les prochains tours)'}:`, sendError);
                    if (sticky) toolsUnsupportedRef.current = true;
                    chatRef.current = getDealChatModel(modelName, { withRestorationTools: false, withPhotoRecall: false })
                        .startChat({ history: buildApiHistory(messages, { elide: false, photoRefIndex }) });
                    chatToolsRef.current = toolsSignature(false, false);
                    result = await chatRef.current.sendMessage(parts);
                    logTokenUsage('tour principal (repli sans tools)', result.response);
                } else {
                    throw sendError;
                }
            }

            // Un tour function-call ne porte aucun texte (`.text()` renverrait '') — jamais
            // persister une part texte vide dans l'historique (rejouée telle quelle au prochain
            // `startChat({history})`, elle risquerait un rejet définitif de la conversation par
            // l'API). On renvoie donc une functionResponse factice dans la même session pour
            // obtenir un vrai texte de suite avant toute écriture Firestore.
            const calls = result.response.functionCalls?.() || [];
            const photoRecallCalls = calls.filter(call => call.name === 'request_photo_review');
            let responseText;
            let restorationProposals;
            let photoRecall;

            if (photoRecallCalls.length) {
                // Alternative C (revue Opus) — mixer functionResponse + inlineData dans le même
                // sendMessage() est IMPOSSIBLE côté SDK (AIError INVALID_CONTENT). On abandonne donc
                // ce résultat et on rejoue le MÊME tour utilisateur, augmenté des photos demandées,
                // sur une session fraîche reconstruite depuis l'historique d'AVANT ce tour — SANS le
                // tool de rappel (empêche structurellement un 2e rappel dans le même tour, la
                // fonction n'est simplement plus déclarée sur cette session).
                const requestedRefs = [...new Set(photoRecallCalls.flatMap(call =>
                    Array.isArray(call.args?.photo_refs) ? call.args.photo_refs.filter(r => typeof r === 'string') : []
                ))];
                const cappedRefs = requestedRefs.slice(0, MAX_RECALLED_PHOTOS_PER_TURN);
                const truncatedCount = requestedRefs.length - cappedRefs.length;
                const { parts: photoParts, missing } = await resolvePhotoRefs(cappedRefs, photoRefIndex, messages);

                if (photoParts.length) {
                    // Deux catégories distinctes, jamais mélangées dans une seule phrase (bug trouvé
                    // en revue — un texte ambigu risquait de faire confondre au modèle "à
                    // redemander plus tard" (plafonné ce tour-ci) et "n'existe pas" (réellement
                    // introuvable/irrécupérable).
                    const noteSegments = ['[Photos demandées ci-jointes.'];
                    if (missing.length) noteSegments.push(` Introuvables (référence invalide ou photo non récupérable, ne redemande pas celles-ci) : ${missing.join(', ')}.`);
                    if (truncatedCount > 0) noteSegments.push(` ${truncatedCount} référence(s) en plus du plafond de ${MAX_RECALLED_PHOTOS_PER_TURN}/tour n'ont pas été traitées cette fois — redemande-les séparément si tu en as toujours besoin.`);
                    noteSegments.push(']');
                    const noteLines = [noteSegments.join('')];
                    const replaySession = getDealChatModel(modelName, { withRestorationTools, withPhotoRecall: false })
                        .startChat({ history: buildApiHistory(messages, { elide: withPhotoRecall, photoRefIndex }) });
                    const replayResult = await replaySession.sendMessage([...parts, { text: noteLines.join('\n') }, ...photoParts]);
                    logTokenUsage('tour rejoué (photos rappelées)', replayResult.response);
                    chatRef.current = replaySession; // la session polluée par le functionCall orphelin est abandonnée
                    chatToolsRef.current = toolsSignature(false, withRestorationTools);
                    photoRecall = { refs: cappedRefs.filter(r => !missing.includes(r)), missing };

                    const replayCalls = replayResult.response.functionCalls?.() || [];
                    if (replayCalls.length) {
                        // Le tour rejoué peut lui-même proposer une étape/un réordonnancement (jamais
                        // un 2e rappel de photo, plus déclaré sur cette session) — traité normalement.
                        restorationProposals = buildRestorationProposalsFromCalls(replayCalls);
                        const functionResponseParts2 = replayCalls.map(call => ({
                            functionResponse: { name: call.name, response: { status: 'proposal_shown_to_user_pending_confirmation' } },
                        }));
                        const followUp2 = await replaySession.sendMessage(functionResponseParts2);
                        logTokenUsage('tour de suite (après rappel photo)', followUp2.response);
                        responseText = followUp2.response.text()?.trim() || "J'ai préparé une proposition ci-dessous.";
                    } else {
                        responseText = replayResult.response.text()?.trim() || "…";
                    }
                } else {
                    // Aucune ref valide/récupérable — pas de rejeu (coûterait une génération pour
                    // rien) : réponse via le chemin functionResponse classique avec un statut
                    // d'erreur explicite. Les éventuels autres appels du même tour (ex: une
                    // proposition de restauration mêlée au même tour) sont traités normalement.
                    restorationProposals = buildRestorationProposalsFromCalls(calls);
                    const functionResponseParts = calls.map(call => ({
                        functionResponse: {
                            name: call.name,
                            response: call.name === 'request_photo_review'
                                ? { status: 'error', message: `Aucune de ces références n'existe ou n'est récupérable (${missing.join(', ')}). Réponds avec ce que tu sais déjà, sans mentionner cette erreur technique.` }
                                : { status: 'proposal_shown_to_user_pending_confirmation' },
                        },
                    }));
                    const followUp = await chat.sendMessage(functionResponseParts);
                    logTokenUsage('tour de suite (rappel photo invalide)', followUp.response);
                    // Le modèle peut réagir à l'erreur en proposant une étape/un réordonnancement
                    // dans ce même tour de suite (bug trouvé en revue — ce chemin ignorait
                    // silencieusement ce cas, contrairement au chemin "rappel réussi" ci-dessus qui
                    // le traite déjà) — même filet : on répond à CES appels avant de considérer le
                    // tour terminé, sinon la proposition est perdue et la bulle persiste vide.
                    const followUpCalls = followUp.response.functionCalls?.() || [];
                    if (followUpCalls.length) {
                        restorationProposals = [...restorationProposals, ...buildRestorationProposalsFromCalls(followUpCalls)];
                        const functionResponseParts2 = followUpCalls.map(call => ({
                            functionResponse: { name: call.name, response: { status: 'proposal_shown_to_user_pending_confirmation' } },
                        }));
                        const followUp2 = await chat.sendMessage(functionResponseParts2);
                        logTokenUsage('tour de suite (après erreur rappel photo)', followUp2.response);
                        responseText = followUp2.response.text()?.trim() || "J'ai préparé une proposition ci-dessous.";
                    } else {
                        responseText = followUp.response.text()?.trim() || "…";
                    }
                }
            } else if (calls.length) {
                // Répond à TOUS les appels de ce tour — l'API exige une functionResponse par
                // functionCall, un appariement incomplet risque un rejet du tour entier. Seul
                // l'AFFICHAGE (les propositions montrées à l'utilisateur) est plafonné, pas la
                // réponse à l'API. La résolution complète des refs de réordonnancement contre
                // l'état courant (voir resolveRestorationReorderProposal) est différée au
                // rendu/à l'application — ici on ne valide que la forme.
                restorationProposals = buildRestorationProposalsFromCalls(calls);
                const functionResponseParts = calls.map(call => ({
                    functionResponse: { name: call.name, response: { status: 'proposal_shown_to_user_pending_confirmation' } },
                }));
                const followUp = await chat.sendMessage(functionResponseParts);
                logTokenUsage('tour de suite (functionResponse)', followUp.response);
                responseText = followUp.response.text()?.trim() || "J'ai préparé une proposition d'étape ci-dessous.";
            } else {
                responseText = result.response.text()?.trim() || "…";
            }

            await addDealChatMessage(
                deal.id, 'model', [{ text: responseText }], responseText, user.uid,
                undefined, restorationProposals?.length ? restorationProposals : undefined, photoRecall
            );
        } catch (e) {
            console.error('Erreur chat Gemini:', e);
            setError(e.message || "Erreur lors de l'envoi du message.");
            // Toujours apparier une réponse (même un placeholder d'erreur) au tour utilisateur
            // déjà sauvegardé — sinon l'alternance user/model requise par l'API casse tous les
            // envois suivants sur cette conversation (voir note d'auto-réparation ci-dessus).
            const errorText = "⚠️ Erreur lors de la génération de la réponse. Réessaie.";
            try {
                await addDealChatMessage(deal.id, 'model', [{ text: errorText }], errorText, user.uid);
            } catch (e2) {
                console.error("Erreur sauvegarde du message d'erreur:", e2);
            }
        } finally {
            setSending(false);
        }
    }, [deal, user, messages, sending, restorationItems, modelName]);

    // Ajoute à la galerie de l'annonce une photo jointe par l'utilisateur dans un message déjà
    // envoyé (2026-08-21, étendu 2026-08-22 pour cibler une photo précise parmi plusieurs par
    // message via `partIndex`) : upload Storage (voir storageService.js) puis écriture Firestore
    // (storageImageUrls + marquage de cette photo sur le message). Les erreurs remontent à
    // l'appelant (DealChatPanel), qui gère un état bouton par photo plutôt que le bandeau d'erreur
    // global du chat (une erreur d'upload photo n'est pas une erreur de conversation). No-op
    // silencieux si cette photo a déjà été ajoutée (garde anti-double-clic — via
    // `getAddedToGalleryUrl`, qui couvre aussi les messages pré-multi-photos ne portant que
    // l'ancien champ singulier `addedToGalleryUrl`, source de vérité persistée, stable même sur
    // un 2e client).
    const addPhotoToGallery = useCallback(async (message, partIndex) => {
        if (!deal?.id || !user || getAddedToGalleryUrl(message, partIndex)) return;
        const inlineData = message.parts?.[partIndex]?.inlineData;
        if (!inlineData) return;
        const blob = await base64ToBlob(inlineData.data, inlineData.mimeType);
        const url = await uploadChatPhotoToDealStorage(deal.id, blob, inlineData.mimeType);
        await addImageToDealGallery(deal.id, url, user.uid);
        await markChatMessageAddedToGallery(deal.id, message.id, partIndex, url, user.uid);
        return url;
    }, [deal, user]);

    // Applique/ignore une proposition d'étape de restauration (2026-08-22, Lot B) — même fonction
    // d'écriture (`addRestorationItem`) que l'ajout manuel dans RestorationPlanPanel.jsx, avec
    // `source: 'ai'` : un seul chemin d'écriture, jamais deux logiques parallèles à maintenir.
    // No-op silencieux si déjà traitée (garde anti-double-clic, même principe que la galerie).
    const applyRestorationProposal = useCallback(async (message, index) => {
        const proposal = message.restorationProposals?.[index];
        if (!deal?.id || !user || !proposal || getRestorationProposalState(message, index)?.status) return;

        if (proposal.type === 'reorder') {
            // Revalidé ICI contre l'état COURANT du plan (`restorationItems`, pas un instantané
            // capturé au tour de chat) — un ajout/suppression manuelle ou une autre proposition
            // appliquée entretemps rend les refs caducs ; jamais d'écriture partielle/incohérente.
            const resolved = resolveRestorationReorderProposal(proposal.orderedItemRefs, restorationItems || []);
            if (!resolved.valid) {
                throw new Error("Le plan a changé depuis cette proposition — redemande à Gemini de faire le point.");
            }
            await reorderRestorationItems(deal.id, user.uid, resolved.orderedItemIds);
            await markChatMessageRestorationProposalStatus(deal.id, message.id, index, 'applied', user.uid);
            return;
        }

        // `order` calculé sur `restorationItems` déjà en mémoire — même correctif que l'ajout
        // manuel (useRestorationPlan.js::addItem) : sans lui, l'item créé sans `order`
        // redéclenchait le rattrapage silencieux sur tout le plan, effaçant un ordre de
        // glisser-déposer déjà mis en place par l'utilisateur.
        const order = restorationItems?.length ? Math.max(...restorationItems.map(i => i.order ?? -1)) + 1 : 0;
        const itemId = await addRestorationItem(deal.id, user.uid, {
            label: proposal.label,
            category: proposal.category,
            estimatedCost: proposal.estimatedCost,
            notes: proposal.justification || null,
            source: 'ai',
            proposedByMessageId: message.id,
            order,
        });
        await markChatMessageRestorationProposalStatus(deal.id, message.id, index, 'applied', user.uid, itemId);
    }, [deal, user, restorationItems]);

    const dismissRestorationProposal = useCallback(async (message, index) => {
        if (!deal?.id || !user || getRestorationProposalState(message, index)?.status) return;
        await markChatMessageRestorationProposalStatus(deal.id, message.id, index, 'dismissed', user.uid);
    }, [deal, user]);

    return {
        messages, loading, sending, error, sendMessage, addPhotoToGallery,
        applyRestorationProposal, dismissRestorationProposal,
    };
};
