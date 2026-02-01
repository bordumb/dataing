-- Initialize DuckDB demo database with fixtures
-- This script runs on container startup via duckgres

-- Create tables from parquet fixtures
CREATE TABLE IF NOT EXISTS users AS SELECT * FROM read_parquet('/data/users.parquet');
CREATE TABLE IF NOT EXISTS categories AS SELECT * FROM read_parquet('/data/categories.parquet');
CREATE TABLE IF NOT EXISTS products AS SELECT * FROM read_parquet('/data/products.parquet');
CREATE TABLE IF NOT EXISTS orders AS SELECT * FROM read_parquet('/data/orders.parquet');
CREATE TABLE IF NOT EXISTS order_items AS SELECT * FROM read_parquet('/data/order_items.parquet');
CREATE TABLE IF NOT EXISTS events AS SELECT * FROM read_parquet('/data/events.parquet');

-- Verify data loaded
SELECT 'users' as table_name, COUNT(*) as row_count FROM users
UNION ALL SELECT 'categories', COUNT(*) FROM categories
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'events', COUNT(*) FROM events;
