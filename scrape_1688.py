#!/usr/bin/env python3
"""
1688 商品主图爬虫 — 三层鲁棒方案
  Layer 1: detail.1688.com HTML 直连，正则抓 window.runParams
  Layer 2: Playwright 持久化 profile (cookie 跨次复用)
  Layer 3: OpenCV 拼图缺口识别 + bezier 拖动 (在 Layer 2 内被调用)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

import httpx

# OpenCV / numpy 仅在滑块求解时用到，延迟导入避免无谓依赖检查
cv2 = None  # type: ignore
np = None   # type: ignore


# ──────────────────────────────────────────────────────────────────────
# Section 1: CLI & 工具函数
# ──────────────────────────────────────────────────────────────────────

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)

OFFER_ID_RE = re.compile(r"offer/(\d+)\.html")
SIZE_SUFFIX_RE = re.compile(r"_\d+x\d+[a-z\d]*\.(jpg|jpeg|png|webp)", re.I)
SUMM_SUFFIX_RE = re.compile(r"\.summ\.(jpg|jpeg|png|webp)", re.I)
IMAGE_KEY_RE = re.compile(r"(image|img|pic|photo|gallery)", re.I)
ALICDN_RE = re.compile(r"(cbu01|gw|img)\.alicdn\.com", re.I)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Scrape main carousel images for a 1688 product.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("target", help="Full 1688 URL or bare offer ID (digits only).")
    p.add_argument("-o", "--output", default=None, help="Output dir (default: ./images/<offer_id>/)")
    p.add_argument("--headful", action="store_true", help="Show the browser (debugging).")
    p.add_argument("--no-api", action="store_true", help="Skip Layer 1 (API direct), go straight to browser.")
    p.add_argument("--profile", default="./.chrome_profile", help="Persistent Chrome profile dir.")
    p.add_argument("--timeout", type=int, default=30, help="Per-step wait timeout (seconds).")
    p.add_argument("--debug-slider", action="store_true",
                   help="Dump bg/piece/match images to ./debug_slider/ for inspection.")
    return p.parse_args()


def extract_offer_id(target: str) -> Optional[str]:
    target = target.strip()
    if target.isdigit():
        return target
    m = OFFER_ID_RE.search(target)
    return m.group(1) if m else None


def normalize_image_url(url: str) -> str:
    """Strip alicdn size suffixes (e.g. `_400x400q90.jpg`) to get original."""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://cbu01.alicdn.com" + url
    url = SIZE_SUFFIX_RE.sub(r".\1", url)
    url = SUMM_SUFFIX_RE.sub(r".\1", url)
    return url


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def find_image_urls(obj: Any) -> list[str]:
    """Recursively walk a JSON-like object collecting image URLs found under
    image-named keys whose values are lists of strings or {url|src|...} dicts."""
    out: list[str] = []

    def extract_url(item: Any) -> Optional[str]:
        if isinstance(item, str):
            if "alicdn.com" in item or item.startswith("//") or item.startswith("http"):
                return item
        elif isinstance(item, dict):
            for k in ("fullPathImageURI", "imageURI", "imageUrl", "url", "src",
                      "big", "imgUrl", "originalImageURI"):
                v = item.get(k)
                if isinstance(v, str) and ("alicdn.com" in v or v.startswith("//") or v.startswith("http")):
                    return v
        return None

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if IMAGE_KEY_RE.search(k):
                    candidates: list[Any] = []
                    if isinstance(v, list):
                        candidates = v
                    elif isinstance(v, dict):
                        # e.g. {"images": {"detailImageList": [...]}}
                        candidates = []
                    for item in candidates:
                        u = extract_url(item)
                        if u:
                            out.append(u)
                walk(v)
        elif isinstance(o, list):
            for item in o:
                walk(item)

    walk(obj)
    return out


# ──────────────────────────────────────────────────────────────────────
# Section 2: Layer 1 — API 直连
# ──────────────────────────────────────────────────────────────────────

RUN_PARAMS_MARKERS = (
    "window.runParams = ",
    "window.runParams=",
    "window._DATA_ = ",
    "window._DATA_=",
    "window.__INIT_DATA__ = ",
    "window.__INIT_DATA__=",
)


def extract_first_object_literal(html: str, start_idx: int) -> Optional[str]:
    """From html[start_idx:] find the first `{...}` literal with balanced braces,
    string-aware. Returns the slice or None."""
    n = len(html)
    i = html.find("{", start_idx)
    if i == -1:
        return None
    depth = 0
    in_str = False
    str_quote = ""
    escape = False
    j = i
    while j < n:
        c = html[j]
        if escape:
            escape = False
            j += 1
            continue
        if in_str:
            if c == "\\":
                escape = True
            elif c == str_quote:
                in_str = False
        else:
            if c == '"' or c == "'":
                in_str = True
                str_quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return html[i:j + 1]
        j += 1
    return None


def parse_run_params(html: str) -> Optional[dict]:
    """Try every known marker; return the first parseable JSON dict found."""
    for marker in RUN_PARAMS_MARKERS:
        idx = html.find(marker)
        if idx == -1:
            continue
        literal = extract_first_object_literal(html, idx + len(marker))
        if not literal:
            continue
        try:
            return json.loads(literal)
        except json.JSONDecodeError:
            # Common escapes that break json: NaN, undefined, single quotes.
            cleaned = literal.replace("undefined", "null")
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue
    return None


def try_api_fetch(offer_id: str, timeout: int = 15) -> Optional[list[str]]:
    """Layer 1: direct HTTP fetch of the desktop product page; parse runParams.
    Returns a list of image URLs, or None if blocked / no images found."""
    url = f"https://detail.1688.com/offer/{offer_id}.html"
    headers = {
        "User-Agent": DESKTOP_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.1688.com/",
        "Cache-Control": "no-cache",
    }
    log(f"Layer 1: GET {url}")
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
            r = client.get(url)
    except httpx.HTTPError as e:
        log(f"Layer 1: network error: {e}")
        return None

    final_url = str(r.url)
    if "punish" in final_url or "_____tmd_____" in final_url:
        log(f"Layer 1: blocked (redirected to punish): {final_url}")
        return None
    if r.status_code != 200:
        log(f"Layer 1: HTTP {r.status_code}")
        return None

    data = parse_run_params(r.text)
    if not data:
        log("Layer 1: no runParams / _DATA_ block in HTML")
        return None

    raw = find_image_urls(data)
    urls = dedupe_preserve_order(normalize_image_url(u) for u in raw if ALICDN_RE.search(u))
    if not urls:
        log("Layer 1: parsed runParams but no alicdn image URLs found")
        return None
    log(f"Layer 1: extracted {len(urls)} image URLs")
    return urls


# ──────────────────────────────────────────────────────────────────────
# Section 4: Layer 3 — OpenCV 拼图滑块求解 (Layer 2 内嵌调用)
# ──────────────────────────────────────────────────────────────────────

SLIDER_BUTTON_SELECTORS = (
    "#nc_1_n1z",
    "[id*='nc_'][id$='_n1z']",
    ".btn_slide",
    ".nc_iconfont.btn_slide",
    "[class*='slider'][role='button']",
    "[class*='captcha'] [class*='slider']",
    "[class*='handler']",
)
SLIDER_TRACK_SELECTORS = (
    "#nc_1__scale_text",
    "#nc_1_wrapper",
    ".nc-lang-cnt",
    "[class*='captcha-bg']",
    "[class*='captcha'] [class*='track']",
)
SLIDER_BG_SELECTORS = (
    "#nc_1__bg",
    "[class*='captcha'] canvas",
    "[class*='puzzle'] canvas",
    "img[src*='bg']",
)
SLIDER_PIECE_SELECTORS = (
    "[class*='puzzle'] canvas + canvas",
    "img[src*='slice']",
    "img[src*='piece']",
)


def _ensure_cv():
    global cv2, np
    if cv2 is None:
        import cv2 as _cv2  # type: ignore
        import numpy as _np  # type: ignore
        cv2, np = _cv2, _np


def _gen_drag_track(distance: float) -> list[float]:
    """Physics-inspired track: accelerate ~70% then decelerate, with overshoot+pullback."""
    track: list[float] = []
    current = 0.0
    mid = distance * 0.7
    t = 0.18
    v = 0.0
    while current < distance:
        a = random.uniform(2.0, 3.5) if current < mid else random.uniform(-4.0, -2.0)
        v0 = v
        v = max(0.0, v0 + a * t)
        move = max(1.0, v0 * t + 0.5 * a * t * t)
        if current + move > distance:
            move = distance - current
        track.append(move)
        current += move
        if move <= 0:
            break
    # Slight overshoot + pull back
    overshoot = random.uniform(2.0, 5.0)
    track.append(overshoot)
    track.append(-random.uniform(overshoot * 0.6, overshoot))
    return track


def _find_gap_x(bg_png: bytes, piece_png: bytes, debug_dir: Optional[Path] = None) -> Optional[int]:
    """OpenCV template matching to locate the puzzle gap inside the background.
    Returns gap-left X in pixels, or None if no confident match."""
    _ensure_cv()
    bg = cv2.imdecode(np.frombuffer(bg_png, np.uint8), cv2.IMREAD_COLOR)  # type: ignore
    piece = cv2.imdecode(np.frombuffer(piece_png, np.uint8), cv2.IMREAD_UNCHANGED)  # type: ignore
    if bg is None or piece is None:
        return None

    # If piece has alpha, crop to the opaque bbox so the template isn't padded with transparent pixels.
    if piece.ndim == 3 and piece.shape[2] == 4:
        alpha = piece[:, :, 3]
        ys, xs = np.where(alpha > 10)  # type: ignore
        if len(xs) and len(ys):
            piece = piece[ys.min():ys.max() + 1, xs.min():xs.max() + 1, :3]
        else:
            piece = piece[:, :, :3]

    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)  # type: ignore
    piece_gray = cv2.cvtColor(piece, cv2.COLOR_BGR2GRAY)  # type: ignore
    bg_edge = cv2.Canny(bg_gray, 100, 200)  # type: ignore
    piece_edge = cv2.Canny(piece_gray, 100, 200)  # type: ignore

    if piece_edge.shape[0] >= bg_edge.shape[0] or piece_edge.shape[1] >= bg_edge.shape[1]:
        return None

    res = cv2.matchTemplate(bg_edge, piece_edge, cv2.TM_CCOEFF_NORMED)  # type: ignore
    _, max_val, _, max_loc = cv2.minMaxLoc(res)  # type: ignore

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / "bg.png"), bg)  # type: ignore
        cv2.imwrite(str(debug_dir / "piece.png"), piece)  # type: ignore
        marked = bg.copy()
        h, w = piece_edge.shape
        cv2.rectangle(marked, max_loc, (max_loc[0] + w, max_loc[1] + h), (0, 0, 255), 2)  # type: ignore
        cv2.imwrite(str(debug_dir / "match.png"), marked)  # type: ignore
        log(f"Layer 3: debug images saved to {debug_dir}/ (match score={max_val:.3f})")

    if max_val < 0.3:
        return None
    return int(max_loc[0])


async def _first_visible(scope, selectors):
    """Return the first locator from `selectors` that resolves to a visible element."""
    for sel in selectors:
        try:
            loc = scope.locator(sel).first
            if await loc.count() == 0:
                continue
            if await loc.is_visible():
                return loc, sel
        except Exception:
            continue
    return None, None


async def _slider_scope(page):
    """Slider may live in an iframe. Return (scope, in_iframe) where scope is a
    Frame or Page whose locator(...) walks the right DOM."""
    for f in page.frames:
        url = (f.url or "").lower()
        if any(k in url for k in ("punish", "x5sec", "captcha", "baxia")):
            return f, True
    # Fallback: any iframe at all that contains a slider button
    for f in page.frames:
        if f == page.main_frame:
            continue
        try:
            cnt = await f.locator(",".join(SLIDER_BUTTON_SELECTORS)).count()
            if cnt > 0:
                return f, True
        except Exception:
            continue
    return page, False


async def solve_puzzle_slider(page, max_attempts: int = 3, debug: bool = False) -> bool:
    """Detect and solve the slider CAPTCHA. Returns True on apparent success."""
    debug_dir = Path("./debug_slider") if debug else None

    for attempt in range(1, max_attempts + 1):
        log(f"Layer 3: slider attempt {attempt}/{max_attempts}")
        await asyncio.sleep(random.uniform(0.5, 1.2))

        scope, in_iframe = await _slider_scope(page)
        log(f"Layer 3: slider scope = {'iframe' if in_iframe else 'main page'}")

        button, btn_sel = await _first_visible(scope, SLIDER_BUTTON_SELECTORS)
        if button is None:
            log("Layer 3: no slider button found — assume already passed")
            return True

        track_loc, _ = await _first_visible(scope, SLIDER_TRACK_SELECTORS)
        bg_loc, _ = await _first_visible(scope, SLIDER_BG_SELECTORS)
        piece_loc, _ = await _first_visible(scope, SLIDER_PIECE_SELECTORS)

        btn_box = await button.bounding_box()
        if not btn_box:
            log("Layer 3: button bounding_box unavailable; retrying")
            continue

        # Compute drag distance: prefer OpenCV gap; fall back to track width.
        distance: Optional[float] = None
        if bg_loc and piece_loc:
            try:
                bg_png = await bg_loc.screenshot()
                piece_png = await piece_loc.screenshot(omit_background=True)
                gap_x = _find_gap_x(bg_png, piece_png, debug_dir)
                if gap_x is not None:
                    bg_box = await bg_loc.bounding_box()
                    piece_box = await piece_loc.bounding_box()
                    if bg_box and piece_box:
                        # Gap X is in bg-image coords; convert to page coords, then
                        # subtract piece's current left edge.
                        target_page_x = bg_box["x"] + gap_x
                        distance = target_page_x - piece_box["x"]
                        log(f"Layer 3: OpenCV gap_x={gap_x}px → drag distance={distance:.1f}px")
            except Exception as e:
                log(f"Layer 3: OpenCV path failed: {e}")

        if distance is None and track_loc is not None:
            try:
                track_box = await track_loc.bounding_box()
                if track_box:
                    distance = track_box["width"] - btn_box["width"] - 4
                    log(f"Layer 3: fallback track-width drag distance={distance:.1f}px")
            except Exception:
                pass

        if distance is None or distance <= 5:
            log("Layer 3: could not determine drag distance; retrying")
            continue

        # Bezier drag
        start_x = btn_box["x"] + btn_box["width"] / 2
        start_y = btn_box["y"] + btn_box["height"] / 2
        track = _gen_drag_track(distance)

        await page.mouse.move(start_x, start_y)
        await asyncio.sleep(random.uniform(0.15, 0.3))
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.1, 0.25))

        x, y = start_x, start_y
        for dx in track:
            x += dx
            y += random.uniform(-1.5, 1.5)
            await page.mouse.move(x, y, steps=1)
            await asyncio.sleep(random.uniform(0.005, 0.022))

        await asyncio.sleep(random.uniform(0.25, 0.45))
        await page.mouse.up()

        # Wait and check whether slider went away / page navigated
        await asyncio.sleep(random.uniform(2.0, 3.0))
        try:
            still_there = await button.is_visible()
        except Exception:
            still_there = False
        cur_url = page.url
        if not still_there and "punish" not in cur_url and "x5sec" not in cur_url:
            log("Layer 3: slider passed")
            return True
        log(f"Layer 3: still on slider/punish (url={cur_url[:80]}...); retrying")

    return False


# ──────────────────────────────────────────────────────────────────────
# Section 3: Layer 2 — Playwright 持久化 profile
# ──────────────────────────────────────────────────────────────────────

STEALTH_JS = r"""
() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
  Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
  window.chrome = window.chrome || { runtime: {} };
  const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
  if (originalQuery) {
    window.navigator.permissions.query = (parameters) => (
      parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
    );
  }
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function (parameter) {
    if (parameter === 37445) return 'Intel Inc.';            // UNMASKED_VENDOR_WEBGL
    if (parameter === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
    return getParameter.call(this, parameter);
  };
}
"""


JS_EXTRACT_IMAGES = r"""
() => {
  const out = [];
  // Walk known global data blobs
  const blobs = [window._DATA_, window.__INIT_DATA__, window.runParams,
                 window.__GLOBAL_DATA__, window.detailData];
  const KEY_RE = /(image|img|pic|photo|gallery)/i;
  const URL_KEYS = ['fullPathImageURI','imageURI','imageUrl','url','src','big','imgUrl','originalImageURI'];
  function walk(o) {
    if (!o) return;
    if (Array.isArray(o)) { o.forEach(walk); return; }
    if (typeof o !== 'object') return;
    for (const [k, v] of Object.entries(o)) {
      if (KEY_RE.test(k) && Array.isArray(v)) {
        for (const item of v) {
          if (typeof item === 'string' && /alicdn\.com/.test(item)) out.push(item);
          else if (item && typeof item === 'object') {
            for (const uk of URL_KEYS) {
              if (typeof item[uk] === 'string' && /alicdn\.com/.test(item[uk])) {
                out.push(item[uk]); break;
              }
            }
          }
        }
      }
      walk(v);
    }
  }
  for (const b of blobs) walk(b);
  // DOM fallback: visible <img> in known carousel containers
  const sel = '[class*="gallery"] img, [class*="preview"] img, [class*="carousel"] img, .swiper-slide img, .image-list img';
  document.querySelectorAll(sel).forEach(img => {
    const u = img.currentSrc || img.src || img.getAttribute('data-src') || img.getAttribute('data-image');
    if (u && /alicdn\.com/.test(u)) out.push(u);
  });
  return out;
}
"""


async def try_browser_fetch(offer_id: str, profile_dir: str, headful: bool,
                            timeout: int, debug_slider: bool) -> Optional[list[str]]:
    """Layer 2: Playwright with persistent context. Calls Layer 3 if slider appears."""
    from playwright.async_api import async_playwright

    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    target_url = f"https://m.1688.com/offer/{offer_id}.html"

    async with async_playwright() as p:
        log(f"Layer 2: launching browser (profile={profile_dir}, headless={not headful})")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=not headful,
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            user_agent=MOBILE_UA,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        await context.add_init_script(STEALTH_JS)
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            log(f"Layer 2: GET {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout * 1000)
            await asyncio.sleep(2.0)

            # Slider check (URL or DOM)
            cur_url = page.url
            slider_in_dom = False
            try:
                btn, _ = await _first_visible(page, SLIDER_BUTTON_SELECTORS)
                slider_in_dom = btn is not None
            except Exception:
                pass
            in_punish = "punish" in cur_url or "x5sec" in cur_url or "_____tmd_____" in cur_url

            if in_punish or slider_in_dom:
                log(f"Layer 2: slider detected (punish={in_punish}, dom={slider_in_dom})")
                ok = await solve_puzzle_slider(page, max_attempts=3, debug=debug_slider)
                if not ok:
                    log("Layer 2: slider unsolved after 3 attempts")
                    raise SliderFailed()
                # After solving, give the page a moment to navigate back
                await asyncio.sleep(2.0)
                if "punish" in page.url or "x5sec" in page.url:
                    # Some flows need an explicit re-navigation
                    log("Layer 2: re-navigating to product page after slider")
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    await asyncio.sleep(2.0)
            else:
                log("Layer 2: no slider — direct extract")

            # Trigger lazy load
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                await asyncio.sleep(0.8)
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(0.5)
            except Exception:
                pass

            raw: list[str] = await page.evaluate(JS_EXTRACT_IMAGES)
            urls = dedupe_preserve_order(
                normalize_image_url(u) for u in raw if ALICDN_RE.search(u)
            )
            if not urls:
                log("Layer 2: no images extracted from page")
                return None
            log(f"Layer 2: extracted {len(urls)} image URLs")
            return urls
        finally:
            await context.close()


class SliderFailed(Exception):
    pass


# ──────────────────────────────────────────────────────────────────────
# Section 5: 下载
# ──────────────────────────────────────────────────────────────────────


def _ext_from_url(url: str) -> str:
    path = urlparse(url).path
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.lower().endswith(ext):
            return ext
    return ".jpg"


def download_images(urls: list[str], out_dir: Path, offer_id: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": "https://detail.1688.com/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    saved: list[Path] = []
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        for i, url in enumerate(urls, start=1):
            ext = _ext_from_url(url)
            dest = out_dir / f"{offer_id}_{i:02d}{ext}"
            try:
                r = client.get(url)
                if r.status_code != 200 or len(r.content) < 1024:
                    log(f"  ! [{i:02d}] HTTP {r.status_code} or too small ({len(r.content)} bytes): {url}")
                    continue
                dest.write_bytes(r.content)
                log(f"  ✓ [{i:02d}] {dest.name} ({len(r.content) // 1024} KB)")
                saved.append(dest)
            except httpx.HTTPError as e:
                log(f"  ! [{i:02d}] download error: {e}")
    return saved


# ──────────────────────────────────────────────────────────────────────
# Section 6: main 编排
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    args = parse_args()
    offer_id = extract_offer_id(args.target)
    if not offer_id:
        print("ERROR: could not extract offer ID from target.", file=sys.stderr)
        return 1

    out_dir = Path(args.output) if args.output else Path("./images") / offer_id
    log(f"Target offer ID: {offer_id}")
    log(f"Output dir:      {out_dir}")

    urls: Optional[list[str]] = None

    # ── Layer 1
    if not args.no_api:
        urls = try_api_fetch(offer_id, timeout=args.timeout)

    # ── Layer 2 (with embedded Layer 3)
    if not urls:
        try:
            urls = asyncio.run(try_browser_fetch(
                offer_id=offer_id,
                profile_dir=args.profile,
                headful=args.headful,
                timeout=args.timeout,
                debug_slider=args.debug_slider,
            ))
        except SliderFailed:
            print("ERROR: slider CAPTCHA could not be solved.", file=sys.stderr)
            return 2
        except Exception as e:
            # Network / browser error — print one clean line, skip the traceback
            print(f"ERROR: Layer 2 browser fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
            urls = None

    if not urls:
        print("ERROR: no images obtained from any layer.", file=sys.stderr)
        return 3

    log(f"Downloading {len(urls)} images...")
    saved = download_images(urls, out_dir, offer_id)
    if not saved:
        print("ERROR: parsed image URLs but none downloaded successfully.", file=sys.stderr)
        return 1

    log(f"Done. Saved {len(saved)} images to {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
