#!/usr/bin/env python3
"""Build public-<site>/ as a self-contained full-screen H5 chatbot demo.

Layouts:
  - `eu`  → multi-locale tree under public-eu/
        /              (English)
        /es            (Spanish UI, same English KB content + ES overrides)
        /it            (Italian UI, same English KB content + IT overrides)
  - `th`  → single-locale public-th/  (Thai)

The Vercel deploy step (scripts/build_vercel.py) calls this so the
deployment always serves a fresh H5 build matching GWM_SITE.

Usage:
    python3 scripts/build_h5.py [eu|th]   (default: eu)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHATBOT = ROOT / "chatbot"

# Per-locale page metadata. The KB for each locale = base + override (shallow
# merge: override fields replace base fields).
EU_LOCALES = [
    {
        "subpath": "",
        "lang": "en",
        "title": "GWM Assistant · Great Wall Motor",
        "tag": "GWM EUROPE · AI DEMO",
        "base_kb": "knowledge.json",
        "override_kb": None,
    },
    {
        "subpath": "es",
        "lang": "es",
        "title": "GWM Assistant · Great Wall Motor (España)",
        "tag": "GWM ESPAÑA · DEMO IA",
        "base_kb": "knowledge.json",
        "override_kb": "knowledge.es.json",
    },
    {
        "subpath": "it",
        "lang": "it",
        "title": "GWM Assistant · Great Wall Motor (Italia)",
        "tag": "GWM ITALIA · DEMO IA",
        "base_kb": "knowledge.json",
        "override_kb": "knowledge.it.json",
    },
]

SITES = {
    "eu": {"output": ROOT / "public-eu", "locales": EU_LOCALES},
    "th": {
        "output": ROOT / "public-th",
        "locales": [
            {
                "subpath": "",
                "lang": "th",
                "title": "GWM Assistant · เกรท วอลล์ มอเตอร์",
                "tag": "GWM THAILAND · AI DEMO",
                "base_kb": "knowledge.th.json",
                "override_kb": None,
            }
        ],
    },
}


def build_locale(out_root: Path, locale: dict) -> None:
    sub = out_root / locale["subpath"] if locale["subpath"] else out_root
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "chatbot").mkdir(exist_ok=True)

    # Widget code is identical across all locales
    shutil.copy(CHATBOT / "chatbot.css", sub / "chatbot" / "chatbot.css")
    shutil.copy(CHATBOT / "chatbot.js", sub / "chatbot" / "chatbot.js")

    # Knowledge base = base + (optional) locale overrides
    kb = json.loads((CHATBOT / locale["base_kb"]).read_text(encoding="utf-8"))
    if locale["override_kb"]:
        overrides = json.loads((CHATBOT / locale["override_kb"]).read_text(encoding="utf-8"))
        for k, v in overrides.items():
            kb[k] = v
    (sub / "chatbot" / "knowledge.json").write_text(
        json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # H5 landing page
    html = (CHATBOT / "h5.html").read_text(encoding="utf-8")
    for placeholder, value in (
        ("{{LANG}}", locale["lang"]),
        ("{{TITLE}}", locale["title"]),
        ("{{TAG}}", locale["tag"]),
    ):
        html = html.replace(placeholder, value)
    (sub / "index.html").write_text(html, encoding="utf-8")


def build(site: str) -> int:
    if site not in SITES:
        print(f"[build_h5] ERROR: unknown site {site!r}. Choose from: {', '.join(SITES)}")
        return 2
    cfg = SITES[site]
    out = cfg["output"]

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for loc in cfg["locales"]:
        build_locale(out, loc)
        label = loc["subpath"] or "/"
        print(f"[build_h5] {site} :: {label} ({loc['lang']}) built")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"[build_h5] {site}: wrote {out.relative_to(ROOT)}/  ({total:,} bytes total)")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "eu"
    sys.exit(build(target))
