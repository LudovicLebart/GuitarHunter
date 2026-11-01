import { streamChatEvents } from './apiService';
import { declarationsToTools } from '../utils/claudeChat';
import { ClaudeChatSession } from '../utils/claudeSession';

// Câblage du chat sur Claude (2026-11-01) : la session (utils/claudeSession.js) appelle l'API (`POST /deals/{id}/chat/claude`,
// clé Anthropic côté serveur, usage enregistré par le serveur). Les outils (propositions d'étapes, rappel de photo,
// requalification) sont exécutés dans le navigateur, comme avec Gemini.

// Même signature que `getGenerativeModel` côté Gemini : `{ startChat({history}) }`. `config` = { systemInstruction, functionDeclarations }.
export const getClaudeChatModel = (modelName, { systemInstruction, functionDeclarations }) => ({
    startChat: ({ history = [] } = {}) => new ClaudeChatSession({
        modelName, systemInstruction, tools: declarationsToTools(functionDeclarations), history, streamEvents: streamChatEvents,
    }),
});
