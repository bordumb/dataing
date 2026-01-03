# DataDr Demo Fixtures: Technical Specification

## Implementation Directive

**TIMELINE:** 2-3 days maximum. This is a demo, not a product. Resist the urge to overengineer.

**GOAL:** Generate realistic e-commerce data with pre-baked anomalies that DataDr can detect, producing compelling "aha moments" in demos.

**OUTPUT:** Parquet files loadable into DuckDB/PostgreSQL/Trino that look like real production data.

---

## 1. Data Model

### 1.1 Schema Overview

We're modeling a typical e-commerce platform with 6 tables:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           E-COMMERCE DATA MODEL                              │
│                                                                              │
│  ┌─────────────┐       ┌─────────────┐       ┌─────────────┐               │
│  │   users     │       │  products   │       │ categories  │               │
│  ├─────────────┤       ├─────────────┤       ├─────────────┤               │
│  │ user_id     │       │ product_id  │       │ category_id │               │
│  │ email       │       │ name        │──────▶│ name        │               │
│  │ created_at  │       │ category_id │       │ parent_id   │               │
│  │ country     │       │ price       │       └─────────────┘               │
│  │ device_type │       │ cost        │                                      │
│  │ is_premium  │       │ stock_qty   │                                      │
│  └──────┬──────┘       │ created_at  │                                      │
│         │              └─────────────┘                                      │
│         │                     │                                              │
│         │                     │                                              │
│         ▼                     ▼                                              │
│  ┌─────────────────────────────────────┐                                    │
│  │              orders                  │                                    │
│  ├─────────────────────────────────────┤                                    │
│  │ order_id                            │                                    │
│  │ user_id ─────────────────────────────────────────────┐                   │
│  │ status (pending/paid/shipped/delivered/cancelled)    │                   │
│  │ total_amount                                         │                   │
│  │ discount_amount                                      │                   │
│  │ shipping_cost                                        │                   │
│  │ created_at                                           │                   │
│  │ updated_at                                           │                   │
│  └──────────────────┬──────────────────┘                │                   │
│                     │                                    │                   │
│                     ▼                                    │                   │
│  ┌─────────────────────────────────────┐                │                   │
│  │           order_items                │                │                   │
│  ├─────────────────────────────────────┤                │                   │
│  │ order_item_id                       │                │                   │
│  │ order_id                            │                │                   │
│  │ product_id                          │                │                   │
│  │ quantity                            │                │                   │
│  │ unit_price                          │                │                   │
│  │ created_at                          │                │                   │
│  └─────────────────────────────────────┘                │                   │
│                                                          │                   │
│  ┌─────────────────────────────────────┐                │                   │
│  │             events                   │◀───────────────┘                   │
│  ├─────────────────────────────────────┤                                    │
│  │ event_id                            │                                    │
│  │ user_id (nullable - anonymous)      │                                    │
│  │ session_id                          │                                    │
│  │ event_type                          │                                    │
│  │ event_properties (JSON)             │                                    │
│  │ page_url                            │                                    │
│  │ referrer                            │                                    │
│  │ device_type                         │                                    │
│  │ country                             │                                    │
│  │ created_at                          │                                    │
│  └─────────────────────────────────────┘                                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Detailed Schema Definitions

