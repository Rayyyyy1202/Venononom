#!/usr/bin/env python3
"""Build public-th/ as a self-contained full-screen H5 chatbot demo.

Instead of mirroring the GWM Thailand homepage (~9 MB) and grafting the widget
on top, this produces a tiny standalone page (~30 KB) that IS the chatbot:
- public-th/index.html       — H5 landing page (full-screen frame)
- public-th/chatbot/         — widget assets (chatbot.css/js + Thai knowledge)

The Vercel deploy step (scripts/build_vercel.py) calls this first when
GWM_SITE=th so the deployment always serves a fresh H5 build.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHATBOT = ROOT / "chatbot"
OUT = ROOT / "public-th"


def main() -> int:
    if not (CHATBOT / "h5.html").exists():
        print("[build_h5] ERROR: chatbot/h5.html missing")
        return 1
    if not (CHATBOT / "knowledge.th.json").exists():
        print("[build_h5] ERROR: chatbot/knowledge.th.json missing")
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # Widget assets — knowledge.th.json is served as knowledge.json so the
    # widget loads it transparently. Other sites' KBs are not shipped.
    (OUT / "chatbot").mkdir()
    shutil.copy(CHATBOT / "chatbot.css", OUT / "chatbot" / "chatbot.css")
    shutil.copy(CHATBOT / "chatbot.js", OUT / "chatbot" / "chatbot.js")
    shutil.copy(CHATBOT / "knowledge.th.json", OUT / "chatbot" / "knowledge.json")

    # H5 landing page
    shutil.copy(CHATBOT / "h5.html", OUT / "index.html")

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"[build_h5] wrote {OUT.relative_to(ROOT)}/  ({total:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
