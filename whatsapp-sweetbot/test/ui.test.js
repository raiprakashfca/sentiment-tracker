const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');

const { startUI } = require('../ui');
const { savePassword } = require('../auth');

const PASSWORD = 'test-only-password';

const freePort = () =>
  new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });

async function startPanel({ withPassword = true } = {}) {
  const port = await freePort();
  const authFile = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'sb-ui-')), '.auth.json');
  if (withPassword) savePassword(PASSWORD, authFile);
  const calls = { stop: 0, relink: 0 };
  const config = { quietHours: { start: 23, end: 8 }, timezone: 'Asia/Kolkata', minGapMinutes: 25, maxGapMinutes: 95, llm: { apiKey: 'secret-key' } };
  const server = await startUI({
    port,
    authFile,
    relink: () => {
      calls.relink += 1;
      return 'Relinking.';
    },
    sendNow: (text) => {
      calls.sent = text;
      return 'Sending it now.';
    },
    config,
    saveConfig: (patch) => Object.assign(config, patch),
    getStatus: () => ({ whatsapp: 'ready', qr: null }),
    pause: () => 'Paused.',
    resume: () => 'Resumed.',
    autostart: { supported: false, get: () => false, set: () => false },
    preview: async () => [],
    stop: () => { calls.stop += 1; },
  });
  const base = `http://localhost:${port}`;
  const post = (route, body, headers = {}) =>
    fetch(base + route, {
      method: 'POST',
      redirect: 'manual',
      headers: { 'Content-Type': 'application/json', 'X-Sweetbot': '1', ...headers },
      body: JSON.stringify(body),
    });
  const get = (route, headers = {}) => fetch(base + route, { redirect: 'manual', headers });
  const login = async (password = PASSWORD) => {
    const res = await post('/api/login', { password });
    const cookie = (res.headers.get('set-cookie') || '').split(';')[0];
    return { res, cookie };
  };
  return { server, authFile, calls, get, post, login, close: () => new Promise((r) => server.close(r)) };
}

test('the panel page redirects to the login page when not logged in', async () => {
  const panel = await startPanel();
  try {
    const res = await panel.get('/');
    assert.equal(res.status, 302);
    assert.equal(res.headers.get('location'), '/login');
  } finally {
    await panel.close();
  }
});

test('every API route refuses requests that are not logged in', async () => {
  const panel = await startPanel();
  try {
    for (const route of ['/api/status', '/api/settings', '/api/autostart']) {
      assert.equal((await panel.get(route)).status, 401, `GET ${route}`);
    }
    for (const route of ['/api/settings', '/api/pause', '/api/resume', '/api/preview', '/api/autostart', '/api/stop', '/api/relink', '/api/send']) {
      assert.equal((await panel.post(route, {})).status, 401, `POST ${route}`);
    }
    assert.equal(panel.calls.stop, 0);
    assert.equal(panel.calls.relink, 0);
  } finally {
    await panel.close();
  }
});

test('a forged session cookie is refused', async () => {
  const panel = await startPanel();
  try {
    const res = await panel.get('/api/status', { Cookie: 'sb_session=' + 'a'.repeat(64) });
    assert.equal(res.status, 401);
  } finally {
    await panel.close();
  }
});

test('the login page is reachable without logging in', async () => {
  const panel = await startPanel();
  try {
    const res = await panel.get('/login');
    assert.equal(res.status, 200);
    assert.match(res.headers.get('content-type'), /text\/html/);
  } finally {
    await panel.close();
  }
});

test('a wrong password is refused and sets no cookie', async () => {
  const panel = await startPanel();
  try {
    const { res, cookie } = await panel.login('wrong-password');
    assert.equal(res.status, 401);
    assert.equal(cookie, '');
  } finally {
    await panel.close();
  }
});

test('the right password opens the panel and the API', async () => {
  const panel = await startPanel();
  try {
    const { res, cookie } = await panel.login();
    assert.equal(res.status, 200);
    assert.match(res.headers.get('set-cookie'), /HttpOnly/);
    assert.match(res.headers.get('set-cookie'), /SameSite=Strict/);
    assert.equal((await panel.get('/', { Cookie: cookie })).status, 200);
    const status = await panel.get('/api/status', { Cookie: cookie });
    assert.equal(status.status, 200);
    assert.equal((await status.json()).whatsapp, 'ready');
  } finally {
    await panel.close();
  }
});

