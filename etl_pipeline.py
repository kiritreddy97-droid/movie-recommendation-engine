import pandas as pd
import numpy as np
import requests
import mysql.connector
from mysql.connector import Error
import time
import logging
from datetime import datetime
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── Database Configuration ────────────────────────────────────────────────────
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'movie_db'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'port': int(os.getenv('DB_PORT', 3306))
}

OMDB_API_KEY = os.getenv('OMDB_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_BASE_URL = 'https://api.themoviedb.org/3'

# ─── Database Connection ───────────────────────────────────────────────────────
def get_db_connection():
    """Create and return a MySQL database connection."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            logger.info(f"Connected to MySQL database: {DB_CONFIG['database']}")
            return conn
    except Error as e:
        logger.error(f"Database connection failed: {e}")
        raise

def initialize_database(conn):
    """Create tables if they don't exist."""
    cursor = conn.cursor()
    
    create_movies_table = """
    CREATE TABLE IF NOT EXISTS movies (
        id INT AUTO_INCREMENT PRIMARY KEY,
        tmdb_id INT UNIQUE,
        imdb_id VARCHAR(20),
        title VARCHAR(500) NOT NULL,
        release_year INT,
        genre VARCHAR(500),
        director VARCHAR(300),
        cast_members TEXT,
        plot TEXT,
        runtime_minutes INT,
        mpaa_rating VARCHAR(20),
        language VARCHAR(100),
        country VARCHAR(200),
        awards TEXT,
        poster_url VARCHAR(1000),
        budget BIGINT,
        revenue BIGINT,
        roi_percentage FLOAT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    
    create_ratings_table = """
    CREATE TABLE IF NOT EXISTS ratings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        movie_id INT NOT NULL,
        source VARCHAR(100) NOT NULL,
        score FLOAT,
        score_normalized FLOAT,
        vote_count INT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
        UNIQUE KEY unique_movie_source (movie_id, source)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    
    create_recommendations_table = """
    CREATE TABLE IF NOT EXISTS recommendations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        movie_id INT NOT NULL,
        recommended_movie_id INT NOT NULL,
        similarity_score FLOAT,
        recommendation_type ENUM('content', 'collaborative', 'hybrid'),
        FOREIGN KEY (movie_id) REFERENCES movies(id),
        FOREIGN KEY (recommended_movie_id) REFERENCES movies(id),
        UNIQUE KEY unique_rec (movie_id, recommended_movie_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    
    for table_sql in [create_movies_table, create_ratings_table, create_recommendations_table]:
        cursor.execute(table_sql)
    
    conn.commit()
    cursor.close()
    logger.info("Database tables initialized successfully")

# ─── TMDB API Fetcher ──────────────────────────────────────────────────────────
def fetch_movies_from_tmdb(page: int = 1, category: str = 'popular') -> list:
    """Fetch movies from TMDB API."""
    endpoint = f"{TMDB_BASE_URL}/movie/{category}"
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',
        'page': page
    }
    
    try:
        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Fetched {len(data['results'])} movies from TMDB (page {page})")
        return data.get('results', [])
    except requests.exceptions.RequestException as e:
        logger.error(f"TMDB API error: {e}")
        return []

def fetch_movie_details(tmdb_id: int) -> Optional[dict]:
    """Fetch detailed movie info including credits and ratings."""
    endpoint = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',
        'append_to_response': 'credits,release_dates,videos,keywords'
    }
    
    try:
        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch details for TMDB ID {tmdb_id}: {e}")
        return None

# ─── Data Transformer ──────────────────────────────────────────────────────────
def transform_movie_data(raw_movie: dict, details: Optional[dict] = None) -> dict:
    """Transform raw API data into clean database-ready format."""
    release_year = None
    release_date = raw_movie.get('release_date', '')
    if release_date and len(release_date) >= 4:
        try:
            release_year = int(release_date[:4])
        except ValueError:
            pass
    
    genre_names = ', '.join([g['name'] for g in raw_movie.get('genres', [])])
    if not genre_names and details:
        genre_names = ', '.join([g['name'] for g in details.get('genres', [])])
    
    director = ''
    cast_members = ''
    if details and 'credits' in details:
        crew = details['credits'].get('crew', [])
        directors = [c['name'] for c in crew if c['job'] == 'Director']
        director = ', '.join(directors[:2])
        
        cast = details['credits'].get('cast', [])
        cast_members = ', '.join([c['name'] for c in cast[:10]])
    
    budget = details.get('budget', 0) if details else 0
    revenue = details.get('revenue', 0) if details else 0
    roi = round(((revenue - budget) / budget * 100), 2) if budget > 0 else None
    
    poster_path = raw_movie.get('poster_path', '')
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ''
    
    return {
        'tmdb_id': raw_movie.get('id'),
        'imdb_id': details.get('imdb_id', '') if details else '',
        'title': raw_movie.get('title', raw_movie.get('original_title', '')),
        'release_year': release_year,
        'genre': genre_names,
        'director': director,
        'cast_members': cast_members,
        'plot': raw_movie.get('overview', ''),
        'runtime_minutes': details.get('runtime') if details else None,
        'mpaa_rating': '',
        'language': raw_movie.get('original_language', ''),
        'country': '',
        'awards': '',
        'poster_url': poster_url,
        'budget': budget if budget > 0 else None,
        'revenue': revenue if revenue > 0 else None,
        'roi_percentage': roi
    }

def transform_ratings_data(movie_id: int, vote_average: float, vote_count: int) -> list:
    """Create normalized rating records."""
    ratings = []
    
    if vote_average and vote_count:
        ratings.append({
            'movie_id': movie_id,
            'source': 'TMDB',
            'score': vote_average,
            'score_normalized': vote_average / 10.0,
            'vote_count': vote_count
        })
    
    return ratings

# ─── Data Loader ───────────────────────────────────────────────────────────────
def load_movie_to_db(conn, movie_data: dict) -> Optional[int]:
    """Insert or update movie record in database. Returns movie_id."""
    cursor = conn.cursor()
    
    upsert_query = """
    INSERT INTO movies (
        tmdb_id, imdb_id, title, release_year, genre, director, cast_members,
        plot, runtime_minutes, mpaa_rating, language, country, awards,
        poster_url, budget, revenue, roi_percentage
    ) VALUES (
        %(tmdb_id)s, %(imdb_id)s, %(title)s, %(release_year)s, %(genre)s,
        %(director)s, %(cast_members)s, %(plot)s, %(runtime_minutes)s,
        %(mpaa_rating)s, %(language)s, %(country)s, %(awards)s,
        %(poster_url)s, %(budget)s, %(revenue)s, %(roi_percentage)s
    )
    ON DUPLICATE KEY UPDATE
        title = VALUES(title),
        genre = VALUES(genre),
        director = VALUES(director),
        cast_members = VALUES(cast_members),
        plot = VALUES(plot),
        runtime_minutes = VALUES(runtime_minutes),
        revenue = VALUES(revenue),
        roi_percentage = VALUES(roi_percentage),
        updated_at = CURRENT_TIMESTAMP
    """
    
    try:
        cursor.execute(upsert_query, movie_data)
        conn.commit()
        
        if cursor.lastrowid:
            return cursor.lastrowid
        
        cursor.execute("SELECT id FROM movies WHERE tmdb_id = %s", (movie_data['tmdb_id'],))
        result = cursor.fetchone()
        return result[0] if result else None
        
    except Error as e:
        logger.error(f"Failed to insert movie '{movie_data.get('title')}': {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()

def load_ratings_to_db(conn, ratings: list):
    """Insert rating records into database."""
    if not ratings:
        return
    
    cursor = conn.cursor()
    upsert_query = """
    INSERT INTO ratings (movie_id, source, score, score_normalized, vote_count)
    VALUES (%(movie_id)s, %(source)s, %(score)s, %(score_normalized)s, %(vote_count)s)
    ON DUPLICATE KEY UPDATE
        score = VALUES(score),
        score_normalized = VALUES(score_normalized),
        vote_count = VALUES(vote_count),
        fetched_at = CURRENT_TIMESTAMP
    """
    
    try:
        cursor.executemany(upsert_query, ratings)
        conn.commit()
    except Error as e:
        logger.error(f"Failed to insert ratings: {e}")
        conn.rollback()
    finally:
        cursor.close()

# ─── Recommendation Engine ─────────────────────────────────────────────────────
def compute_content_similarity(df: pd.DataFrame) -> pd.DataFrame:
    """Compute content-based similarity using genre and other features."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    
    df['features'] = (
        df['genre'].fillna('') + ' ' +
        df['director'].fillna('') + ' ' +
        df['cast_members'].fillna('')
    )
    
    tfidf = TfidfVectorizer(stop_words='english', max_features=5000)
    tfidf_matrix = tfidf.fit_transform(df['features'])
    
    cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)
    logger.info(f"Computed similarity matrix: {cosine_sim.shape}")
    return pd.DataFrame(cosine_sim, index=df['id'], columns=df['id'])

