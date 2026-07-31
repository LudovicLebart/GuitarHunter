import { useState, useEffect, useCallback, useRef } from 'react';
import { onDealChatUpdate, addDealChatMessage } from '../services/firestoreService';
import { getDealChatModel, buildDealContextText, buildDealImageParts } from '../services/geminiChatService';

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
                // Auto-réparation (2026-08-01) : des échanges dont l'appel Gemini a échoué avant ce
                // correctif (ex: App Check mal configuré) ont pu laisser PLUSIEURS tours 'user'
                // consécutifs sans réponse en Firestore (une nouvelle tentative pendant que le bug
                // était encore présent = un nouveau tour 'user' non apparié à chaque fois). L'API
                // exige une alternance stricte user/model — on retire donc TOUTE la chaîne de tours
                // 'user' finaux non appariés de l'historique renvoyé à l'IA (toujours affichés dans
                // l'UI via `messages`, qui lit Firestore indépendamment).
                let history = msgs.map(m => ({ role: m.role, parts: m.parts }));
                while (history.length > 0 && history[history.length - 1].role === 'user') {
                    history = history.slice(0, -1);
                }
                chatRef.current = model.startChat({ history });
            } catch (e) {
                console.error('Erreur initialisation session Gemini:', e);
                setError(e.message);
            }
        }, (e) => { setError(e.message); setLoading(false); }, user.uid);
        return () => unsubscribe();
    }, [deal?.id, user, modelName]);

    const sendMessage = useCallback(async (text) => {
        const trimmed = text.trim();
        if (!trimmed || !deal?.id || !user || sending || !chatRef.current) return;

        const chat = chatRef.current; // capturé avant toute écriture Firestore (voir note ci-dessus)
        setSending(true);
        setError(null);

        const isFirstMessage = messages.length === 0;
        const parts = isFirstMessage
            ? [{ text: `${buildDealContextText(deal)}\n\n${trimmed}` }, ...buildDealImageParts(deal)]
            : [{ text: trimmed }];

        try {
            await addDealChatMessage(deal.id, 'user', parts, trimmed, user.uid);
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