```sql
-- users.sql
CREATE TABLE users (
    user_id         VARCHAR(36) PRIMARY KEY,  -- UUID
    email           VARCHAR(255) NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    country         VARCHAR(2),               -- ISO 3166-1 alpha-2
    device_type     VARCHAR(20),              -- 'mobile', 'desktop', 'tablet'
    is_premium      BOOLEAN DEFAULT FALSE,
    lifetime_value  DECIMAL(10,2)
);

-- categories.sql
CREATE TABLE categories (
    category_id     INTEGER PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    parent_id       INTEGER REFERENCES categories(category_id),
    slug            VARCHAR(100) NOT NULL
);

-- products.sql
CREATE TABLE products (
    product_id      VARCHAR(36) PRIMARY KEY,  -- UUID
    name            VARCHAR(255) NOT NULL,
    category_id     INTEGER REFERENCES categories(category_id),
    price           DECIMAL(10,2) NOT NULL,
    cost            DECIMAL(10,2),
    stock_qty       INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL
);

-- orders.sql
CREATE TABLE orders (
    order_id        VARCHAR(36) PRIMARY KEY,  -- UUID
    user_id         VARCHAR(36) REFERENCES users(user_id),
    status          VARCHAR(20) NOT NULL,     -- pending/paid/shipped/delivered/cancelled
    total_amount    DECIMAL(10,2) NOT NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0,
    shipping_cost   DECIMAL(10,2) DEFAULT 0,
    payment_method  VARCHAR(20),              -- card/paypal/applepay/crypto
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);

-- order_items.sql
CREATE TABLE order_items (
    order_item_id   VARCHAR(36) PRIMARY KEY,  -- UUID
    order_id        VARCHAR(36) REFERENCES orders(order_id),
    product_id      VARCHAR(36) REFERENCES products(product_id),
    quantity        INTEGER NOT NULL,
    unit_price      DECIMAL(10,2) NOT NULL,
    created_at      TIMESTAMP NOT NULL
);

-- events.sql
CREATE TABLE events (
    event_id        VARCHAR(36) PRIMARY KEY,  -- UUID
    user_id         VARCHAR(36),              -- NULL for anonymous
    session_id      VARCHAR(36) NOT NULL,
    event_type      VARCHAR(50) NOT NULL,
    event_properties JSON,
    page_url        VARCHAR(500),
    referrer        VARCHAR(500),
    device_type     VARCHAR(20),
    country         VARCHAR(2),
    created_at      TIMESTAMP NOT NULL
);
```

### 1.3 Event Types

```
EVENT TAXONOMY
──────────────────────────────────────────────────────────────

Page Views:
  • page_view              {page: string, title: string}

Search:
  • search                 {query: string, results_count: int}
  • search_click           {query: string, product_id: string, position: int}

Product:
  • product_view           {product_id: string, source: string}
  • product_add_to_cart    {product_id: string, quantity: int}
  • product_remove_from_cart {product_id: string}

Checkout:
  • checkout_started       {cart_value: float, item_count: int}
  • checkout_step          {step: int, step_name: string}
  • checkout_completed     {order_id: string, total: float}
  • checkout_abandoned     {step: int, cart_value: float}

User:
  • user_signup            {method: string}
  • user_login             {method: string}
  • user_logout            {}

Error:
  • error                  {error_type: string, message: string, page: string}
```

---

## 2. Data Volume Targets

### 2.1 Baseline Volumes (7 Days)

| Table | Row Count | Rationale |
|-------|-----------|-----------|
| users | 10,000 | Mix of new and returning |
| categories | 50 | 10 top-level, 40 subcategories |
| products | 500 | Typical mid-size catalog |
| orders | 5,000 | ~700/day, 5% of users purchase |
| order_items | 12,500 | Avg 2.5 items per order |
| events | 500,000 | ~70K/day, realistic for mid-size site |

### 2.2 Temporal Distribution

