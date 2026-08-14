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
import os
import re
import time

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from bs4 import BeautifulSoup
from PIL import Image
TARGETS = {
    "currently_reading": "currently-reading",
    "to_read": "to-read",
    "read": "books-read",
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


def spine_text_color(cover_url):
    """'dark' or 'light' - whichever reads clearly over the strip of the
    cover that's actually visible on the spine (its left edge), sampled
    from the real image rather than guessed from genre/palette."""
    try:
        resp = requests.get(cover_url, impersonate="chrome", timeout=10)
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        w, h = img.size
        strip = img.crop((0, 0, max(1, w // 4), h)).resize((6, 6))
        avg = tuple(sum(c) / len(c) for c in zip(*strip.getdata()))
        return "dark" if _relative_luminance(avg) > 0.55 else "light"
    except Exception:
        return "light"


def annotate_spine_text_colors(data):
    """Adds a spine_text ('dark'/'light') field to every book across all
    three lists in a fetch_all()-shaped dict, in place."""
    for books in data.values():
        for book in books:
            book["spine_text"] = spine_text_color(book["cover_url"]) if book.get("cover_url") else "light"
    return data
