#!/usr/bin/env python3
"""Vercel build step — pick which site's static files to serve.

Vercel's CDN serves the repo's `public/` folder (via vercel.json rewrites),
and the serverless function can't stream the large video assets (4.5 MB
response cap). So at build time we (re)build the H5 demo for the chosen
site and swap public/ to match.

Set as the Vercel project's Build Command:
    python3 scripts/build_vercel.py

Driven by the GWM_SITE env var:
    GWM_SITE=eu     -> build public-eu/    then swap into public/
    GWM_SITE=th     -> build public-th/    then swap into public/
    GWM_SITE=im-th  -> build public-im-th/ then swap into public/
    (any other)     -> no-op (keep public/ as-is)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = os.getenv("GWM_SITE", "").strip().lower()
KNOWN_SITES = ("eu", "th", "im-th")


def main() -> int:
    if SITE not in KNOWN_SITES:
        print(f"[build] GWM_SITE={SITE!r}: serving public/ as-is, nothing to do.")
        return 0

    # Build the H5 source for this site so deploys are deterministic.
    h5 = ROOT / "scripts" / "build_h5.py"
    if h5.exists():
        rc = subprocess.run([sys.executable, str(h5), SITE], check=False).returncode
        if rc != 0:
            print(f"[build] build_h5.py exited {rc}")
            return rc

    src = ROOT / f"public-{SITE}"
    dst = ROOT / "public"
    if not (src / "index.html").exists():
        print(f"[build] ERROR: {src}/index.html missing.")
        return 1

    print(f"[build] GWM_SITE={SITE}: replacing {dst}/ with {src}/ contents…")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"[build] done. public/ now serves the {SITE.upper()} H5 demo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
