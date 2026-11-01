import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ClaudeChatSession } from './claudeSession.js';

const FINAL_TEXT = { type: 'final', stop_reason: 'end_turn', content: [{ type: 'text', text: 'Bonjour' }], usage: { input: 10, cache_read: 0, cache_write: 0, output: 5 } };

// Transport simulé : enregistre les requêtes et rejoue une liste d'événements.
const fakeTransport = (events) => {
    const calls = [];
    const streamEvents = async function* (path, body, { signal }) {
        calls.push({ path, body, signal });
        for (const event of events) yield event;
    };
    return { calls, streamEvents };
};

const makeSession = (streamEvents, history = []) => new ClaudeChatSession({
    modelName: 'claude-sonnet-5-5', systemInstruction: 'sys', tools: [{ name: 'outil' }], history, streamEvents,
});

const drain = async (stream) => { for await (const chunk of stream.stream) void chunk; return stream.response; };

test('un tour de texte renvoie le texte, l\'usage, et la session retient la conversation', async () => {
    const t = fakeTransport([{ type: 'text', delta: 'Bon' }, { type: 'text', delta: 'jour' }, FINAL_TEXT]);
    const session = makeSession(t.streamEvents, [{ role: 'user', parts: [{ text: 'a' }] }, { role: 'model', parts: [{ text: 'b' }] }]);
    const stream = await session.sendMessageStream([{ text: 'Salut' }], { dealId: 'd1', action: 'chat_turn' });
    const chunks = [];
    for await (const chunk of stream.stream) chunks.push(chunk.text());
    const response = await stream.response;
    assert.deepEqual(chunks, ['Bon', 'jour']);
    assert.equal(response.text(), 'Bonjour');
    assert.equal(response.usageMetadata.promptTokenCount, 10);
    assert.equal(t.calls[0].path, '/deals/d1/chat/claude');
    assert.equal(t.calls[0].body.model, 'claude-sonnet-5-5');
    assert.equal(t.calls[0].body.messages.length, 3); // historique (2) + nouveau message
    assert.equal(session.messages.length, 4); // + la réponse
});

test('un appel d\'outil est renvoyé en tool_result avec les blocs de réflexion du tour, tels quels', async () => {
    const toolTurn = {
        type: 'final', stop_reason: 'tool_use', usage: { input: 5, output: 5 },
        content: [{ type: 'thinking', thinking: '', signature: 'sig' }, { type: 'tool_use', id: 'tu1', name: 'propose_restoration_step', input: { label: 'x' } }],
    };
    const first = fakeTransport([toolTurn]);
    const session = makeSession(first.streamEvents);
    const response = await drain(await session.sendMessageStream([{ text: 'Ajoute une étape' }], { dealId: 'd1' }));
    assert.deepEqual(response.functionCalls().map(c => c.name), ['propose_restoration_step']);

    session.streamEvents = fakeTransport([FINAL_TEXT]).streamEvents; // 2e envoi : la réponse à l'outil
    const second = fakeTransport([FINAL_TEXT]);
    session.streamEvents = second.streamEvents;
    await drain(await session.sendMessageStream([{ functionResponse: { name: 'propose_restoration_step', response: { status: 'ok' } } }], { dealId: 'd1' }));
    const sent = second.calls[0].body.messages;
    assert.equal(sent[1].role, 'assistant');
    assert.equal(sent[1].content[0].signature, 'sig'); // bloc de réflexion conservé
    assert.equal(sent[2].content[0].type, 'tool_result');
    assert.equal(sent[2].content[0].tool_use_id, 'tu1');
});

test('un événement d\'erreur rejette avec le statut HTTP lisible par classifyChatError, sans modifier la session', async () => {
    const t = fakeTransport([{ type: 'error', status: 529, message: 'surcharge' }]);
    const session = makeSession(t.streamEvents);
    const stream = await session.sendMessageStream([{ text: 'x' }], { dealId: 'd1' });
    await assert.rejects(drain(stream), (e) => e.customErrorData.status === 529);
    assert.equal(session.messages.length, 0);
});

test('un flux sans réponse finale est une erreur réseau (nouvelle tentative possible)', async () => {
    const session = makeSession(fakeTransport([{ type: 'text', delta: 'a' }]).streamEvents);
    await assert.rejects(drain(await session.sendMessageStream([{ text: 'x' }], { dealId: 'd1' })), /network error/);
});

test('un refus du modèle est signalé comme une erreur', async () => {
    const session = makeSession(fakeTransport([{ ...FINAL_TEXT, stop_reason: 'refusal' }]).streamEvents);
    await assert.rejects(drain(await session.sendMessageStream([{ text: 'x' }], { dealId: 'd1' })), /refusé/);
});

test('le délai maximal coupe la requête avec un message contenant « timeout »', async () => {
    const hanging = async function* (_path, _body, { signal }) {
        await new Promise((_, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
        yield FINAL_TEXT;
    };
    const session = makeSession(hanging);
    const stream = await session.sendMessageStream([{ text: 'x' }], { dealId: 'd1', timeout: 20 });
    await assert.rejects(drain(stream), /timeout/);
});

test('sans dealId ou sans contenu, l\'envoi est refusé avant tout appel réseau', async () => {
    const t = fakeTransport([FINAL_TEXT]);
    const session = makeSession(t.streamEvents);
    await assert.rejects(session.sendMessageStream([{ text: 'x' }], {}), /dealId/);
    await assert.rejects(session.sendMessageStream([{ text: '' }], { dealId: 'd1' }), /sans contenu/);
    assert.equal(t.calls.length, 0);
});

test('un flux abandonné par le lecteur coupe la requête (le serveur cesse de générer)', async () => {
    const t = fakeTransport([{ type: 'text', delta: 'a' }, { type: 'text', delta: 'b' }, FINAL_TEXT]);
    const session = makeSession(t.streamEvents);
    const stream = await session.sendMessageStream([{ text: 'x' }], { dealId: 'd1' });
    for await (const chunk of stream.stream) { void chunk; break; } // le lecteur s'arrête après le premier morceau
    assert.equal(t.calls[0].signal.aborted, true);
    assert.equal(session.messages.length, 0); // tour inachevé : la session n'a rien retenu
});
