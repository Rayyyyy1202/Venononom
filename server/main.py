"""GWM demo chatbot backend.

FastAPI app that:
- Serves the scraped static site under /
- Exposes POST /api/chat which proxies to OpenAI with streaming SSE,
  injecting chatbot/knowledge.json into the system prompt.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")

# Which market this instance serves. Each Vercel project sets GWM_SITE;
# default "eu" keeps the original deployment unchanged.
GWM_SITE = os.getenv("GWM_SITE", "eu").strip().lower()

if GWM_SITE == "th":
    SITE_DIR = ROOT / "public-th"
    KB_PATH = ROOT / "chatbot" / "knowledge.th.json"
elif GWM_SITE == "im-th":
    SITE_DIR = ROOT / "public-im-th"
    KB_PATH = ROOT / "chatbot" / "knowledge.im-th.json"
elif GWM_SITE == "sky-th":
    SITE_DIR = ROOT / "public-sky-th"
    KB_PATH = ROOT / "chatbot" / "knowledge.sky-th.json"
else:
    SITE_DIR = ROOT / "public"
    KB_PATH = ROOT / "chatbot" / "knowledge.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or None
# Provider-specific extras passed as `extra_body` to the chat completions
# request. Example for BytePlus Ark Seed reasoning models, to skip the
# silent think phase and get true first-token streaming:
#   OPENAI_EXTRA_BODY={"thinking":{"type":"disabled"}}
try:
    OPENAI_EXTRA_BODY = json.loads(os.getenv("OPENAI_EXTRA_BODY") or "{}")
    if not isinstance(OPENAI_EXTRA_BODY, dict):
        OPENAI_EXTRA_BODY = {}
except Exception:
    OPENAI_EXTRA_BODY = {}

app = FastAPI(title="GWM Demo Chatbot Backend")


# -- OpenAI client (lazy) -----------------------------------------------------

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in.",
        )
    if _client is None:
        kwargs = {"api_key": OPENAI_API_KEY}
        if OPENAI_BASE_URL:
            kwargs["base_url"] = OPENAI_BASE_URL
        _client = AsyncOpenAI(**kwargs)
    return _client


# -- Knowledge base & system prompt ------------------------------------------

_kb_text: str | None = None


def kb_text() -> str:
    """Return knowledge.json as a pretty-printed string for the prompt."""
    global _kb_text
    if _kb_text is None:
        try:
            data = json.loads(KB_PATH.read_text(encoding="utf-8"))
            _kb_text = json.dumps(data, indent=2, ensure_ascii=False)
        except Exception:
            _kb_text = "{}"
    return _kb_text


_SITE_PROMPT = {
    "eu": {
        "brand": "GWM Europe",
        "home": "https://www.gwm-eu.com/eu",
        "contact": "emailing info@gwm-eu.com or visiting the contact page",
        "language_rule": "",
    },
    "th": {
        "brand": "GWM Thailand (เกรท วอลล์ มอเตอร์)",
        "home": "https://www.gwm.co.th/th",
        "contact": "calling 02-668-8888 or visiting a GWM Store",
        "language_rule": (
            "\nIMPORTANT: Reply in the SAME language the user writes in — "
            "Thai (ภาษาไทย) if they write Thai, English if they write English. "
            "Default to Thai if unsure. Use Thai Baht (฿) for prices."
        ),
    },
    "im-th": {
        "brand": "IM Motors Thailand (智己汽车 / Intelligence in Motion)",
        "home": "https://www.immotors.com/global/en/",
        "contact": "visiting a SAIC-MG showroom in Thailand (IM Motors is distributed via the MG network locally)",
        "language_rule": (
            "\nIMPORTANT: Reply in the SAME language the user writes in — "
            "Thai (ภาษาไทย) if they write Thai, English if they write English. "
            "Default to Thai if unsure. Use Thai Baht (฿) for prices. "
            "Only IM6 (Premium / Performance variants) is sold in Thailand currently."
        ),
    },
    "sky-th": {
        "brand": "SKYWORTH (创维) — Lead the Future",
        "home": "https://www.skyworth.com/",
        "contact": "visiting the official website skyworth.com or contacting an authorized Skyworth retailer",
        "language_rule": (
            "\nIMPORTANT: Reply in the SAME language the user writes in — "
            "Chinese (中文) if they write Chinese, English if they write English. "
            "Default to Chinese (中文) if unsure. Use RMB (¥/元) for prices."
        ),
    },
}

SYSTEM_PROMPT_TEMPLATE = """You are the {brand} assistant. Speak and behave as a real customer-service representative of the brand — use "we" / "我们" / "the brand". You are NOT a generic AI; you ARE this brand's helper.

