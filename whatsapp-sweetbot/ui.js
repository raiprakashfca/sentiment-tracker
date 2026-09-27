// Local control panel: a tiny web server on 127.0.0.1 that serves public/index.html
// and a JSON API. Only reachable from this PC, and only after logging in.

const http = require('http');
const fs = require('fs');
const path = require('path');
const { AUTH_PATH, COOKIE_NAME, loadAuth, verifyPassword, createSessionStore, createLoginThrottle, readCookie } = require('./auth');

const PAGE = path.join(__dirname, 'public', 'index.html');
const LOGIN_PAGE = path.join(__dirname, 'public', 'login.html');
const MAX_BODY_CHARS = 100_000;
const REQUEST_TIMEOUT_MS = 30_000;
const NO_PASSWORD_MESSAGE ='No password has been set yet. Double-click "Set Password" in the Sweetbot folder, then try again.';
const PAGE_HEADERS = {
  'Content-Type': 'text/html; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
};

function publicSettings(config) {
  return {
    recipientNumber: config.recipientNumber || '',
    recipientName: config.recipientName || '',
    timezone: config.timezone || '',
    minGapMinutes: config.minGapMinutes,
    maxGapMinutes: config.maxGapMinutes,
    bedtime: config.quietHours?.start ?? 23,
    startAfterMyFirstMessage: config.startAfterMyFirstMessage !== false,
    neverSay: config.myStyle?.neverSay || [],
    notes: config.myStyle?.notes || [],
    llm: {
      enabled: !!config.llm?.enabled,
      baseUrl: config.llm?.baseUrl || '',
      model: config.llm?.model || '',
      hasApiKey: !!config.llm?.apiKey, // the key itself never leaves this PC's config file
    },
  };
}

const clamp = (n, lo, hi, def) => (Number.isFinite(Number(n)) ? Math.min(hi, Math.max(lo, Number(n))) : def);
const cleanList = (list) =>
  (Array.isArray(list) ? list : String(list || '').split('\n'))
    .map((s) => String(s).trim())
    .filter(Boolean)
    .slice(0, 100);

function applySettings(config, body) {
  const number = String(body.recipientNumber ?? config.recipientNumber ?? '').replace(/\D/g, '');
  if (number && !/^\d{10,15}$/.test(number)) throw new Error('Her number should be 10–15 digits including the country code, e.g. 919812345678.');
  const timezone = String(body.timezone || config.timezone).trim();
  try {
    new Intl.DateTimeFormat('en-GB', { timeZone: timezone });
  } catch {
    throw new Error(`"${timezone}" is not a timezone. Try Asia/Kolkata.`);
  }
  let min = clamp(body.minGapMinutes, 10, 600, config.minGapMinutes);
  let max = clamp(body.maxGapMinutes, 10, 720, config.maxGapMinutes);
  if (min > max) [min, max] = [max, min];

  const llm = { ...(config.llm || {}) };
  if (body.llm) {
    llm.enabled = !!body.llm.enabled;
    if (body.llm.baseUrl) llm.baseUrl = String(body.llm.baseUrl).trim();
    if (body.llm.model) llm.model = String(body.llm.model).trim();
    if (body.llm.apiKey) llm.apiKey = String(body.llm.apiKey).trim();
    if (body.llm.clearApiKey) delete llm.apiKey;
    if (/groq\.com/.test(llm.baseUrl) && !llm.reasoningEffort) llm.reasoningEffort = 'low';
    if (llm.enabled && (!llm.baseUrl || !llm.model)) throw new Error('To use AI messages, fill in the server address and model.');
  }

  return {
    recipientNumber: number,
    recipientName: String(body.recipientName ?? config.recipientName).trim().slice(0, 40) || 'Shona',
    timezone,
    minGapMinutes: min,
    maxGapMinutes: max,
    quietHours: { ...config.quietHours, start: Math.round(clamp(body.bedtime, 18, 23, config.quietHours.start)) },
    startAfterMyFirstMessage: body.startAfterMyFirstMessage !== false,
    myStyle: { notes: cleanList(body.notes ?? config.myStyle?.notes), neverSay: cleanList(body.neverSay ?? config.myStyle?.neverSay) },
    llm,
  };
}

// The responders return true so the login gate can report "already answered".
function send(res, code, data, headers = {}) {
  res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...headers });
  res.end(JSON.stringify(data));
  return true;
}

function sendPage(res, file) {
  res.writeHead(200, PAGE_HEADERS);
  res.end(fs.readFileSync(file));
  return true;
}

function redirect(res, location) {
  res.writeHead(302, { Location: location, 'Cache-Control': 'no-store' });
  res.end();
  return true;
}

