"""
Load the "Top 10,000 TMDB's Highest Rated Movies" Kaggle dataset into the
movie_db database (same schema as schema.sql / etl_pipeline.py).

Dataset: https://www.kaggle.com/datasets/rosemeenshaikh/top-10000-tmdbs-highest-rated-movies
Expected CSV columns (as published):
    adult, id, original_language, original_title, overview, popularity,
    release_date, title, vote_average, vote_count

Important: this CSV does NOT include genre, director, cast, runtime,
poster, budget, or revenue data -- fields TMDB's own API exposes but this
export doesn't carry. Movies loaded from this CSV will have those columns
NULL/empty. That means:
  - action=search with a `genre` filter will not match anything for these
    rows (m.genre is empty).
  - action=top (ranks by ROI/revenue) will not include these rows (budget
    and revenue are NULL, and getTopPerformers() requires revenue > 0).
  - Content-based recommendations (which cluster on genre/director/cast)
    will be meaningless for this data -- there's nothing to compare.
  - action=search by text query (title/director/cast) still works for
    title matches; director/cast matches will simply never hit.
If you need genre/cast/budget/revenue, run etl_pipeline.py against the
TMDB API instead (or in addition -- both loaders upsert on tmdb_id, so
running etl_pipeline.py afterwards will backfill the missing fields for
movies that are already in the database).

Usage:
    python load_kaggle_dataset.py path/to/top_rated_movies.csv
"""
import csv
import logging
import os
import sys

import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'movie_db'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASS', ''),
    'port': int(os.getenv('DB_PORT', 3306)),
}


def get_db_connection():
    conn = mysql.connector.connect(**DB_CONFIG)
    if conn.is_connected():
        logger.info(f"Connected to MySQL database: {DB_CONFIG['database']}")
        return conn
    raise RuntimeError("Could not connect to database")


def parse_year(release_date: str):
    if not release_date or len(release_date) < 4:
        return None
    try:
        return int(release_date[:4])
    except ValueError:
        return None


def load_csv(conn, csv_path: str):
    upsert_movie = """
    INSERT INTO movies (tmdb_id, title, release_year, language, plot)
    VALUES (%(tmdb_id)s, %(title)s, %(release_year)s, %(language)s, %(plot)s)
    ON DUPLICATE KEY UPDATE
        title = VALUES(title),
        release_year = VALUES(release_year),
        language = VALUES(language),
        plot = VALUES(plot),
        updated_at = CURRENT_TIMESTAMP
    """
    upsert_rating = """
    INSERT INTO ratings (movie_id, source, score, score_normalized, vote_count)
    VALUES (%(movie_id)s, 'TMDB', %(score)s, %(score_normalized)s, %(vote_count)s)
    ON DUPLICATE KEY UPDATE
        score = VALUES(score),
        score_normalized = VALUES(score_normalized),
        vote_count = VALUES(vote_count),
        fetched_at = CURRENT_TIMESTAMP
    """

    cursor = conn.cursor()
    stats = {'rows': 0, 'loaded': 0, 'skipped': 0}

    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        missing = {'id', 'title', 'vote_average', 'vote_count'} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"CSV is missing expected column(s): {sorted(missing)}. "
                f"Found columns: {reader.fieldnames}"
            )

        for row in reader:
            stats['rows'] += 1
            tmdb_id = row.get('id', '').strip()
            title = row.get('title', '').strip()
            if not tmdb_id or not title:
                stats['skipped'] += 1
                continue

            try:
                tmdb_id = int(tmdb_id)
            except ValueError:
                stats['skipped'] += 1
                continue

            movie_params = {
                'tmdb_id': tmdb_id,
                'title': title,
                'release_year': parse_year(row.get('release_date', '')),
                'language': row.get('original_language', '') or None,
                'plot': row.get('overview', '') or None,
            }

            try:
                cursor.execute(upsert_movie, movie_params)
                if cursor.lastrowid:
                    movie_id = cursor.lastrowid
                else:
                    cursor.execute("SELECT id FROM movies WHERE tmdb_id = %s", (tmdb_id,))
                    result = cursor.fetchone()
                    movie_id = result[0] if result else None

                if movie_id is None:
                    stats['skipped'] += 1
                    continue

                vote_average = row.get('vote_average', '').strip()
                vote_count = row.get('vote_count', '').strip()
                if vote_average and vote_count:
                    cursor.execute(upsert_rating, {
                        'movie_id': movie_id,
                        'score': float(vote_average),
                        'score_normalized': float(vote_average) / 10.0,
                        'vote_count': int(float(vote_count)),
                    })

                stats['loaded'] += 1
            except Error as e:
                logger.error(f"Failed to load row for '{title}' (tmdb_id={tmdb_id}): {e}")
                conn.rollback()
                stats['skipped'] += 1
                continue

            if stats['loaded'] % 500 == 0:
                conn.commit()
                logger.info(f"...{stats['loaded']} movies loaded so far")

    conn.commit()
    cursor.close()
    return stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python load_kaggle_dataset.py path/to/top_rated_movies.csv")
        sys.exit(1)

    csv_path = sys.argv[1]
    if not os.path.isfile(csv_path):
        print(f"File not found: {csv_path}")
        sys.exit(1)

    conn = get_db_connection()
    try:
        stats = load_csv(conn, csv_path)
    finally:
        conn.close()

    logger.info("=" * 60)
    logger.info("Kaggle CSV import complete")
    logger.info(f"  Rows read:     {stats['rows']}")
    logger.info(f"  Movies loaded: {stats['loaded']}")
    logger.info(f"  Rows skipped:  {stats['skipped']}")
    logger.info("=" * 60)
    logger.info(
        "Note: genre, director, cast, budget, and revenue are NOT in this "
        "dataset, so they're empty for these rows. Genre search and the "
        "'top performers' endpoint won't surface them until that data is "
        "backfilled (e.g. by also running etl_pipeline.py)."
    )


if __name__ == '__main__':
    main()
