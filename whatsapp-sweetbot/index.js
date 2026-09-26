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

const botSent = new Set();

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
    botSent.add(part);
    await client.sendMessage(chatId, part);
    console.log(`  sent: ${part}`);
    await sleep(rand(2000, 7000));
  }
}

// ---- Day / pause state (persisted so a restart doesn't forget) ----------------
const statePath = path.join(__dirname, '.state.json');
const readState = () => { try { return JSON.parse(fs.readFileSync(statePath, 'utf8')); } catch { return {}; } };
const state = readState();
const saveState = () => DRY_RUN || fs.writeFileSync(statePath, JSON.stringify(state));

// A "day" runs from 4am to 4am, so texting her at 1am still counts as last night.
const DAY_STARTS_AT = 4;
const dayKey = () =>
  new Date(Date.now() - DAY_STARTS_AT * 3600e3).toLocaleDateString('en-CA', { timeZone: config.timezone });
const timeStr = (ms) => new Date(ms).toLocaleTimeString('en-GB', { timeZone: config.timezone, hour: '2-digit', minute: '2-digit' });

const waitForMe = config.startAfterMyFirstMessage !== false;
let nextSendAt = null;
let lastStatus = '';

function status(text) {
  if (text !== lastStatus) console.log(text);
  lastStatus = text;
}

function isPaused() {
  if (!state.pausedUntil) return false;
  if (state.pausedUntil !== 'forever' && Date.now() >= state.pausedUntil) {
    delete state.pausedUntil;
    saveState();
    console.log('Pause is over — resuming.');
    return false;
  }
  return true;
}

// Someone texted in her chat (you by hand, or her): the bot backs off for a fresh
// random gap, so it never cuts into a real conversation.
function onChatActivity(fromMe) {
  if (fromMe && state.awakeOn !== dayKey()) {
    state.awakeOn = dayKey();
    saveState();
    console.log(`You texted ${config.recipientName} — bot starts for today.`);
  }
  if (state.awakeOn === dayKey()) {
    nextSendAt = Math.max(nextSendAt || 0, Date.now() + nextGapMs());
    console.log(`Chat activity — next bot message not before ${timeStr(nextSendAt)}`);
  }
}

// "pause", "pause 2h", "pause 30m", "pause today", "resume", "status"
function handleCommand(text) {
  const [cmd, arg = ''] = text.trim().toLowerCase().split(/\s+/);
  if (cmd === 'pause' || cmd === 'stop') {
    const m = arg.match(/^(\d+(?:\.\d+)?)\s*(h|m)/);
    if (m) state.pausedUntil = Date.now() + Number(m[1]) * (m[2] === 'h' ? 3600e3 : 60e3);
    else if (arg === 'today') {
      const hoursLeft = 24 - ((localHour() - DAY_STARTS_AT + 24) % 24); // until 4am
      state.pausedUntil = Date.now() + hoursLeft * 3600e3;
    } else state.pausedUntil = 'forever';
    saveState();
    return state.pausedUntil === 'forever' ? 'Paused until you say "bot resume".' : `Paused until ${timeStr(state.pausedUntil)}.`;
  }
  if (cmd === 'resume' || cmd === 'start') {
    delete state.pausedUntil;
    saveState();
    return 'Resumed.';
  }
  if (cmd === 'status') {
    if (isPaused()) return state.pausedUntil === 'forever' ? 'Paused (until you resume).' : `Paused until ${timeStr(state.pausedUntil)}.`;
    if (waitForMe && state.awakeOn !== dayKey()) return `Running — waiting for your first message to ${config.recipientName} today.`;
    return nextSendAt ? `Running — next message around ${timeStr(nextSendAt)}.` : 'Running.';
  }
  return 'Commands: pause, pause 2h, pause 30m, pause today, resume, status';
}

