# movie-recommendation-engine
Interactive movie recommendation system analyzing 1000+ films from IMDb, Rotten Tomatoes, Metacritic &amp; Box Office Mojo using MySQL, PHP, Python ETL, Pandas, and NumPy.

## Data Source

The movie dataset used in this project was sourced from Kaggle: [Top 10,000 TMDB's Highest Rated Movies](https://www.kaggle.com/datasets/rosemeenshaikh/top-10000-tmdbs-highest-rated-movies) by Rosemeen Shaikh.

This CSV has 10 columns: `adult, id, original_language, original_title, overview, popularity, release_date, title, vote_average, vote_count`. It does **not** include genre, director, cast, runtime, poster, budget, or revenue — fields `index.php`'s genre filter and `action=top` (ROI/revenue ranking) both depend on. Movies loaded from this CSV alone will have those columns empty, so genre search and top-performers will return no results for them. Run `etl_pipeline.py` against the TMDB API (same `tmdb_id`s) to backfill those fields if you need them.

## What's in this repo

- `etl_pipeline.py` — fetches movie data from the TMDB API, normalizes it, loads it into MySQL, and computes content-based recommendations (TF-IDF + cosine similarity over genre/director/cast).
- `load_kaggle_dataset.py` — loads the Kaggle CSV described above into the same database (title, release year, language, overview, and ratings only — see the caveat above).
- `index.php` — a JSON API (search, movie details + recommendations, genre stats, top performers) that reads from the MySQL database.
- `schema.sql` — the database schema (movies, ratings, recommendations tables), in case you want to set up the database without running the Python pipeline.

This repo does not currently include a frontend — `index.php` returns JSON only.

## Setup

### 1. Database

Create the database and tables:

```bash
mysql -u root -p < schema.sql
```

(`etl_pipeline.py` also creates these tables automatically on first run if they don't already exist, so this step is optional if you're running the pipeline first.)

### 2. Environment variables

Copy `.env.example` to `.env` and fill in your own values:

```bash
cp .env.example .env
```

Both `etl_pipeline.py` and `index.php` read the same `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASS`, and `DB_PORT` variables, so one `.env` file covers both.

### 3. Load movie data

Install Python dependencies:

```bash
pip install -r requirements.txt
```

You have two options, and they can be combined (both upsert on `tmdb_id`, so running one after the other merges rather than duplicates):

**Option A — load the Kaggle CSV** (title, year, language, overview, ratings only):

```bash
python load_kaggle_dataset.py path/to/top_rated_movies.csv
```

**Option B — run the TMDB ETL pipeline** (full data including genre, director, cast, budget, revenue; needs a free API key from https://www.themoviedb.org/settings/api):

```bash
python etl_pipeline.py 10   # 10 = number of pages of popular movies to fetch
```

This populates `movies` and `ratings`, then generates `recommendations`. If you've already loaded the Kaggle CSV, running this afterwards backfills genre/director/cast/budget/revenue for the same movies instead of creating duplicates.

### 4. Run the API

```bash
php -S localhost:8000
```

Example requests:

```bash
curl "http://localhost:8000/index.php?action=search&q=nolan"
curl "http://localhost:8000/index.php?action=details&id=1"
curl "http://localhost:8000/index.php?action=top&metric=revenue"
```

## Notes

- See the Data Source section above for what the Kaggle CSV does and doesn't contain, and why combining it with `etl_pipeline.py` gives the most complete data.
