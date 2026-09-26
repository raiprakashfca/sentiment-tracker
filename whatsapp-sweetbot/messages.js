// Builds short, varied messages that read like someone typing on their phone.
// If style.json exists (see learn-style.js), your own phrases and emoji are used.

const fs = require('fs');
const path = require('path');

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const chance = (p) => Math.random() < p;

const openers = ['', '', '', 'hey', 'heyy', 'hii', 'oye', 'psst', 'hey you'];

const bodies = {
  // No "good morning" here: you greet her yourself, and the bot starts after that.
  morning: [
    'woke up thinking about you',
    'had breakfast?',
    'hope you slept well',
    'have a good day okay',
  ],
  day: [
    'miss you',
    'missing you so much',
    'miss youuu',
    'thinking about you',
    'cant stop thinking about you',
    'wish you were here',
    'how is your day going',
    'did you eat?',
    'just wanted to say hi',
    'you are so cute you know that',
    'randomly smiling thinking about you',
    'counting the hours till i see you',
    'what are you up to',
    'i love you',
    'love youuu',
    'you there?',
  ],
  evening: [
    'miss you',
    'how was your day',
    'tired but missing you',
    'wish i could hug you right now',
    'cant wait to see you',
    'thinking about you',
    'love you',
  ],
  night: [
    'sleep well {name}',
    'good night {name}',
    'gn, love you',
    'sweet dreams',
    'miss you, sleep tight',
  ],
};

const emojiSets = [
  ['🥺'], ['❤️'], ['😘'], ['🥰'], ['💕'], ['😊'], ['🤗'], ['😚'], ['💖'], ['☺️'],
  ['❤️', '❤️'], ['🥺', '❤️'], ['😘', '😘'], ['🥰', '💕'], ['🙈'],
];

// A small chance of a follow-up "second text", which people do constantly.
const followUps = ['🥺', '❤️', 'hehe', 'thats it', 'okay bye 🙈', 'reply when free', '😘', 'just saying'];

function loadStyle() {
  const file = path.join(__dirname, 'style.json');
  if (!fs.existsSync(file)) return null;
  const style = JSON.parse(fs.readFileSync(file, 'utf8'));
  const all = Object.values(style.phrases).flat();
  if (!all.length) return null;
  // Phrases safe to send at any hour (no "good morning" at night).
  const TIMED = /morning|\bgm\b|\bgn\b|night|sleep|dream|tonight|today|your day|lunch|dinner|breakfast/i;
  return { ...style, all, anytime: all.filter((p) => !TIMED.test(p)) };
}

const style = loadStyle();

// Emoji picked in proportion to how often you actually use them.
function pickWeightedEmoji() {
  const entries = Object.entries(style.emoji);
  let r = Math.random() * entries.reduce((sum, [, n]) => sum + n, 0);
  for (const [e, n] of entries) if ((r -= n) < 0) return e;
  return entries[0][0];
}

function buildFromStyle(hour) {
  const own = style.phrases[periodFor(hour)];
  // Mostly phrases you used at this time of day, sometimes anything of yours.
  let text = !own.length || (style.anytime.length && chance(0.2)) ? pick(style.anytime.length ? style.anytime : style.all) : pick(own);
  if (chance(0.1)) text = stretchLastVowel(text);
  if (chance(style.lowercaseRatio)) text = text.toLowerCase();

  if (Object.keys(style.emoji).length && chance(style.emojiRate)) {
    const emojis = pickWeightedEmoji().repeat(chance(0.25) ? 2 : 1);
    text = chance(0.5) ? `${text} ${emojis}` : `${text}${emojis}`;
  }

  const parts = [text];
  if (chance(0.12)) parts.push(Object.keys(style.emoji).length ? pickWeightedEmoji() : pick(followUps));
  return parts;
}

function periodFor(hour) {
  if (hour >= 5 && hour < 11) return 'morning';
  if (hour >= 11 && hour < 18) return 'day';
  if (hour >= 18 && hour < 22) return 'evening';
  return 'night';
}

function stretchLastVowel(text) {
  // "miss you" -> "miss youuu" occasionally
  return text.replace(/([aeiouy])(\W*)$/i, (_, v, tail) => v.repeat(2 + Math.floor(Math.random() * 3)) + tail);
}

function styleCase(text) {
  if (chance(0.7)) return text.toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// True if text contains any banned word/phrase (whole words, any case), or a
// morning greeting (you send that one yourself).
function isBanned(text, neverSay = []) {
  const lower = text.toLowerCase();
  if (/good ?morning|\bgm\b/.test(lower)) return true;
  return neverSay.some((w) => new RegExp(`(^|[^\\p{L}])${w.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^\\p{L}])`, 'u').test(lower));
}

// With only a few learned phrases, mix in built-in ones so it doesn't loop the same lines.
const ownShare = style ? Math.min(0.9, style.all.length / 25) : 0;
const recent = [];

function buildMessage({ hour, name, neverSay }) {
  let parts;
  for (let tries = 0; tries < 20; tries++) {
    parts = chance(ownShare) && (style.phrases[periodFor(hour)].length || style.anytime.length)
      ? buildFromStyle(hour)
      : buildGeneric({ hour, name });
    if (parts.some((p) => isBanned(p, neverSay))) continue;
    const key = parts[0].replace(/\P{L}/gu, '').toLowerCase();
    // "hope you slept well" and "hey you hope you slept well" count as the same message.
    if (!recent.some((r) => r.includes(key) || key.includes(r))) {
      recent.push(key);
      if (recent.length > 6) recent.shift();
      break;
    }
  }
  return parts;
}

function buildGeneric({ hour, name }) {
  let body = pick(bodies[periodFor(hour)]).replace('{name}', name);
  if (chance(0.2)) body = stretchLastVowel(body);

  const opener = pick(openers);
  let text = opener && chance(0.4) ? `${opener} ${body}` : body;
  text = styleCase(text);

  if (chance(0.85)) {
    const emojis = pick(emojiSets).join('');
    text = chance(0.5) ? `${text} ${emojis}` : `${text}${emojis}`;
  }

  const parts = [text];
  if (chance(0.15)) parts.push(pick(followUps));
  return parts;
}

module.exports = { buildMessage, periodFor, isBanned };
