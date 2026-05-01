#!/usr/bin/env python3
"""
GWM EU homepage scraper.

Downloads https://www.gwm-eu.com/eu and all its same-origin static assets
(CSS, JS, images, fonts), rewrites URLs so the page renders from the local
filesystem, strips noisy third-party tracking scripts, and injects the
chatbot widget assets into the HTML before </body>.

Output: ./site/  (relative to repo root)

Usage:
    pip install requests beautifulsoup4
    python3 scripts/scrape.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

# -------- Configuration -------------------------------------------------------

ENTRY_URL = "https://www.gwm-eu.com/eu"
ORIGIN = "https://www.gwm-eu.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
CHATBOT_SRC = REPO_ROOT / "chatbot"

# Third-party domains whose <script> tags we strip (cleaner local console)
TRACKING_DOMAINS = {
    "googletagmanager.com",
    "google-analytics.com",
    "googleadservices.com",
    "doubleclick.net",
    "facebook.net",
    "clarity.ms",
    "hotjar.com",
    "hubspot.com",
    "linkedin.com",
}

REQUEST_TIMEOUT = 15
ASSET_RETRY = 1


# -------- Helpers -------------------------------------------------------------

session = requests.Session()
session.headers.update(HEADERS)

# Track downloaded URLs to avoid duplicates
downloaded: set[str] = set()
failed: set[str] = set()


def log(tag: str, msg: str) -> None:
    print(f"[{tag:>4}] {msg}")


def is_same_origin(url: str) -> bool:
    try:
        netloc = urlparse(url).netloc
        return netloc == "" or netloc == urlparse(ORIGIN).netloc
    except Exception:
        return False


def normalise(url: str, base: str) -> str | None:
    """Resolve a URL against the base; drop fragments and javascript:/data:/mailto:."""
    if not url:
        return None
    url = url.strip()
    if url.startswith(("javascript:", "data:", "mailto:", "tel:", "#")):
        return None
    absolute = urljoin(base, url)
    absolute, _ = urldefrag(absolute)
    return absolute


def url_to_local_path(url: str) -> Path:
    """Map an asset URL to a path under SITE_DIR, preserving structure."""
    parsed = urlparse(url)
    path = parsed.path
    if not path or path.endswith("/"):
        path = (path or "/") + "index.html"
    # Encode query string into filename so siblings with different ?v= survive
    if parsed.query:
        suffix = re.sub(r"[^A-Za-z0-9._-]+", "_", parsed.query)[:60]
        root, ext = os.path.splitext(path)
        path = f"{root}__{suffix}{ext}"
    local = SITE_DIR / path.lstrip("/")
    return local


def download_asset(url: str) -> Path | None:
    """Download a single same-origin asset to disk. Returns local path or None."""
    if url in downloaded:
        return url_to_local_path(url)
    if url in failed:
        return None

    local = url_to_local_path(url)
    if local.exists() and local.stat().st_size > 0:
        downloaded.add(url)
        return local

    local.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(ASSET_RETRY + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT, stream=True)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            with open(local, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            downloaded.add(url)
            log("OK", f"{url}  ->  {local.relative_to(SITE_DIR)}")
            return local
        except Exception as e:
            last_err = e
            time.sleep(0.3)
    failed.add(url)
    log("FAIL", f"{url}  ({last_err})")
    return None


# -------- CSS post-processing -------------------------------------------------

CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.IGNORECASE)
CSS_IMPORT_RE = re.compile(
    r"""@import\s+(?:url\()?\s*['"]([^'"\)]+)['"]\s*\)?\s*;""", re.IGNORECASE
)


def process_css(css_path: Path, base_url: str) -> None:
    """Find url(...) and @import refs inside CSS, download them, rewrite paths."""
    try:
        text = css_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log("WARN", f"could not read {css_path}: {e}")
        return

    def handle(asset_url: str) -> str:
        absolute = normalise(asset_url, base_url)
        if not absolute or not is_same_origin(absolute):
            return asset_url  # leave external CDN refs alone
        downloaded_path = download_asset(absolute)
        if downloaded_path is None:
            return asset_url
        # Rewrite to absolute path under site root so it works from any depth
        rel = "/" + str(downloaded_path.relative_to(SITE_DIR)).replace(os.sep, "/")
        # Recurse into nested CSS
        if downloaded_path.suffix.lower() == ".css":
            process_css(downloaded_path, absolute)
        return rel

    def url_repl(m: re.Match) -> str:
        quote, asset_url = m.group(1), m.group(2)
        new = handle(asset_url)
        return f"url({quote}{new}{quote})"

    def import_repl(m: re.Match) -> str:
        new = handle(m.group(1))
        return f'@import "{new}";'

    new_text = CSS_URL_RE.sub(url_repl, text)
    new_text = CSS_IMPORT_RE.sub(import_repl, new_text)
    if new_text != text:
        css_path.write_text(new_text, encoding="utf-8")


# -------- HTML processing -----------------------------------------------------

def is_tracking_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host.endswith(dom) for dom in TRACKING_DOMAINS)


def rewrite_attr(tag, attr: str, base_url: str, *, allow_cross_origin_link: bool = False) -> None:
    """Resolve `attr` on `tag`; download if same-origin; rewrite to local path."""
    val = tag.get(attr)
    if not val:
        return
    absolute = normalise(val, base_url)
    if not absolute:
        return
    if is_tracking_url(absolute):
        return
    if not is_same_origin(absolute):
        if allow_cross_origin_link:
            tag[attr] = absolute  # leave links to other gwm regions absolute
        else:
            tag[attr] = absolute  # external resource – let the browser fetch it
        return
    local = download_asset(absolute)
    if local is None:
        return
    rel = "/" + str(local.relative_to(SITE_DIR)).replace(os.sep, "/")
    tag[attr] = rel
    if local.suffix.lower() == ".css":
        process_css(local, absolute)


def rewrite_srcset(tag, base_url: str) -> None:
    val = tag.get("srcset")
    if not val:
        return
    parts = []
    for item in val.split(","):
        item = item.strip()
        if not item:
            continue
        bits = item.split()
        if not bits:
            continue
        url = bits[0]
        descriptor = " ".join(bits[1:])
        absolute = normalise(url, base_url)
        if absolute and is_same_origin(absolute) and not is_tracking_url(absolute):
            local = download_asset(absolute)
            if local is not None:
                url = "/" + str(local.relative_to(SITE_DIR)).replace(os.sep, "/")
        elif absolute:
            url = absolute
        parts.append(url + (f" {descriptor}" if descriptor else ""))
    tag["srcset"] = ", ".join(parts)


def rewrite_inline_style(tag, base_url: str) -> None:
    style = tag.get("style")
    if not style or "url(" not in style:
        return

    def repl(m: re.Match) -> str:
        quote, asset_url = m.group(1), m.group(2)
        absolute = normalise(asset_url, base_url)
        if not absolute or not is_same_origin(absolute):
            return m.group(0)
        local = download_asset(absolute)
        if local is None:
            return m.group(0)
        rel = "/" + str(local.relative_to(SITE_DIR)).replace(os.sep, "/")
        return f"url({quote}{rel}{quote})"

    tag["style"] = CSS_URL_RE.sub(repl, style)


def rewrite_anchor(tag) -> None:
    """Same-origin /eu/* links point to pages we don't have → neuter to '#'."""
    href = tag.get("href")
    if not href:
        return
    absolute = normalise(href, ENTRY_URL)
    if not absolute:
        return
    if absolute == ENTRY_URL or absolute == ENTRY_URL + "/":
        tag["href"] = "/"
        return
    parsed = urlparse(absolute)
    if parsed.netloc == urlparse(ORIGIN).netloc and parsed.path.startswith("/eu"):
        # internal EU page that we did not scrape → no-op anchor with tooltip
        tag["href"] = "#"
        tag["data-original-href"] = absolute
        existing_title = tag.get("title", "")
        tag["title"] = (existing_title + " (demo: page not scraped)").strip()
    else:
        # cross-region or external → keep absolute so it still works
        tag["href"] = absolute


def inject_chatbot(soup: BeautifulSoup) -> None:
    head = soup.find("head") or soup
    body_tag = soup.find("body") or soup
    css = soup.new_tag("link", rel="stylesheet", href="/chatbot/chatbot.css")
    head.append(css)
    js = soup.new_tag("script", src="/chatbot/chatbot.js")
    js["defer"] = ""
    body_tag.append(js)


def remove_tracking(soup: BeautifulSoup) -> int:
    removed = 0
    for s in list(soup.find_all("script")):
        src = s.get("src") or ""
        if src and is_tracking_url(normalise(src, ENTRY_URL) or src):
            s.decompose()
            removed += 1
            continue
        # Inline GTM / GA bootstrap snippets
        text = (s.string or "").lower()
        if any(t in text for t in ("googletagmanager", "google-analytics", "gtag(", "fbq(")):
            s.decompose()
            removed += 1
    return removed


def process_homepage(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 1. Strip tracking
    n_removed = remove_tracking(soup)
    if n_removed:
        log("INFO", f"removed {n_removed} tracking scripts")

    # 2. Asset-bearing tags
    for link in soup.find_all("link"):
        rels = link.get("rel") or []
        if any(r in ("stylesheet", "icon", "shortcut icon", "apple-touch-icon",
                     "preload", "modulepreload", "manifest", "mask-icon") for r in rels):
            rewrite_attr(link, "href", ENTRY_URL)

    for script in soup.find_all("script"):
        rewrite_attr(script, "src", ENTRY_URL)

    for img in soup.find_all("img"):
        rewrite_attr(img, "src", ENTRY_URL)
        rewrite_srcset(img, ENTRY_URL)

    for source in soup.find_all("source"):
        rewrite_attr(source, "src", ENTRY_URL)
        rewrite_srcset(source, ENTRY_URL)

    for video in soup.find_all(["video", "audio"]):
        rewrite_attr(video, "src", ENTRY_URL)
        rewrite_attr(video, "poster", ENTRY_URL)

    for tag in soup.find_all(style=True):
        rewrite_inline_style(tag, ENTRY_URL)

    # 3. Inline <style> blocks
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            tmp = SITE_DIR / "_tmp_inline.css"
            SITE_DIR.mkdir(parents=True, exist_ok=True)
            tmp.write_text(style_tag.string, encoding="utf-8")
            process_css(tmp, ENTRY_URL)
            style_tag.string.replace_with(tmp.read_text(encoding="utf-8"))
            tmp.unlink(missing_ok=True)

    # 4. Anchors
    for a in soup.find_all("a"):
        rewrite_anchor(a)

    # 5. Inject chatbot
    inject_chatbot(soup)

    return str(soup)


# -------- Main ----------------------------------------------------------------

def copy_chatbot_assets() -> None:
    target = SITE_DIR / "chatbot"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(CHATBOT_SRC, target)
    log("OK", f"copied chatbot assets -> {target.relative_to(SITE_DIR)}")


def main() -> int:
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    log("INFO", f"fetching homepage: {ENTRY_URL}")
    try:
        r = session.get(ENTRY_URL, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        log("FAIL", f"could not fetch homepage: {e}")
        return 1

    html = r.text
    log("INFO", f"homepage size: {len(html):,} bytes")

    new_html = process_homepage(html)

    # Write index.html
    index_path = SITE_DIR / "index.html"
    index_path.write_text(new_html, encoding="utf-8")
    log("OK", f"wrote {index_path.relative_to(REPO_ROOT)}  ({len(new_html):,} bytes)")

    # Copy chatbot widget
    copy_chatbot_assets()

    log("INFO", f"downloaded {len(downloaded)} assets, {len(failed)} failed")
    log("INFO", f"site root: {SITE_DIR}")
    log("INFO", "preview with:  ./run.sh   (then open http://localhost:8000)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
