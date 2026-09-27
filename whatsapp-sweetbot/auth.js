// Password login for the control panel. Only a salted scrypt hash is kept on disk
// (.auth.json) — the password itself is never stored.

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const AUTH_PATH = path.join(__dirname, '.auth.json');
const COOKIE_NAME = 'sb_session';

const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_LENGTH = 200;
const SESSION_TTL_MS = 12 * 60 * 60 * 1000;
const MAX_FAILED_ATTEMPTS = 5;
const LOCKOUT_MS = 15 * 60 * 1000;

const SALT_BYTES = 16;
const HASH_BYTES = 64;
const TOKEN_BYTES = 32;

function hashPassword(password) {
  if (typeof password !== 'string' || password.length < MIN_PASSWORD_LENGTH) {
    throw new Error(`The password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
  }
  if (password.length > MAX_PASSWORD_LENGTH) {
    throw new Error(`The password must be at most ${MAX_PASSWORD_LENGTH} characters.`);
  }
  const salt = crypto.randomBytes(SALT_BYTES);
  const hash = crypto.scryptSync(password, salt, HASH_BYTES);
  return { salt: salt.toString('hex'), hash: hash.toString('hex') };
}

function verifyPassword(password, record) {
  if (!record || typeof password !== 'string' || !password || password.length > MAX_PASSWORD_LENGTH) return false;
  const expected = Buffer.from(record.hash, 'hex');
  const actual = crypto.scryptSync(password, Buffer.from(record.salt, 'hex'), expected.length);
  return crypto.timingSafeEqual(actual, expected);
}

const isHex = (value, bytes) => typeof value === 'string' && new RegExp(`^[0-9a-f]{${bytes * 2}}$`).test(value);

function loadAuth(file = AUTH_PATH) {
  try {
    const record = JSON.parse(fs.readFileSync(file, 'utf8'));
    return isHex(record.salt, SALT_BYTES) && isHex(record.hash, HASH_BYTES) ? { salt: record.salt, hash: record.hash } : null;
  } catch {
    return null;
  }
}

function savePassword(password, file = AUTH_PATH) {
  const record = hashPassword(password);
  fs.writeFileSync(file, JSON.stringify(record) + '\n', { mode: 0o600 });
  return record;
}

// Sessions live in memory only, so restarting the bot signs everyone out.
// Each one is tied to the password hash it was created under.
function createSessionStore({ ttlMs = SESSION_TTL_MS, now = Date.now } = {}) {
  const sessions = new Map();
  const dropExpired = () => {
    for (const [token, session] of sessions) if (now() >= session.expiresAt) sessions.delete(token);
  };
  return {
    ttlMs,
    create(passwordHash) {
      dropExpired();
      const token = crypto.randomBytes(TOKEN_BYTES).toString('hex');
      sessions.set(token, { expiresAt: now() + ttlMs, passwordHash });
      return token;
    },
    isValid(token, passwordHash) {
      const session = typeof token === 'string' ? sessions.get(token) : undefined;
      if (!session) return false;
      if (now() >= session.expiresAt || session.passwordHash !== passwordHash) {
        sessions.delete(token);
        return false;
      }
      return true;
    },
    destroy(token) {
      sessions.delete(token);
    },
  };
}

// One shared counter rather than per-visitor: the panel only listens on 127.0.0.1,
// so every visitor has the same address.
function createLoginThrottle({ maxAttempts = MAX_FAILED_ATTEMPTS, lockoutMs = LOCKOUT_MS, now = Date.now } = {}) {
  let failures = 0;
  let lockedUntil = 0;
  return {
    retryAfterMs: () => Math.max(0, lockedUntil - now()),
    recordFailure() {
      failures += 1;
      if (failures >= maxAttempts) {
        failures = 0;
        lockedUntil = now() + lockoutMs;
      }
    },
    recordSuccess() {
      failures = 0;
      lockedUntil = 0;
    },
  };
}

function readCookie(header, name) {
  for (const part of String(header || '').split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return rest.join('=');
  }
  return undefined;
}

module.exports = {
  AUTH_PATH,
  COOKIE_NAME,
  MIN_PASSWORD_LENGTH,
  hashPassword,
  verifyPassword,
  loadAuth,
  savePassword,
  createSessionStore,
  createLoginThrottle,
  readCookie,
};
