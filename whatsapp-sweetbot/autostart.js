// Start-with-Windows: drops a tiny hidden launcher (Sweetbot.vbs) into the user's
// Startup folder. No admin rights needed; removing the file turns it off.

const fs = require('fs');
const path = require('path');

const supported = () => process.platform === 'win32' && !!process.env.APPDATA;

const launcherPath = () =>
  path.join(process.env.APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'Sweetbot.vbs');

const vbsQuote = (s) => `""${s}""`; // a quote inside a VBScript string literal is doubled

function launcherScript() {
  const cmd = `${vbsQuote(process.execPath)} ${vbsQuote(path.join(__dirname, 'index.js'))} --no-browser`;
  return [
    "' Starts Sweetbot in the background when you log in. Delete this file to stop that.",
    'Set sh = CreateObject("WScript.Shell")',
    `sh.CurrentDirectory = "${__dirname}"`,
    `sh.Run "${cmd}", 0, False`,
    '',
  ].join('\r\n');
}

function isEnabled() {
  return supported() && fs.existsSync(launcherPath());
}

function setEnabled(on) {
  if (!supported()) throw new Error('Starting automatically is only set up for Windows.');
  const file = launcherPath();
  if (on) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    // UTF-16 with a BOM so Windows Script Host handles non-English folder names.
    fs.writeFileSync(file, Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(launcherScript(), 'utf16le')]));
  } else {
    fs.rmSync(file, { force: true });
  }
  return isEnabled();
}

module.exports = { supported, isEnabled, setEnabled, launcherScript, launcherPath };
