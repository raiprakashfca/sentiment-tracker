// Asks a few questions and writes config.json, so nobody has to edit JSON by hand.
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const file = path.join(__dirname, 'config.json');
const defaults = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.example.json'), 'utf8'));
const current = fs.existsSync(file) ? { ...defaults, ...JSON.parse(fs.readFileSync(file, 'utf8')) } : defaults;
current.timezone = current.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;

const PRESETS = {
  groq: { baseUrl: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile', needsKey: true },
  ollama: { baseUrl: 'http://localhost:11434/v1', model: 'llama3.1', needsKey: false },
  lmstudio: { baseUrl: 'http://localhost:1234/v1', model: 'local-model', needsKey: false },
};

async function main() {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const lines = rl[Symbol.asyncIterator]();
  const ask = async (q, def) => {
    process.stdout.write(def ? `${q} [${def}]: ` : `${q}: `);
    const { value = '' } = await lines.next();
    return value.trim() || def || '';
  };

  console.log('Press Enter to keep the value in [brackets].\n');

  let number = '';
  while (number.length < 10) {
    number = (await ask('Her WhatsApp number with country code (e.g. 91 and then the number)', current.recipientNumber)).replace(/\D/g, '');
    if (number.length < 10) console.log('  That looks too short — include the country code.');
  }
  const name = await ask('What you call her', current.recipientName);
  const timezone = await ask('Your timezone', current.timezone);

  const llmNow = current.llm?.enabled ? Object.keys(PRESETS).find((k) => PRESETS[k].baseUrl === current.llm.baseUrl) || 'none' : 'none';
  const choice = (await ask('Who writes the messages? groq / ollama / lmstudio / none', llmNow)).toLowerCase();

  const config = { ...current, recipientNumber: number, recipientName: name, timezone };
  if (PRESETS[choice]) {
    const p = PRESETS[choice];
    const sameProvider = current.llm?.baseUrl === p.baseUrl;
    const llm = { enabled: true, baseUrl: p.baseUrl, model: sameProvider ? current.llm.model : p.model, temperature: 1.0 };
    if (p.needsKey) {
      const shown = sameProvider && current.llm.apiKey ? `${current.llm.apiKey.slice(0, 8)}…` : '';
      const key = await ask('Paste your API key (starts with gsk_)', shown);
      llm.apiKey = key === shown ? current.llm.apiKey : key;
    }
    llm.model = await ask('Model', llm.model);
    config.llm = llm;
  } else {
    config.llm = { ...(current.llm || defaults.llm), enabled: false };
  }
  rl.close();

  fs.writeFileSync(file, JSON.stringify(config, null, 2) + '\n');
  console.log(`\nSaved config.json.${config.llm.enabled ? ' Next: npm run test-llm' : ' Next: npm run preview'}`);
}

main();
