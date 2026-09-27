// Sets or changes the control-panel password.
//   node set-password.js            asks for it (typing stays hidden)
//   <something> | node set-password.js   reads it from the pipe

const { savePassword, MIN_PASSWORD_LENGTH } = require('./auth');

const CTRL_C = '\u0003';
const BACKSPACES = new Set(['\b', '\u007f']);

function askHidden(prompt) {
  return new Promise((resolve, reject) => {
    const { stdin, stdout } = process;
    let typed = '';
    const finish = () => {
      stdin.setRawMode(false);
      stdin.pause();
      stdin.off('data', onData);
      stdout.write('\n');
    };
    const onData = (chunk) => {
      for (const ch of chunk) {
        if (ch === '\r' || ch === '\n') {
          finish();
          return resolve(typed);
        }
        if (ch === CTRL_C) {
          finish();
          return reject(new Error('Cancelled — the password was not changed.'));
        }
        typed = BACKSPACES.has(ch) ? typed.slice(0, -1) : typed + ch;
      }
    };
    stdout.write(prompt);
    stdin.setRawMode(true);
    stdin.setEncoding('utf8');
    stdin.resume();
    stdin.on('data', onData);
  });
}

function readPipe() {
  return new Promise((resolve, reject) => {
    let raw = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => (raw += chunk));
    process.stdin.on('end', () => resolve(raw.replace(/\r?\n$/, '')));
    process.stdin.on('error', reject);
  });
}

async function askTwice() {
  const first = await askHidden(`New password (at least ${MIN_PASSWORD_LENGTH} characters): `);
  const second = await askHidden('Type it again: ');
  if (first !== second) throw new Error('The two passwords did not match — nothing was changed.');
  return first;
}

async function main() {
  const password = process.stdin.isTTY ? await askTwice() : await readPipe();
  savePassword(password);
  console.log('Password saved. Anyone already logged in to the control panel has been signed out.');
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
