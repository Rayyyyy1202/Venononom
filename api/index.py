"""Vercel Python serverless entrypoint.

Vercel's @vercel/python runtime auto-detects ASGI apps exported as `app`.
We just import the existing FastAPI app and re-export it. All /api/*
routes hit this function (per vercel.json rewrites); static files are
served by Vercel directly from public/, so the StaticFiles mount in
server.main is a no-op in production.
"""

import sys
from pathlib import Path

# Make the repo root importable so `from server.main import app` works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.main import app  # noqa: E402, F401