```
DAILY EVENT VOLUME (Typical Week)
─────────────────────────────────────────────────────────────

              Mon    Tue    Wed    Thu    Fri    Sat    Sun
Events:       65K    60K    62K    68K    80K    85K    75K
Orders:       600    550    580    650    750    850    720

Hourly Distribution (UTC):
┌────────────────────────────────────────────────────────────┐
│     ▁▁▂▂▃▄▅▆▇███████▇▇▆▅▄▃▂▁                              │
│  00 02 04 06 08 10 12 14 16 18 20 22 24                   │
│                                                            │
│  Peak: 10:00-14:00 and 19:00-21:00                        │
│  Trough: 02:00-06:00                                       │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Anomaly Scenarios

Each scenario is a separate fixture set. DataDr should detect each anomaly type.

### 3.1 Scenario: NULL Spike

**What:** `user_id` in `orders` table goes from 0% NULL to 40% NULL on Day 3.

**Root Cause Story:** "Mobile app update shipped with a bug that doesn't pass user context to the checkout API."

**Detection Signal:**
- NULL rate spike in `orders.user_id`
- Correlates with `device_type = 'mobile'` in events
- Temporal: starts exactly at 14:00 UTC on Day 3

```
NULL Rate in orders.user_id
─────────────────────────────────────────────────────────────
Day 1:  ████ 0.1%
Day 2:  ████ 0.1%
Day 3:  ████████████████████████████████████████ 41.2%  ← ANOMALY
Day 4:  ████████████████████████████████████████ 39.8%
Day 5:  ████████████████████████████████████████ 40.1%
Day 6:  ████ 0.2%  ← "Fixed" by reverting app
Day 7:  ████ 0.1%
```

### 3.2 Scenario: Volume Drop

**What:** `events` table volume drops 80% on Day 5.

**Root Cause Story:** "CDN misconfiguration blocked the tracking pixel for EU users."

**Detection Signal:**
- Event count drops from ~70K to ~14K
- Only affects `country IN ('DE', 'FR', 'GB', 'IT', 'ES', 'NL')`
- Orders unaffected (server-side tracking)

```
Daily Event Volume
─────────────────────────────────────────────────────────────
Day 1:  ████████████████████████████████████████ 72,341
Day 2:  ████████████████████████████████████████ 68,892
Day 3:  ████████████████████████████████████████ 71,203
Day 4:  ████████████████████████████████████████ 69,445
Day 5:  ████████ 14,221  ← ANOMALY (EU traffic missing)
Day 6:  ████████ 13,998
Day 7:  ████████████████████████████████████████ 70,112  ← Fixed
```

### 3.3 Scenario: Schema Drift

**What:** `products.price` column type changes from DECIMAL to VARCHAR on Day 4.

**Root Cause Story:** "New product import job doesn't cast types properly, starts inserting '29.99' as string."

**Detection Signal:**
- Type inconsistency in `products.price`
- Downstream: `order_items.unit_price` calculations start failing
- Some prices appear as "29.99 USD" (string with currency)

```
products.price Data Type Distribution
─────────────────────────────────────────────────────────────
Days 1-3:   DECIMAL(10,2) - 100%
Day 4+:     DECIMAL(10,2) - 72%
            VARCHAR       - 28%  ← New products have string prices
```

### 3.4 Scenario: Duplicate Records

**What:** `order_items` has duplicate entries for the same order on Day 6.

**Root Cause Story:** "Retry logic in checkout service doesn't check for idempotency, network timeout caused duplicate inserts."

**Detection Signal:**
- Same `(order_id, product_id)` appears multiple times
- Affects ~15% of orders on Day 6
- `total_amount` in orders doesn't match sum of `order_items`

```
Duplicate order_items per order
─────────────────────────────────────────────────────────────
Days 1-5:   0.0% of orders have duplicates
Day 6:      14.7% of orders have duplicate items  ← ANOMALY
Day 7:      0.1% (residual from Day 6 processing)
```

### 3.5 Scenario: Late Arriving Data

**What:** Events from Day 2 arrive with `created_at` timestamps from Day 2, but inserted on Day 5.

**Root Cause Story:** "Mobile app queues events offline, batch uploaded when user reconnects after 3-day flight."

**Detection Signal:**
- Events with `created_at` on Day 2 appear in Day 5 partition
- If using `INSERT_TIME` for partitioning, creates data "in the past"
- Affects ~3% of Day 2's events

```
Event Arrival Pattern
─────────────────────────────────────────────────────────────
                    created_at timestamp
                    Day1  Day2  Day3  Day4  Day5  Day6  Day7
Inserted on Day 1:  100%
Inserted on Day 2:        100%
Inserted on Day 3:              100%
Inserted on Day 4:                    100%
Inserted on Day 5:        3%←         97%   ← Late arrivals
Inserted on Day 6:                                100%
Inserted on Day 7:                                      100%
```

### 3.6 Scenario: Referential Integrity Violation

**What:** `orders.user_id` references users that don't exist on Day 4.

**Root Cause Story:** "User deletion job ran before order archival job, orphaned orders."

**Detection Signal:**
- `orders.user_id` values with no matching `users.user_id`
- ~8% of Day 4 orders are orphaned
- Affects queries that JOIN orders to users

```
Orphaned Orders (user_id not in users)
─────────────────────────────────────────────────────────────
Days 1-3:   0.0%
Day 4:      8.2%  ← ANOMALY
Days 5-7:   0.0%
```

---

## 4. Generation Strategy

### 4.1 Seed Data (Static)

Generate once, reuse across scenarios:

```python
# Reference data that doesn't change
CATEGORIES = [
    {"category_id": 1, "name": "Electronics", "parent_id": None},
    {"category_id": 2, "name": "Phones", "parent_id": 1},
    {"category_id": 3, "name": "Laptops", "parent_id": 1},
    # ... 50 total
]

PRODUCTS = generate_products(
    count=500,
    price_range=(9.99, 999.99),
    categories=CATEGORIES,
)

