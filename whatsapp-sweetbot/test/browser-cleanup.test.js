const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const { killLeftoverBrowsers } = require('../browser-cleanup');

const onWindows = process.platform === 'win32';
const IDLE = 'setTimeout(() => {}, 60000)';

const waitForExit = (child, ms) =>
  new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) return resolve(true);
    child.once('exit', () => resolve(true));
    setTimeout(() => resolve(false), ms);
  });

// Stands in for a headless Chrome: a process whose command line names the folder.
// The "--" stops Node treating the flag as one of its own options and exiting.
const startStandIn = (dir) => spawn(process.execPath, ['-e', IDLE, '--', `--user-data-dir=${dir}`], { stdio: 'ignore' });

test('ends a process that still holds the session folder', { skip: !onWindows }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sb-session-'));
  const standIn = startStandIn(dir);
  try {
    const ended = await killLeftoverBrowsers(dir, { names: ['node.exe'] });
    assert.equal(ended, 1);
    assert.equal(await waitForExit(standIn, 5000), true);
  } finally {
    standIn.kill();
  }
});

test('leaves processes using a different folder alone', { skip: !onWindows }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sb-session-'));
  const other = fs.mkdtempSync(path.join(os.tmpdir(), 'sb-other-'));
  const bystander = startStandIn(other);
  try {
    const ended = await killLeftoverBrowsers(dir, { names: ['node.exe'] });
    assert.equal(ended, 0);
    assert.equal(await waitForExit(bystander, 1000), false);
  } finally {
    bystander.kill();
  }
});

test('does nothing on systems other than Windows', { skip: onWindows }, async () => {
  assert.equal(await killLeftoverBrowsers('/tmp/anything'), 0);
});
