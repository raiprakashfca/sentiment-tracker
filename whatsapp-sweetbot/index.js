const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const { buildMessage } = require('./messages');
const { generateWithLLM, llmLastError, pickAvailableModel, listModelIds } = require('./llm');
const { startUI } = require('./ui');
const { loadAuth } = require('./auth');
const { killLeftoverBrowsers } = require('./browser-cleanup');
const { newSessionId, removeOldSessions } = require('./session-folders');
const autostart = require('./autostart');
const { matchesRecipient, sweetbotDayKey, latestFromMeMs } = require('./her-chat');

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
const dayKeyAt = (ms) => sweetbotDayKey(ms, config.timezone, DAY_STARTS_AT);
const dayKey = () => dayKeyAt(Date.now());

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
function onChatActivity(fromMe, atMs = Date.now()) {
  if (fromMe && state.awakeOn !== dayKey()) {
    state.awakeOn = dayKey();
    saveState();
    log(`You texted ${config.recipientName} — bot starts for today.`, 'status');
  }
  if (state.awakeOn !== dayKey()) return;
  // The wait is measured from the message itself, so a text from this morning
  // is not treated as if it had just arrived.
  nextSendAt = Math.max(nextSendAt || 0, atMs + nextGapMs());
  if (nextSendAt <= Date.now()) {
    log('The usual wait after your message has already passed, so the next one goes out shortly.', 'status');
  } else {
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
  return { mode: 'running', text: nextSendAt ? `Next message around ${timeStr(nextSendAt)} (${roughlyWhen(nextSendAt)})` : 'Running' };
}

function roughlyWhen(ms) {
  const min = Math.round((ms - Date.now()) / 60000);
  if (min <= 1) return 'any moment now';
  if (min < 60) return `in about ${min} minutes`;
  const hours = Math.floor(min / 60);
  const rest = min % 60;
  if (!rest) return `in about ${hours} hour${hours === 1 ? '' : 's'}`;
  return `in about ${hours}h ${rest}m`;
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
  if (fromLLM) lastLLMError = {};
  if (config.llm?.enabled && !fromLLM) {
    error = friendlyLLMError(llmLastError());
    if (error !== lastLLMError.text || Date.now() - lastLLMError.t > 60e3) {
      log(`AI writer didn't work (${error}) — used a built-in message.`, 'error');
      lastLLMError = { text: error, t: Date.now() };
    }
  }
  return { parts: fromLLM || buildMessage(args), source: fromLLM ? 'AI' : 'built-in', error };
}

// Groq and the other hosts retire model names without notice. If the saved model
// is gone but another one we can use is listed, switch to it and remember that.
async function adoptWorkingModel() {
  const llm = config.llm;
  if (!llm?.enabled || !llm.baseUrl || !llm.model) return null;
  let ids;
  try {
    ids = await listModelIds(llm);
  } catch {
    return null; // offline or a host that has no model list: keep the saved setting
  }
  const next = pickAvailableModel(llm.model, ids);
  if (next === llm.model) return null;
  if (!next) {
    const text = `AI writer model "${llm.model}" is not offered by that server. Choose another in Settings.`;
    log(text, 'error');
    return text;
  }
  const from = llm.model;
  llm.model = next;
  if (/groq\.com/.test(llm.baseUrl) && !llm.reasoningEffort) llm.reasoningEffort = 'low';
  saveConfig({});
  const text = `"${from}" is no longer available, so the AI writer now uses ${next}.`;
  log(text, 'status');
  return text;
}

function friendlyLLMError(e = '') {
  if (/fetch failed|ECONNREFUSED/i.test(e)) return `can't reach ${config.llm.baseUrl} — is it running?`;
  if (/HTTP 401/.test(e)) return 'the API key was rejected';
  if (/HTTP 404|model.*(not found|does not exist)/i.test(e)) return `model "${config.llm.model}" not found`;
  if (/HTTP 429/.test(e)) return 'rate limit reached, try later';
  return e.replace(/^HTTP \d+ /, '').slice(0, 140) || 'unknown error';
}

async function sendParts(parts, source = 'bot') {
  const client = activeClient;
  const label = source === 'yours' ? 'Sent your message' : 'Sent';
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
    log(`${label}: ${part}`, 'sent');
    await sleep(rand(2000, 7000));
  }
}

// ---- Messages you write yourself ----------------------------------------------------
// Queued in a file so they survive a restart, and sent even while the bot is paused.
const outboxPath = path.join(__dirname, '.outbox.json');
const readOutbox = () => { try { return readJson(outboxPath).filter((t) => typeof t === 'string'); } catch { return []; } };
const MAX_OWN_MESSAGE = 1000;

