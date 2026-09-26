# WhatsApp Sweetbot 💕

Sends short, affectionate messages ("miss you 🥺", "gm baby ❤️", …) to one contact at
randomised, human-looking intervals.

## How it behaves
- **Timing:** it waits a random 40–95 minutes between messages (around an hour on average, bunched toward the middle of the range), and adds random seconds on top.
- **Skips:** about 15% of rounds are skipped at random, so there's no fixed rhythm.
- **Quiet hours:** it sends nothing between 23:00 and 08:00 (you can change this).
- **Time of day:** morning, day, evening and night each have their own messages.
- **Typing like a person:** it shows "typing…" for as long as the text would take to type, mostly writes in lowercase, sometimes stretches words ("youuu"), picks emoji at random, and now and then sends a quick follow-up text.

## Setup
```bash
cd whatsapp-sweetbot
npm install
cp config.example.json config.json   # set her number (country code, no +), name, timezone
npm run preview                       # dry run: prints messages, sends nothing (Ctrl+C to stop)
npm start                             # shows a QR code the first time
```
Scan the QR in WhatsApp → **Settings → Linked devices → Link a device**. You never
give it your password. The session is saved in `.wwebjs_auth/`, so you only scan once. To log out,
remove the linked device in your phone's WhatsApp or delete that folder.

The bot has to keep running for messages to go out. Use a machine that is always on, such as a small
VPS or a Raspberry Pi, with something like `pm2 start index.js`.

## Caveats
- This uses [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js), an
  **unofficial** WhatsApp Web client. Automating a personal account breaks WhatsApp's
  terms, and your number could be banned. Keep the volume modest.
- Messages are sent from your account as you. If she replies, the bot won't notice. Reply to her yourself.
