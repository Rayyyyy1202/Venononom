#!/usr/bin/env python3
"""Build public-<site>/ as a self-contained full-screen H5 chatbot demo.

Instead of mirroring the GWM homepage and grafting the widget on top, this
produces a tiny standalone page (~30 KB) that IS the chatbot:
- public-<site>/index.html       — H5 landing page (full-screen frame)
- public-<site>/chatbot/         — widget assets (chatbot.css/js + KB)

The Vercel deploy step (scripts/build_vercel.py) calls this first so the
deployment always serves a fresh H5 build.

Usage:
    python3 scripts/build_h5.py [eu|th]
    (default: eu)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHATBOT = ROOT / "chatbot"

SITES = {
    "eu": {
        "output": ROOT / "public-eu",
        "knowledge": "knowledge.json",
        "lang": "en",
        "title": "GWM Assistant · Great Wall Motor",
        "tag": "GWM EUROPE · AI DEMO",
    },
    "th": {
        "output": ROOT / "public-th",
        "knowledge": "knowledge.th.json",
        "lang": "th",
        "title": "GWM Assistant · เกรท วอลล์ มอเตอร์",
        "tag": "GWM THAILAND · AI DEMO",
    },
}


def build(site: str) -> int:
    if site not in SITES:
        print(f"[build_h5] ERROR: unknown site {site!r}. Choose from: {', '.join(SITES)}")
        return 2
    cfg = SITES[site]
    out = cfg["output"]

    template = CHATBOT / "h5.html"
    kb_src = CHATBOT / cfg["knowledge"]
    if not template.exists():
        print(f"[build_h5] ERROR: {template} missing")
        return 1
    if not kb_src.exists():
        print(f"[build_h5] ERROR: {kb_src} missing")
        return 1

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Widget assets — the site's knowledge file is served as knowledge.json
    # so the widget always loads /chatbot/knowledge.json regardless of site.
    (out / "chatbot").mkdir()
    shutil.copy(CHATBOT / "chatbot.css", out / "chatbot" / "chatbot.css")
    shutil.copy(CHATBOT / "chatbot.js", out / "chatbot" / "chatbot.js")
    shutil.copy(kb_src, out / "chatbot" / "knowledge.json")

    # H5 landing page with site-specific substitutions
    html = template.read_text(encoding="utf-8")
    for placeholder, value in (
        ("{{LANG}}", cfg["lang"]),
        ("{{TITLE}}", cfg["title"]),
        ("{{TAG}}", cfg["tag"]),
    ):
        html = html.replace(placeholder, value)
    (out / "index.html").write_text(html, encoding="utf-8")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"[build_h5] {site}: wrote {out.relative_to(ROOT)}/  ({total:,} bytes)")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "eu"
    sys.exit(build(target))
