from flask import Flask, render_template, request, jsonify, url_for
from markupsafe import Markup
import pandas as pd
import numpy as np
import re
import requests
import threading
from collections import OrderedDict
from rapidfuzz import process, fuzz
from rapidfuzz.utils import default_process
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))

# The catalog (built offline by "Pre-process Steps/build_catalog.py"): one row
# of metadata per book, and a matching row of unit-length bge-m3 embeddings,
# so cosine similarity is a plain dot product.
books = pd.read_parquet(os.path.join(HERE, 'books.parquet'))
embeddings = np.load(os.path.join(HERE, 'embeddings.npy')).astype(np.float32)
titles = books['Book'].tolist()


def _bayesian(avg, n, prior_n):
    """Average rating pulled towards 3.9 when it rests on few ratings."""
    avg = avg.fillna(3.9)
    return (prior_n * 3.9 + n * avg) / (prior_n + n)


# A small nudge towards well-rated, widely-read books, so near-ties in
# similarity go to the better book, plus a little more for Goodreads Choice
# Award nominees (and more again for winners). Goodreads counts run to
# millions and Hardcover's to thousands, so each source gets its own prior
# and scale.
_goodreads = (books['Source'] == 'goodreads').to_numpy()
_rating = np.where(_goodreads,
                   _bayesian(books['Avg_Rating'], books['Num_Ratings'], 2000),
                   _bayesian(books['Avg_Rating'], books['Num_Ratings'], 50))
_reach = np.log1p(books['Num_Ratings'].to_numpy(dtype=np.float64))
_reach = np.where(_goodreads, _reach / _reach[_goodreads].max(),
                  _reach / max(_reach[~_goodreads].max(initial=0), 1))
quality = (0.06 * np.clip(_rating - 3.9, -0.6, 0.6) + 0.02 * _reach
           + 0.015 * books['Choice'].to_numpy()).astype(np.float32)

_series = books['Series'].fillna('').str.lower().to_numpy()
_author = books['Author'].str.lower().to_numpy()
_title_key = books['Book'].str.lower().str.replace(r'\s*\([^)]*\)\s*$', '', regex=True) \
    .str.replace(r'[^a-z0-9]', '', regex=True).to_numpy()

# Titles as typed by a person: without the "(Dune, #1)" series tag.
_match_titles = [default_process(t) for t in books['Book'].str.replace(r'\s*\([^)]*#[^)]*\)\s*$', '', regex=True)]
_popularity = np.where(_goodreads, books['Num_Ratings'], books['Num_Ratings'] * 300)

# A rating is only shown once a handful of people have given one.
_rated = (books['Num_Ratings'] >= 5).to_numpy()

RESULTS = 15
PER_AUTHOR = 2


def _results(scores, exclude=None):
    """Top books by score, at most one per series and PER_AUTHOR per author,
    so a search doesn't come back as five books of the same series."""
    exclude = exclude or (lambda i: False)
    seen_series, seen_titles, per_author, out = set(), set(), {}, []
    for i in np.argsort(-scores)[:RESULTS * 20]:
        series, author, key = _series[i], _author[i], _title_key[i]
        if exclude(i) or key in seen_titles or (series and series in seen_series) \
                or per_author.get(author, 0) >= PER_AUTHOR:
            continue
        seen_titles.add(key)
        if series:
            seen_series.add(series)
        per_author[author] = per_author.get(author, 0) + 1
        out.append({'Book': titles[i], 'Author': books['Author'].iat[i],
                    'Avg_Rating': round(float(books['Avg_Rating'].iat[i]), 2) if _rated[i] else None,
                    'URL': books['URL'].iat[i]})
        if len(out) == RESULTS:
            break
    return out


# --- Query embeddings: Cloudflare Workers AI, bge-m3 -------------------------
#
# The account's free allocation is 10,000 neurons a day, but Cloudflare didn't
# refuse calls past it when building the catalog, so it can't be relied on as
# a limit. The app keeps its own tally of the neurons Cloudflare reports per
# call instead, and stops calling once AI_DAILY_BUDGET is spent for the UTC
# day, so heavy traffic can never run up usage.
AI_DAILY_BUDGET = 1000   # neurons; a typical search costs ~0.01
AI_URL = 'https://api.cloudflare.com/client/v4/accounts/{}/ai/run/@cf/baai/bge-m3'
AI_USAGE_PATH = os.path.join(HERE, 'ai_usage.json')
MAX_QUERY_CHARS = 300

_ai_lock = threading.Lock()
_query_cache = OrderedDict()  # query text -> embedding


