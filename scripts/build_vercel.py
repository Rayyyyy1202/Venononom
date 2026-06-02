#!/usr/bin/env python3
"""Vercel build step — pick which site's static files to serve.

Vercel's CDN serves the repo's `public/` folder (via vercel.json rewrites),
and a serverless function can't stream the large video assets (4.5 MB
response cap). So for the Thailand deployment we swap `public/` contents
with `public-th/` at build time.

Set as the TH Vercel project's Build Command:
    python3 scripts/build_vercel.py

Driven by the GWM_SITE env var:
    GWM_SITE=th  -> replace public/ with public-th/
    GWM_SITE=eu  -> no-op (public/ already holds the EU site)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = os.getenv("GWM_SITE", "eu").strip().lower()


def main() -> int:
    if SITE != "th":
        print(f"[build] GWM_SITE={SITE!r}: serving public/ as-is, nothing to do.")
        return 0

    # Always (re)build the H5 source so deploys are deterministic even if
    # public-th/ in git is stale.
    h5 = ROOT / "scripts" / "build_h5.py"
    if h5.exists():
        rc = subprocess.run([sys.executable, str(h5)], check=False).returncode
        if rc != 0:
            print(f"[build] build_h5.py exited {rc}")
            return rc

    src = ROOT / "public-th"
    dst = ROOT / "public"
    if not (src / "index.html").exists():
        print(f"[build] ERROR: {src}/index.html missing.")
        return 1

    print(f"[build] GWM_SITE=th: replacing {dst}/ with {src}/ contents…")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"[build] done. public/ now serves the Thailand site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
