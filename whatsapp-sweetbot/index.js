const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const { buildMessage } = require('./messages');
const { generateWithLLM, llmLastError } = require('./llm');
const { startUI } = require('./ui');
const autostart = require('./autostart');

const DRY_RUN = process.argv.includes('--dry-run');
const NO_BROWSER = process.argv.includes('--no-browser');

// ---- Config -------------------------------------------------------------------
const configPath = path.join(__dirname, 'config.json');
const examplePath = path.join(__dirname, 'config.example.json');
const readJson = (f) => JSON.parse(fs.readFileSync(f, 'utf8'));

function loadConfig() {
  const defaults = readJson(examplePath);
  if (!fs.existsSync(configPath)) return defaults;
  try {
    // Settings missing from an older config.json fall back to config.example.json.
    return { ...defaults, ...readJson(configPath) };
  } catch {
    console.error('config.json is not valid JSON — using defaults until you save settings.');
    return defaults;
  }
}

const config = loadConfig();

function saveConfig(patch) {
  Object.assign(config, patch);
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n');
}

const hasNumber = () => /^\d{10,15}$/.test(String(config.recipientNumber));
const herChatId = () => `${config.recipientNumber}@c.us`;

// ---- Activity log (shown in the control panel) ----------------------------------
// Also written to sweetbot.log, since with auto-start there's no window to read.
const events = [];
const logPath = path.join(__dirname, 'sweetbot.log');
try {
  if (fs.statSync(logPath).size > 1_000_000) fs.rmSync(logPath);
} catch {}

function log(text, kind = 'info') {
  console.log(text);
  events.push({ t: Date.now(), text, kind });
  if (events.length > 200) events.shift();
  try {
    fs.appendFileSync(logPath, `${new Date().toISOString()}  ${text}\n`);
  } catch {}
}

let lastStatus = '';
function status(text) {
  if (text !== lastStatus) log(text, 'status');
  lastStatus = text;
}

// ---- Timing helpers -------------------------------------------------------------
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

const timeStr = (ms) =>
  new Date(ms).toLocaleTimeString('en-GB', { timeZone: config.timezone, hour: '2-digit', minute: '2-digit' });

// ---- Day / pause state (persisted so a restart doesn't forget) ----------------
const statePath = path.join(__dirname, '.state.json');
const state = (() => { try { return readJson(statePath); } catch { return {}; } })();
const saveState = () => DRY_RUN || fs.writeFileSync(statePath, JSON.stringify(state));

// A "day" runs from 4am to 4am, so texting her at 1am still counts as last night.
const DAY_STARTS_AT = 4;
const dayKey = () =>
  new Date(Date.now() - DAY_STARTS_AT * 3600e3).toLocaleDateString('en-CA', { timeZone: config.timezone });

const waitForMe = () => config.startAfterMyFirstMessage !== false;
const awakeToday = () => DRY_RUN || state.awakeOn === dayKey();
let nextSendAt = null;

function isPaused() {
  if (!state.pausedUntil) return false;
  if (state.pausedUntil !== 'forever' && Date.now() >= state.pausedUntil) {
    delete state.pausedUntil;
    saveState();
    log('Pause is over — resuming.', 'status');
    return false;
  }
  return true;
}

function pause(what) {
  if (what === 'today') {
    const hoursLeft = 24 - ((localHour() - DAY_STARTS_AT + 24) % 24); // until 4am
    state.pausedUntil = Date.now() + hoursLeft * 3600e3;
  } else if (typeof what === 'number' && what > 0) {
    state.pausedUntil = Date.now() + what * 60e3;
  } else {
    state.pausedUntil = 'forever';
  }
  saveState();
  const text = state.pausedUntil === 'forever' ? 'Paused until you resume.' : `Paused until ${timeStr(state.pausedUntil)}.`;
  log(text, 'status');
  return text;
}

function resume() {
  delete state.pausedUntil;
  saveState();
  log('Resumed.', 'status');
  return 'Resumed.';
}

// Someone texted in her chat (you by hand, or her): the bot backs off for a fresh
// random gap, so it never cuts into a real conversation.
function onChatActivity(fromMe) {
  if (fromMe && state.awakeOn !== dayKey()) {
    state.awakeOn = dayKey();
    saveState();
    log(`You texted ${config.recipientName} — bot starts for today.`, 'status');
  }
  if (state.awakeOn === dayKey()) {
    nextSendAt = Math.max(nextSendAt || 0, Date.now() + nextGapMs());
    log(`Chat activity — next bot message not before ${timeStr(nextSendAt)}.`);
  }
}

