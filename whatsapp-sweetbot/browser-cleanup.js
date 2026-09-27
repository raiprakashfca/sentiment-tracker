// A headless Chrome left behind by a crash or a forced stop keeps the WhatsApp session
// folder locked, so no new Chrome can use it. This finds those and ends them.

const { execFile } = require('child_process');

const BROWSER_NAMES = ['chrome.exe', 'msedge.exe'];
const TIMEOUT_MS = 20_000;

// The folder reaches PowerShell through the environment, never inside the command text,
// so a folder name with quotes or spaces cannot change what the command does.
const SCRIPT = [
  '$dir = $env:SWEETBOT_SESSION_DIR',
  "$names = $env:SWEETBOT_BROWSER_NAMES -split ','",
  '$found = @(Get-CimInstance Win32_Process | Where-Object {',
  "  $names -contains $_.Name -and $_.CommandLine -and $_.CommandLine.Contains('--user-data-dir') -and $_.CommandLine.Contains($dir)",
  '})',
  '$found | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }',
  '$found.Count',
].join('\n');

// Resolves to how many processes were ended. Never rejects: failing to clean up
// must not stop the bot from trying to start.
function killLeftoverBrowsers(sessionDir, { names = BROWSER_NAMES } = {}) {
  if (process.platform !== 'win32') return Promise.resolve(0);
  const env = { ...process.env, SWEETBOT_SESSION_DIR: sessionDir, SWEETBOT_BROWSER_NAMES: names.join(',') };
  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', SCRIPT],
      { env, windowsHide: true, timeout: TIMEOUT_MS },
      (err, stdout) => resolve(err ? 0 : Number(String(stdout).trim()) || 0),
    );
  });
}

module.exports = { killLeftoverBrowsers };
