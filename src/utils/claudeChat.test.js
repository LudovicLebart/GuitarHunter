import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    isClaudeModel, schemaToJsonSchema, declarationsToTools, historyToMessages, partsToUserContent,
    wrapFinalResponse, parseSseBuffer, estimateCostUsd,
} from './claudeChat.js';

test('isClaudeModel reconnaît les modèles Claude uniquement', () => {
    assert.equal(isClaudeModel('claude-sonnet-5-5'), true);
    assert.equal(isClaudeModel('gemini-3.1-pro-preview'), false);
    assert.equal(isClaudeModel(undefined), false);
});

test('declarationsToTools convertit un schéma sérialisable en JSON Schema sans nullable:false', () => {
    const schema = { toJSON: () => ({ type: 'object', nullable: false, properties: { label: { type: 'string', nullable: false } }, required: ['label'] }) };
    const [tool] = declarationsToTools([{ name: 'propose_restoration_step', description: 'd', parameters: schema }]);
    assert.deepEqual(tool, {
        name: 'propose_restoration_step', description: 'd',
        input_schema: { type: 'object', properties: { label: { type: 'string' } }, required: ['label'] },
    });
});

test('historyToMessages mappe model→assistant, texte et photos, et retire les tours vides', () => {
    const msgs = historyToMessages([
        { role: 'user', parts: [{ text: 'Bonjour' }, { inlineData: { data: 'AAA', mimeType: 'image/jpeg' } }] },
        { role: 'model', parts: [{ text: 'Salut' }] },
        { role: 'user', parts: [{ text: '' }] },
    ]);
    assert.equal(msgs.length, 2);
    assert.deepEqual(msgs[0].content[1], { type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: 'AAA' } });
    assert.equal(msgs[1].role, 'assistant');
});

test('partsToUserContent apparie les functionResponse aux tool_use (ordre, nom) et les place en premier', () => {
    const pending = [{ id: 't1', name: 'a' }, { id: 't2', name: 'b' }];
    const content = partsToUserContent([
        { text: 'note' },
        { functionResponse: { name: 'b', response: { status: 'ok' } } },
        { functionResponse: { name: 'a', response: { status: 'ok' } } },
    ], pending);
    assert.equal(content[0].tool_use_id, 't2');
    assert.equal(content[1].tool_use_id, 't1');
    assert.deepEqual(content[2], { type: 'text', text: 'note' });
    assert.equal(JSON.parse(content[0].content).status, 'ok');
});

test('partsToUserContent ignore une functionResponse sans appel correspondant', () => {
    assert.deepEqual(partsToUserContent([{ functionResponse: { name: 'x', response: {} } }], []), []);
});

test('wrapFinalResponse expose text(), functionCalls(), usageMetadata et MAX_TOKENS comme le SDK Gemini', () => {
    const r = wrapFinalResponse({
        stop_reason: 'max_tokens',
        content: [{ type: 'text', text: 'A' }, { type: 'text', text: 'B' }, { type: 'tool_use', id: 't', name: 'n', input: { x: 1 } }],
        usage: { input: 100, cache_read: 50, cache_write: 20, output: 30 },
    });
    assert.equal(r.text(), 'AB');
    assert.deepEqual(r.functionCalls(), [{ name: 'n', args: { x: 1 }, id: 't' }]);
    assert.equal(r.usageMetadata.promptTokenCount, 170);
    assert.equal(r.usageMetadata.cachedContentTokenCount, 50);
    assert.equal(r.usageMetadata.candidatesTokenCount, 30);
    assert.equal(r.candidates[0].finishReason, 'MAX_TOKENS');
});

test('parseSseBuffer rend les événements complets, garde le reste et ignore les commentaires', () => {
    const { events, rest } = parseSseBuffer('data: {"type":"text","delta":"a"}\n\n: keepalive\n\ndata: {"type":"fin');
    assert.deepEqual(events, [{ type: 'text', delta: 'a' }]);
    assert.equal(rest, 'data: {"type":"fin');
});

test('estimateCostUsd reprend les tarifs du serveur (écriture 1,25 ×, lecture 5 %)', () => {
    const cost = estimateCostUsd('claude-sonnet-5-5', { input: 1_000_000, cache_read: 0, cache_write: 0, output: 100_000 });
    assert.ok(Math.abs(cost - 3) < 1e-9);
    const cached = estimateCostUsd('claude-opus-5-5', { input: 200_000, cache_read: 800_000, cache_write: 0, output: 10_000 });
    assert.ok(Math.abs(cached - (0.8 + 0.16 + 0.2)) < 1e-9);
    assert.equal(estimateCostUsd('inconnu', {}), null);
});
