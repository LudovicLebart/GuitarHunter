// Conversion entre le format « parts » de Gemini (celui du chat et de l'historique persisté) et le format « messages » d'Anthropic,
// plus l'analyse du flux SSE de `POST /deals/{id}/chat/claude`. Fonctions PURES (aucune dépendance Firebase/React), testées par
// `claudeChat.test.js`. L'adaptateur de session qui les utilise est dans `services/claudeChatService.js`.

export const isClaudeModel = (name) => String(name || '').startsWith('claude');

// Modèles proposés par le réglage `analysisConfig.chatModel` (Opus n'y figure pas : il n'est consulté qu'à la demande).
export const CHAT_MODEL_OPTIONS = [
    { value: 'claude-sonnet-5-5', label: 'Claude Sonnet 5.5 (défaut)' },
    { value: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro (secours)' },
];

// Schéma Gemini (`Schema.object(...)` de firebase/ai, sérialisé par son `toJSON`) → JSON Schema d'Anthropic. Les types y sont déjà
// en minuscules ; seul `nullable: false`/les clés vides sont retirés (rejetés ou inutiles côté Anthropic).
export const schemaToJsonSchema = (schema) => {
    const clean = (node) => {
        if (Array.isArray(node)) return node.map(clean);
        if (node && typeof node === 'object') {
            const out = {};
            for (const [key, value] of Object.entries(node)) {
                if (key === 'nullable' && value === false) continue;
                out[key] = clean(value);
            }
            return out;
        }
        return node;
    };
    return clean(JSON.parse(JSON.stringify(schema)));
};

export const declarationsToTools = (functionDeclarations = []) => functionDeclarations.map((decl) => ({
    name: decl.name,
    description: decl.description || '',
    input_schema: schemaToJsonSchema(decl.parameters || { type: 'object', properties: {} }),
}));

const partToBlock = (part) => {
    // Anthropic refuse un bloc texte vide ou fait d'espaces : écarté ici (le serveur le refait par sécurité).
    if (part?.text !== undefined && String(part.text).trim() !== '') return { type: 'text', text: String(part.text) };
    if (part?.inlineData?.data) {
        return { type: 'image', source: { type: 'base64', media_type: part.inlineData.mimeType || 'image/jpeg', data: part.inlineData.data } };
    }
    return null; // `fileData` (gs://) n'est jamais produit par le chat actuel ; une part vide est ignorée
};

// Historique persisté (`[{role: 'user'|'model', parts}]`, déjà alterné par sanitizeHistory) → messages Anthropic.
export const historyToMessages = (history = []) => history
    .map((turn) => ({
        role: turn.role === 'model' ? 'assistant' : 'user',
        content: (turn.parts || []).map(partToBlock).filter(Boolean),
    }))
    .filter((msg) => msg.content.length > 0);

// Parts d'un envoi → blocs d'un message `user`. Les `functionResponse` deviennent des `tool_result` appariés, dans l'ordre, aux
// `tool_use` du tour précédent (`pendingToolUses`, de même nom) ; ils passent AVANT tout autre bloc (exigence d'Anthropic).
export const partsToUserContent = (parts, pendingToolUses = []) => {
    const list = Array.isArray(parts) ? parts : [{ text: String(parts) }];
    const pending = [...pendingToolUses];
    const results = [];
    const others = [];
    for (const part of list) {
        if (part?.functionResponse) {
            const at = pending.findIndex((use) => use.name === part.functionResponse.name);
            const use = at >= 0 ? pending.splice(at, 1)[0] : pending.shift();
            if (!use) continue; // réponse sans appel correspondant : ignorée plutôt que d'envoyer un tool_result orphelin
            results.push({ type: 'tool_result', tool_use_id: use.id, content: JSON.stringify(part.functionResponse.response ?? {}) });
        } else {
            const block = partToBlock(part);
            if (block) others.push(block);
        }
    }
    return [...results, ...others];
};

// Réponse finale du serveur → objet qui a la forme que useDealChat lit sur une réponse du SDK Gemini.
export const wrapFinalResponse = (final) => {
    const content = final?.content || [];
    const usage = final?.usage || {};
    const promptTokens = (usage.input || 0) + (usage.cache_read || 0) + (usage.cache_write || 0);
    return {
        text: () => content.filter((b) => b.type === 'text').map((b) => b.text).join(''),
        functionCalls: () => content.filter((b) => b.type === 'tool_use').map((b) => ({ name: b.name, args: b.input || {}, id: b.id })),
        usageMetadata: {
            promptTokenCount: promptTokens,
            cachedContentTokenCount: usage.cache_read || 0,
            candidatesTokenCount: usage.output || 0,
            thoughtsTokenCount: 0,
            totalTokenCount: promptTokens + (usage.output || 0),
        },
        candidates: [{ finishReason: final?.stop_reason === 'max_tokens' ? 'MAX_TOKENS' : 'STOP' }],
        stopReason: final?.stop_reason,
        content,
        rawUsage: usage, // { input, cache_read, cache_write, output } tel que renvoyé par le serveur (pour estimateCostUsd)
    };
};

// Découpe un tampon de flux SSE en événements JSON complets ; retourne aussi le reste (événement partiel). Les lignes de
// commentaire (`: keepalive`) sont ignorées.
export const parseSseBuffer = (buffer) => {
    const events = [];
    const chunks = buffer.split('\n\n');
    const rest = chunks.pop();
    for (const chunk of chunks) {
        const data = chunk.split('\n').filter((line) => line.startsWith('data: ')).map((line) => line.slice(6)).join('\n');
        if (!data) continue;
        try { events.push(JSON.parse(data)); } catch { /* événement corrompu : ignoré */ }
    }
    return { events, rest };
};

// Coût estimé (en $) d'un tour, d'après l'usage renvoyé par le serveur. Tarifs de `backend/api/llm_pricing.py` (à garder
// synchronisés) : écriture de cache 1,25 × l'entrée (TTL 5 min), lecture 5 %.
// `claudeChat.test.js` compare ce tableau à `llm_pricing.py` : un prix changé d'un seul côté fait échouer le test.
export const PRICES = { 'claude-sonnet-5-5': { in: 2, out: 10, cached: 0.05 }, 'claude-opus-5-5': { in: 4, out: 20, cached: 0.05 } };
export const estimateCostUsd = (model, usage = {}) => {
    const price = PRICES[model];
    if (!price) return null;
    return ((usage.input || 0) * price.in + (usage.cache_read || 0) * price.in * price.cached
        + (usage.cache_write || 0) * price.in * 1.25 + (usage.output || 0) * price.out) / 1e6;
};