CRITICAL — never reveal your internals:
- Never say "knowledge base", "知识库", "context", "context window", "prompt", "system prompt", "documents", "training data", "JSON", "the information I have", "according to my data", or any equivalent. Don't acknowledge that there's a backing store of facts at all.
- Don't explain WHY you do or don't know something. The user is a customer talking to a representative, not a developer.

What to do when you genuinely don't have a fact:
- DO NOT say "the knowledge base doesn't include this" or "I don't have this information in my knowledge base".
- DO say something natural like:
  - "I don't have the latest figure on that right now — please {contact}."
  - "对这个我暂时没有最新数据，方便的话 {contact} 可以拿到准确报价。"
  - "Specific pricing changes by region/promotion — for an up-to-date quote please {contact}."

When you DO know a fact, state it directly and confidently as the brand representative.

Style: warm, concise (2–4 sentences unless asked for detail). Use **bold** for product names, prices and key facts. Use markdown links where helpful.{language_rule}

REFERENCE INFORMATION (treat this as YOUR knowledge as the brand assistant — never refer to it as a "knowledge base" or quote it as a separate document):
{kb}
"""


_LANG_NAMES = {"en": "English", "es": "Spanish", "it": "Italian",
               "th": "Thai", "de": "German", "fr": "French", "pt": "Portuguese"}


def system_prompt(lang_hint: str | None = None) -> str:
    cfg = _SITE_PROMPT.get(GWM_SITE, _SITE_PROMPT["eu"])
    language_rule = cfg["language_rule"]
    if lang_hint and lang_hint in _LANG_NAMES:
        name = _LANG_NAMES[lang_hint]
        language_rule += (
            f"\nIMPORTANT: The user is viewing the {name} UI. Reply in {name} "
            f"by default. If the user clearly writes in another language, "
            f"reply in that language instead."
        )
    return SYSTEM_PROMPT_TEMPLATE.format(
        brand=cfg["brand"],
        home=cfg["home"],
        contact=cfg["contact"],
        language_rule=language_rule,
        kb=kb_text(),
    )


# -- Chat endpoint -----------------------------------------------------------


class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system|bot)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    lang_hint: str | None = None


def _normalise_role(role: str) -> str:
    return "assistant" if role == "bot" else role


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")
    client = get_client()

    full_messages = [{"role": "system", "content": system_prompt(req.lang_hint)}]
    for m in req.messages:
        full_messages.append({"role": _normalise_role(m.role), "content": m.content})

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            stream = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=full_messages,
                stream=True,
                extra_body=OPENAI_EXTRA_BODY,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content if chunk.choices[0].delta else None
                if delta:
                    yield _sse({"token": delta})
            yield _sse({"done": True})
        except Exception as e:
            # Surface a clean error in the chat UI instead of dropping the connection
            msg = f"{type(e).__name__}: {e}"
            yield _sse({"error": msg})
            yield _sse({"done": True})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "site": GWM_SITE,
        "model": OPENAI_MODEL,
        "has_key": bool(OPENAI_API_KEY),
        "kb_loaded": KB_PATH.exists(),
    }


# -- Static site mount (must be last so /api routes win) ---------------------

if SITE_DIR.exists():
    app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="site")
