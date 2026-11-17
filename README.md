# Book Recommender

Recommends your next book by title or by a description of what you're in the
mood for, using text embeddings and similarity search. Live at
https://books.mikhail.codes/recommender.

## How it works

- **Catalog:** ~25,000 well-rated books, built offline by
  `Pre-process Steps/build_catalog.py` from:
  - Goodreads: the original top-10k list plus the
    [Best Books Ever](https://zenodo.org/record/4265095) dataset (CC BY-NC 4.0),
    kept to books rated 3.8+ with 2,000+ ratings;
  - [Hardcover](https://hardcover.app): its most-read books (for everything
    since 2020) and reader moods;
  - Goodreads Choice Awards nominees and winners, which get a small ranking boost.
- **Embeddings:** `@cf/baai/bge-m3` on Cloudflare Workers AI, for the catalog
  (`embeddings.npy`) and for description searches. The app caps its own
  Workers AI use per day (`AI_DAILY_BUDGET` in `app.py`), well inside the free
  allocation.
- **Ranking:** cosine similarity plus a small nudge for well-rated,
  widely-read and award-nominated books; at most one book per series and two
  per author.

## Running locally

```bash
pip install -r requirements-render.txt
python app.py
```

Then open http://0.0.0.0:10000.

`.env` needs `CF_ACCOUNT_ID` and `CF_AI_TOKEN` (a Cloudflare token with Workers
AI access). Rebuilding the catalog also needs `HARDCOVER_TOKEN`.
