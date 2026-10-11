// Decides whether a WhatsApp id is her number, and whether you already texted
// her in the current "day" (which starts at 4am, not midnight).

function digits(value) {
  return String(value ?? '').split('@')[0].replace(/\D/g, '');
}

function matchesRecipient(candidates, recipientNumber) {
  const want = digits(recipientNumber);
  if (!want) return false;
  return [].concat(candidates).some((value) => digits(value) === want);
}

function sweetbotDayKey(ms, timeZone, dayStartsAt = 4) {
  return new Date(ms - dayStartsAt * 3600e3).toLocaleDateString('en-CA', { timeZone });
}

// Latest message you sent that still belongs to today's key. Timestamps from
// WhatsApp are seconds; a value that is already milliseconds is accepted too.
function latestFromMeMs(messages, sameDay) {
  let latest = null;
  for (const msg of messages || []) {
    if (!msg?.fromMe) continue;
    const raw = Number(msg.timestamp);
    if (!Number.isFinite(raw)) continue;
    const ms = raw > 1e12 ? raw : raw * 1000;
    if (!sameDay(ms)) continue;
    if (latest === null || ms > latest) latest = ms;
  }
  return latest;
}

module.exports = { digits, matchesRecipient, sweetbotDayKey, latestFromMeMs };
