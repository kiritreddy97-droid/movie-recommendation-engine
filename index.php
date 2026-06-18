<?php
declare(strict_types=1);

// ─── Database Configuration ────────────────────────────────────────────────────
define('DB_HOST', $_ENV['DB_HOST'] ?? 'localhost');
define('DB_NAME', $_ENV['DB_NAME'] ?? 'movie_db');
define('DB_USER', $_ENV['DB_USER'] ?? 'root');
define('DB_PASS', $_ENV['DB_PASS'] ?? '');
define('DB_PORT', (int)($_ENV['DB_PORT'] ?? 3306));
define('RESULTS_PER_PAGE', 20);

// ─── Database Connection ───────────────────────────────────────────────────────
function getDbConnection(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        $dsn = sprintf(
            'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
            DB_HOST, DB_PORT, DB_NAME
        );
        $options = [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ];
        $pdo = new PDO($dsn, DB_USER, DB_PASS, $options);
    }
    return $pdo;
}

// ─── Movie Search & Filter ─────────────────────────────────────────────────────
function searchMovies(
    string $query = '',
    string $genre = '',
    int $yearFrom = 1900,
    int $yearTo = 2024,
    float $minRating = 0.0,
    string $sortBy = 'avg_rating',
    int $page = 1
): array {
    $pdo = getDbConnection();
    $offset = ($page - 1) * RESULTS_PER_PAGE;
    
    $allowedSort = ['avg_rating', 'release_year', 'roi_percentage', 'title', 'revenue'];
    if (!in_array($sortBy, $allowedSort)) $sortBy = 'avg_rating';
    
    $sql = "
        SELECT 
            m.id,
            m.title,
            m.release_year,
            m.genre,
            m.director,
            m.poster_url,
            m.runtime_minutes,
            m.budget,
            m.revenue,
            m.roi_percentage,
            ROUND(AVG(r.score_normalized * 10), 1) AS avg_rating,
            SUM(r.vote_count) AS total_votes
        FROM movies m
        LEFT JOIN ratings r ON m.id = r.movie_id
        WHERE m.release_year BETWEEN :year_from AND :year_to
    ";
    
    $params = [
        ':year_from' => $yearFrom,
        ':year_to'   => $yearTo,
    ];
    
    if (!empty($query)) {
        $sql .= " AND (m.title LIKE :query OR m.director LIKE :query OR m.cast_members LIKE :query)";
        $params[':query'] = "%{$query}%";
    }
    
    if (!empty($genre)) {
        $sql .= " AND m.genre LIKE :genre";
        $params[':genre'] = "%{$genre}%";
    }
    
    $sql .= "
        GROUP BY m.id
        HAVING avg_rating >= :min_rating
        ORDER BY {$sortBy} DESC
        LIMIT :limit OFFSET :offset
    ";
    
    $stmt = $pdo->prepare($sql);
    foreach ($params as $key => $val) {
        $stmt->bindValue($key, $val);
    }
    $stmt->bindValue(':min_rating', $minRating, PDO::PARAM_STR);
    $stmt->bindValue(':limit', RESULTS_PER_PAGE, PDO::PARAM_INT);
    $stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
    $stmt->execute();
    
    return $stmt->fetchAll();
}

