"""Build the recommender's catalog and embed it with Cloudflare Workers AI
(bge-m3). Three sources, deduplicated by title + author:

  * Goodreads: the original top-10k list plus the "Best Books Ever" list
    (Lorena Casanova & scostap, CC BY-NC 4.0, https://zenodo.org/record/4265096),
    kept to well-rated books with plenty of ratings.
  * Hardcover (hardcover.app): its most-read books, for everything published
    since those lists were scraped (2020), plus reader moods for every book it
    has.
  * Goodreads Choice Awards nominees and winners, which get a small ranking
    boost in the app: from the Best Books Ever award lists up to 2020, and from
    goodreads.com/choiceawards for 2020 onwards.

    python build_catalog.py hardcover       # -> sources/hardcover.jsonl   (needs HARDCOVER_TOKEN)
    python build_catalog.py choiceawards    # -> sources/choice_awards.json
    python build_catalog.py choicebooks     # -> sources/hardcover_choice.jsonl (nominees not in the above)
    python build_catalog.py select          # -> catalog_books.parquet
    python build_catalog.py embed           # -> ../books.parquet, ../embeddings.npy

Best Books Ever goes in sources/best_books_ever.csv (download from Zenodo).

`embed` never spends more than EMBED_BUDGET neurons per UTC day (the free
Workers AI allocation is 10,000/day), counted from the `neurons` figure
Cloudflare returns with every call. When the budget is used up it stops; run
it again the next day and it carries on from where it left off.
"""
import ast
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from langdetect import DetectorFactory, LangDetectException, detect

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCES = os.path.join(HERE, 'sources')
load_dotenv(os.path.join(ROOT, '.env'))

HARDCOVER = os.path.join(SOURCES, 'hardcover.jsonl')
HARDCOVER_CHOICE = os.path.join(SOURCES, 'hardcover_choice.jsonl')
CHOICE = os.path.join(SOURCES, 'choice_awards.json')
BBE = os.path.join(SOURCES, 'best_books_ever.csv')
CATALOG = os.path.join(HERE, 'catalog_books.parquet')
PARTIAL = os.path.join(HERE, 'embeddings_partial.npy')
LEDGER = os.path.join(HERE, 'embed_ledger.json')

# Quality bar for a book to be recommended at all.
GOODREADS_MIN_RATING, GOODREADS_MIN_RATINGS = 3.8, 2000
HARDCOVER_MIN_RATING, HARDCOVER_MIN_RATINGS = 3.8, 50
HARDCOVER_PAGES = 800     # x25 = the 20,000 most-read books on Hardcover
MIN_DESCRIPTION = 150     # characters; shorter blurbs embed poorly
EMBED_CHARS = 850         # text per book sent for embedding (~0.26 neurons each)
EMBED_BUDGET = 7000       # neurons per UTC day for this script, of the free 10,000
BATCH = 50

DetectorFactory.seed = 0
BROWSER_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130 Safari/537.36'


def norm_title(title):
    title = re.sub(r'\s*\([^)]*\)\s*$', '', str(title))  # "(Dune, #1)", "(Scholastic Bookshelf)"
    title = re.split(r'[:;]', title)[0]
    return re.sub(r'[^a-z0-9]', '', title.lower())


def norm_author(author):
    parts = re.sub(r'[^a-z\s]', '', str(author).lower()).split()
    return parts[-1] if parts else ''


def key(title, author):
    return norm_title(title), norm_author(author)


def series_of(title):
    m = re.search(r'\(([^)#]+?),?\s*#[\d.\-]+\)\s*$', title)
    return m.group(1).strip() if m else None


def latin_title(title):
    letters = [c for c in str(title) if c.isalpha()]
    return bool(letters) and sum(c.isascii() or c in 'àáâäãåçèéêëìíîïñòóôöõøùúûüýÿæœß' for c in map(str.lower, letters)) / len(letters) > 0.8


NOT_A_BOOK = re.compile(
    r'\b(?:summary|study guide|sparknotes|cliffsnotes|bookrags|companion to|movie companion|official illustrated'
    r'|unofficial companion|sampler|esampler|excerpt|sneak peek|box(?:ed)? ?set|omnibus)\b'
    r'|#\d+\s*-\s*\d+', re.IGNORECASE)


def not_a_book(title):
    """Summaries and study guides of other books, samplers, box sets and
    omnibus editions ("#1-3"): not things to recommend on their own."""
    return bool(NOT_A_BOOK.search(str(title)))


def is_english(text):
    try:
        return detect(text) == 'en'
    except LangDetectException:
        return False