COUNTRIES = ["US", "GB", "DE", "FR", "CA", "AU", "JP", "BR", "IN", "MX"]
COUNTRY_WEIGHTS = [0.35, 0.15, 0.10, 0.08, 0.07, 0.05, 0.05, 0.05, 0.05, 0.05]
```

### 4.2 User Generation

```python
def generate_users(count: int, date_range: tuple[date, date]) -> list[User]:
    """
    Generate users with realistic distribution.

    - 70% created before the simulation period (returning users)
    - 30% created during the simulation (new users)
    - Device distribution: 55% mobile, 35% desktop, 10% tablet
    - Premium rate: 8%
    """
    users = []

    for i in range(count):
        is_new = random.random() < 0.30

        if is_new:
            created_at = random_datetime_in_range(date_range)
        else:
            # Created 1-365 days before simulation start
            days_before = random.randint(1, 365)
            created_at = date_range[0] - timedelta(days=days_before)

        users.append(User(
            user_id=str(uuid4()),
            email=fake.email(),
            created_at=created_at,
            country=random.choices(COUNTRIES, COUNTRY_WEIGHTS)[0],
            device_type=random.choices(
                ["mobile", "desktop", "tablet"],
                [0.55, 0.35, 0.10]
            )[0],
            is_premium=random.random() < 0.08,
        ))

    return users
```

### 4.3 Session & Event Generation

```python
def generate_session(user: User, start_time: datetime) -> list[Event]:
    """
    Generate a realistic user session.

    Session flow:
    1. Landing (page_view)
    2. Browse/Search loop (1-10 iterations)
    3. Maybe add to cart (30% chance per product view)
    4. Maybe checkout (40% of carts)
    5. Maybe complete (60% of checkouts)
    """
    session_id = str(uuid4())
    events = []
    current_time = start_time

    # Landing
    events.append(Event(
        event_type="page_view",
        page_url=random.choice(["/", "/sale", "/new-arrivals"]),
        timestamp=current_time,
    ))
    current_time += random_delay(seconds=(5, 30))

    # Browse loop
    products_viewed = []
    cart = []

    for _ in range(random.randint(1, 10)):
        action = random.choices(
            ["search", "browse_category", "view_product"],
            [0.2, 0.3, 0.5]
        )[0]

        if action == "search":
            events.append(Event(
                event_type="search",
                event_properties={"query": fake.word(), "results_count": random.randint(0, 50)},
                timestamp=current_time,
            ))
        elif action == "view_product":
            product = random.choice(PRODUCTS)
            products_viewed.append(product)
            events.append(Event(
                event_type="product_view",
                event_properties={"product_id": product.product_id},
                timestamp=current_time,
            ))

            # Maybe add to cart
            if random.random() < 0.30:
                cart.append(product)
                events.append(Event(
                    event_type="product_add_to_cart",
                    event_properties={"product_id": product.product_id, "quantity": 1},
                    timestamp=current_time + timedelta(seconds=random.randint(10, 60)),
                ))

        current_time += random_delay(seconds=(20, 180))

    # Checkout flow
    if cart and random.random() < 0.40:
        events.extend(generate_checkout_flow(cart, current_time, complete=random.random() < 0.60))

    # Attach session metadata to all events
    for event in events:
        event.session_id = session_id
        event.user_id = user.user_id
        event.device_type = user.device_type
        event.country = user.country

    return events
```

### 4.4 Order Generation

```python
def generate_order_from_checkout(
    user: User,
    cart: list[Product],
    timestamp: datetime,
) -> tuple[Order, list[OrderItem]]:
    """
    Generate order and order_items from a completed checkout.
    """
    order_id = str(uuid4())

    items = []
    subtotal = Decimal("0.00")

    for product in cart:
        quantity = random.randint(1, 3)
        items.append(OrderItem(
            order_item_id=str(uuid4()),
            order_id=order_id,
            product_id=product.product_id,
            quantity=quantity,
            unit_price=product.price,
            created_at=timestamp,
        ))
        subtotal += product.price * quantity

    # Apply discount (20% of orders)
    discount = Decimal("0.00")
    if random.random() < 0.20:
        discount = (subtotal * Decimal(random.uniform(0.05, 0.25))).quantize(Decimal("0.01"))

    # Shipping
    shipping = Decimal("5.99") if subtotal < Decimal("50.00") else Decimal("0.00")

    order = Order(
        order_id=order_id,
        user_id=user.user_id,
        status="paid",
        total_amount=subtotal - discount + shipping,
        discount_amount=discount,
        shipping_cost=shipping,
        payment_method=random.choices(
            ["card", "paypal", "applepay"],
            [0.70, 0.20, 0.10]
        )[0],
        created_at=timestamp,
        updated_at=timestamp,
    )

    return order, items