def generate_recommendations(conn, top_n: int = 10):
    """Generate and store movie recommendations."""
    query = "SELECT id, title, genre, director, cast_members FROM movies LIMIT 1000"
    df = pd.read_sql(query, conn)
    
    if len(df) < 2:
        logger.warning("Not enough movies for recommendations")
        return
    
    sim_matrix = compute_content_similarity(df)
    
    cursor = conn.cursor()
    insert_query = """
    INSERT IGNORE INTO recommendations 
    (movie_id, recommended_movie_id, similarity_score, recommendation_type)
    VALUES (%s, %s, %s, 'content')
    """
    
    recommendations = []
    for movie_id in df['id']:
        if movie_id not in sim_matrix.index:
            continue
        
        similar = sim_matrix[movie_id].drop(movie_id).nlargest(top_n)
        for rec_id, score in similar.items():
            if score > 0.1:
                recommendations.append((int(movie_id), int(rec_id), float(score)))
    
    if recommendations:
        cursor.executemany(insert_query, recommendations)
        conn.commit()
        logger.info(f"Generated {len(recommendations)} recommendations")
    
    cursor.close()

# ─── Analytics & Reporting ─────────────────────────────────────────────────────
def generate_analytics_report(conn) -> pd.DataFrame:
    """Generate analytics report on movie database."""
    query = """
    SELECT 
        m.genre,
        COUNT(*) as movie_count,
        AVG(r.score) as avg_rating,
        AVG(m.roi_percentage) as avg_roi,
        SUM(m.revenue) as total_revenue,
        AVG(m.runtime_minutes) as avg_runtime
    FROM movies m
    LEFT JOIN ratings r ON m.id = r.movie_id AND r.source = 'TMDB'
    WHERE m.release_year >= 2010
    GROUP BY m.genre
    HAVING movie_count >= 5
    ORDER BY avg_rating DESC
    """
    
    df = pd.read_sql(query, conn)
    df['avg_roi'] = df['avg_roi'].round(2)
    df['avg_rating'] = df['avg_rating'].round(2)
    df['total_revenue_M'] = (df['total_revenue'] / 1_000_000).round(1)
    
    report_path = f"analytics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(report_path, index=False)
    logger.info(f"Analytics report saved: {report_path}")
    return df

