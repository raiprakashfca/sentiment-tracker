# WhatsApp Sweetbot 💕

Sends short, affectionate messages ("miss you 🥺", "gm baby ❤️", …) to one contact at
randomised, human-looking intervals.

## How it behaves
- **Timing:** it waits a random 40–95 minutes between messages (around an hour on average, bunched toward the middle of the range), and adds random seconds on top.
- **Skips:** about 15% of rounds are skipped at random, so there's no fixed rhythm.
- **Starts when you do:** nothing is sent each day until you've texted her yourself, and nothing after 11pm.
- **Time of day:** morning, day, evening and night each have their own messages.
- **Typing like a person:** it shows "typing…" for as long as the text would take to type, mostly writes in lowercase, sometimes stretches words ("youuu"), picks emoji at random, and now and then sends a quick follow-up text.

## Setup (Windows, no typing needed)
1. Install [Node.js](https://nodejs.org) (LTS).
2. Double-click **`Start Sweetbot.bat`**. The first run installs everything, which takes a couple of
   minutes. Then the **control panel** opens in your browser at http://localhost:3737.
3. Scan the QR code shown in the panel with WhatsApp → **Settings → Linked devices → Link a device**.
4. Fill in **Settings** (her number, what you call her) and click **Save**.

The panel shows what the bot is doing and when the next message is due. It has buttons to pause and resume,
**Show sample messages** to preview without sending, all the settings, and **Stop bot**.

Keep the black `Start Sweetbot` window open (minimise it). Closing it stops the bot. To get a newer version,
double-click **`Update Sweetbot.bat`**, then stop the bot and start it again.

(Mac/Linux: `npm install && npm start`.)

## Your own habits
In `config.json`:
- `myStyle.neverSay`: words or phrases that are never sent (whole words, any case). A message
  containing one is rejected and rewritten.
- `myStyle.notes`: plain-English notes on how you text, passed to the LLM.

```json
"myStyle": {
  "notes": ["Write full words: \"you\" not \"u\". Don't use \"rn\"."],
  "neverSay": ["gm", "hey", "thinking about u rn", "u", "rn"]
}
```

## It starts after you text her
With `"startAfterMyFirstMessage": true` (the default), the bot sends nothing each day until **you've
texted her yourself** from your phone, for example your own good morning. If you wake up late, it
starts late. After that it sends at random gaps until bedtime (`quietHours.start`, 11pm by default).
The day resets at 4am.

Whenever either of you texts in her chat, the bot waits for a new random gap before its next message,
so it never butts into a real conversation.

## Pause it any time
Text these to **yourself** on WhatsApp (the "Message yourself" chat), or type them without `bot` in
the bot's window:

| Command | What it does |
|---|---|
| `bot pause` | pause until you resume |
| `bot pause 2h` / `bot pause 30m` | pause for a while |
| `bot pause today` | pause until tomorrow |
| `bot resume` | start again |
| `bot status` | what it's doing / when the next message is |

The bot replies in that chat with 🤖. The pause survives restarts. Commands typed in any other
chat are ignored.

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
Run `npm run setup` and choose `groq`, `ollama` or `lmstudio`, then check it with `npm run test-llm`.
Any other OpenAI-compatible server works too. Set these in `config.json`:

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
