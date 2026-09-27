// Each WhatsApp link lives in its own Chrome profile folder. Relinking switches to a
// brand-new folder instead of emptying the old one, because Windows can keep a folder
// locked for a minute or more after its Chrome has gone. Old folders are removed later.

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const ID_BYTES = 6;
const SESSION_FOLDER = /^session(-[-_\w]+)?$/; // "session" or "session-<id>", as the library names them

const newSessionId = () => crypto.randomBytes(ID_BYTES).toString('hex');

const folderName = (id) => (id ? `session-${id}` : 'session');

const sessionDir = (root, id) => path.join(root, folderName(id));

// Resolves to the names it removed. A folder that is still locked is simply left for next time.
async function removeOldSessions(root, currentId) {
  let entries;
  try {
    entries = await fs.promises.readdir(root, { withFileTypes: true });
  } catch {
    return [];
  }
  const old = entries.filter((e) => e.isDirectory() && SESSION_FOLDER.test(e.name) && e.name !== folderName(currentId));
  const removed = await Promise.all(
    old.map((e) =>
      fs.promises
        .rm(path.join(root, e.name), { recursive: true, force: true, maxRetries: 3, retryDelay: 300 })
        .then(() => e.name)
        .catch(() => null),
    ),
  );
  return removed.filter(Boolean);
}

module.exports = { newSessionId, sessionDir, removeOldSessions };