// ─── Get Movie Details ─────────────────────────────────────────────────────────
function getMovieDetails(int $movieId): ?array {
    $pdo = getDbConnection();
    
    $stmt = $pdo->prepare("
        SELECT m.*, 
               GROUP_CONCAT(CONCAT(r.source, ': ', ROUND(r.score, 1)) SEPARATOR ' | ') AS all_ratings
        FROM movies m
        LEFT JOIN ratings r ON m.id = r.movie_id
        WHERE m.id = :id
        GROUP BY m.id
    ");
    $stmt->execute([':id' => $movieId]);
    return $stmt->fetch() ?: null;
}

// ─── Get Recommendations ──────────────────────────────────────────────────────
function getRecommendations(int $movieId, int $limit = 8): array {
    $pdo = getDbConnection();
    
    $stmt = $pdo->prepare("
        SELECT 
            m.id, m.title, m.release_year, m.genre, m.poster_url,
            ROUND(AVG(r.score_normalized * 10), 1) AS avg_rating,
            rec.similarity_score
        FROM recommendations rec
        JOIN movies m ON rec.recommended_movie_id = m.id
        LEFT JOIN ratings r ON m.id = r.movie_id
        WHERE rec.movie_id = :movie_id
        GROUP BY m.id
        ORDER BY rec.similarity_score DESC, avg_rating DESC
        LIMIT :limit
    ");
    $stmt->bindValue(':movie_id', $movieId, PDO::PARAM_INT);
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->execute();
    return $stmt->fetchAll();
}

// ─── Genre Stats ──────────────────────────────────────────────────────────────
function getGenreStats(): array {
    $pdo = getDbConnection();
    $stmt = $pdo->query("
        SELECT 
            genre,
            COUNT(*) AS count,
            ROUND(AVG(roi_percentage), 1) AS avg_roi,
            ROUND(AVG(r.score_normalized * 10), 1) AS avg_rating,
            SUM(revenue) AS total_revenue
        FROM movies m
        LEFT JOIN ratings r ON m.id = r.movie_id
        WHERE genre != '' AND release_year >= 2010
        GROUP BY genre
        HAVING count >= 3
        ORDER BY avg_rating DESC
        LIMIT 20
    ");
    return $stmt->fetchAll();
}

// ─── Top Performers ───────────────────────────────────────────────────────────
function getTopPerformers(string $metric = 'roi', int $limit = 10): array {
    $pdo = getDbConnection();
    
    $orderClause = match($metric) {
        'roi'     => 'm.roi_percentage DESC',
        'revenue' => 'm.revenue DESC',
        'rating'  => 'avg_rating DESC',
        default   => 'm.roi_percentage DESC'
    };
    
    $stmt = $pdo->prepare("
        SELECT 
            m.id, m.title, m.release_year, m.genre, m.director,
            m.budget, m.revenue, m.roi_percentage, m.poster_url,
            ROUND(AVG(r.score_normalized * 10), 1) AS avg_rating
        FROM movies m
        LEFT JOIN ratings r ON m.id = r.movie_id
        WHERE m.roi_percentage IS NOT NULL AND m.revenue > 0
        GROUP BY m.id
        ORDER BY {$orderClause}
        LIMIT :limit
    ");
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->execute();
    return $stmt->fetchAll();
}

// ─── Request Router ────────────────────────────────────────────────────────────
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('X-Content-Type-Options: nosniff');

$action = $_GET['action'] ?? 'search';
$response = ['success' => false, 'data' => null, 'error' => null];

try {
    switch ($action) {
        case 'search':
            $response['data'] = searchMovies(
                query:     trim($_GET['q'] ?? ''),
                genre:     trim($_GET['genre'] ?? ''),
                yearFrom:  (int)($_GET['year_from'] ?? 1900),
                yearTo:    (int)($_GET['year_to'] ?? 2024),
                minRating: (float)($_GET['min_rating'] ?? 0),
                sortBy:    $_GET['sort'] ?? 'avg_rating',
                page:      max(1, (int)($_GET['page'] ?? 1))
            );
            $response['success'] = true;
            break;
            
        case 'details':
            $movieId = (int)($_GET['id'] ?? 0);
            if ($movieId <= 0) throw new InvalidArgumentException('Invalid movie ID');
            $movie = getMovieDetails($movieId);
            if (!$movie) throw new RuntimeException('Movie not found');
            $movie['recommendations'] = getRecommendations($movieId);
            $response['data'] = $movie;
            $response['success'] = true;
            break;
            
        case 'genres':
            $response['data'] = getGenreStats();
            $response['success'] = true;
            break;
            
        case 'top':
            $response['data'] = getTopPerformers(
                metric: $_GET['metric'] ?? 'roi',
                limit:  min(50, (int)($_GET['limit'] ?? 10))
            );
            $response['success'] = true;
            break;
            
        default:
            throw new InvalidArgumentException("Unknown action: {$action}");
    }
} catch (InvalidArgumentException $e) {
    http_response_code(400);
    $response['error'] = $e->getMessage();
} catch (RuntimeException $e) {
    http_response_code(404);
    $response['error'] = $e->getMessage();
} catch (Exception $e) {
    http_response_code(500);
    $response['error'] = 'Internal server error';
    error_log("Movie API Error: " . $e->getMessage());
}

echo json_encode($response, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
