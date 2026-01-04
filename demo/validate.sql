-- Dataing Demo Fixtures: Validation Queries
-- Run these queries to verify fixtures are correct before demos.

-- ==============================================================================
-- BASIC INTEGRITY CHECKS
-- ==============================================================================

-- Row counts (should match manifest)
SELECT '=== ROW COUNTS ===' AS section;
SELECT 'users' AS tbl, COUNT(*) AS cnt FROM users
UNION ALL SELECT 'categories', COUNT(*) FROM categories
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'events', COUNT(*) FROM events;

-- ==============================================================================
-- TEMPORAL DISTRIBUTION
-- ==============================================================================

-- Events per day (should be ~60K-85K with variation)
SELECT '=== EVENTS PER DAY ===' AS section;
SELECT
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*) AS events,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM events
GROUP BY 1
ORDER BY 1;

-- Orders per day
SELECT '=== ORDERS PER DAY ===' AS section;
SELECT
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*) AS orders
FROM orders
GROUP BY 1
ORDER BY 1;

-- Hourly distribution (should show peak 10-14 and 19-21)
SELECT '=== HOURLY EVENT DISTRIBUTION ===' AS section;
SELECT
    EXTRACT(HOUR FROM created_at) AS hour,
    COUNT(*) AS events,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM events
GROUP BY 1
ORDER BY 1;

-- ==============================================================================
-- NULL SPIKE DETECTION (Scenario 3.1)
-- ==============================================================================

SELECT '=== NULL SPIKE CHECK ===' AS section;
SELECT
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) AS null_user_orders,
    ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS null_pct
FROM orders
GROUP BY 1
ORDER BY 1;
-- Expected: Days 1-2 ~0%, Days 3-5 ~40%, Days 6-7 ~0%

-- ==============================================================================
-- VOLUME DROP DETECTION (Scenario 3.2)
-- ==============================================================================

SELECT '=== VOLUME DROP CHECK (EU Traffic) ===' AS section;
SELECT
    DATE_TRUNC('day', created_at) AS day,
    country,
    COUNT(*) AS events
FROM events
WHERE country IN ('DE', 'FR', 'GB', 'IT', 'ES', 'NL')
GROUP BY 1, 2
ORDER BY 1, 2;
-- Expected: Day 5-6 should show ~80% drop for EU countries

-- Total events by region
SELECT '=== EVENTS BY REGION ===' AS section;
SELECT
    DATE_TRUNC('day', created_at) AS day,
    CASE WHEN country IN ('DE', 'FR', 'GB', 'IT', 'ES', 'NL') THEN 'EU' ELSE 'Non-EU' END AS region,
    COUNT(*) AS events
FROM events
GROUP BY 1, 2
ORDER BY 1, 2;

-- ==============================================================================
-- SCHEMA DRIFT DETECTION (Scenario 3.3)
-- ==============================================================================

SELECT '=== SCHEMA DRIFT CHECK ===' AS section;
-- Check for non-numeric prices (contains ' USD')
SELECT
    COUNT(*) AS total_products,
    SUM(CASE WHEN CAST(price AS VARCHAR) LIKE '% USD' THEN 1 ELSE 0 END) AS string_prices,
    ROUND(100.0 * SUM(CASE WHEN CAST(price AS VARCHAR) LIKE '% USD' THEN 1 ELSE 0 END) / COUNT(*), 1) AS string_pct
FROM products;

-- Sample of string prices
SELECT '=== SAMPLE STRING PRICES ===' AS section;
SELECT product_id, name, price
FROM products
WHERE CAST(price AS VARCHAR) LIKE '% USD'
LIMIT 10;

-- ==============================================================================
-- DUPLICATE DETECTION (Scenario 3.4)
-- ==============================================================================

SELECT '=== DUPLICATE ORDER ITEMS CHECK ===' AS section;
SELECT
    DATE_TRUNC('day', oi.created_at) AS day,
    COUNT(*) AS total_items,
    COUNT(*) - COUNT(DISTINCT (oi.order_id || '-' || oi.product_id)) AS duplicate_items,
    ROUND(100.0 * (COUNT(*) - COUNT(DISTINCT (oi.order_id || '-' || oi.product_id))) / COUNT(*), 1) AS dup_pct