```

### 4.5 Anomaly Injection

```python
def inject_null_spike(
    orders: list[Order],
    start_day: int,
    end_day: int,
    null_rate: float,
    condition: Callable[[Order], bool] = lambda o: True,
) -> list[Order]:
    """
    Inject NULL values into orders.user_id.

    Args:
        orders: List of orders to modify
        start_day: Day number to start injection (1-indexed)
        end_day: Day number to end injection
        null_rate: Fraction of orders to NULL (0.0 to 1.0)
        condition: Additional filter (e.g., mobile only)
    """
    modified = []

    for order in orders:
        day = (order.created_at.date() - SIMULATION_START).days + 1

        if start_day <= day <= end_day and condition(order):
            if random.random() < null_rate:
                order = order._replace(user_id=None)

        modified.append(order)

    return modified


def inject_volume_drop(
    events: list[Event],
    day: int,
    drop_rate: float,
    condition: Callable[[Event], bool],
) -> list[Event]:
    """
    Remove events to simulate tracking failure.
    """
    return [
        e for e in events
        if not (
            get_day(e.created_at) == day
            and condition(e)
            and random.random() < drop_rate
        )
    ]


def inject_duplicates(
    order_items: list[OrderItem],
    day: int,
    duplicate_rate: float,
) -> list[OrderItem]:
    """
    Duplicate order_items to simulate retry bug.
    """
    result = []

    for item in order_items:
        result.append(item)

        if get_day(item.created_at) == day and random.random() < duplicate_rate:
            # Duplicate with new ID but same order_id/product_id
            duplicate = item._replace(order_item_id=str(uuid4()))
            result.append(duplicate)

    return result
```

---

## 5. Output Format

### 5.1 Directory Structure

```
fixtures/
├── baseline/                      # Clean data, no anomalies
│   ├── users.parquet
│   ├── categories.parquet
│   ├── products.parquet
│   ├── orders.parquet
│   ├── order_items.parquet
│   ├── events.parquet
│   └── manifest.json              # Metadata about this fixture
│
├── null_spike/                    # Scenario 3.1
│   ├── users.parquet
│   ├── categories.parquet
│   ├── products.parquet
│   ├── orders.parquet             # Modified: NULLs on days 3-5
│   ├── order_items.parquet
│   ├── events.parquet
│   └── manifest.json
│
├── volume_drop/                   # Scenario 3.2
│   └── ...
│
├── schema_drift/                  # Scenario 3.3
│   └── ...
│
├── duplicates/                    # Scenario 3.4
│   └── ...
│
├── late_arriving/                 # Scenario 3.5
│   └── ...
│
└── orphaned_records/              # Scenario 3.6
    └── ...
```

### 5.2 Manifest Schema

```json
{
  "name": "null_spike",
  "description": "Mobile app bug causes NULL user_id in orders",
  "created_at": "2024-01-15T10:30:00Z",
  "simulation_period": {
    "start": "2024-01-08",
    "end": "2024-01-14"
  },
  "tables": {
    "users": {"row_count": 10000, "file": "users.parquet"},
    "categories": {"row_count": 50, "file": "categories.parquet"},
    "products": {"row_count": 500, "file": "products.parquet"},
    "orders": {"row_count": 5023, "file": "orders.parquet"},
    "order_items": {"row_count": 12547, "file": "order_items.parquet"},
    "events": {"row_count": 498234, "file": "events.parquet"}
  },
  "anomalies": [
    {
      "type": "null_spike",
      "table": "orders",
      "column": "user_id",
      "start_day": 3,
      "end_day": 5,
      "severity": 0.41,
      "root_cause": "Mobile app v2.3.1 bug - checkout API not passing user context",
      "expected_detection": {
        "pattern_type": "NULL_SPIKE",
        "confidence": 0.95
      }
    }
  ],
  "ground_truth": {
    "affected_order_ids": ["uuid1", "uuid2", "..."],
    "affected_row_count": 892
  }
}
```

### 5.3 Parquet Configuration

```python
# Write configuration for optimal query performance
PARQUET_CONFIG = {
    "compression": "snappy",
    "row_group_size": 100_000,
    "use_dictionary": True,
    "write_statistics": True,
}

