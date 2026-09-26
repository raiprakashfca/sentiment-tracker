// Checks the LLM settings in config.json by writing a few sample messages. Sends nothing.
const fs = require('fs');
const path = require('path');
const { generateWithLLM } = require('./llm');

async function main() {
  const config = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
  const { llm } = config;
  if (!llm || !llm.baseUrl || !llm.model) {
    console.error('Add an "llm" section with baseUrl and model to config.json first.');
    process.exit(1);
  }
  console.log(`Testing ${llm.model} at ${llm.baseUrl}\n`);

  let ok = 0;
  for (const hour of [8, 13, 19, 22]) {
    const parts = await generateWithLLM({ llm, hour, name: config.recipientName });
    if (parts) {
      ok++;
      console.log(`  ${String(hour).padStart(2, '0')}:00  ${parts[0]}`);
    }
  }
  if (ok) return console.log(`\nWorking (${ok}/4 usable). Set "enabled": true in config.json if it isn't already.`);

  // Most failures are a wrong model name or key, so show what the server offers.
  try {
    const res = await fetch(`${llm.baseUrl.replace(/\/$/, '')}/models`, {
      headers: { Authorization: `Bearer ${llm.apiKey || 'local'}` },
    });
    if (res.status === 401) return console.error('\nThe API key was rejected. Check "apiKey" in config.json.');
    const ids = ((await res.json()).data || []).map((m) => m.id).sort();
    console.error(`\nModels available here — put one of these in "model":\n  ${ids.join('\n  ')}`);
  } catch (err) {
    console.error(`\nCouldn't reach ${llm.baseUrl}: ${err.message}`);
  }
}

main();
