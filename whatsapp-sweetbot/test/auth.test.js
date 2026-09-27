const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  hashPassword,
  verifyPassword,
  savePassword,
  loadAuth,
  createSessionStore,
  createLoginThrottle,
  readCookie,
  MIN_PASSWORD_LENGTH,
} = require('../auth');

const tempFile = () => path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'sb-auth-')), '.auth.json');

test('verifyPassword accepts the password that was hashed', () => {
  const record = hashPassword('correct horse battery');
  assert.equal(verifyPassword('correct horse battery', record), true);
});

test('verifyPassword rejects a wrong password', () => {
  const record = hashPassword('correct horse battery');
  assert.equal(verifyPassword('correct horse batterx', record), false);
});

test('verifyPassword rejects when no password has been set', () => {
  assert.equal(verifyPassword('anything at all', null), false);
});

test('hashPassword never stores the password itself and salts every hash', () => {
  const a = hashPassword('correct horse battery');
  const b = hashPassword('correct horse battery');
  assert.ok(!JSON.stringify(a).includes('correct horse battery'));
  assert.notEqual(a.hash, b.hash);
});

test('hashPassword refuses passwords shorter than the minimum', () => {
  assert.throws(() => hashPassword('x'.repeat(MIN_PASSWORD_LENGTH - 1)), /at least/);
});

test('savePassword writes a record that loadAuth reads back', () => {
  const file = tempFile();
  savePassword('correct horse battery', file);
  assert.equal(verifyPassword('correct horse battery', loadAuth(file)), true);
});

test('loadAuth returns null when the file is missing or damaged', () => {
  const file = tempFile();
  assert.equal(loadAuth(file), null);
  fs.writeFileSync(file, 'not json');
  assert.equal(loadAuth(file), null);
});

test('a session is valid until it expires', () => {
  let clock = 1000;
  const sessions = createSessionStore({ ttlMs: 500, now: () => clock });
  const token = sessions.create('hash-a');
  assert.equal(sessions.isValid(token, 'hash-a'), true);
  clock += 500;
  assert.equal(sessions.isValid(token, 'hash-a'), false);
});

test('a session stops working once the password changes', () => {
  const sessions = createSessionStore();
  const token = sessions.create('hash-a');
  assert.equal(sessions.isValid(token, 'hash-b'), false);
});

test('unknown, empty and destroyed tokens are not valid sessions', () => {
  const sessions = createSessionStore();
  const token = sessions.create('hash-a');
  sessions.destroy(token);
  assert.equal(sessions.isValid(token, 'hash-a'), false);
  assert.equal(sessions.isValid('made-up', 'hash-a'), false);
  assert.equal(sessions.isValid(undefined, 'hash-a'), false);
});

test('throttle locks after too many failures and unlocks after the lockout', () => {
  let clock = 0;
  const throttle = createLoginThrottle({ maxAttempts: 3, lockoutMs: 1000, now: () => clock });
  throttle.recordFailure();
  throttle.recordFailure();
  assert.equal(throttle.retryAfterMs(), 0);
  throttle.recordFailure();
  assert.equal(throttle.retryAfterMs(), 1000);
  clock += 1000;
  assert.equal(throttle.retryAfterMs(), 0);
});

test('a successful login resets the failure count', () => {
  const throttle = createLoginThrottle({ maxAttempts: 2, lockoutMs: 1000 });
  throttle.recordFailure();
  throttle.recordSuccess();
  throttle.recordFailure();
  assert.equal(throttle.retryAfterMs(), 0);
});

test('readCookie finds one cookie among several', () => {
  assert.equal(readCookie('a=1; sb_session=abc123; b=2', 'sb_session'), 'abc123');
  assert.equal(readCookie('a=1', 'sb_session'), undefined);
  assert.equal(readCookie(undefined, 'sb_session'), undefined);
});