# Partition strategy (for events table)
EVENTS_PARTITIONING = {
    "partition_cols": ["date"],  # Daily partitions
    "existing_data_behavior": "overwrite_or_ignore",
}
```

---

## 6. Loading Into Demo Environment

### 6.1 DuckDB (Fastest for Demo)

```sql
-- Load all tables
CREATE TABLE users AS SELECT * FROM 'fixtures/null_spike/users.parquet';
CREATE TABLE categories AS SELECT * FROM 'fixtures/null_spike/categories.parquet';
CREATE TABLE products AS SELECT * FROM 'fixtures/null_spike/products.parquet';
CREATE TABLE orders AS SELECT * FROM 'fixtures/null_spike/orders.parquet';
CREATE TABLE order_items AS SELECT * FROM 'fixtures/null_spike/order_items.parquet';
CREATE TABLE events AS SELECT * FROM 'fixtures/null_spike/events.parquet';

-- Verify anomaly is present
SELECT
    DATE_TRUNC('day', created_at) as day,
    COUNT(*) as total_orders,
    SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_user_orders,
    ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as null_pct
FROM orders
GROUP BY 1
ORDER BY 1;
```

### 6.2 PostgreSQL

```bash
# Create schema
psql -d datadr_demo -f schema.sql

# Load data (requires parquet_fdw or convert to CSV first)
# Option 1: Use DuckDB to convert
duckdb -c "COPY (SELECT * FROM 'fixtures/null_spike/orders.parquet') TO 'orders.csv' (HEADER, DELIMITER ',');"

# Option 2: Use pgloader
pgloader parquet://fixtures/null_spike/orders.parquet postgresql:///datadr_demo
```

### 6.3 Trino (For Production-Like Demo)

```sql
-- Create external tables pointing to parquet files
CREATE SCHEMA IF NOT EXISTS demo WITH (location = 's3://datadr-demo-fixtures/');

CREATE TABLE demo.orders (
    order_id VARCHAR,
    user_id VARCHAR,
    status VARCHAR,
    total_amount DECIMAL(10,2),
    -- ...
)
WITH (
    external_location = 's3://datadr-demo-fixtures/null_spike/orders/',
    format = 'PARQUET'
);
```

---

## 7. Validation Queries

Run these queries to verify fixtures are correct before demos.

### 7.1 Basic Integrity

```sql
-- Row counts match manifest
SELECT 'users' as tbl, COUNT(*) as cnt FROM users
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'events', COUNT(*) FROM events;

-- No unexpected NULLs in baseline
SELECT
    'orders.user_id' as col,
    COUNT(*) as total,
    SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as nulls
FROM orders;

-- Referential integrity (baseline should pass)
SELECT COUNT(*) as orphaned_orders
FROM orders o
LEFT JOIN users u ON o.user_id = u.user_id
WHERE o.user_id IS NOT NULL AND u.user_id IS NULL;
```

### 7.2 Temporal Distribution

```sql
-- Events per day (should be ~70K with variance)
SELECT
    DATE_TRUNC('day', created_at) as day,
    COUNT(*) as events
FROM events
GROUP BY 1
ORDER BY 1;

-- Hourly distribution (should show expected pattern)
SELECT
    EXTRACT(HOUR FROM created_at) as hour,
    COUNT(*) as events
FROM events
GROUP BY 1
ORDER BY 1;
```

### 7.3 Anomaly Verification

```sql
-- NULL spike scenario: Verify spike exists
SELECT
    DATE_TRUNC('day', created_at) as day,
    ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as null_pct
FROM orders
GROUP BY 1
ORDER BY 1;
-- Expected: Days 1-2 ≈ 0%, Days 3-5 ≈ 40%, Days 6-7 ≈ 0%

-- Volume drop scenario: Verify EU traffic missing
SELECT
    DATE_TRUNC('day', created_at) as day,
    country,
    COUNT(*) as events
