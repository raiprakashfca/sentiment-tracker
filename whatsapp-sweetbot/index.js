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
// Settings missing from an older config.json fall back to config.example.json.
const config = {
  ...JSON.parse(fs.readFileSync(path.join(__dirname, 'config.example.json'), 'utf8')),
  ...JSON.parse(fs.readFileSync(configPath, 'utf8')),
};
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

// The first message of each morning is always your own greeting, e.g. "Good Morning Shona 😘😘".
const statePath = path.join(__dirname, '.state.json');
const readState = () => { try { return JSON.parse(fs.readFileSync(statePath, 'utf8')); } catch { return {}; } };
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: config.timezone });

let greetedOn = readState().greetedOn;

function morningGreetingDue(hour) {
  if (!config.morningGreeting || hour < 5 || hour >= 12 || greetedOn === today()) return null;
  const kisses = (config.greetingEmoji || '😘').repeat(2 + Math.floor(Math.random() * 2));
  return `${config.morningGreeting.replace('{name}', config.recipientName)} ${kisses}`;
}

function markGreeted() {
  greetedOn = today();
  if (!DRY_RUN) fs.writeFileSync(statePath, JSON.stringify({ ...readState(), greetedOn }));
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
      const greeting = morningGreetingDue(hour);
      if (greeting) {
        await sendParts(client, chatId, [greeting]);
        markGreeted();
        continue;
      }
      const args = { hour, name: config.recipientName, neverSay: config.myStyle?.neverSay, myStyle: config.myStyle };
      const parts = (config.llm?.enabled && (await generateWithLLM({ llm: config.llm, ...args }))) || buildMessage(args);
      await sendParts(client, chatId, parts);
    } catch (err) {
      console.error('Send failed:', err.message);
    }
  }
}

// Puppeteer's own Chrome download is sometimes blocked (e.g. npm's allow-scripts),
// so fall back to a Chrome or Edge that's already installed.
function findBrowser() {
  if (config.browserPath) return config.browserPath;
  try {
    const bundled = require('puppeteer').executablePath();
    if (fs.existsSync(bundled)) return bundled;
  } catch {}
  const pf = process.env.PROGRAMFILES || 'C:\\Program Files';
  const pf86 = process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)';
  const local = process.env.LOCALAPPDATA || '';
  const candidates = [
    path.join(pf, 'Google/Chrome/Application/chrome.exe'),
    path.join(pf86, 'Google/Chrome/Application/chrome.exe'),
    path.join(local, 'Google/Chrome/Application/chrome.exe'),
    path.join(pf86, 'Microsoft/Edge/Application/msedge.exe'),
    path.join(pf, 'Microsoft/Edge/Application/msedge.exe'),
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ];
  return candidates.find((p) => fs.existsSync(p)); // undefined → let puppeteer decide
}

async function main() {
  if (DRY_RUN) {
    console.log('Dry run: printing messages instead of sending them.\n');
    return loop(null);
  }

  const { Client, LocalAuth } = require('whatsapp-web.js');
  const qrcode = require('qrcode-terminal');
  const QRCode = require('qrcode');
  const { exec } = require('child_process');

  const browser = findBrowser();
  console.log(`Starting browser${browser ? ` (${browser})` : ''}…`);

  const client = new Client({
    authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth') }),
    puppeteer: { headless: true, executablePath: browser, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
  });

  // Text QR codes often render badly in PowerShell, so also save a PNG and open it.
  const qrFile = path.join(__dirname, 'whatsapp-qr.png');
  let qrOpened = false;
  client.on('qr', async (qr) => {
    console.log('\nScan this QR in WhatsApp → Settings → Linked devices → Link a device:');
    qrcode.generate(qr, { small: true });
    try {
      await QRCode.toFile(qrFile, qr, { width: 400, margin: 2 });
      console.log(`Also saved as an image: ${qrFile}`);
      if (!qrOpened) {
        qrOpened = true;
        const opener = process.platform === 'win32' ? 'start ""' : process.platform === 'darwin' ? 'open' : 'xdg-open';
        exec(`${opener} "${qrFile}"`);
      }
    } catch (err) {
      console.error('Could not save the QR image:', err.message);
    }
    console.log('(The code refreshes every ~20 seconds; the image file updates too — reopen it if it expired.)');
  });
  client.on('loading_screen', (percent) => console.log(`Loading WhatsApp… ${percent}%`));
  client.on('authenticated', () => {
    console.log('Linked! Finishing login…');
    fs.rmSync(qrFile, { force: true });
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

  console.log('Opening WhatsApp Web (can take up to a minute the first time)…');
  try {
    await client.initialize();
  } catch (err) {
    console.error(`\nCould not start WhatsApp Web: ${err.message}`);
    if (/executable|browser|chrome|launch/i.test(err.message)) {
      console.error('No usable browser found. Install Google Chrome, or set "browserPath" in config.json to chrome.exe / msedge.exe.');
    }
    process.exit(1);
  }
}

main();
