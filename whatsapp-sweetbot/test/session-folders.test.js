const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { newSessionId, sessionDir, removeOldSessions } = require('../session-folders');

const tempRoot = () => fs.mkdtempSync(path.join(os.tmpdir(), 'sb-sessions-'));
const makeDir = (root, name) => {
  fs.mkdirSync(path.join(root, name, 'Default'), { recursive: true });
  fs.writeFileSync(path.join(root, name, 'Default', 'data'), 'x');
};
const names = (root) => fs.readdirSync(root).sort();

test('with no id the folder is the one WhatsApp used before relinking existed', () => {
  assert.equal(sessionDir('root', undefined), path.join('root', 'session'));
});

test('an id gives the folder name the WhatsApp library will use for it', () => {
  assert.equal(sessionDir('root', 'abc123'), path.join('root', 'session-abc123'));
});

test('new ids are different each time and safe to use in a folder name', () => {
  const a = newSessionId();
  const b = newSessionId();
  assert.notEqual(a, b);
  assert.match(a, /^[a-z0-9]+$/);
});

test('removeOldSessions keeps the current folder and removes the other session folders', async () => {
  const root = tempRoot();
  for (const name of ['session', 'session-old1', 'session-current']) makeDir(root, name);
  const removed = await removeOldSessions(root, 'current');
  assert.deepEqual(removed.sort(), ['session', 'session-old1']);
  assert.deepEqual(names(root), ['session-current']);
});

test('removeOldSessions keeps the original folder when that is the current one', async () => {
  const root = tempRoot();
  for (const name of ['session', 'session-old1']) makeDir(root, name);
  await removeOldSessions(root, undefined);
  assert.deepEqual(names(root), ['session']);
});

test('removeOldSessions leaves anything that is not a session folder alone', async () => {
  const root = tempRoot();
  for (const name of ['session-current', 'session.before-relink-2026-09-27', 'sessions', 'notes']) makeDir(root, name);
  fs.writeFileSync(path.join(root, 'session-file.txt'), 'x');
  await removeOldSessions(root, 'current');
  assert.deepEqual(names(root), ['notes', 'session-current', 'session-file.txt', 'session.before-relink-2026-09-27', 'sessions']);
});

test('removeOldSessions copes with a missing root folder', async () => {
  assert.deepEqual(await removeOldSessions(path.join(tempRoot(), 'nope'), 'current'), []);
});