FROM events
WHERE country IN ('DE', 'FR', 'GB')
GROUP BY 1, 2
ORDER BY 1, 2;
-- Expected: Day 5 should show ~80% drop for EU countries
```

---

## 8. Implementation Checklist

### Day 1: Core Generation

- [ ] Set up Python project with dependencies (polars, faker, uuid)
- [ ] Implement seed data generation (categories, products)
- [ ] Implement user generation with realistic distribution
- [ ] Implement session/event generation
- [ ] Implement order generation from checkout events
- [ ] Generate baseline fixture (no anomalies)
- [ ] Write validation queries, verify baseline is clean

### Day 2: Anomaly Injection

- [ ] Implement `inject_null_spike()` function
- [ ] Implement `inject_volume_drop()` function
- [ ] Implement `inject_duplicates()` function
- [ ] Implement `inject_late_arriving()` function
- [ ] Implement `inject_orphaned_records()` function
- [ ] Implement `inject_schema_drift()` function
- [ ] Generate all 6 anomaly fixtures
- [ ] Write anomaly verification queries, confirm each anomaly is detectable

### Day 3: Integration & Polish

- [ ] Create manifest.json generator
- [ ] Write DuckDB loading script
- [ ] Write PostgreSQL loading script (if needed)
- [ ] Run DataDr against each fixture, verify detection
- [ ] Document demo script ("At this point, DataDr will detect...")
- [ ] Create demo video script/storyboard

---

## 9. Demo Script Outline

### Slide 1: "The Problem"

> "Your data warehouse has 500 tables. Something breaks. You find out 3 days later when a dashboard is wrong. Sound familiar?"

### Slide 2: "Live Demo"

> "Let me show you DataDr detecting a real issue in this e-commerce dataset."

**Action:** Load `null_spike` fixture, run DataDr investigation.

### Slide 3: "Detection"

> "DataDr identified a NULL spike in `orders.user_id` that started on January 10th. 41% of orders are affected."

**Show:** DataDr UI with detection result.

### Slide 4: "Root Cause"

> "It correlated this with mobile traffic and identified the likely cause: the mobile app checkout flow isn't passing user context."

**Show:** DataDr root cause analysis.

### Slide 5: "Impact"

> "This affected 892 orders, representing $47,000 in revenue that can't be attributed to users. Your marketing attribution is broken."

**Show:** Impact quantification.

### Slide 6: "Call to Action"

> "DataDr would have caught this in minutes, not days. Want to see it on your data?"

---

## 10. Dependencies

```toml
# pyproject.toml
[project]
name = "datadr-fixtures"
version = "0.1.0"
dependencies = [
    "polars>=0.20.0",      # Fast DataFrame operations
    "faker>=22.0.0",       # Realistic fake data
    "pyarrow>=15.0.0",     # Parquet I/O
]

[project.optional-dependencies]
dev = [
    "duckdb>=0.9.0",       # Validation queries
    "pytest>=8.0.0",
]
```

---

## Final Notes

**Remember:** This is a demo, not a product. The goal is to show DataDr detecting problems in realistic-looking data. Don't spend time on:

- Perfect statistical distributions
- Edge cases that won't appear in demos
- Multiple data domains (e-commerce is enough)
- Configurable generation (hardcode everything)

**Do spend time on:**

- Making sure each anomaly is clearly detectable
- Having a compelling "story" for each anomaly
- Smooth demo flow with no loading delays

Yes, `./demo` at the root is perfect. Clean and obvious.

```
datadr/
├── backend/
├── frontend/
├── demo/
│   ├── fixtures/
│   │   ├── baseline/
│   │   ├── null_spike/
│   │   ├── volume_drop/
│   │   └── ...
│   ├── generate.py        # One-shot script to build all fixtures
│   ├── load_duckdb.sql    # Quick load for demos
│   └── README.md          # "How to run the demo"
├── docs/
└── ...
```

A few practical notes:

**1. Gitignore the parquet files, commit the generator**

```gitignore
# demo/.gitignore
fixtures/**/*.parquet
!fixtures/**/manifest.json
```

Parquet files are large and binary. Commit the `generate.py` and manifests, regenerate fixtures locally or in CI.

**2. Add a one-liner to your README**

```bash
# Generate demo data and run
cd demo && python generate.py && cd ../backend && make run
```

**3. Consider a `make demo` target**

```makefile
# Makefile (root)
demo:
	cd demo && uv run generate.py
	cd backend && uv run python -m datadr.cli investigate --source duckdb://demo/fixtures/null_spike
```

This keeps the demo self-contained without polluting your core codebase. When you're ready to ship, you can even exclude `demo/` from the production Docker image.
