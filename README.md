# movie-recommendation-engine
Interactive movie recommendation system analyzing 1000+ films from IMDb, Rotten Tomatoes, Metacritic &amp; Box Office Mojo using MySQL, PHP, Python ETL, Pandas, and NumPy.

## Data Source

The movie dataset used in this project was sourced from [Kaggle](https://www.kaggle.com/).

## What's in this repo

- `etl_pipeline.py` — fetches movie data from the TMDB API, normalizes it, loads it into MySQL, and computes content-based recommendations (TF-IDF + cosine similarity over genre/director/cast).
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

Run the ETL pipeline (fetches movie data from TMDB — you'll need a free API key from https://www.themoviedb.org/settings/api):

```bash
python etl_pipeline.py 10   # 10 = number of pages of popular movies to fetch
```

This populates `movies` and `ratings`, then generates `recommendations`.

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

- `etl_pipeline.py` currently sources movie data from the TMDB API. If you're working from a Kaggle CSV export instead, you'll need a separate loader that maps the CSV's columns onto the `movies` / `ratings` schema in `schema.sql`.