test('relinking WhatsApp works once logged in', async () => {
  const panel = await startPanel();
  try {
    const { cookie } = await panel.login();
    const res = await panel.post('/api/relink', {}, { Cookie: cookie });
    assert.equal(res.status, 200);
    assert.equal((await res.json()).message, 'Relinking.');
    assert.equal(panel.calls.relink, 1);
  } finally {
    await panel.close();
  }
});

test('the chat page and its messages need a login', async () => {
  const panel = await startPanel();
  try {
    assert.equal((await panel.get('/chat')).status, 302);
    assert.equal((await panel.get('/api/chat')).status, 401);
    const { cookie } = await panel.login();
    assert.equal((await panel.get('/chat', { Cookie: cookie })).status, 200);
    const res = await panel.get('/api/chat', { Cookie: cookie });
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { connected: false, messages: [] });
  } finally {
    await panel.close();
  }
});

test('automatic messages can be switched off and the setting is reported back', async () => {
  const panel = await startPanel();
  try {
    const { cookie } = await panel.login();
    const res = await panel.post('/api/settings', { automaticMessages: false, timezone: 'Asia/Kolkata' }, { Cookie: cookie });
    assert.equal(res.status, 200);
    assert.equal((await res.json()).settings.automaticMessages, false);
  } finally {
    await panel.close();
  }
});

test('a logged-in user can send an exact message', async () => {
  const panel = await startPanel();
  try {
    const { cookie } = await panel.login();
    const res = await panel.post('/api/send', { text: 'hello there' }, { Cookie: cookie });
    assert.equal(res.status, 200);
    assert.equal(panel.calls.sent, 'hello there');
  } finally {
    await panel.close();
  }
});

test('logging out ends the session', async () => {
  const panel = await startPanel();
  try {
    const { cookie } = await panel.login();
    assert.equal((await panel.post('/api/logout', {}, { Cookie: cookie })).status, 200);
    assert.equal((await panel.get('/api/status', { Cookie: cookie })).status, 401);
  } finally {
    await panel.close();
  }
});

test('changing the password signs out existing sessions', async () => {
  const panel = await startPanel();
  try {
    const { cookie } = await panel.login();
    savePassword('a-different-password', panel.authFile);
    assert.equal((await panel.get('/api/status', { Cookie: cookie })).status, 401);
  } finally {
    await panel.close();
  }
});

test('with no password set the panel stays locked', async () => {
  const panel = await startPanel({ withPassword: false });
  try {
    assert.equal((await panel.get('/api/status')).status, 401);
    const { res, cookie } = await panel.login('anything-at-all');
    assert.equal(res.status, 403);
    assert.equal(cookie, '');
  } finally {
    await panel.close();
  }
});

test('repeated wrong passwords lock the login, even for the right password', async () => {
  const panel = await startPanel();
  try {
    for (let i = 0; i < 5; i++) await panel.login('wrong-password');
    const { res, cookie } = await panel.login();
    assert.equal(res.status, 429);
    assert.equal(cookie, '');
  } finally {
    await panel.close();
  }
});

test('a login body that is not an object is treated as a wrong password', async () => {
  const panel = await startPanel();
  try {
    for (const body of [null, 42, 'text', []]) {
      const res = await panel.post('/api/login', body);
      assert.equal(res.status, 401, JSON.stringify(body));
      assert.equal((await res.json()).error, 'Wrong password.');
    }
  } finally {
    await panel.close();
  }
});

test('an oversized request is refused instead of left hanging', async () => {
  const panel = await startPanel();
  try {
    const res = await panel.post('/api/login', { password: 'x'.repeat(150_000) });
    assert.equal(res.status, 413);
  } finally {
    await panel.close();
  }
});

test('the login route still needs the anti-forgery header', async () => {
  const panel = await startPanel();
  try {
    const res = await panel.post('/api/login', { password: PASSWORD }, { 'X-Sweetbot': '0' });
    assert.equal(res.status, 403);
  } finally {
    await panel.close();
  }
});