function describe() {
  if (isPaused()) {
    return { mode: 'paused', text: state.pausedUntil === 'forever' ? 'Paused until you resume' : `Paused until ${timeStr(state.pausedUntil)}` };
  }
  if (!hasNumber()) return { mode: 'setup', text: 'Add her number in Settings' };
  if (wa.state !== 'ready' && !DRY_RUN) return { mode: 'offline', text: 'WhatsApp is not linked yet' };
  const hour = localHour();
  if (waitForMe()) {
    if (!awakeToday()) return { mode: 'waiting', text: `Waiting for your first message to ${config.recipientName} today` };
    if (hour >= config.quietHours.start || hour < DAY_STARTS_AT) return { mode: 'bedtime', text: 'Bedtime — done for today' };
  } else if (inQuietHours(hour)) {
    return { mode: 'bedtime', text: 'Quiet hours' };
  }
  return { mode: 'running', text: nextSendAt ? `Next message around ${timeStr(nextSendAt)}` : 'Running' };
}

// ---- Commands (WhatsApp self-chat) ----------------------------------------------
// "pause", "pause 2h", "pause 30m", "pause today", "resume", "status"
function handleCommand(text) {
  const [cmd, arg = ''] = text.trim().toLowerCase().split(/\s+/);
  if (cmd === 'pause' || cmd === 'stop') {
    const m = arg.match(/^(\d+(?:\.\d+)?)\s*(h|m)/);
    if (m) return pause(Number(m[1]) * (m[2] === 'h' ? 60 : 1));
    return pause(arg === 'today' ? 'today' : 'forever');
  }
  if (cmd === 'resume' || cmd === 'start') return resume();
  if (cmd === 'status') return describe().text + '.';
  return 'Commands: pause, pause 2h, pause 30m, pause today, resume, status';
}

// ---- Sending --------------------------------------------------------------------
const botSent = new Set();

let lastLLMError = {};

async function writeMessage(hour) {
  const args = { hour, name: config.recipientName, neverSay: config.myStyle?.neverSay, myStyle: config.myStyle };
  const fromLLM = config.llm?.enabled && (await generateWithLLM({ llm: config.llm, ...args }));
  let error = null;
  if (config.llm?.enabled && !fromLLM) {
    error = friendlyLLMError(llmLastError());
    if (error !== lastLLMError.text || Date.now() - lastLLMError.t > 60e3) {
      log(`AI writer didn't work (${error}) — used a built-in message.`, 'error');
      lastLLMError = { text: error, t: Date.now() };
    }
  }
  return { parts: fromLLM || buildMessage(args), source: fromLLM ? 'AI' : 'built-in', error };
}

function friendlyLLMError(e = '') {
  if (/fetch failed|ECONNREFUSED/i.test(e)) return `can't reach ${config.llm.baseUrl} — is it running?`;
  if (/HTTP 401/.test(e)) return 'the API key was rejected';
  if (/HTTP 404|model.*(not found|does not exist)/i.test(e)) return `model "${config.llm.model}" not found`;
  if (/HTTP 429/.test(e)) return 'rate limit reached, try later';
  return e.replace(/^HTTP \d+ /, '').slice(0, 140) || 'unknown error';
}

async function sendParts(parts) {
  const client = activeClient;
  for (const part of parts) {
    if (DRY_RUN) {
      log(`[preview] would send: ${part}`, 'sent');
      continue;
    }
    const chatId = herChatId();
    const chat = await client.getChatById(chatId);
    await chat.sendStateTyping();
    await sleep(typingMs(part));
    await chat.clearState();
    botSent.add(part);
    await client.sendMessage(chatId, part);
    log(`Sent: ${part}`, 'sent');
    await sleep(rand(2000, 7000));
  }
}

async function loop() {
  for (;;) {
    await sleep(DRY_RUN ? 300 : Number(process.env.SWEETBOT_POLL_MS) || 20000);
    const d = describe();
    if (d.mode !== 'running') {
      status(d.text + '.');
      continue;
    }

    if (!nextSendAt) {
      nextSendAt = Date.now() + (DRY_RUN ? 1500 : nextGapMs());
      status(`Next message around ${timeStr(nextSendAt)}.`);
    }
    if (Date.now() < nextSendAt) continue;
    nextSendAt = Date.now() + (DRY_RUN ? 1500 : nextGapMs());

    if (Math.random() < config.skipChance) {
      status(`Skipped one (people get busy). Next around ${timeStr(nextSendAt)}.`);
      continue;
    }
    try {
      const { parts } = await writeMessage(localHour());
      await sendParts(parts);
      status(`Next message around ${timeStr(nextSendAt)}.`);
    } catch (err) {
      log(`Send failed: ${err.message}`, 'error');
    }
  }
}

// ---- Browser discovery ------------------------------------------------------------
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

function openInBrowser(target) {
  const opener = process.platform === 'win32' ? 'start ""' : process.platform === 'darwin' ? 'open' : 'xdg-open';
  exec(`${opener} "${target}"`);
}

// ---- WhatsApp -----------------------------------------------------------------------
// state: starting → qr → linked → ready (or disconnected / error)
const wa = { state: DRY_RUN ? 'preview' : 'starting', qr: null, error: null };
let activeClient = null;
let loopStarted = false;
let restartTimer = null;

