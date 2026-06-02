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
        # Empty lang lets pickLocale() in chatbot.js fall through to
        # navigator.languages — i.e. the root URL auto-adapts to the
        # visitor's browser language (en, es, it, ...).
        "lang": "",
        "title": "GWM Assistant · Great Wall Motor",
        "tag": "GWM EUROPE · AI DEMO",
        "base_kb": "knowledge.json",
        "override_kb": None,
    },
    # `/es` and `/it` are kept as explicit force-locale URLs (shareable, for
    # when you want to send a Spanish or Italian native speaker straight to
    # their language regardless of browser). The widget detects `<html lang>`
    # and uses it as the locale; merged localizations live in knowledge.json
    # so no per-locale override files are needed.
    {
        "subpath": "es",
        "lang": "es",
        "title": "GWM Assistant · Great Wall Motor (España)",
        "tag": "GWM ESPAÑA · DEMO IA",
        "base_kb": "knowledge.json",
        "override_kb": None,
    },
    {
        "subpath": "it",
        "lang": "it",
        "title": "GWM Assistant · Great Wall Motor (Italia)",
        "tag": "GWM ITALIA · DEMO IA",
        "base_kb": "knowledge.json",
        "override_kb": None,
    },
]

GWM_BRAND = {
    "primary": "#c8102e",
    "primary_dark": "#9a0c24",
    "page_bg": "radial-gradient(120% 80% at 50% 0%, #2a0d12 0%, #0c0c0e 70%)",
    "glow": "rgba(200, 16, 46, 0.25)",
}

# IM Motors brand: dark navy / metallic, very different from GWM red.
IM_BRAND = {
    "primary": "#101828",
    "primary_dark": "#0a0f1a",
    "page_bg": "radial-gradient(120% 80% at 50% 0%, #1a2740 0%, #050810 70%)",
    "glow": "rgba(120, 160, 220, 0.18)",
}

SITES = {
    "eu": {"output": ROOT / "public-eu", "brand": GWM_BRAND, "locales": EU_LOCALES},
    "th": {
        "output": ROOT / "public-th",
        "brand": GWM_BRAND,
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
    "im-th": {
        "output": ROOT / "public-im-th",
        "brand": IM_BRAND,
        "locales": [
            {
                "subpath": "",
                "lang": "th",
                "title": "IM Assistant · IM Motors Thailand",
                "tag": "IM MOTORS THAILAND · AI DEMO",
                "base_kb": "knowledge.im-th.json",
                "override_kb": None,
            }
        ],
    },
}


def build_locale(out_root: Path, locale: dict, brand: dict) -> None:
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

    # H5 landing page (with site-specific brand colors injected)
    html = (CHATBOT / "h5.html").read_text(encoding="utf-8")
    for placeholder, value in (
        ("{{LANG}}", locale["lang"]),
        ("{{TITLE}}", locale["title"]),
        ("{{TAG}}", locale["tag"]),
        ("{{BRAND_PRIMARY}}", brand["primary"]),
        ("{{BRAND_PRIMARY_DARK}}", brand["primary_dark"]),
        ("{{PAGE_BG}}", brand["page_bg"]),
        ("{{BRAND_GLOW}}", brand["glow"]),
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

    brand = cfg.get("brand", GWM_BRAND)
    for loc in cfg["locales"]:
        build_locale(out, loc, brand)
        label = loc["subpath"] or "/"
        print(f"[build_h5] {site} :: {label} ({loc['lang']}) built")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"[build_h5] {site}: wrote {out.relative_to(ROOT)}/  ({total:,} bytes total)")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "eu"
    sys.exit(build(target))