function queueOwnMessage(text) {
  const clean = String(text || '').trim().slice(0, MAX_OWN_MESSAGE);
  if (!clean) throw new Error('Type the message first.');
  if (!hasNumber()) throw new Error('Add her number in Settings first.');
  fs.writeFileSync(outboxPath, JSON.stringify([...readOutbox(), clean]));
  log(`Queued your message: ${clean}`, 'status');
  return wa.state === 'ready' ? 'Sending it now.' : 'Saved — it goes out as soon as WhatsApp is connected.';
}

async function drainOutbox() {
  if (wa.state !== 'ready' || !activeClient) return;
  for (const text of readOutbox()) {
    try {
      await sendParts([text], 'yours');
    } catch (err) {
      log(`Could not send your message: ${err.message}`, 'error');
      return; // keep it queued and try again on the next round
    }
    fs.writeFileSync(outboxPath, JSON.stringify(readOutbox().filter((t) => t !== text)));
  }
}

// The last messages in her chat, oldest first, for the chat page.
async function conversation(limit = 60) {
  if (wa.state !== 'ready' || !activeClient || !hasNumber()) return { connected: false, messages: [] };
  const chat = await activeClient.getChatById(herChatId());
  const messages = await chat.fetchMessages({ limit });
  return {
    connected: true,
    messages: messages
      .filter((m) => m.body || m.hasMedia)
      .map((m) => ({ id: m.id?._serialized || m.id?.$1 || String(m.timestamp), fromMe: !!m.fromMe, text: m.body || '[attachment]', t: m.timestamp * 1000, ack: m.ack })),
  };
}

