// Builds short, varied messages that read like someone typing on their phone.

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const chance = (p) => Math.random() < p;

const openers = ['', '', '', 'hey', 'heyy', 'hii', 'oye', 'psst', 'hey you'];

const bodies = {
  morning: [
    'good morning {name}',
    'gm {name}',
    'morninggg',
    'woke up thinking about you',
    'hope you slept well',
    'have a good day okay',
  ],
  day: [
    'miss you',
    'missing you so much rn',
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
    'good night',
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

function buildMessage({ hour, name }) {
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

module.exports = { buildMessage, periodFor };
