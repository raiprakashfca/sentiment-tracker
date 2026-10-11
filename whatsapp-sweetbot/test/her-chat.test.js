const test = require('node:test');
const assert = require('node:assert/strict');
const { matchesRecipient, sweetbotDayKey, latestFromMeMs } = require('../her-chat');

test('a phone number matches the saved number, a lid does not', () => {
  const her = '919812345678';
  assert.equal(matchesRecipient(['919812345678@c.us', '15551212@lid'], her), true);
  assert.equal(matchesRecipient(['15551212@lid'], her), false);
  assert.equal(matchesRecipient('919812345678', her), true);
});

test('the day starts at 4am in the configured timezone', () => {
  const tz = 'Asia/Kolkata';
  // 28 Sep 2026, 3:30am IST is still the previous Sweetbot day.
  assert.equal(sweetbotDayKey(Date.parse('2026-09-27T22:00:00.000Z'), tz), '2026-09-27');
  // 28 Sep 2026, 8:00am IST is the new day.
  assert.equal(sweetbotDayKey(Date.parse('2026-09-28T02:30:00.000Z'), tz), '2026-09-28');
});

test('only your own messages from this Sweetbot day count', () => {
  const tz = 'Asia/Kolkata';
  const today = sweetbotDayKey(Date.parse('2026-09-28T08:00:00.000Z'), tz);
  const sameDay = (ms) => sweetbotDayKey(ms, tz) === today;
  const morning = Date.parse('2026-09-28T03:30:00.000Z') / 1000; // 9:00am IST
  const overnight = Date.parse('2026-09-27T20:00:00.000Z') / 1000; // 1:30am IST, previous day
  const found = latestFromMeMs(
    [
      { fromMe: false, timestamp: morning },
      { fromMe: true, timestamp: overnight },
      { fromMe: true, timestamp: morning },
    ],
    sameDay,
  );
  assert.equal(found, morning * 1000);
});

test('no message from you today returns null', () => {
  assert.equal(latestFromMeMs([{ fromMe: false, timestamp: 1 }], () => true), null);
  assert.equal(latestFromMeMs([], () => true), null);
});