function canSendNow(hour) {
  if (isPaused()) return status('Paused.'), false;
  if (DRY_RUN) return true;
  if (waitForMe) {
    if (state.awakeOn !== dayKey()) return status(`Waiting for your first message to ${config.recipientName} today…`), false;
    // After you're up, only bedtime applies (quietHours.start until 4am).
    if (hour >= config.quietHours.start || hour < DAY_STARTS_AT) return status('Bedtime — done for today.'), false;
    return true;
  }
  if (inQuietHours(hour)) return status('Quiet hours.'), false;
  return true;
}

async function loop(client, chatId) {
  for (;;) {
    await sleep(DRY_RUN ? 300 : Number(process.env.SWEETBOT_POLL_MS) || 20000);
    const hour = localHour();
    if (!canSendNow(hour)) continue;

    if (!nextSendAt) {
      nextSendAt = Date.now() + (DRY_RUN ? 1000 : nextGapMs());
      status(`Next message around ${timeStr(nextSendAt)}`);
    }
    if (Date.now() < nextSendAt) continue;
    nextSendAt = Date.now() + (DRY_RUN ? 1000 : nextGapMs());

    if (Math.random() < config.skipChance) {
      status(`Skipping this one (people get busy). Next around ${timeStr(nextSendAt)}`);
      continue;
    }
    try {
      const args = { hour, name: config.recipientName, neverSay: config.myStyle?.neverSay, myStyle: config.myStyle };
      const parts = (config.llm?.enabled && (await generateWithLLM({ llm: config.llm, ...args }))) || buildMessage(args);
      await sendParts(client, chatId, parts);
      status(`Next message around ${timeStr(nextSendAt)}`);
    } catch (err) {
      console.error('Send failed:', err.message);
    }
  }
}

// Typing commands into this window works too: pause / pause 2h / resume / status
function listenToKeyboard() {
  if (!process.stdin.isTTY) return;
  const rl = require('readline').createInterface({ input: process.stdin });
  rl.on('line', (line) => line.trim() && console.log(handleCommand(line.replace(/^bot\s+/i, ''))));
  console.log('Type "pause", "pause 2h", "resume" or "status" here any time.');
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
    console.log('Dry run: printing messages instead of sending them (assumes you are awake).\n');
    listenToKeyboard();
    return loop(null, null);
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
  const chatId = `${config.recipientNumber}@c.us`;
  const herIds = new Set([chatId]);

  // WhatsApp sometimes uses other ids (e.g. @lid) for the same chat, so match by number too.
  async function isHerChat(msg) {
    const other = msg.fromMe ? msg.to : msg.from;
    if (herIds.has(other)) return true;
    if (other.endsWith('@g.us')) return false;
    try {
      const chat = await msg.getChat();
      if (chat.isGroup) return false;
      const contact = await chat.getContact();
      if (String(contact.number) === String(config.recipientNumber) || chat.id.user === String(config.recipientNumber)) {
        herIds.add(other);
        return true;
      }
    } catch {}
    return false;
  }

  client.on('message_create', async (msg) => {
    try {
      if (msg.type !== 'chat' && !msg.hasMedia) return;
      const body = msg.body || '';

      // "bot pause" etc. typed in your own "Message yourself" chat.
      const toSelf = msg.from === msg.to || msg.to === client.info?.wid?._serialized;
      if (msg.fromMe && toSelf && /^bot\b/i.test(body)) {
        const reply = handleCommand(body.replace(/^bot\s*/i, ''));
        console.log(`[command] ${body} → ${reply}`);
        await msg.reply(`🤖 ${reply}`);
        return;
      }

      if (!(await isHerChat(msg))) return;
      if (msg.fromMe && botSent.delete(body)) return; // the bot's own message
      onChatActivity(msg.fromMe);
    } catch (err) {
      console.error('Could not read an incoming message:', err.message);
    }
  });

  client.on('ready', () => {
    console.log('Logged in. Starting.');
    console.log(`Text "bot pause", "bot pause 2h", "bot resume" or "bot status" to yourself on WhatsApp to control it.`);
    listenToKeyboard();
    loop(client, chatId);
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