FROM order_items oi
GROUP BY 1
ORDER BY 1;
-- Expected: Day 6 should show ~15% duplicates

-- Orders with duplicate items
SELECT '=== ORDERS WITH DUPLICATES ===' AS section;
SELECT order_id, product_id, COUNT(*) AS occurrences
FROM order_items
GROUP BY order_id, product_id
HAVING COUNT(*) > 1
LIMIT 20;

-- ==============================================================================
-- LATE ARRIVING DATA DETECTION (Scenario 3.5)
-- ==============================================================================

SELECT '=== LATE ARRIVING DATA CHECK ===' AS section;
SELECT
    DATE_TRUNC('day', created_at) AS event_day,
    DATE_TRUNC('day', inserted_at) AS insert_day,
    COUNT(*) AS event_count,
    CASE
        WHEN DATE_TRUNC('day', created_at) != DATE_TRUNC('day', inserted_at) THEN 'LATE'
        ELSE 'ON_TIME'
    END AS arrival_status
FROM events
GROUP BY 1, 2, arrival_status
ORDER BY 1, 2;
-- Expected: Some Day 2 events with Day 5 insert time

-- ==============================================================================
-- ORPHANED RECORDS DETECTION (Scenario 3.6)
-- ==============================================================================

SELECT '=== ORPHANED ORDERS CHECK ===' AS section;
SELECT
    DATE_TRUNC('day', o.created_at) AS day,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN o.user_id IS NOT NULL AND u.user_id IS NULL THEN 1 ELSE 0 END) AS orphaned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.user_id IS NOT NULL AND u.user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS orphan_pct
FROM orders o
LEFT JOIN users u ON o.user_id = u.user_id
GROUP BY 1
ORDER BY 1;
-- Expected: Day 4 should show ~8% orphaned orders

-- ==============================================================================
-- REFERENTIAL INTEGRITY
-- ==============================================================================

SELECT '=== REFERENTIAL INTEGRITY ===' AS section;

-- Orders with invalid user_id (excluding NULLs)
SELECT 'orphaned_orders' AS check_type, COUNT(*) AS count
FROM orders o
LEFT JOIN users u ON o.user_id = u.user_id
WHERE o.user_id IS NOT NULL AND u.user_id IS NULL;

-- Order items with invalid order_id
SELECT 'invalid_order_items' AS check_type, COUNT(*) AS count
FROM order_items oi
LEFT JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_id IS NULL;

-- Order items with invalid product_id
SELECT 'invalid_product_items' AS check_type, COUNT(*) AS count
FROM order_items oi
LEFT JOIN products p ON oi.product_id = p.product_id
WHERE p.product_id IS NULL;

-- Products with invalid category_id
SELECT 'invalid_product_categories' AS check_type, COUNT(*) AS count
FROM products p
LEFT JOIN categories c ON p.category_id = c.category_id
WHERE c.category_id IS NULL;

-- ==============================================================================
-- DATA QUALITY SUMMARY
-- ==============================================================================

SELECT '=== DATA QUALITY SUMMARY ===' AS section;
SELECT
    (SELECT ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) FROM orders) AS orders_null_user_pct,
    (SELECT COUNT(*) FROM orders o LEFT JOIN users u ON o.user_id = u.user_id WHERE o.user_id IS NOT NULL AND u.user_id IS NULL) AS orphaned_orders,
    (SELECT COUNT(*) - COUNT(DISTINCT (order_id || '-' || product_id)) FROM order_items) AS duplicate_order_items,
    (SELECT SUM(CASE WHEN CAST(price AS VARCHAR) LIKE '% USD' THEN 1 ELSE 0 END) FROM products) AS string_price_products,
    (SELECT COUNT(*) FROM events WHERE DATE_TRUNC('day', created_at) != DATE_TRUNC('day', inserted_at)) AS late_arriving_events;
