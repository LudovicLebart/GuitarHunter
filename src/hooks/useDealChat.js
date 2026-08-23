import { useState, useEffect, useCallback, useRef } from 'react';
import {
    onDealChatUpdate, addDealChatMessage, addImageToDealGallery, markChatMessageAddedToGallery,
    addRestorationItem, markChatMessageRestorationProposalStatus,
} from '../services/firestoreService';
import {
    getDealChatModel, buildDealContextText, buildDealImageParts, filesToInlineParts,
    buildRestorationPlanContextText, validateRestorationStepProposal,
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

const MAX_RESTORATION_PROPOSALS_PER_TURN = 5;

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
    // Ce que `chatRef.current` porte RÉELLEMENT (tools attachés ou non) — comparé au statut Acheté
    // courant avant chaque envoi (voir sendMessage) ; tenu à jour par l'effet ci-dessous à chaque
    // nouveau message aussi, donc un rebuild dans sendMessage ne devrait déclencher que si aucun
    // message Firestore n'a encore fait passer ce ref par le statut courant (ex. juste après avoir
    // basculé "Acheté" sans qu'aucun nouveau message n'ait encore été échangé).
    const chatToolsRef = useRef(false);
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
                const model = getDealChatModel(modelName, { withRestorationTools });
                chatRef.current = model.startChat({ history: sanitizeHistory(msgs) });
                chatToolsRef.current = withRestorationTools;
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
        if (chatToolsRef.current !== withRestorationTools) {
            try {
                chatRef.current = getDealChatModel(modelName, { withRestorationTools }).startChat({ history: sanitizeHistory(messages) });
                chatToolsRef.current = withRestorationTools;
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
        let uploadedParts, dealImageParts;
        try {
            [uploadedParts, dealImageParts] = await Promise.all([
                files ? filesToInlineParts(files) : Promise.resolve([]),
                isFirstMessage ? buildDealImageParts(deal) : Promise.resolve([]),
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

        try {
            await addDealChatMessage(deal.id, 'user', parts, trimmed, user.uid, attachedImagePartIndices);
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
            } catch (sendError) {
                // Le rejet d'un modèle qui ne supporte pas le function calling arrive ICI (pas à
                // la construction du modèle) — on retente une fois sans tools depuis le même
                // historique assaini, sans re-persister le tour utilisateur déjà écrit ci-dessus
                // (sinon doublon cassant l'alternance user/model requise par sanitizeHistory).
                if (withRestorationTools && !toolsUnsupportedRef.current) {
                    console.error('Échec avec function calling actif, repli sans tools:', sendError);
                    toolsUnsupportedRef.current = true;
                    chatRef.current = getDealChatModel(modelName, { withRestorationTools: false }).startChat({ history: sanitizeHistory(messages) });
                    chatToolsRef.current = false;
                    result = await chatRef.current.sendMessage(parts);
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
            let responseText;
            let restorationProposals;
            if (calls.length) {
                // Répond à TOUS les appels de ce tour — l'API exige une functionResponse par
                // functionCall, un appariement incomplet risque un rejet du tour entier. Seul
                // l'AFFICHAGE (les propositions montrées à l'utilisateur) est plafonné, pas la
                // réponse à l'API : un tour à plus de 5 appels reste valide côté Gemini, juste
                // tronqué côté carte de proposition.
                restorationProposals = calls
                    .slice(0, MAX_RESTORATION_PROPOSALS_PER_TURN)
                    .map(call => validateRestorationStepProposal(call.args))
                    .filter(Boolean);
                const functionResponseParts = calls.map(call => ({
                    functionResponse: { name: call.name, response: { status: 'proposal_shown_to_user_pending_confirmation' } },
                }));
                const followUp = await chat.sendMessage(functionResponseParts);
                responseText = followUp.response.text()?.trim() || "J'ai préparé une proposition d'étape ci-dessous.";
            } else {
                responseText = result.response.text()?.trim() || "…";
            }

            await addDealChatMessage(
                deal.id, 'model', [{ text: responseText }], responseText, user.uid,
                undefined, restorationProposals?.length ? restorationProposals : undefined
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
        const itemId = await addRestorationItem(deal.id, user.uid, {
            label: proposal.label,
            category: proposal.category,
            estimatedCost: proposal.estimatedCost,
            notes: proposal.justification || null,
            source: 'ai',
            proposedByMessageId: message.id,
        });
        await markChatMessageRestorationProposalStatus(deal.id, message.id, index, 'applied', user.uid, itemId);
    }, [deal, user]);

    const dismissRestorationProposal = useCallback(async (message, index) => {
        if (!deal?.id || !user || getRestorationProposalState(message, index)?.status) return;
        await markChatMessageRestorationProposalStatus(deal.id, message.id, index, 'dismissed', user.uid);
    }, [deal, user]);

    return {
        messages, loading, sending, error, sendMessage, addPhotoToGallery,
        applyRestorationProposal, dismissRestorationProposal,
    };
};
