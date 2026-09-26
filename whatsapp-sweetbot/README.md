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

## Teach it your texting style
1. In WhatsApp, open her chat → ⋮ → More → **Export chat** → **Without media**, and copy the `.txt` file into this folder.
2. Run:
   ```bash
   node learn-style.js "WhatsApp Chat with Her.txt" "Your Name"
   ```
   (If you get your name wrong, it lists the sender names it found.)
3. Open `style.json` and **delete any phrase you wouldn't want sent out of the blue**.
4. Try it with `npm run preview`, then restart the bot.

It only keeps **your** short messages that are affectionate or greetings. It skips media, links, phone
numbers, multi-line messages, and everyday messages like "pick up milk". It also copies which emoji you
use and how often, and how often you write in lowercase. A phrase about morning or night is only sent at
that time of day. It never sends the same message twice in a row. The more phrases it learns, the more
it uses them. With fewer than about 25 it mixes in its built-in ones so it doesn't repeat itself.

`style.json` and the chat export are listed in `.gitignore`, so they stay on your machine.

## Use a local LLM to write the messages (optional)
Any local LLM app with an OpenAI-compatible server works. In `config.json`, set `llm.enabled` to `true` and fill in:

| App | `baseUrl` | `model` |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | name from `ollama list`, e.g. `llama3.1` |
| LM Studio | `http://localhost:1234/v1` | model id shown in the Developer tab (start the server there) |
| llama.cpp `llama-server` | `http://localhost:8080/v1` | anything |
| Jan | `http://localhost:1337/v1` | model id from Jan's settings |

If you've run `learn-style.js`, it shows the model 30 random phrases of yours so it copies your
style. It tells the model the time of day and what it sent recently so it doesn't repeat. If the LLM
is off, too slow, or replies with something unusable (too long, "Sure! Here's…", a repeat), that round
uses the built-in messages instead. Everything stays on your PC.

## Caveats
- This uses [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js), an
  **unofficial** WhatsApp Web client. Automating a personal account breaks WhatsApp's
  terms, and your number could be banned. Keep the volume modest.
- Messages are sent from your account as you. If she replies, the bot won't notice. Reply to her yourself.