# ─── Main ETL Pipeline ─────────────────────────────────────────────────────────
def run_etl_pipeline(num_pages: int = 10, fetch_details: bool = True):
    """
    Full ETL pipeline:
    1. Extract: Fetch movies from TMDB API
    2. Transform: Clean and normalize data
    3. Load: Insert into MySQL database
    4. Compute: Generate recommendations
    """
    logger.info("=" * 60)
    logger.info("Starting Movie ETL Pipeline")
    logger.info("=" * 60)
    
    conn = get_db_connection()
    initialize_database(conn)
    
    stats = {'fetched': 0, 'inserted': 0, 'failed': 0, 'ratings_added': 0}
    
    for page in range(1, num_pages + 1):
        logger.info(f"Processing page {page}/{num_pages}")
        raw_movies = fetch_movies_from_tmdb(page=page, category='popular')
        
        for raw_movie in raw_movies:
            stats['fetched'] += 1
            details = None
            
            if fetch_details:
                details = fetch_movie_details(raw_movie['id'])
                time.sleep(0.25)
            
            movie_data = transform_movie_data(raw_movie, details)
            movie_id = load_movie_to_db(conn, movie_data)
            
            if movie_id:
                stats['inserted'] += 1
                ratings = transform_ratings_data(
                    movie_id,
                    raw_movie.get('vote_average'),
                    raw_movie.get('vote_count')
                )
                load_ratings_to_db(conn, ratings)
                stats['ratings_added'] += len(ratings)
            else:
                stats['failed'] += 1
        
        time.sleep(0.5)
    
    logger.info("\nGenerating recommendations...")
    generate_recommendations(conn)
    
    logger.info("\nGenerating analytics report...")
    report = generate_analytics_report(conn)
    
    conn.close()
    
    logger.info("\n" + "=" * 60)
    logger.info("ETL Pipeline Complete!")
    logger.info(f"  Movies fetched:   {stats['fetched']}")
    logger.info(f"  Movies inserted:  {stats['inserted']}")
    logger.info(f"  Ratings added:    {stats['ratings_added']}")
    logger.info(f"  Failed:           {stats['failed']}")
    logger.info("=" * 60)
    
    return stats

if __name__ == "__main__":
    import sys
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run_etl_pipeline(num_pages=pages)
