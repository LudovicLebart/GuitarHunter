import { useState, useEffect, useCallback, useRef } from 'react';
import { onDealChatUpdate, addDealChatMessage } from '../services/firestoreService';
import { getDealChatModel, buildDealContextText, buildDealImageParts, fileToInlinePart } from '../services/geminiChatService';

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

    // `imageFile` (optionnel, 2026-08-01) : photo jointe depuis le chat (prise sur place ou
    // choisie dans la galerie) — envoyer un message avec une image seule (sans texte) est permis.
    const sendMessage = useCallback(async (text, imageFile) => {
        const trimmed = (text || '').trim();
        if ((!trimmed && !imageFile) || !deal?.id || !user || sending || !chatRef.current) return;

        const chat = chatRef.current; // capturé avant toute écriture Firestore (voir note ci-dessus)
        setSending(true);
        setError(null);

        const isFirstMessage = messages.length === 0;

        // fileToInlinePart() peut échouer (fichier corrompu/non décodable) — contrairement à
        // buildDealImageParts() qui avale déjà ses propres erreurs par image. Sans ce try/catch,
        // une exception ici court-circuite le reste de la fonction et laisse `sending` bloqué à
        // `true` pour toujours (le seul `setSending(false)` atteignable est plus bas).
        let uploadedPart, dealImageParts;
        try {
            [uploadedPart, dealImageParts] = await Promise.all([
                imageFile ? fileToInlinePart(imageFile) : Promise.resolve(null),
                isFirstMessage ? buildDealImageParts(deal) : Promise.resolve([]),
            ]);
        } catch (e) {
            console.error('Erreur préparation de la photo jointe:', e);
            setError("Impossible de préparer la photo jointe. Réessaie ou envoie sans photo.");
            setSending(false);
            return;
        }

        const firstMessageText = isFirstMessage
            ? (trimmed ? `${buildDealContextText(deal)}\n\n${trimmed}` : buildDealContextText(deal))
            : trimmed;
        const parts = [
            ...(firstMessageText ? [{ text: firstMessageText }] : []),
            ...dealImageParts,
            ...(uploadedPart ? [uploadedPart] : []),
        ];

        // Référence l'index de la photo jointe dans `parts` plutôt que de dupliquer son base64
        // (uploadedPart, quand présent, est toujours ajouté en dernier ci-dessus) — évite de
        // stocker/retransmettre deux fois les mêmes données image par message.
        const attachedImagePartIndex = uploadedPart ? parts.length - 1 : undefined;

        try {
            await addDealChatMessage(deal.id, 'user', parts, trimmed, user.uid, attachedImagePartIndex);
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

    return { messages, loading, sending, error, sendMessage };
};