async function loop() {
  for (;;) {
    await sleep(DRY_RUN ? 300 : Number(process.env.SWEETBOT_POLL_MS) || 20000);
    await drainOutbox();
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
const sessionRoot = path.join(__dirname, '.wwebjs_auth');
const SHUTDOWN_TIMEOUT_MS = 10_000;
let currentClient = null; // being started or running; activeClient is set only once it is ready
let activeClient = null;
let waGeneration = 0; // goes up on every start, so late events from an older client are ignored
let loopStarted = false;
let restartTimer = null;
let relinking = false;
let stopping = false; // set once Stop is pressed, so nothing starts a new Chrome on the way out

// Closes a client's Chrome for certain: politely first, then by ending the process.
// A Chrome left behind keeps the session folder locked, and every later start fails.
async function shutDownClient(client) {
  if (!client) return;
  const chrome = client.pupBrowser?.process?.();
  try {
    await Promise.race([client.destroy(), sleep(SHUTDOWN_TIMEOUT_MS)]);
  } catch {}
  try {
    if (chrome && chrome.exitCode === null) chrome.kill();
  } catch {}
  if (activeClient === client) activeClient = null;
  if (currentClient === client) currentClient = null;
}

// Reconnect on its own: at PC start-up the internet may not be ready yet, and
// WhatsApp occasionally drops linked devices. If you unlinked it, a new QR appears.
function restartWhatsApp(client, delayMs) {
  if (restartTimer) return;
  log(`Reconnecting to WhatsApp in ${Math.round(delayMs / 1000)} seconds…`);
  restartTimer = setTimeout(async () => {
    restartTimer = null;
    const generation = waGeneration;
    await shutDownClient(client);
    if (generation === waGeneration) startWhatsApp(); // a relink in the meantime starts it instead
  }, delayMs);
}

async function forgetLink(client, wasLinked) {
  // Logging out tells WhatsApp to drop this PC from "Linked devices" on the phone.
  if (client && wasLinked) {
    try {
      await Promise.race([client.logout(), sleep(SHUTDOWN_TIMEOUT_MS)]);
    } catch {}
  }
  await shutDownClient(client);
  // A new folder rather than emptying the old one: Windows can keep that locked for a while.
  state.sessionId = newSessionId();
  saveState();
}

// If this client has neither shown a QR code nor become ready within the time
// given, start again on a fresh session folder: a stuck Chrome profile is the usual cause.
function watchFor(generation, client, ms, what) {
  setTimeout(() => {
    if (generation !== waGeneration || stopping || ['qr', 'ready'].includes(wa.state)) return;
    log(`${what} in ${Math.round(ms / 60000)} minute(s). Starting WhatsApp again…`, 'error');
    state.sessionId = newSessionId();
    saveState();
    restartWhatsApp(client, 1000);
  }, ms);
}

// A bug anywhere in the WhatsApp layer used to end the whole process with no trace.
function recoverFrom(kind, err) {
  log(`Sweetbot hit ${kind}: ${err?.stack?.split('\n').slice(0, 2).join(' ') || err}. Reconnecting…`, 'error');
  if (!stopping && !DRY_RUN) restartWhatsApp(currentClient, 5000);
}
process.on('unhandledRejection', (err) => recoverFrom('an unexpected error', err));
process.on('uncaughtException', (err) => recoverFrom('a crash', err));

// Forgets the current WhatsApp link and starts over, so the panel shows a new QR code.
function relinkWhatsApp() {
  if (DRY_RUN) return 'Preview mode — there is nothing to relink.';
  if (stopping) return 'The bot is stopping.';
  if (relinking) return 'Already relinking — the QR code will appear in a minute.';
  relinking = true;
  const client = currentClient;
  const wasLinked = wa.state === 'ready';
  waGeneration += 1;
  clearTimeout(restartTimer);
  restartTimer = null;
  Object.assign(wa, { state: 'starting', qr: null, error: null });
  log('Relinking WhatsApp — a new QR code will appear in a minute…', 'status');
  forgetLink(client, wasLinked)
    .catch((err) => log(`Could not clear the old WhatsApp link: ${err.message}`, 'error'))
    .finally(() => {
      relinking = false;
      startWhatsApp();
    });
  return 'Relinking — a new QR code will appear in a minute.';
}

async function startWhatsApp() {
  if (stopping) return;
  const generation = ++waGeneration;
  const isCurrent = () => generation === waGeneration;
  const { Client, LocalAuth } = require('whatsapp-web.js');
  const QRCode = require('qrcode');

  if (await killLeftoverBrowsers(sessionRoot)) log('Closed a leftover browser from an earlier run.');
  await removeOldSessions(sessionRoot, state.sessionId);
  if (!isCurrent() || stopping) return;

  const browser = findBrowser();
  log(`Starting WhatsApp Web${browser ? ` with ${path.basename(browser)}` : ''} — this can take a minute…`);

  // When WhatsApp logs this device out, the library wipes the profile folder while its
  // Chrome still holds it, which fails on Windows. We switch to a new folder instead.
  class KeepFolderAuth extends LocalAuth {
    async logout() {}
  }

  const client = new Client({
    authStrategy: new KeepFolderAuth({ clientId: state.sessionId || undefined, dataPath: sessionRoot }),
    puppeteer: { headless: true, executablePath: browser, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
    // Headless Chrome refuses WhatsApp Web's request for persistent storage, and WhatsApp
    // answers a later reload by logging the device out. Grant it before the page loads.
    evalOnNewDoc: () => {
      if (navigator.storage) {
        navigator.storage.persist = async () => true;
        navigator.storage.persisted = async () => true;
      }
    },
  });
  currentClient = client;
  const on = (event, handler) => client.on(event, (...args) => (isCurrent() ? handler(...args) : undefined));

  on('qr', async (qr) => {
    const image = await QRCode.toDataURL(qr, { width: 320, margin: 1 });
    if (!isCurrent()) return;
    wa.state = 'qr';
    wa.qr = image;
    status('Scan the QR code in the control panel to link WhatsApp.');
  });
  on('loading_screen', (percent) => status(`Loading WhatsApp… ${percent}%`));
  on('authenticated', () => {
    wa.state = 'linked';
    wa.qr = null;
    log('WhatsApp linked — finishing login…', 'status');
    const generation = waGeneration;
    setTimeout(() => {
      if (generation !== waGeneration || wa.state === 'ready' || stopping) return;
      log('WhatsApp did not finish loading. Reconnecting…', 'error');
      restartWhatsApp(client, 3000);
    }, 45000);
  });
  on('auth_failure', (m) => {
    wa.state = 'error';
    wa.error = `Login failed: ${m}`;
    log(wa.error, 'error');
  });
  on('disconnected', (reason) => {
    wa.qr = null;
    if (reason === 'LOGOUT') {
      wa.state = 'starting';
      wa.error = null;
      log('WhatsApp was unlinked from your phone — a new QR code will appear here.', 'error');
      state.sessionId = newSessionId(); // fresh folder; see KeepFolderAuth
      saveState();
      restartWhatsApp(client, 2000);
      return;
    }
    wa.state = 'disconnected';
    wa.error = `WhatsApp disconnected (${reason}).`;
    log(wa.error, 'error');
    restartWhatsApp(client, 15e3);
  });
  watchFor(generation, client, 180e3, 'WhatsApp Web did not open');

  const herIds = new Set();
  let herIdsFor = null;
  let resolvedHerIds = false;

  function trackHerId(id) {
    if (id) herIds.add(id);
  }

  // WhatsApp now addresses people with an extra id (@lid) that is not their phone
  // number. Remember every id we can resolve, and compare the phone number itself.
  async function rememberHerIds() {
    if (herIdsFor !== config.recipientNumber) {
      herIds.clear();
      herIdsFor = config.recipientNumber;
      resolvedHerIds = false;
    }
    trackHerId(herChatId());
    if (resolvedHerIds) return;
    try {
      const [row] = await client.getContactLidAndPhone([herChatId()]);
      trackHerId(row?.lid);
      trackHerId(row?.pn);
      resolvedHerIds = !!(row?.lid || row?.pn);
    } catch {}
  }

  async function isHerChat(msg) {
    await rememberHerIds();
    const other = msg.fromMe ? msg.to : msg.from;
    if (!other || String(other).endsWith('@g.us')) return false;
    if (herIds.has(other)) return true;
    try {
      const chat = await msg.getChat();
      if (chat.isGroup) return false;
      const contact = await chat.getContact();
      const known = matchesRecipient(
        [other, contact?.number, contact?.id?.user, contact?.id?._serialized, chat.id?.user, chat.id?._serialized],
        config.recipientNumber,
      );
      if (!known) {
        const [row] = await client.getContactLidAndPhone([chat.id?._serialized || other]);
        if (!matchesRecipient([row?.pn], config.recipientNumber)) return false;
        trackHerId(row?.lid);
        trackHerId(row?.pn);
      }
      trackHerId(other);
      trackHerId(chat.id?._serialized);
      return true;
    } catch {
      return false;
    }
  }

  // A good-morning text sent before the bot was watching, or one WhatsApp never
  // announced as a new event, is still sitting in the chat. Read it from there.
  async function catchUpOnHerChat() {
    if (!hasNumber() || awakeToday()) return;
    try {
      await rememberHerIds();
      let chat = null;
      for (const id of herIds) {
        try {
          chat = await client.getChatById(id);
          break;
        } catch {}
      }
      if (!chat) {
        log(`Couldn't open ${config.recipientName}'s chat to see if you already texted today.`, 'error');
        return;
      }
      trackHerId(chat.id?._serialized);
      const mine = await chat.fetchMessages({ limit: 20, fromMe: true });
      const at = latestFromMeMs(mine, (ms) => dayKeyAt(ms) === dayKey());
      if (!at) {
        log(`Checked ${config.recipientName}'s chat: none of your messages are from today yet.`, 'status');
        return;
      }
      onChatActivity(true, at);
    } catch (err) {
      log(`Couldn't check ${config.recipientName}'s chat for your message today: ${err.message}`, 'error');
    }
  }

  on('message_create', async (msg) => {
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

  on('ready', async () => {
    activeClient = client;
    wa.state = 'ready';
    wa.error = null;
    log('WhatsApp is ready.', 'status');
    if (!isCurrent()) return;
    await catchUpOnHerChat();
    if (!isCurrent() || loopStarted) return;
    loopStarted = true;
    loop();
  });

  try {
    await client.initialize();
  } catch (err) {
    if (!isCurrent()) return;
    const reason = err?.message || String(err);
    wa.state = 'error';
    wa.error = `Could not start WhatsApp Web: ${reason}`;
    // "already running" means a leftover browser holds the session folder: worth another try.
    if (/executable|browser|chrome|launch/i.test(reason) && !/net::|timeout|already running/i.test(reason)) {
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
      onSettingsSaved: adoptWorkingModel,
      log,
      getStatus: () => ({
        whatsapp: wa.state,
        qr: wa.qr,
        error: wa.error,
        bot: describe(),
        events: events.slice(-60).reverse(),
        preview: DRY_RUN,
        ai: {
          enabled: !!config.llm?.enabled,
          model: config.llm?.model || '',
          problem: config.llm?.enabled ? lastLLMError.text || '' : '',
        },
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
      relink: relinkWhatsApp,
      sendNow: queueOwnMessage,
      conversation,
      stop: () => {
        log('Stopping — bye!');
        stopping = true;
        waGeneration += 1;
        clearTimeout(restartTimer);
        shutDownClient(currentClient).finally(() => setTimeout(() => process.exit(0), 300));
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
  if (!loadAuth()) log('The control panel is locked until you set a password: double-click "Set Password" in the Sweetbot folder.', 'error');
  if (!NO_BROWSER) openInBrowser(url);
  await adoptWorkingModel();

  if (DRY_RUN) {
    log('Preview mode: messages are shown here, nothing is sent.', 'status');
    return loop();
  }
  startWhatsApp();
}

main();
