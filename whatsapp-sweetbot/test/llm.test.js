const test = require('node:test');
const assert = require('node:assert/strict');
const { pickAvailableModel } = require('../llm');

test('keeps a model the server still offers', () => {
  assert.equal(pickAvailableModel('llama3.1', ['llama3.1', 'openai/gpt-oss-120b']), 'llama3.1');
});

test('replaces a retired model with the first fallback the server offers', () => {
  assert.equal(
    pickAvailableModel('llama-3.3-70b-versatile', ['whisper-large-v3', 'openai/gpt-oss-20b', 'openai/gpt-oss-120b']),
    'openai/gpt-oss-120b',
  );
});

test('uses a later fallback when the preferred one is missing', () => {
  assert.equal(pickAvailableModel('retired-model', ['openai/gpt-oss-20b']), 'openai/gpt-oss-20b');
});

test('returns null when nothing listed is a model Sweetbot can use', () => {
  assert.equal(pickAvailableModel('retired-model', ['whisper-large-v3']), null);
});
