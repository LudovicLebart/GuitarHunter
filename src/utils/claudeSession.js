import { historyToMessages, partsToUserContent, wrapFinalResponse } from './claudeChat.js';

// Session de chat Claude (2026-11-01) : même interface que la session du SDK Gemini (`sendMessageStream(payload, opts)` →
// `{stream, response}`), pour que `useDealChat.js` fonctionne sans changement de logique. Pure : le transport (`streamEvents`, le
// flux SSE de l'API) est injecté, ce qui permet de la tester sans réseau (voir claudeSession.test.js). Câblage réel :
// services/claudeChatService.js.
export class ClaudeChatSession {
    constructor({ modelName, systemInstruction, tools, history, streamEvents }) {
        this.modelName = modelName;
        this.systemInstruction = systemInstruction;
        this.tools = tools;
        this.streamEvents = streamEvents;
        this.messages = historyToMessages(history);
        this.pendingToolUses = []; // appels d'outils du dernier tour, en attente de leur functionResponse
    }

    // `opts` : { signal, timeout } comme le SDK, plus { dealId, action } fournis par useDealChat (le SDK Gemini n'en a pas besoin).
    async sendMessageStream(payload, { signal, timeout, dealId, action } = {}) {
        if (!dealId) throw new Error('claudeChatService: dealId manquant.');
        const content = partsToUserContent(payload, this.pendingToolUses);
        if (!content.length) throw new Error('claudeChatService: message sans contenu.');
        const turnMessages = [...this.messages, { role: 'user', content }];

        const controller = new AbortController();
        if (signal) {
            if (signal.aborted) controller.abort(signal.reason);
            else signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true });
        }
        const timer = timeout
            ? setTimeout(() => controller.abort(new Error(`Délai dépassé (timeout ${Math.round(timeout / 1000)} s)`)), timeout)
            : null;

        let resolveFinal;
        let rejectFinal;
        const response = new Promise((resolve, reject) => { resolveFinal = resolve; rejectFinal = reject; });
        response.catch(() => { /* l'erreur remonte déjà par le flux ; évite un « unhandled rejection » si seul le flux est lu */ });

        const session = this;
        const body = {
            model: this.modelName, system: this.systemInstruction, tools: this.tools, messages: turnMessages,
            action: action || 'chat_turn',
        };
        async function* events() {
            try {
                let final = null;
                for await (const event of session.streamEvents(`/deals/${dealId}/chat/claude`, body, { signal: controller.signal })) {
                    if (event.type === 'text') {
                        yield { text: () => event.delta };
                    } else if (event.type === 'final') {
                        final = event;
                    } else if (event.type === 'error') {
                        const error = new Error(event.message || 'Erreur du serveur de chat');
                        error.customErrorData = { status: event.status || 500 };
                        throw error;
                    }
                }
                if (!final) throw new Error('network error : flux interrompu avant la réponse finale');
                if (final.stop_reason === 'refusal') throw new Error('Le modèle a refusé de répondre à cette demande.');
                // Tour réussi : la session retient la conversation, y compris les blocs d'outil et de réflexion de ce tour
                // (à renvoyer tels quels avec le tool_result qui suit). Un tour échoué ne change rien à la session.
                session.messages = [...turnMessages, { role: 'assistant', content: final.content }];
                session.pendingToolUses = final.content.filter((b) => b.type === 'tool_use').map((b) => ({ id: b.id, name: b.name }));
                resolveFinal(wrapFinalResponse(final));
            } catch (error) {
                rejectFinal(error);
                throw error;
            } finally {
                if (timer) clearTimeout(timer);
                // Flux terminé OU abandonné par le lecteur : la requête est coupée, donc le serveur arrête de générer (et de facturer).
                controller.abort();
            }
        }
        return { stream: events(), response };
    }
}
