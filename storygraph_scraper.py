"""Scrapes book lists from a public StoryGraph profile.

No headless browser needed - StoryGraph's list pages are plain
server-rendered HTML, so a normal HTTP request plus a session cookie is
enough. The Cloudflare challenge that guards these pages occasionally
triggers on a fresh request but reliably clears on a short retry, so each
fetch retries a few times before giving up.

This module only fetches and parses; it doesn't cache or schedule
anything, that's handled by refresh_cache.py.
"""

import os
import re
import time

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
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
    headers = {"User-Agent": USER_AGENT}
    cookies = {"_storygraph_session": cookie}
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, cookies=cookies, timeout=15)
        except requests.RequestException as exc:
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
