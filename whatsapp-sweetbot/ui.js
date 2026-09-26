// Local control panel: a tiny web server on 127.0.0.1 that serves public/index.html
// and a JSON API. Only reachable from this PC.

const http = require('http');
const fs = require('fs');
const path = require('path');

const PAGE = path.join(__dirname, 'public', 'index.html');

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

function startUI({ port, config, saveConfig, getStatus, pause, resume, autostart, preview, stop }) {
  const allowedHosts = new Set([`localhost:${port}`, `127.0.0.1:${port}`]);

  const send = (res, code, data) => {
    res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(data));
  };

  const readBody = (req) =>
    new Promise((resolve, reject) => {
      let raw = '';
      req.on('data', (c) => {
        raw += c;
        if (raw.length > 100_000) req.destroy();
      });
      req.on('end', () => {
        try {
          resolve(raw ? JSON.parse(raw) : {});
        } catch {
          reject(new Error('Bad request'));
        }
      });
    });

  const server = http.createServer(async (req, res) => {
    // Block other websites from talking to the panel (DNS rebinding / cross-site requests).
    if (!allowedHosts.has(req.headers.host)) return send(res, 403, { error: 'Forbidden' });
    if (req.method === 'POST' && req.headers['x-sweetbot'] !== '1') return send(res, 403, { error: 'Forbidden' });

    try {
      const url = new URL(req.url, `http://${req.headers.host}`);
      if (req.method === 'GET' && url.pathname === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        return res.end(fs.readFileSync(PAGE));
      }
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
          case '/api/stop':
            send(res, 200, { ok: true });
            return stop();
        }
      }
      send(res, 404, { error: 'Not found' });
    } catch (err) {
      send(res, 400, { error: err.message });
    }
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

module.exports = { startUI, applySettings, publicSettings };
