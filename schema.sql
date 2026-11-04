-- movie-recommendation-engine database schema
-- Run this once against a MySQL/MariaDB server before running etl_pipeline.py
-- or pointing index.php at the database.
--
-- Usage:
--   mysql -u root -p < schema.sql
--
-- This mirrors the tables that etl_pipeline.py's initialize_database()
-- creates automatically on first run; this file exists so the schema
-- can be inspected or applied without running the Python pipeline.

CREATE DATABASE IF NOT EXISTS movie_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE movie_db;

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