def as_list(value):
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return []
    return [v for v in (value or []) if isinstance(v, str)]


def clean(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


# --- Fetching ----------------------------------------------------------------

HARDCOVER_FIELDS = ['id', 'slug', 'title', 'author_names', 'description', 'genres', 'moods',
                    'series_names', 'rating', 'ratings_count', 'users_read_count', 'release_year', 'compilation']


def hardcover_search(variables, query):
    """One Hardcover search request, paced under its 60 requests/minute limit."""
    headers = {'authorization': 'Bearer ' + os.environ['HARDCOVER_TOKEN'],
               'user-agent': 'mikhail.codes book recommender (one-off catalog build)'}
    for _ in range(6):
        try:
            r = requests.post('https://api.hardcover.app/v1/graphql', headers=headers,
                              json={'query': query, 'variables': variables}, timeout=60)
            if r.status_code == 200:
                time.sleep(1.1)
                return [{k: h['document'].get(k) for k in HARDCOVER_FIELDS}
                        for h in r.json()['data']['search']['results']['hits']]
        except requests.exceptions.RequestException:
            pass
        time.sleep(30)
    sys.exit(f'Hardcover kept refusing {variables}')


def fetch_hardcover():
    """The most-read books on Hardcover, 25 per request (the API's page cap).
    Resumes a partial download."""
    query = ('query($p:Int!){search(query:"*",query_type:"Book",per_page:25,page:$p,'
             'sort:"users_read_count:desc"){results}}')
    os.makedirs(SOURCES, exist_ok=True)
    done = {json.loads(l)['_page'] for l in open(HARDCOVER)} if os.path.exists(HARDCOVER) else set()
    with open(HARDCOVER, 'a') as f:
        for page in range(1, HARDCOVER_PAGES + 1):
            if page not in done:
                for book in hardcover_search({'p': page}, query):
                    f.write(json.dumps(dict(book, _page=page)) + '\n')
                f.flush()


def fetch_choice_books():
    """Hardcover's entry for each Choice Award nominee that isn't among its
    most-read books, found by searching title + author."""
    query = 'query($q:String!){search(query:$q,query_type:"Book",per_page:5,page:1){results}}'
    have = {key(b['title'], (b.get('author_names') or [''])[0]) for b in map(json.loads, open(HARDCOVER))}
    looked = {json.loads(l)['_nominee'] for l in open(HARDCOVER_CHOICE)} if os.path.exists(HARDCOVER_CHOICE) else set()
    nominees = {key(n['title'], n['author']): n for n in json.load(open(CHOICE))}
    with open(HARDCOVER_CHOICE, 'a') as f:
        for k, n in nominees.items():
            if k in have or '|'.join(k) in looked:
                continue
            hits = hardcover_search({'q': f"{n['title']} {n['author']}"}, query)
            match = next((h for h in hits if key(h['title'], (h.get('author_names') or [''])[0]) == k), None)
            f.write(json.dumps(dict(match or {}, _nominee='|'.join(k))) + '\n')
            f.flush()


def fetch_choice_awards():
    """Nominees and winners of every Goodreads Choice Awards category since 2020."""
    s = requests.Session()
    s.headers['User-Agent'] = BROWSER_UA

    def get(path):
        for attempt in range(5):
            try:
                return s.get('https://www.goodreads.com/choiceawards/' + path, timeout=30).text
            except requests.exceptions.RequestException:
                time.sleep(10 * (attempt + 1))
        sys.exit(f'Goodreads kept failing on {path}')

    out = []
    for year in range(2020, datetime.now().year + 1):
        index = get(f'best-books-{year}')
        cats = set(re.findall(rf'href="/choiceawards/([a-z0-9-]+-{year})"', index)) - {f'best-books-{year}'}
        for cat in sorted(cats):
            time.sleep(2)
            page = get(cat)
            winner = re.search(r'class="winningTitle[^"]*" href="(/book/show/[^"?]+)', page)
            for href, alt in re.findall(r'class="pollAnswer__bookLink" href="(/book/show/[^"?]+)[^"]*"><img alt="([^"]+)"', page):
                title, _, author = html.unescape(alt).rpartition(' by ')
                out.append({'year': year, 'category': cat, 'title': title, 'author': author,
                            'winner': bool(winner) and href == winner.group(1)})
    os.makedirs(SOURCES, exist_ok=True)
    with open(CHOICE, 'w') as f:
        json.dump(out, f, indent=0)
    print(f'{len(out)} nominations')


# --- Selecting ---------------------------------------------------------------

def goodreads():
    """The original top-10k list and Best Books Ever, one row per book, with
    each book's Choice Award standing (2 winner, 1 nominee) up to 2020."""
    top = pd.read_csv(os.path.join(HERE, 'filtered_goodreads_data.csv'))
    top = pd.DataFrame({
        'Book': top['Book'].map(clean), 'Author': top['Author'], 'Description': top['Description'],
        'Genres': top['Genres'].map(as_list), 'Avg_Rating': top['Avg_Rating'].astype(float),
        'Num_Ratings': top['Num_Ratings'].astype(str).str.replace(',', '').astype(int),
        'URL': top['URL'], 'Series': top['Book'].map(series_of)})

    bbe = pd.read_csv(BBE)
    bbe = bbe[bbe['language'] == 'English']
    author = bbe['author'].str.split(',').str[0].str.replace(r'\s*\([^)]*\)', '', regex=True).str.strip()
    bbe = pd.DataFrame({
        'Book': bbe['title'].map(clean), 'Author': author, 'Description': bbe['description'],
        'Genres': bbe['genres'].map(as_list), 'Avg_Rating': bbe['rating'].astype(float),
        'Num_Ratings': bbe['numRatings'].astype(int),
        'URL': 'https://www.goodreads.com/book/show/' + bbe['bookId'].astype(str),
        'Series': bbe['series'].str.replace(r'\s*#.*$', '', regex=True).str.strip().replace('', None),
        'Awards': bbe['awards'].fillna('')})

    def choice(awards):
        if re.search(r'Goodreads Choice Award for', awards):
            return 2
        return 1 if 'Goodreads Choice Award Nominee' in awards else 0

    bbe['Choice'] = bbe['Awards'].map(choice)
    awards = {key(b, a): c for b, a, c in zip(bbe['Book'], bbe['Author'], bbe['Choice'])}
    top['Choice'] = [awards.get(key(b, a), 0) for b, a in zip(top['Book'], top['Author'])]

    # The top-10k list's rows win (they're what the site has always used).
    df = pd.concat([top, bbe.drop(columns=['Awards'])], ignore_index=True)
    df['Key'] = [key(b, a) for b, a in zip(df['Book'], df['Author'])]
    df = df.drop_duplicates('Key')
    df = df[(df['Avg_Rating'] >= GOODREADS_MIN_RATING) & (df['Num_Ratings'] >= GOODREADS_MIN_RATINGS)
            & (df['Description'].fillna('').str.len() >= MIN_DESCRIPTION)]
    df['Moods'] = [[] for _ in range(len(df))]
    df['Source'] = 'goodreads'
    return df


def hardcover():
    rows = [json.loads(l) for l in open(HARDCOVER)]
    if os.path.exists(HARDCOVER_CHOICE):
        rows += [r for r in map(json.loads, open(HARDCOVER_CHOICE)) if r.get('slug')]
    df = pd.DataFrame({
        'Book': [clean(r['title']) for r in rows],
        'Author': [(r.get('author_names') or [''])[0] for r in rows],
        'Description': [clean(r.get('description')) for r in rows],
        'Genres': [as_list(r.get('genres'))[:6] for r in rows],
        'Moods': [as_list(r.get('moods'))[:6] for r in rows],
        'Avg_Rating': [round(r.get('rating') or 0, 2) for r in rows],
        'Num_Ratings': [r.get('ratings_count') or 0 for r in rows],
        'URL': ['https://hardcover.app/books/' + r['slug'] for r in rows],
        'Series': [(r.get('series_names') or [None])[0] for r in rows],
        'Compilation': [bool(r.get('compilation')) for r in rows],
    })
    df['Key'] = [key(b, a) for b, a in zip(df['Book'], df['Author'])]
    return df.drop_duplicates('Key')


def select():
    gr = goodreads()
    hc = hardcover()

    # Hardcover's reader moods for the Goodreads books it also has.
    moods = dict(zip(hc['Key'], hc['Moods']))
    gr['Moods'] = [moods.get(k, []) for k in gr['Key']]

    # Choice Awards since 2020. A nomination counts as the quality bar, so
    # nominees skip Hardcover's rating threshold (many have few ratings there).
    standing = {}
    for n in json.load(open(CHOICE)):
        k = key(n['title'], n['author'])
        standing[k] = max(standing.get(k, 0), 2 if n['winner'] else 1)
    nominee = hc['Key'].isin(set(standing))

    new = hc[~hc['Key'].isin(set(gr['Key'])) & ~hc['Compilation']
             & (nominee | ((hc['Avg_Rating'] >= HARDCOVER_MIN_RATING) & (hc['Num_Ratings'] >= HARDCOVER_MIN_RATINGS)))
             & (hc['Description'].str.len() >= MIN_DESCRIPTION)].copy()
    new = new[new['Description'].map(is_english)]
    new['Source'] = 'hardcover'
    new['Choice'] = 0

    df = pd.concat([gr, new.drop(columns=['Compilation'])], ignore_index=True)
    df = df[df['Book'].map(latin_title) & ~df['Book'].map(not_a_book)]
    df['Series'] = [s if isinstance(s, str) and s else series_of(b) for s, b in zip(df['Series'], df['Book'])]
    df['Choice'] = [max(c, standing.get(k, 0)) for c, k in zip(df['Choice'], df['Key'])]

    df['Genres'] = df['Genres'].map(lambda g: ', '.join(g))
    df['Moods'] = df['Moods'].map(lambda m: ', '.join(m))
    df = df.drop(columns=['Key']).reset_index(drop=True)
    df.to_parquet(CATALOG, index=False)
    chars = df.apply(embed_text, axis=1).str.len().sum()
    print(f"{(df['Source'] == 'goodreads').sum()} Goodreads + {(df['Source'] == 'hardcover').sum()} Hardcover "
          f"= {len(df)} books; {(df['Choice'] > 0).sum()} Choice Award nominees ({(df['Choice'] == 2).sum()} winners)")
    print(f'~{chars * 0.273 / 900:.0f} neurons to embed')  # measured: 0.273 neurons per 900 characters


# --- Embedding ---------------------------------------------------------------

def embed_text(row):
    # No title: with it, shared title words ("Gone Girl" -> "Gone",
    # "Pride and Prejudice" -> "Prom & Prejudice") outweighed what the books
    # are actually about.
    text = f"{row['Author']}. Genres: {row['Genres']}."
    if row['Moods']:
        text += f" Mood: {row['Moods']}."
    return clean(f"{text} {row['Description']}")[:EMBED_CHARS]


def embed():
    account, token = os.environ['CF_ACCOUNT_ID'], os.environ['CF_AI_TOKEN']
    url = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/baai/bge-m3'
    df = pd.read_parquet(CATALOG)
    texts = df.apply(embed_text, axis=1).tolist()
    done = np.load(PARTIAL) if os.path.exists(PARTIAL) else np.zeros((0, 1024), np.float16)
    print(f'{len(done)}/{len(texts)} already embedded')

    while len(done) < len(texts):
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        try:
            with open(LEDGER) as f:
                ledger = json.load(f)
        except FileNotFoundError:
            ledger = {}
        if ledger.get(today, 0) >= EMBED_BUDGET - 50:
            print(f'Used {ledger[today]:.0f} of the {EMBED_BUDGET} neuron budget for {today} (UTC). '
                  'Stopping; run again after 00:00 UTC to continue.')
            return
        batch = texts[len(done):len(done) + BATCH]
        for attempt in range(5):
            try:
                body = requests.post(url, headers={'Authorization': f'Bearer {token}'},
                                     json={'text': batch}, timeout=60).json()
            except (requests.exceptions.RequestException, ValueError) as e:
                body = {'errors': [{'message': str(e), 'code': 'network'}]}
            # Retry Cloudflare's own hiccups; anything else (e.g. the free
            # allocation being used up) stops the run.
            transient = any(e.get('code') in (8008, 'network') for e in body.get('errors') or [])
            if body.get('success') or not transient:
                break
            time.sleep(5 * (attempt + 1))
        if not body.get('success'):
            print('Cloudflare refused the request, stopping:', body.get('errors'))
            return
        ledger[today] = ledger.get(today, 0) + body['result']['meta']['neurons']
        with open(LEDGER, 'w') as f:
            json.dump(ledger, f)
        vecs = np.asarray(body['result']['data'], dtype=np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        done = np.vstack([done, vecs.astype(np.float16)])
        np.save(PARTIAL, done)
        print(f'{len(done)}/{len(texts)}  {ledger[today]:.0f} neurons today', flush=True)
        time.sleep(0.2)

    df.drop(columns=['Description']).to_parquet(os.path.join(ROOT, 'books.parquet'), index=False)
    np.save(os.path.join(ROOT, 'embeddings.npy'), done)
    print('Wrote books.parquet and embeddings.npy')


if __name__ == '__main__':
    steps = {'hardcover': fetch_hardcover, 'choiceawards': fetch_choice_awards, 'choicebooks': fetch_choice_books,
             'select': select, 'embed': embed}
    if sys.argv[1:2] and sys.argv[1] in steps:
        steps[sys.argv[1]]()
    else:
        print(__doc__)
