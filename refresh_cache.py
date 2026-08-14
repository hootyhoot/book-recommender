"""Refreshes the local StoryGraph cache file.

Run periodically (systemd timer / cron), not on the request path - the
scrape takes a few seconds and occasionally retries through a Cloudflare
challenge, which has no business happening inline with a page load.

Usage: python refresh_cache.py
Requires env vars: storygraph_username, storygraph_session_cookie
"""

import json
import os
import sys
import time
from dotenv import load_dotenv

import storygraph_scraper as sg

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storygraph_cache.json')


def main():
    load_dotenv()
    username = os.getenv('storygraph_username')
    if not username:
        print('storygraph_username environment variable is not set', file=sys.stderr)
        sys.exit(1)

    try:
        data = sg.fetch_all(username)
    except sg.StoryGraphError as e:
        print(f'refresh failed: {e}', file=sys.stderr)
        sys.exit(1)

    sg.annotate_spine_text_colors(data)

    payload = {
        'username': username,
        'fetched_at': int(time.time()),
        **data,
    }

    tmp_path = CACHE_PATH + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, CACHE_PATH)  # atomic swap, no half-written cache if this crashes mid-write

    print(f"cache refreshed: {len(data['read'])} read, {len(data['to_read'])} to-read, "
          f"{len(data['currently_reading'])} currently reading")


if __name__ == '__main__':
    main()