// Reconnect on its own: at PC start-up the internet may not be ready yet, and
// WhatsApp occasionally drops linked devices. If you unlinked it, a new QR appears.
function restartWhatsApp(client, delayMs) {
  if (restartTimer) return;
  log(`Reconnecting to WhatsApp in ${Math.round(delayMs / 1000)} seconds…`);
  restartTimer = setTimeout(async () => {
    restartTimer = null;
    try { await client.destroy(); } catch {}
    startWhatsApp();
  }, delayMs);
}

async function startWhatsApp() {
  const { Client, LocalAuth } = require('whatsapp-web.js');
  const QRCode = require('qrcode');

  const browser = findBrowser();
  log(`Starting WhatsApp Web${browser ? ` with ${path.basename(browser)}` : ''} — this can take a minute…`);

  const client = new Client({
    authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth') }),
    puppeteer: { headless: true, executablePath: browser, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
  });

  client.on('qr', async (qr) => {
    wa.state = 'qr';
    wa.qr = await QRCode.toDataURL(qr, { width: 320, margin: 1 });
    status('Scan the QR code in the control panel to link WhatsApp.');
  });
  client.on('loading_screen', (percent) => status(`Loading WhatsApp… ${percent}%`));
  client.on('authenticated', () => {
    wa.state = 'linked';
    wa.qr = null;
    log('WhatsApp linked — finishing login…', 'status');
  });
  client.on('auth_failure', (m) => {
    wa.state = 'error';
    wa.error = `Login failed: ${m}`;
    log(wa.error, 'error');
  });
  client.on('disconnected', (r) => {
    wa.state = 'disconnected';
    wa.error = r === 'LOGOUT' ? 'WhatsApp was unlinked from your phone — a new QR code will appear here.' : `WhatsApp disconnected (${r}).`;
    log(wa.error, 'error');
    restartWhatsApp(client, 15e3);
  });

  const herIds = new Set();
  let herIdsFor = null;

  // WhatsApp sometimes uses other ids (e.g. @lid) for the same chat, so match by number too.
  async function isHerChat(msg) {
    if (herIdsFor !== config.recipientNumber) {
      herIds.clear();
      herIds.add(herChatId());
      herIdsFor = config.recipientNumber;
    }
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
        log(`WhatsApp command "${body}" → ${reply}`);
        await msg.reply(`🤖 ${reply}`);
        return;
      }

      if (!hasNumber() || !(await isHerChat(msg))) return;
      if (msg.fromMe && botSent.delete(body)) return; // the bot's own message
      onChatActivity(msg.fromMe);
    } catch (err) {
      log(`Could not read an incoming message: ${err.message}`, 'error');
    }
  });

  client.on('ready', () => {
    activeClient = client;
    wa.state = 'ready';
    wa.error = null;
    log('WhatsApp is ready.', 'status');
    if (!loopStarted) {
      loopStarted = true;
      loop();
    }
  });

  try {
    await client.initialize();
  } catch (err) {
    wa.state = 'error';
    wa.error = `Could not start WhatsApp Web: ${err.message}`;
    if (/executable|browser|chrome|launch/i.test(err.message) && !/net::|timeout/i.test(err.message)) {
      wa.error += ' — no usable browser found. Install Google Chrome, or set "browserPath" in config.json.';
      return log(wa.error, 'error');
    }
    log(wa.error, 'error');
    restartWhatsApp(client, 60e3); // most likely no internet yet
  }
}

// ---- Start ----------------------------------------------------------------------------
async function main() {
  const port = Number(config.uiPort) || 3737;
  try {
    await startUI({
      port,
      config,
      saveConfig,
      getStatus: () => ({
        whatsapp: wa.state,
        qr: wa.qr,
        error: wa.error,
        bot: describe(),
        events: events.slice(-60).reverse(),
        preview: DRY_RUN,
      }),
      pause,
      resume,
      autostart: {
        supported: autostart.supported(),
        get: () => autostart.isEnabled(),
        set: (on) => {
          const now = autostart.setEnabled(on);
          log(now ? 'Sweetbot will start by itself when you log in to Windows.' : 'Auto-start turned off.', 'status');
          return now;
        },
      },
      preview: async () => {
        const hour = localHour();
        const out = [];
        for (let i = 0; i < 4; i++) out.push(await writeMessage(hour));
        return out;
      },
      stop: () => {
        log('Stopping — bye!');
        setTimeout(() => process.exit(0), 300);
      },
    });
  } catch (err) {
    if (err.code === 'EADDRINUSE') {
      console.error(`Sweetbot already seems to be running — opening its control panel.`);
      if (!NO_BROWSER) openInBrowser(`http://localhost:${port}`);
      process.exit(0);
    }
    throw err;
  }
  const url = `http://localhost:${port}`;
  log(`Control panel: ${url}`);
  if (!NO_BROWSER) openInBrowser(url);

  if (DRY_RUN) {
    log('Preview mode: messages are shown here, nothing is sent.', 'status');
    return loop();
  }
  startWhatsApp();
}

main();