const httpError = (status, message) => Object.assign(new Error(message), { status });

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > MAX_BODY_CHARS) {
        req.removeAllListeners('data'); // whatever else arrives is thrown away, not stored
        reject(httpError(413, 'That request is too large.'));
      }
    });
    req.on('end', () => {
      try {
        const parsed = raw ? JSON.parse(raw) : {};
        // Handlers read fields off the body, so anything that is not a plain object counts as empty.
        resolve(parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {});
      } catch {
        reject(httpError(400, 'Bad request'));
      }
    });
    req.on('error', reject);
    req.on('close', () => reject(httpError(400, 'Bad request'))); // ignored if the body already arrived
  });
}

const sessionCookie = (token, maxAgeSeconds) =>
  `${COOKIE_NAME}=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${maxAgeSeconds}`;

// Answers login/logout and refuses everything else until logged in. The function it
// returns resolves to false only when the request may continue to the panel itself.
function createLoginGate({ authFile, log }) {
  const sessions = createSessionStore();
  const throttle = createLoginThrottle();

  function logIn(res, record, body) {
    if (!record) return send(res, 403, { error: NO_PASSWORD_MESSAGE });
    const waitMs = throttle.retryAfterMs();
    if (waitMs > 0) {
      return send(res, 429, { error: `Too many wrong passwords. Try again in ${Math.ceil(waitMs / 60000)} minutes.` });
    }
    if (!verifyPassword(body.password, record)) {
      throttle.recordFailure();
      log(
        throttle.retryAfterMs() > 0
          ? 'Too many wrong passwords at the control panel — login is locked for a while.'
          : 'Someone entered a wrong password at the control panel.',
        'error',
      );
      return send(res, 401, { error: 'Wrong password.' });
    }
    throttle.recordSuccess();
    const token = sessions.create(record.hash);
    return send(res, 200, { ok: true }, { 'Set-Cookie': sessionCookie(token, Math.floor(sessions.ttlMs / 1000)) });
  }

  return async function loginGate(req, res, url) {
    const record = loadAuth(authFile);
    const token = readCookie(req.headers.cookie, COOKIE_NAME);
    const loggedIn = !!record && sessions.isValid(token, record.hash);
    const route = `${req.method} ${url.pathname}`;

    if (route === 'GET /login') return loggedIn ? redirect(res, '/') : sendPage(res, LOGIN_PAGE);
    if (route === 'POST /api/login') return logIn(res, record, await readBody(req));
    if (route === 'POST /api/logout') {
      sessions.destroy(token);
      return send(res, 200, { ok: true }, { 'Set-Cookie': sessionCookie('', 0) });
    }
    if (loggedIn) return false;
    if (route === 'GET /') return redirect(res, '/login');
    return send(res, 401, { error: 'Log in first.' });
  };
}

function startUI({ port, config, saveConfig, getStatus, pause, resume, autostart, preview, stop, relink, authFile = AUTH_PATH, log = () => {} }) {
  const allowedHosts = new Set([`localhost:${port}`, `127.0.0.1:${port}`]);
  const loginGate = createLoginGate({ authFile, log });

  const server = http.createServer(async (req, res) => {
    // Block other websites from talking to the panel (DNS rebinding / cross-site requests).
    if (!allowedHosts.has(req.headers.host)) return send(res, 403, { error: 'Forbidden' });
    if (req.method === 'POST' && req.headers['x-sweetbot'] !== '1') return send(res, 403, { error: 'Forbidden' });

    try {
      const url = new URL(req.url, `http://${req.headers.host}`);
      if (await loginGate(req, res, url)) return;

      if (req.method === 'GET' && url.pathname === '/') return sendPage(res, PAGE);
      if (req.method === 'GET' && url.pathname === '/api/status') return send(res, 200, getStatus());
      if (req.method === 'GET' && url.pathname === '/api/settings') return send(res, 200, publicSettings(config));
      if (req.method === 'GET' && url.pathname === '/api/autostart') {
        return send(res, 200, { supported: autostart.supported, enabled: autostart.supported && autostart.get() });
      }

      if (req.method === 'POST') {
        const body = await readBody(req);
        switch (url.pathname) {
          case '/api/settings':
            saveConfig(applySettings(config, body));
            return send(res, 200, { ok: true, settings: publicSettings(config) });
          case '/api/pause':
            return send(res, 200, { ok: true, message: pause(body.minutes === 'today' ? 'today' : Number(body.minutes) || 'forever') });
          case '/api/autostart':
            return send(res, 200, { ok: true, enabled: autostart.set(!!body.enabled) });
          case '/api/resume':
            return send(res, 200, { ok: true, message: resume() });
          case '/api/preview':
            return send(res, 200, { ok: true, samples: await preview() });
          case '/api/relink':
            return send(res, 200, { ok: true, message: relink() });
          case '/api/stop':
            send(res, 200, { ok: true });
            return stop();
        }
      }
      send(res, 404, { error: 'Not found' });
    } catch (err) {
      if (!res.headersSent) send(res, err.status || 400, { error: err.message });
    }
  });
  server.requestTimeout = REQUEST_TIMEOUT_MS;

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

module.exports = { startUI, applySettings, publicSettings };
