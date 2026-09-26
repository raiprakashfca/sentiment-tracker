const fs = require('fs');
const path = require('path');
const { buildMessage } = require('./messages');
const { generateWithLLM } = require('./llm');

const DRY_RUN = process.argv.includes('--dry-run');

const configPath = path.join(__dirname, 'config.json');
if (!fs.existsSync(configPath)) {
  console.error('Missing config.json — copy config.example.json to config.json and fill it in.');
  process.exit(1);
}
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
if (!DRY_RUN && !/^\d{10,15}$/.test(String(config.recipientNumber))) {
  console.error('Set her number in config.json first (run: npm run setup).');
  process.exit(1);
}

const rand = (min, max) => min + Math.random() * (max - min);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function localHour(date = new Date()) {
  return Number(
    new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hourCycle: 'h23', timeZone: config.timezone }).format(date),
  );
}

function inQuietHours(hour) {
  const { start, end } = config.quietHours;
  return start > end ? hour >= start || hour < end : hour >= start && hour < end;
}

// Gaps cluster around the middle of the range instead of being uniform,
// which looks less mechanical than an even spread.
function nextGapMs() {
  const avg = (rand(0, 1) + rand(0, 1) + rand(0, 1)) / 3;
  const minutes = config.minGapMinutes + avg * (config.maxGapMinutes - config.minGapMinutes);
  return (minutes * 60 + rand(0, 59)) * 1000;
}

// Roughly how long a person takes to type the text on a phone.
function typingMs(text) {
  return Math.min(12000, 1200 + text.length * rand(120, 220));
}

async function sendParts(client, chatId, parts) {
  for (const part of parts) {
    if (DRY_RUN) {
      console.log(`  [dry-run] would send: ${part}`);
      continue;
    }
    const chat = await client.getChatById(chatId);
    await chat.sendStateTyping();
    await sleep(typingMs(part));
    await chat.clearState();
    await client.sendMessage(chatId, part);
    console.log(`  sent: ${part}`);
    await sleep(rand(2000, 7000));
  }
}

async function loop(client) {
  const chatId = `${config.recipientNumber}@c.us`;
  for (;;) {
    const gap = nextGapMs();
    const at = new Date(Date.now() + gap);
    console.log(`Next check at ${at.toLocaleTimeString('en-GB', { timeZone: config.timezone })}`);
    await sleep(DRY_RUN ? 1000 : gap);

    const hour = localHour();
    if (inQuietHours(hour) && !DRY_RUN) {
      console.log('Quiet hours — skipping.');
      continue;
    }
    if (Math.random() < config.skipChance) {
      console.log('Randomly skipping this round (people get busy).');
      continue;
    }

    try {
      const args = { hour, name: config.recipientName };
      const parts = (config.llm?.enabled && (await generateWithLLM({ llm: config.llm, ...args }))) || buildMessage(args);
      await sendParts(client, chatId, parts);
    } catch (err) {
      console.error('Send failed:', err.message);
    }
  }
}

async function main() {
  if (DRY_RUN) {
    console.log('Dry run: printing messages instead of sending them.\n');
    return loop(null);
  }

  const { Client, LocalAuth } = require('whatsapp-web.js');
  const qrcode = require('qrcode-terminal');

  const client = new Client({
    authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth') }),
    puppeteer: { headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
  });

  client.on('qr', (qr) => {
    console.log('Scan this QR in WhatsApp → Settings → Linked devices → Link a device:');
    qrcode.generate(qr, { small: true });
  });
  client.on('auth_failure', (m) => console.error('Auth failed:', m));
  client.on('disconnected', (r) => {
    console.error('Disconnected:', r);
    process.exit(1);
  });
  client.on('ready', () => {
    console.log('Logged in. Starting.');
    loop(client);
  });

  await client.initialize();
}

main();
