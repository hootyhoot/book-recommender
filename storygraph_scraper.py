"""Scrapes book lists from a public StoryGraph profile.

No headless browser needed - StoryGraph's list pages are plain
server-rendered HTML, so a request plus a session cookie is enough,
as long as the TLS fingerprint looks like a real browser (Cloudflare
serves a JS challenge that plain `requests` can never pass otherwise,
since it doesn't run JS - curl_cffi's browser impersonation clears it).

This module only fetches and parses; it doesn't cache or schedule
anything, that's handled by refresh_cache.py.
"""

import io
import json
import os
import re
import time

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from bs4 import BeautifulSoup
from PIL import Image

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
COVERS_DIR = os.path.join(_MODULE_DIR, "static", "covers")
_COVER_META_CACHE_PATH = os.path.join(COVERS_DIR, "meta.json")

TARGETS = {
    "currently_reading": "currently-reading",
    "to_read": "to-read",
    "read": "books-read",
    "favorites": "favorites",
}


class StoryGraphError(Exception):
    pass


def _session_cookie():
    cookie = os.getenv("storygraph_session_cookie")
    if not cookie:
        raise StoryGraphError("storygraph_session_cookie environment variable is not set")
    return cookie


def _parse_book_pane(pane):
    book = {"id": pane.get("data-book-id")}

    cover_img = pane.select_one(".book-cover img")
    book["cover_url"] = cover_img["src"] if cover_img and cover_img.get("src") else None

    title_a = pane.select_one('.book-title-author-and-series a[href^="/books/"]')
    book["title"] = title_a.get_text(strip=True) if title_a else None
    book["url"] = f"https://app.thestorygraph.com{title_a['href']}" if title_a else None

    author_a = pane.select_one('.book-title-author-and-series a[href^="/authors/"]')
    book["author"] = author_a.get_text(strip=True) if author_a else None

    book["genre_tags"] = list(dict.fromkeys(
        t.get_text(strip=True) for t in pane.select(".book-pane-tag-section span.text-teal-700")
    ))
    book["mood_tags"] = list(dict.fromkeys(
        t.get_text(strip=True) for t in pane.select(".book-pane-tag-section span.text-pink-500")
    ))

    book["page_count"] = None
    for p in pane.find_all("p"):
        text = p.get_text(strip=True)
        if "pages" in text.lower():
            match = re.search(r"(\d+)", text)
            if match:
                book["page_count"] = int(match.group(1))
            break

    return book


def _fetch_page(url, cookie, retries=5, backoff=4):
    cookies = {"_storygraph_session": cookie}
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, cookies=cookies, impersonate="chrome", timeout=15)
        except RequestException as exc:
            last_error = exc
            time.sleep(backoff)
            continue

        title = BeautifulSoup(response.content, "html.parser").title
        title_text = title.get_text() if title else ""

        if "Sign In" in title_text:
            raise StoryGraphError(
                "StoryGraph returned a sign-in page - the session cookie has likely expired "
                "and needs to be refreshed from the browser."
            )
        if response.status_code == 200 and "moment" not in title_text.lower():
            return response.content

        last_error = StoryGraphError(f"unexpected response (status={response.status_code}, title={title_text!r})")
        time.sleep(backoff)

    raise last_error


def fetch_list(target, username, max_pages=25):
    """Fetch one of currently-reading / to-read / books-read for a user."""
    cookie = _session_cookie()
    books = []
    for page in range(1, max_pages + 1):
        url = f"https://app.thestorygraph.com/{target}/{username}?page={page}"
        html = _fetch_page(url, cookie)
        soup = BeautifulSoup(html, "html.parser")
        panes = soup.select(".book-pane")
        books.extend(_parse_book_pane(pane) for pane in panes)
        if len(panes) < 10:
            break
    return books


def fetch_all(username, max_pages=25):
    """Fetch currently reading, to-read, and read lists for a user."""
    result = {}
    for key, target in TARGETS.items():
        result[key] = fetch_list(target, username, max_pages=max_pages)
        time.sleep(2)  # space out requests to different endpoints, not just retries
    return result


def _relative_luminance(rgb):
    r, g, b = (c / 255 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _load_cover_meta_cache():
    try:
        with open(_COVER_META_CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cover_meta_cache(cache):
    os.makedirs(COVERS_DIR, exist_ok=True)
    tmp_path = _COVER_META_CACHE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp_path, _COVER_META_CACHE_PATH)


def _fetch_cover_meta(cover_url, book_id):
    """(spine_text, cover_ratio, cover_local) sampled directly from the
    real image: spine_text is 'dark' or 'light', whichever reads clearly
    over the strip of the cover actually visible on the spine (its left
    edge); cover_ratio is width/height, used so the hover pull-out can
    size itself to the book's real proportions instead of cropping tall
    or wide covers to an assumed 2:3. Also saves a local WebP copy so the
    page serves covers from itself instead of hot-linking StoryGraph's
    CDN on every visitor's browser - cover_local is the static/-relative
    path to that copy, or None if the save failed."""
    try:
        resp = requests.get(cover_url, impersonate="chrome", timeout=10)
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        w, h = img.size
        strip = img.crop((0, 0, max(1, w // 4), h)).resize((6, 6))
        avg = tuple(sum(c) / len(c) for c in zip(*strip.getdata()))
        text_color = "dark" if _relative_luminance(avg) > 0.55 else "light"
        ratio = round(w / h, 4)

        cover_local = None
        if book_id:
            os.makedirs(COVERS_DIR, exist_ok=True)
            dest = os.path.join(COVERS_DIR, f"{book_id}.webp")
            img.save(dest, "WEBP", quality=92, method=6)
            cover_local = f"covers/{book_id}.webp"

        return text_color, ratio, cover_local
    except Exception:
        return "light", 0.667, None


def annotate_cover_meta(data):
    """Adds spine_text, cover_ratio, and cover_local (see
    _fetch_cover_meta) to every book across all lists in a fetch_all()-
    shaped dict, in place. Books already seen in a previous run are read
    straight from the on-disk meta cache with no network fetch at all -
    only genuinely new book ids get downloaded and converted, so a daily
    refresh stays fast and StoryGraph/its CDN only ever sees a request
    for a cover exactly once, ever."""
    cache = _load_cover_meta_cache()
    cache_changed = False

    for books in data.values():
        for book in books:
            book_id = book.get("id")
            cached = cache.get(book_id) if book_id else None
            if cached:
                book["spine_text"] = cached["spine_text"]
                book["cover_ratio"] = cached["cover_ratio"]
                if cached.get("cover_local"):
                    book["cover_local"] = cached["cover_local"]
                continue

            if book.get("cover_url"):
                text_color, ratio, cover_local = _fetch_cover_meta(book["cover_url"], book_id)
            else:
                text_color, ratio, cover_local = "light", 0.667, None

            book["spine_text"], book["cover_ratio"] = text_color, ratio
            if cover_local:
                book["cover_local"] = cover_local

            if book_id:
                cache[book_id] = {"spine_text": text_color, "cover_ratio": ratio, "cover_local": cover_local}
                cache_changed = True

    if cache_changed:
        _save_cover_meta_cache(cache)
    return data
