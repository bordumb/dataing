-- DataDr Demo Fixtures: DuckDB Loading Script
-- Usage: duckdb demo.db < load_duckdb.sql
-- Or: duckdb -c ".read load_duckdb.sql"

-- Set the fixture to load (change this to load different scenarios)
-- Options: baseline, null_spike, volume_drop, schema_drift, duplicates, late_arriving, orphaned_records
SET VARIABLE fixture = 'null_spike';

-- Load all tables from parquet files
CREATE OR REPLACE TABLE users AS
SELECT * FROM read_parquet('fixtures/' || getvariable('fixture') || '/users.parquet');

CREATE OR REPLACE TABLE categories AS
SELECT * FROM read_parquet('fixtures/' || getvariable('fixture') || '/categories.parquet');

CREATE OR REPLACE TABLE products AS
SELECT * FROM read_parquet('fixtures/' || getvariable('fixture') || '/products.parquet');

CREATE OR REPLACE TABLE orders AS
SELECT * FROM read_parquet('fixtures/' || getvariable('fixture') || '/orders.parquet');

CREATE OR REPLACE TABLE order_items AS
SELECT * FROM read_parquet('fixtures/' || getvariable('fixture') || '/order_items.parquet');

CREATE OR REPLACE TABLE events AS
SELECT * FROM read_parquet('fixtures/' || getvariable('fixture') || '/events.parquet');

-- Display summary
SELECT 'Loaded fixture: ' || getvariable('fixture') AS status;

SELECT 'users' AS table_name, COUNT(*) AS row_count FROM users
UNION ALL SELECT 'categories', COUNT(*) FROM categories
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'events', COUNT(*) FROM events;
