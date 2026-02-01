-- Initialize pg_duckdb demo database with fixtures
-- This script runs on PostgreSQL container startup

-- Enable pg_duckdb extension
CREATE EXTENSION IF NOT EXISTS pg_duckdb;

-- Create tables by importing from parquet files using DuckDB
-- pg_duckdb allows running DuckDB queries through PostgreSQL

-- Import users table
CREATE TABLE users AS
SELECT * FROM read_parquet('/data/users.parquet');

-- Import categories table
CREATE TABLE categories AS
SELECT * FROM read_parquet('/data/categories.parquet');

-- Import products table
CREATE TABLE products AS
SELECT * FROM read_parquet('/data/products.parquet');

-- Import orders table (contains NULL spike anomaly)
CREATE TABLE orders AS
SELECT * FROM read_parquet('/data/orders.parquet');

-- Import order_items table
CREATE TABLE order_items AS
SELECT * FROM read_parquet('/data/order_items.parquet');

-- Import events table
CREATE TABLE events AS
SELECT * FROM read_parquet('/data/events.parquet');

-- Verify data loaded
SELECT 'Data loaded successfully' as status;
SELECT 'users' as table_name, COUNT(*) as row_count FROM users
UNION ALL SELECT 'categories', COUNT(*) FROM categories
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'events', COUNT(*) FROM events;
