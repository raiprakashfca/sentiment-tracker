// Writes messages with a local LLM through any OpenAI-compatible server
// (Ollama, LM Studio, llama.cpp server, Jan, ...). Returns null on any problem
// so the caller can fall back to the built-in generator.

const fs = require('fs');
const path = require('path');
const { periodFor } = require('./messages');

const PERIOD_HINT = {
  morning: 'It is morning.',
  day: 'It is daytime; they are probably busy.',
  evening: 'It is evening.',
  night: 'It is late night, close to bedtime.',
};

function examples() {
  const file = path.join(__dirname, 'style.json');
  if (!fs.existsSync(file)) return [];
  const all = Object.values(JSON.parse(fs.readFileSync(file, 'utf8')).phrases).flat();
  return all.sort(() => Math.random() - 0.5).slice(0, 30);
}

const recent = [];

function clean(text) {
  // Reasoning models: drop finished <think> blocks; an unfinished one means it ran out of tokens.
  let t = (text || '').replace(/<think>[\s\S]*?<\/think>/g, '');
  if (/<think>/.test(t)) return null;
  t = t
    .trim()
    .split('\n')[0]
    .trim()
    .replace(/^["'“”]+|["'“”]+$/g, '')
    .trim();
  if (!t || t.length > 90) return null;
  if (/\b(as an ai|language model|here'?s|sure[,!]|message:)/i.test(t)) return null;
  return t;
}

async function generateWithLLM({ llm, hour, name }) {
  const shots = examples();
  const prompt = [
    `Write ONE short WhatsApp text to my girlfriend (I call her "${name}"), saying I miss her or am thinking of her.`,
    PERIOD_HINT[periodFor(hour)],
    shots.length
      ? `Match my texting style exactly — these are real messages I've sent her:\n${shots.map((s) => `- ${s}`).join('\n')}`
      : 'Write casually like a real person on their phone: short, mostly lowercase, 0-2 emoji.',
    recent.length ? `Don't repeat or closely paraphrase these recent ones:\n${recent.map((s) => `- ${s}`).join('\n')}` : '',
    'Under 12 words. Reply with the message text only — no quotes, no explanation.',
  ]
    .filter(Boolean)
    .join('\n\n');

  try {
    const res = await fetch(`${llm.baseUrl.replace(/\/$/, '')}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${llm.apiKey || 'local'}` },
      body: JSON.stringify({
        model: llm.model,
        messages: [{ role: 'user', content: prompt }],
        temperature: llm.temperature ?? 1.0,
        max_tokens: llm.maxTokens || 2000, // room for reasoning models to think first
        ...(llm.reasoningEffort && { reasoning_effort: llm.reasoningEffort }),
      }),
      signal: AbortSignal.timeout((llm.timeoutSeconds || 120) * 1000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} ${await res.text()}`);
    const text = clean((await res.json()).choices?.[0]?.message?.content);
    if (!text) throw new Error('reply was empty or not usable');
    if (recent.includes(text)) throw new Error('repeated a recent message');
    recent.push(text);
    if (recent.length > 8) recent.shift();
    return [text];
  } catch (err) {
    console.error(`  LLM failed (${err.message}) — using built-in messages instead.`);
    return null;
  }
}

module.exports = { generateWithLLM };