def _ai_usage():
    try:
        with open(AI_USAGE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def embed_query(text):
    text = text[:MAX_QUERY_CHARS]
    with _ai_lock:
        if text in _query_cache:
            _query_cache.move_to_end(text)
            return _query_cache[text]
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        usage = _ai_usage()
        if usage.get(today, 0) >= AI_DAILY_BUDGET:
            raise Exception("Description search has hit its daily limit. Try again tomorrow, "
                            "or search by title in the meantime.")
        try:
            r = requests.post(AI_URL.format(os.getenv('CF_ACCOUNT_ID')),
                              headers={'Authorization': f"Bearer {os.getenv('CF_AI_TOKEN')}"},
                              json={'text': [text]}, timeout=20)
            body = r.json()
        except (requests.exceptions.RequestException, ValueError):
            raise Exception("Couldn't reach the embedding service. Please try again.")
        if not body.get('success'):
            app.logger.error(f"Workers AI error: {body.get('errors')}")
            raise Exception("Description search is unavailable right now. Try searching by title.")
        # Only today's entry is kept, so the file never grows.
        with open(AI_USAGE_PATH, 'w') as f:
            json.dump({today: usage.get(today, 0) + body['result']['meta']['neurons']}, f)
        vec = np.asarray(body['result']['data'][0], dtype=np.float32)
        vec /= np.linalg.norm(vec)
        _query_cache[text] = vec
        if len(_query_cache) > 1000:
            _query_cache.popitem(last=False)
        return vec


def get_recommendations_by_description(user_query):
    query = re.sub(r'\s+', ' ', user_query or '').strip()
    if not query:
        raise Exception("Please enter a description to search")
    scores = embeddings @ embed_query(query) + quality
    return _results(scores)


def get_recommendations_by_title(book_title):
    if not book_title or book_title.strip() == "":
        raise Exception("Please enter a book title to search")

    # Best-scoring titles first, and among equal scores the more widely read
    # book (so "Dune" picks Herbert's, not a namesake).
    matches = process.extract(book_title, _match_titles, scorer=fuzz.WRatio, limit=25,
                              processor=default_process)
    matches.sort(key=lambda m: (-round(m[1]), -_popularity[m[2]]))
    _, score, position = matches[0]
    if score >= 92:
        seed_series, seed_author = _series[position], _author[position]
        scores = embeddings @ embeddings[position] + quality
        # Skip the book itself and the rest of its series; one more by the
        # same author is fine.
        same_author = [0]

        def exclude(i):
            if i == position or (seed_series and _series[i] == seed_series):
                return True
            if _author[i] == seed_author:
                same_author[0] += 1
                return same_author[0] > 1
            return False
        return _results(scores, exclude)

    picks, seen = [], set()
    for _, s, i in matches:
        if _title_key[i] not in seen:
            seen.add(_title_key[i])
            picks.append({'Book': titles[i], 'similarity': round(s), 'Author': books['Author'].iat[i]})
    return picks[:5]

STORYGRAPH_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storygraph_cache.json')
_storygraph_cache = (None, None)  # (mtime, parsed data)


def load_storygraph_cache():
    """Parsed shelf data, re-read only when refresh_cache.py has rewritten
    the file rather than on every page view."""
    global _storygraph_cache
    try:
        mtime = os.path.getmtime(STORYGRAPH_CACHE_PATH)
        if _storygraph_cache[0] != mtime:
            with open(STORYGRAPH_CACHE_PATH) as f:
                _storygraph_cache = (mtime, json.load(f))
        return _storygraph_cache[1]
    except (FileNotFoundError, json.JSONDecodeError):
        return None


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
_inlined = {}  # filename -> (mtime, contents)


@app.template_global()
def asset(filename):
    """Static URL with ?v=<mtime>: Caddy caches versioned css/js for a
    year, and any edit changes the URL."""
    return url_for('static', filename=filename, v=int(os.path.getmtime(os.path.join(STATIC_DIR, filename))))


@app.template_global()
def inline_static(filename):
    """A static text file's contents, for inlining into the page (so first
    paint doesn't wait on a stylesheet request). Re-read when it changes."""
    path = os.path.join(STATIC_DIR, filename)
    mtime = os.path.getmtime(path)
    if _inlined.get(filename, (None,))[0] != mtime:
        with open(path) as f:
            _inlined[filename] = (mtime, f.read())
    return Markup(_inlined[filename][1])


@app.template_global()
def current_year():
    return datetime.now().year


@app.template_global()
def cover_src(book):
    """Local WebP copy if refresh_cache.py has converted one, otherwise
    the original StoryGraph CDN URL as a fallback (e.g. before the first
    refresh has run for a brand-new book)."""
    if book.get('cover_local'):
        return url_for('static', filename=book['cover_local'])
    return book.get('cover_url')


@app.route('/')
def showcase():
    cache = load_storygraph_cache()
    return render_template('showcase.html', data=cache)


@app.route('/recommender')
def recommender():
    return render_template('recommend.html')

@app.route('/recommend', methods=['POST'])
def recommend():
    try:
        # Get form data
        search_type = request.form.get('search_type')
        query = request.form.get('query')
        
        # Validate inputs
        if not search_type:
            return jsonify({'error': 'Please select a search type'}), 400
        
        if not query:
            return jsonify({'error': 'Please enter a search query'}), 400
        
        # Process based on search type
        if search_type == 'description':
            recommendations = get_recommendations_by_description(query)
        elif search_type == 'title':
            recommendations = get_recommendations_by_title(query)
        else:
            return jsonify({'error': 'Invalid search type'}), 400

        return jsonify(recommendations)
    
    except Exception as e:
        # Log the error for debugging
        app.logger.error(f"Error in /recommend: {str(e)}")
        
        # Return user-friendly error message
        error_message = str(e)
        if not error_message or error_message == "":
            error_message = "An unexpected error occurred. Please try again."
        
        return jsonify({'error': error_message}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
