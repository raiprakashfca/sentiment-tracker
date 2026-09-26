// Learns your texting style from an exported WhatsApp chat and writes style.json.
// Usage: node learn-style.js <chat.txt> "<your name as it appears in the export>"
//
// Only your own short, affectionate messages are kept. Review style.json afterwards
// and delete anything you wouldn't want re-sent out of context.

const fs = require('fs');
const path = require('path');
const { periodFor } = require('./messages');

const [file, me] = process.argv.slice(2);
if (!file) {
  console.error('Usage: node learn-style.js <chat.txt> "<your name>"');
  process.exit(1);
}

// Android: "26/09/2026, 14:03 - Name: text"   iOS: "[26/09/26, 2:03:04 PM] Name: text"
const LINE = /^\[?(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}),?\s+(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp]\.?\s?[Mm]\.?)?\]?\s*(?:-\s*)?([^:]+?):\s(.*)$/;

const messages = [];
for (const raw of fs.readFileSync(file, 'utf8').replace(/‎/g, '').split(/\r?\n/)) {
  const m = raw.match(LINE);
  if (m) {
    let hour = Number(m[2]) % 24;
    const ampm = m[4] && m[4].toLowerCase()[0];
    if (ampm === 'p' && hour < 12) hour += 12;
    if (ampm === 'a' && hour === 12) hour = 0;
    messages.push({ sender: m[5].trim(), hour, text: m[6].trim() });
  } else if (messages.length && raw.trim()) {
    messages[messages.length - 1].text += '\n' + raw.trim(); // continuation of a multi-line message
  }
}

if (!messages.length) {
  console.error('No messages found. Is this a WhatsApp "Export chat" .txt file?');
  process.exit(1);
}

const senders = [...new Set(messages.map((m) => m.sender))];
if (!me || !senders.includes(me)) {
  console.error(`Tell me which sender is you. Senders in this chat:\n  ${senders.join('\n  ')}`);
  process.exit(1);
}

const EMOJI = /\p{Extended_Pictographic}(️)?/gu;
const AFFECTION = new RegExp(
  [
    'miss', 'love', 'luv', 'cute', 'baby', 'babe', 'bby', 'jaan', 'jaanu', 'shona', 'yaad', 'pyaar', 'pyar',
    'hug', 'kiss', 'good ?morning', '\\bgm\\b', '\\bgn\\b', 'good ?night', 'sleep', 'dream', 'thinking',
    'wish', 'see you', 'beautiful', 'sweet', '\\bhi+\\b', '\\bhe+y+\\b', 'how are', 'your day', 'did you eat',
    'khana', 'care', 'mine', 'heart',
  ].join('|'),
  'i',
);
const SKIP = /omitted|deleted|<media|https?:\/\/|\d{4,}|@|edited>|null$/i;

const mine = messages.filter((m) => m.sender === me);
const phrases = { morning: new Set(), day: new Set(), evening: new Set(), night: new Set() };
const emojiCounts = {};
let lower = 0;
let cased = 0;

for (const { text, hour } of mine) {
  for (const e of text.match(EMOJI) || []) emojiCounts[e] = (emojiCounts[e] || 0) + 1;

  const plain = text.replace(EMOJI, '').trim();
  if (/[a-z]/i.test(plain)) (plain === plain.toLowerCase() ? lower++ : cased++);

  if (SKIP.test(text) || text.includes('\n') || plain.length < 2 || plain.length > 70) continue;
  if (!AFFECTION.test(plain)) continue;
  phrases[periodFor(hour)].add(plain);
}

const topEmoji = Object.entries(emojiCounts)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 15);

const style = {
  learnedFrom: path.basename(file),
  lowercaseRatio: lower + cased ? Number((lower / (lower + cased)).toFixed(2)) : 0.7,
  emojiRate: mine.length
    ? Number((mine.filter((m) => m.text.match(EMOJI)).length / mine.length).toFixed(2))
    : 0.85,
  emoji: Object.fromEntries(topEmoji),
  phrases: Object.fromEntries(Object.entries(phrases).map(([k, v]) => [k, [...v]])),
};

fs.writeFileSync(path.join(__dirname, 'style.json'), JSON.stringify(style, null, 2));

const counts = Object.entries(style.phrases).map(([k, v]) => `${k}: ${v.length}`).join(', ');
console.log(`Read ${mine.length} of your messages.`);
console.log(`Phrases kept — ${counts}`);
console.log(`Favourite emoji: ${topEmoji.map(([e]) => e).join(' ') || '(none)'}`);
console.log(`Lowercase: ${Math.round(style.lowercaseRatio * 100)}%, messages with emoji: ${Math.round(style.emojiRate * 100)}%`);
console.log('\nWrote style.json — open it and delete any phrase you would not want re-sent.');
