# GWM EU Homepage Demo + AI Chatbot Widget

A self-contained internal demo: a local mirror of [gwm-eu.com/eu](https://www.gwm-eu.com/eu)
with an AI-style chat widget grafted onto it. Built to show "what would the GWM
homepage look like if it had a 24/7 AI assistant?".

> **Disclaimer.** All GWM trademarks, copy, imagery and assets belong to
> Great Wall Motor. This repository scrapes the public homepage for an internal
> demo only. Do not redistribute or use commercially. Delete the `site/` folder
> at any time to remove cached assets.

## What's inside

```
.
├── README.md
├── run.sh                       Local preview server (python http.server)
├── scripts/
│   └── scrape.py                One-shot scraper: downloads /eu + assets,
│                                rewrites URLs, injects the chatbot widget
├── chatbot/
│   ├── chatbot.css              Floating button + chat panel styles
│   ├── chatbot.js               Widget logic (vanilla JS, ~9 KB)
│   └── knowledge.json           GWM Q&A knowledge base
└── site/                        (generated) the localised homepage + assets
```

## Quick start

```bash
# 1. install scraper deps (one-time)
pip install requests beautifulsoup4

# 2. download the homepage + assets and inject the widget
python3 scripts/scrape.py

# 3. preview locally
./run.sh          # serves http://localhost:8000
```

Open <http://localhost:8000> in your browser. The page should look identical
to the live site, with a small red chat button in the bottom-right corner.

## How the chatbot works

The widget is **frontend-only** — there is no backend, no API key, no network
calls outside `knowledge.json`. When the user sends a message, the JS runs a
keyword-overlap match against the Q&A entries in `chatbot/knowledge.json` and
returns the best-scoring answer (or a fallback). A typing indicator + slow
typewriter render gives the illusion of a real LLM.

### Try these prompts
- "Tell me about GWM ORA 5"
- "What models are coming to Europe?"
- "How can I become a dealer?"
- "How do I contact GWM?"
- "Anything about the H7?"

## Upgrading to a real LLM

When you're ready to wire it to Claude / OpenAI / etc.:

1. Stand up a small backend (e.g. FastAPI) exposing `POST /api/chat`
2. In `chatbot/chatbot.js`, replace the `respondTo()` function with a `fetch`
   call to your endpoint
3. Pass the contents of `knowledge.json` as system-prompt context (or do real
   RAG over the scraped HTML in `site/`)

The widget's UI does not need to change.

## Re-running the scraper

The scraper is idempotent — it re-downloads `index.html` but skips assets that
already exist on disk. To start completely fresh:

```bash
rm -rf site/
python3 scripts/scrape.py
```

## Notes & limitations

- Only the **English EU homepage** (`/eu`) is scraped. Internal links to
  unscraped pages (e.g. `/eu/models/h7`) are neutralised to `#` with a tooltip
  noting "demo: page not scraped". Cross-region links (`/it`, `/es`) point back
  to the live site.
- Tracking scripts (Google Tag Manager, Analytics, Clarity, etc.) are stripped
  for a cleaner local console; some AEM client-side libraries may still log
  warnings because they expect the live backend — these are non-fatal.
- Newsletter / contact forms on the page won't submit (no backend).
