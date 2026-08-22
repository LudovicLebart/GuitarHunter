import { useState, useEffect, useCallback, useRef } from 'react';
import { onDealChatUpdate, addDealChatMessage, addImageToDealGallery, markChatMessageAddedToGallery } from '../services/firestoreService';
import { getDealChatModel, buildDealContextText, buildDealImageParts, filesToInlineParts } from '../services/geminiChatService';
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

// Gère une session de chat Gemini (Firebase AI Logic) pour une annonce donnée. L'historique est
// la source de vérité Firestore (guitar_deals/{dealId}/chat) — la session Gemini en mémoire
// (chatRef) est reconstruite à chaque mise à jour pour permettre de reprendre après un rechargement
// de page, mais l'appel en cours utilise toujours la référence capturée avant l'écriture Firestore
// du tour utilisateur pour éviter toute course entre les deux.
export const useDealChat = (deal, user, modelName) => {
    const [messages, setMessages] = useState([]);
    const [loading, setLoading] = useState(true);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState(null);
    const chatRef = useRef(null);

    useEffect(() => {
        if (!deal?.id || !user) return;
        setLoading(true);
        const unsubscribe = onDealChatUpdate(deal.id, (msgs) => {
            setMessages(msgs);
            setLoading(false);
            try {
                const model = getDealChatModel(modelName);
                chatRef.current = model.startChat({ history: sanitizeHistory(msgs) });
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

        const firstMessageText = isFirstMessage
            ? (trimmed ? `${buildDealContextText(deal)}\n\n${trimmed}` : buildDealContextText(deal))
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
            const result = await chat.sendMessage(parts);
            const responseText = result.response.text();
            await addDealChatMessage(deal.id, 'model', [{ text: responseText }], responseText, user.uid);
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
    }, [deal, user, messages.length, sending]);

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

    return { messages, loading, sending, error, sendMessage, addPhotoToGallery };
};
