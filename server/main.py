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
SITE_DIR = ROOT / "site"
KB_PATH = ROOT / "chatbot" / "knowledge.json"

load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or None

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


SYSTEM_PROMPT_TEMPLATE = """You are the GWM Europe assistant — a friendly, concise demo chatbot embedded in the GWM Europe homepage (https://www.gwm-eu.com/eu).

Use the JSON knowledge base below as your source of truth for product names, taglines, contact info and section URLs. If a question can't be answered from the knowledge base, say so briefly and suggest emailing info@gwm-eu.com or visiting the contact page.

Tone: warm, professional, brief (2-4 sentences unless asked for detail). Use **bold** for product names and key facts. When relevant, include a link in markdown form like [Models](https://www.gwm-eu.com/eu/models).

KNOWLEDGE BASE:
{kb}
"""


def system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(kb=kb_text())


# -- Chat endpoint -----------------------------------------------------------


class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system|bot)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


def _normalise_role(role: str) -> str:
    return "assistant" if role == "bot" else role


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")
    client = get_client()

    full_messages = [{"role": "system", "content": system_prompt()}]
    for m in req.messages:
        full_messages.append({"role": _normalise_role(m.role), "content": m.content})

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            stream = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=full_messages,
                stream=True,
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
        "model": OPENAI_MODEL,
        "has_key": bool(OPENAI_API_KEY),
        "kb_loaded": KB_PATH.exists(),
    }


# -- Static site mount (must be last so /api routes win) ---------------------

if SITE_DIR.exists():
    app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="site")
