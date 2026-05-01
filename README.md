# GWM Europe — Website + AI Chatbot Demo

A self-contained demo prototype for pitching an AI chatbot integration to
GWM Europe. The site is a single-page, GWM-styled landing page covering the
launch line-up (ORA 5, H7, JOLION MAX), technology, brand story, and service.
A floating AI assistant lives in the bottom-right corner.

> **Note** — this is an unaffiliated sales prototype. All copy and imagery are
> original placeholders; replace with the client's official assets before any
> external use.

## Project layout

```
.
├── index.html              # The page
├── assets/
│   ├── css/styles.css      # All styles (incl. chatbot widget)
│   └── js/
│       ├── main.js         # Header / nav / scroll-reveal
│       └── chatbot.js      # Chatbot widget (demo + API modes)
└── server/
    └── server.js           # Optional zero-dep Node server + Anthropic proxy
```

## Run it

### Option A — pure static (no backend)

Just open `index.html`, or serve the folder with anything you have handy:

```bash
python3 -m http.server 3000
# or
npx serve .
```

The chatbot will run in **demo mode** — rule-based responses about the GWM
line-up, no API key needed. Perfect for a first pitch.

### Option B — live AI via Anthropic (Node ≥ 18)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
node server/server.js
```

Then in `index.html`, before the chatbot script tag, add:

```html
<script>
  window.GWM_CHATBOT_CONFIG = { mode: 'api', endpoint: '/api/chat' };
</script>
```

The server is a single file with no external dependencies. It serves the
static site **and** exposes `POST /api/chat`, which forwards the conversation
to Anthropic's Messages API with a GWM-tuned system prompt.

Default model: `claude-haiku-4-5-20251001` (fast and cheap, suitable for a
chat widget). Override with `ANTHROPIC_MODEL=claude-sonnet-4-6` for higher
quality at higher cost.

## Customisation cheatsheet

| What | Where |
|---|---|
| Brand colour (signal red) | `--c-accent` in `assets/css/styles.css` |
| Hero copy / stats | `.hero` in `index.html` |
| Models, specs, taglines | `.model-grid` cards in `index.html` |
| System prompt for live AI | `SYSTEM_PROMPT` in `server/server.js` |
| Demo bot answers | `KB` and `answer()` in `assets/js/chatbot.js` |
| Greeting + suggestion chips | `CONFIG` at the top of `assets/js/chatbot.js` |

## Replacing the placeholder car visuals

The model cards currently use CSS-only gradient placeholders so the demo runs
with no asset dependencies. To use real photos, drop them into
`assets/img/` and replace the relevant `.model-img-*` rules in `styles.css`:

```css
.model-img-ora5::before {
  background: url('../img/ora5.jpg') center/cover no-repeat;
}
.model-img-ora5::after { content: none; }   /* hide the text watermark */
```

## What to show in the pitch

1. Open the site, scroll through hero → models → tech → service.
2. Click the red chat bubble (bottom-right). The greeting + suggestion chips
   appear immediately.
3. Click a suggestion ("Tell me about ORA 5") — instant, on-brand answer.
4. Type a free-form question ("compare H7 and JOLION MAX") to show the
   conversation flow.
5. If wired to the API, finish with an off-script question to demonstrate
   that the live model stays on-brand thanks to the system prompt.
