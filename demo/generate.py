#!/usr/bin/env python3
"""
Dataing Demo Fixtures Generator.

Generates realistic e-commerce data with pre-baked anomalies for demos.
Run with: uv run python demo/generate.py
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl
from faker import Faker

# Initialize Faker for realistic data
fake = Faker()
Faker.seed(42)
random.seed(42)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Simulation period: 7 days
SIMULATION_START = date(2026, 1, 8)
SIMULATION_END = date(2026, 1, 14)

# Volume targets
USER_COUNT = 10_000
PRODUCT_COUNT = 500
CATEGORY_COUNT = 50
TARGET_ORDERS_PER_DAY = 700
TARGET_EVENTS_PER_DAY = 70_000

# Geographic distribution
COUNTRIES = ["US", "GB", "DE", "FR", "CA", "AU", "JP", "BR", "IN", "MX"]
COUNTRY_WEIGHTS = [0.35, 0.15, 0.10, 0.08, 0.07, 0.05, 0.05, 0.05, 0.05, 0.05]

# EU countries for volume drop scenario
EU_COUNTRIES = ["DE", "FR", "GB", "IT", "ES", "NL"]

# Device distribution
DEVICES = ["mobile", "desktop", "tablet"]
DEVICE_WEIGHTS = [0.55, 0.35, 0.10]

# Payment methods
PAYMENT_METHODS = ["card", "paypal", "applepay", "crypto"]
PAYMENT_WEIGHTS = [0.70, 0.20, 0.08, 0.02]

# Output directory
OUTPUT_DIR = Path(__file__).parent / "fixtures"

# Parquet configuration
PARQUET_CONFIG = {
    "compression": "snappy",
}


# ==============================================================================
# DATA MODELS
# ==============================================================================


@dataclass
class Category:
    """Product category."""

    category_id: int
    name: str
    parent_id: int | None
    slug: str


@dataclass
class Product:
    """Product in the catalog."""

    product_id: str
    name: str
    category_id: int
    price: Decimal
    cost: Decimal
    stock_qty: int
    is_active: bool
    created_at: datetime


@dataclass
class User:
    """Registered user."""

    user_id: str
    email: str
    created_at: datetime
    country: str
    device_type: str
    is_premium: bool
    lifetime_value: Decimal


@dataclass
class Order:
    """Customer order."""

    order_id: str
    user_id: str | None
    status: str
    total_amount: Decimal
    discount_amount: Decimal
    shipping_cost: Decimal
    payment_method: str
    created_at: datetime
    updated_at: datetime
    # Channel and platform info for root cause investigation
    channel: str  # "mobile_app", "web", "api"
    platform: str | None  # "ios", "android", None for web
    app_version: str | None  # "2.3.0", "2.3.1", etc. None for web
    session_id: str | None  # Links to events table


@dataclass
class OrderItem:
    """Individual item in an order."""

    order_item_id: str
    order_id: str
    product_id: str
    quantity: int
    unit_price: Decimal
    created_at: datetime


@dataclass
class Event:
    """Analytics event."""

    event_id: str
    user_id: str | None
    session_id: str
    event_type: str
    event_properties: dict[str, Any]
    page_url: str
    referrer: str | None
    device_type: str
    country: str
    created_at: datetime
    # Channel and app info for correlation with orders
    channel: str = "web"  # "mobile_app", "web", "api"
    platform: str | None = None  # "ios", "android", None for web
    app_version: str | None = None  # "2.3.0", "2.3.1", etc. None for web
    # For late-arriving data scenario
    inserted_at: datetime | None = None


@dataclass
class GeneratedData:
    """Container for all generated data."""

    categories: list[Category] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    users: list[User] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    order_items: list[OrderItem] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


# ==============================================================================
# SEED DATA GENERATION
# ==============================================================================


def generate_categories() -> list[Category]:
    """Generate hierarchical product categories."""
    categories = []

    # Top-level categories
    top_categories = [
        ("Electronics", "electronics"),
        ("Clothing", "clothing"),
        ("Home & Garden", "home-garden"),
        ("Sports", "sports"),
        ("Books", "books"),
        ("Beauty", "beauty"),
        ("Toys", "toys"),
        ("Food", "food"),
        ("Automotive", "automotive"),
        ("Office", "office"),
    ]

    # Subcategories for each top-level
    subcategories = {
        "Electronics": ["Phones", "Laptops", "TVs", "Audio"],
        "Clothing": ["Men", "Women", "Kids", "Accessories"],
        "Home & Garden": ["Furniture", "Kitchen", "Garden", "Decor"],
        "Sports": ["Fitness", "Outdoor", "Team Sports", "Water Sports"],
        "Books": ["Fiction", "Non-Fiction", "Children", "Academic"],
        "Beauty": ["Skincare", "Makeup", "Haircare", "Fragrance"],
        "Toys": ["Action Figures", "Board Games", "Educational", "Outdoor"],
        "Food": ["Snacks", "Beverages", "Organic", "International"],
        "Automotive": ["Parts", "Accessories", "Tools", "Care"],
        "Office": ["Supplies", "Furniture", "Electronics", "Storage"],
    }

    cat_id = 1
    for name, slug in top_categories:
        categories.append(Category(category_id=cat_id, name=name, parent_id=None, slug=slug))
        parent_id = cat_id
        cat_id += 1

        for sub_name in subcategories.get(name, []):
            sub_slug = f"{slug}-{sub_name.lower().replace(' ', '-')}"
            categories.append(
                Category(category_id=cat_id, name=sub_name, parent_id=parent_id, slug=sub_slug)
            )
            cat_id += 1

    return categories


def generate_products(categories: list[Category]) -> list[Product]:
    """Generate product catalog."""
    products = []

    # Get subcategory IDs (non-null parent_id)
    subcategory_ids = [c.category_id for c in categories if c.parent_id is not None]

    product_adjectives = [
        "Premium",
        "Pro",
        "Ultra",
        "Classic",
        "Essential",
        "Deluxe",
        "Basic",
        "Advanced",
        "Elite",
        "Standard",
    ]
    product_nouns = [
        "Widget",
        "Gadget",
        "Tool",
        "Item",
        "Product",
        "Device",
        "Kit",
        "Set",
        "Pack",
        "Bundle",
    ]

    for _ in range(PRODUCT_COUNT):
        price = Decimal(str(round(random.uniform(9.99, 999.99), 2)))
        margin = Decimal(str(round(random.uniform(0.2, 0.6), 2)))
        cost = (price * (1 - margin)).quantize(Decimal("0.01"))

        # Created 1-180 days before simulation start
        days_before = random.randint(1, 180)
        created_at = datetime.combine(
            SIMULATION_START - timedelta(days=days_before),
            datetime.min.time().replace(hour=random.randint(0, 23), minute=random.randint(0, 59)),
        )

        name = f"{random.choice(product_adjectives)} {fake.word().title()} {random.choice(product_nouns)}"

        products.append(
            Product(
                product_id=str(uuid4()),
                name=name,
                category_id=random.choice(subcategory_ids),
                price=price,
                cost=cost,
                stock_qty=random.randint(0, 1000),
                is_active=random.random() > 0.05,  # 95% active
                created_at=created_at,
            )
        )

    return products


# ==============================================================================
# USER GENERATION
# ==============================================================================


def generate_users() -> list[User]:
    """Generate users with realistic distribution."""
    users = []

    for _ in range(USER_COUNT):
        # 70% created before simulation, 30% during
        is_new = random.random() < 0.30

        if is_new:
            # New user - created during simulation period
            days_into_sim = random.randint(0, 6)
            created_at = datetime.combine(
                SIMULATION_START + timedelta(days=days_into_sim),
                datetime.min.time().replace(
                    hour=random.randint(8, 22), minute=random.randint(0, 59)
                ),
            )
        else:
            # Returning user - created 1-365 days before simulation
            days_before = random.randint(1, 365)
            created_at = datetime.combine(
                SIMULATION_START - timedelta(days=days_before),
                datetime.min.time().replace(
                    hour=random.randint(0, 23), minute=random.randint(0, 59)
                ),
            )

        country = random.choices(COUNTRIES, COUNTRY_WEIGHTS)[0]
        device_type = random.choices(DEVICES, DEVICE_WEIGHTS)[0]
        is_premium = random.random() < 0.08
        lifetime_value = Decimal(str(round(random.uniform(0, 5000), 2)))

        users.append(
            User(
                user_id=str(uuid4()),
                email=fake.email(),
                created_at=created_at,
                country=country,
                device_type=device_type,
                is_premium=is_premium,
                lifetime_value=lifetime_value,
            )
        )

    return users


# ==============================================================================
# SESSION & EVENT GENERATION
# ==============================================================================


def get_hourly_weight(hour: int) -> float:
    """Get traffic weight for a given hour (UTC)."""
    # Peak hours: 10:00-14:00 and 19:00-21:00
    # Trough: 02:00-06:00
    weights = {
        0: 0.3,
        1: 0.2,
        2: 0.1,
        3: 0.1,
        4: 0.1,
        5: 0.15,
        6: 0.3,
        7: 0.5,
        8: 0.7,
        9: 0.85,
        10: 1.0,
        11: 1.0,
        12: 0.95,
        13: 1.0,
        14: 0.9,
        15: 0.8,
        16: 0.75,
        17: 0.7,
        18: 0.8,
        19: 0.95,
        20: 1.0,
        21: 0.9,
        22: 0.6,
        23: 0.4,
    }
    return weights.get(hour, 0.5)


def random_timestamp_for_day(day: date) -> datetime:
    """Generate a random timestamp weighted by hourly traffic."""
    hours = list(range(24))
    weights = [get_hourly_weight(h) for h in hours]
    hour = random.choices(hours, weights)[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return datetime.combine(
        day, datetime.min.time().replace(hour=hour, minute=minute, second=second)
    )


def generate_session_events(
    user: User | None,
    session_start: datetime,
    products: list[Product],
) -> tuple[list[Event], list[Order], list[OrderItem]]:
    """Generate events for a single user session."""
    events = []
    orders = []
    order_items = []

    session_id = str(uuid4())
    current_time = session_start

    # For anonymous users
    if user:
        user_id = user.user_id
        device_type = user.device_type
        country = user.country
    else:
        user_id = None
        device_type = random.choices(DEVICES, DEVICE_WEIGHTS)[0]
        country = random.choices(COUNTRIES, COUNTRY_WEIGHTS)[0]

    # Determine channel, platform, and app_version based on device and date
    day = get_day_number(session_start)
    if device_type == "mobile":
        # 70% mobile app, 30% mobile web
        if random.random() < 0.70:
            channel = "mobile_app"
            platform = random.choice(["ios", "android"])
            # App version logic: v2.3.1 released on day 3, causes the bug
            # Before day 3: everyone on 2.3.0
            # Day 3+: 60% upgrade to 2.3.1 (phased rollout)
            if day < 3:
                app_version = "2.3.0"
            else:
                app_version = "2.3.1" if random.random() < 0.60 else "2.3.0"
        else:
            channel = "web"
            platform = None
            app_version = None
    else:
        channel = "web"
        platform = None
        app_version = None

    # Landing page
    landing_pages = ["/", "/sale", "/new-arrivals", "/categories"]
    referrers = [
        None,
        "https://google.com",
        "https://facebook.com",
        "https://instagram.com",
        "https://email.example.com",
    ]

    events.append(
        Event(
            event_id=str(uuid4()),
            user_id=user_id,
            session_id=session_id,
            event_type="page_view",
            event_properties={"page": random.choice(landing_pages), "title": "Home"},
            page_url=random.choice(landing_pages),
            referrer=random.choice(referrers),
            device_type=device_type,
            country=country,
            created_at=current_time,
            channel=channel,
            platform=platform,
            app_version=app_version,
        )
    )
    current_time += timedelta(seconds=random.randint(5, 30))

    # Browse loop
    products_viewed = []
    cart = []

    for _ in range(random.randint(1, 10)):
        action = random.choices(["search", "browse_category", "view_product"], [0.2, 0.3, 0.5])[0]

        if action == "search":
            query = fake.word()
            results = random.randint(0, 50)
            events.append(
                Event(
                    event_id=str(uuid4()),
                    user_id=user_id,
                    session_id=session_id,
                    event_type="search",
                    event_properties={"query": query, "results_count": results},
                    page_url=f"/search?q={query}",
                    referrer=events[-1].page_url if events else None,
                    device_type=device_type,
                    country=country,
                    created_at=current_time,
                    channel=channel,
                    platform=platform,
                    app_version=app_version,
                )
            )
        elif action == "browse_category":
            events.append(
                Event(
                    event_id=str(uuid4()),
                    user_id=user_id,
                    session_id=session_id,
                    event_type="page_view",
                    event_properties={"page": "/category", "title": "Category"},
                    page_url="/category/" + fake.word().lower(),
                    referrer=events[-1].page_url if events else None,
                    device_type=device_type,
                    country=country,
                    created_at=current_time,
                    channel=channel,
                    platform=platform,
                    app_version=app_version,
                )
            )
        else:  # view_product
            product = random.choice(products)
            products_viewed.append(product)
            events.append(
                Event(
                    event_id=str(uuid4()),
                    user_id=user_id,
                    session_id=session_id,
                    event_type="product_view",
                    event_properties={
                        "product_id": product.product_id,
                        "source": "browse",
                    },
                    page_url=f"/product/{product.product_id}",
                    referrer=events[-1].page_url if events else None,
                    device_type=device_type,
                    country=country,
                    created_at=current_time,
                    channel=channel,
                    platform=platform,
                    app_version=app_version,
                )
            )

            # Maybe add to cart (30% chance)
            if random.random() < 0.30:
                quantity = random.randint(1, 3)
                cart.append((product, quantity))
                current_time += timedelta(seconds=random.randint(10, 60))
                events.append(
                    Event(
                        event_id=str(uuid4()),
                        user_id=user_id,
                        session_id=session_id,
                        event_type="product_add_to_cart",
                        event_properties={
                            "product_id": product.product_id,
                            "quantity": quantity,
                        },
                        page_url=f"/product/{product.product_id}",
                        referrer=None,
                        device_type=device_type,
                        country=country,
                        created_at=current_time,
                        channel=channel,
                        platform=platform,
                        app_version=app_version,
                    )
                )

        current_time += timedelta(seconds=random.randint(20, 180))

    # Checkout flow (40% of carts proceed)
    if cart and random.random() < 0.40:
        cart_value = sum(float(p.price) * q for p, q in cart)

        # Checkout started
        events.append(
            Event(
                event_id=str(uuid4()),
                user_id=user_id,
                session_id=session_id,
                event_type="checkout_started",
                event_properties={"cart_value": cart_value, "item_count": len(cart)},
                page_url="/checkout",
                referrer="/cart",
                device_type=device_type,
                country=country,
                created_at=current_time,
                channel=channel,
                platform=platform,
                app_version=app_version,
            )
        )
        current_time += timedelta(seconds=random.randint(30, 120))

        # Checkout steps
        steps = ["shipping", "payment", "review"]
        for i, step in enumerate(steps, 1):
            events.append(
                Event(
                    event_id=str(uuid4()),
                    user_id=user_id,
                    session_id=session_id,
                    event_type="checkout_step",
                    event_properties={"step": i, "step_name": step},
                    page_url=f"/checkout/{step}",
                    referrer="/checkout",
                    device_type=device_type,
                    country=country,
                    created_at=current_time,
                    channel=channel,
                    platform=platform,
                    app_version=app_version,
                )
            )
            current_time += timedelta(seconds=random.randint(30, 90))

        # Complete checkout (60% complete)
        if random.random() < 0.60 and user:
            order_id = str(uuid4())
            subtotal = Decimal("0.00")
            items = []

            for product, quantity in cart:
                item = OrderItem(
                    order_item_id=str(uuid4()),
                    order_id=order_id,
                    product_id=product.product_id,
                    quantity=quantity,
                    unit_price=product.price,
                    created_at=current_time,
                )
                items.append(item)
                subtotal += product.price * quantity

            # Apply discount (20% of orders)
            discount = Decimal("0.00")
            if random.random() < 0.20:
                discount_pct = Decimal(str(round(random.uniform(0.05, 0.25), 2)))
                discount = (subtotal * discount_pct).quantize(Decimal("0.01"))

            # Shipping
            shipping = Decimal("5.99") if subtotal < Decimal("50.00") else Decimal("0.00")
            total = subtotal - discount + shipping

            order = Order(
                order_id=order_id,
                user_id=user.user_id,
                status="paid",
                total_amount=total,
                discount_amount=discount,
                shipping_cost=shipping,
                payment_method=random.choices(PAYMENT_METHODS, PAYMENT_WEIGHTS)[0],
                created_at=current_time,
                updated_at=current_time,
                channel=channel,
                platform=platform,
                app_version=app_version,
                session_id=session_id,
            )
            orders.append(order)
            order_items.extend(items)

            events.append(
                Event(
                    event_id=str(uuid4()),
                    user_id=user_id,
                    session_id=session_id,
                    event_type="checkout_completed",
                    event_properties={"order_id": order_id, "total": float(total)},
                    page_url="/checkout/confirmation",
                    referrer="/checkout/review",
                    device_type=device_type,
                    country=country,
                    created_at=current_time,
                    channel=channel,
                    platform=platform,
                    app_version=app_version,
                )
            )
        else:
            # Abandoned checkout
            events.append(
                Event(
                    event_id=str(uuid4()),
                    user_id=user_id,
                    session_id=session_id,
                    event_type="checkout_abandoned",
                    event_properties={"step": len(steps), "cart_value": cart_value},
                    page_url="/checkout",
                    referrer=None,
                    device_type=device_type,
                    country=country,
                    created_at=current_time,
                    channel=channel,
                    platform=platform,
                    app_version=app_version,
                )
            )

    return events, orders, order_items


def generate_daily_sessions(
    day: date,
    users: list[User],
    products: list[Product],
    target_events: int,
) -> tuple[list[Event], list[Order], list[OrderItem]]:
    """Generate all sessions for a single day."""
    all_events = []
    all_orders = []
    all_order_items = []

    # Estimate sessions needed (avg ~15 events per session)
    estimated_sessions = target_events // 15

    for _ in range(estimated_sessions):
        # 70% logged-in, 30% anonymous
        if random.random() < 0.70:
            user = random.choice(users)
        else:
            user = None

        session_start = random_timestamp_for_day(day)
        events, orders, items = generate_session_events(user, session_start, products)
        all_events.extend(events)
        all_orders.extend(orders)
        all_order_items.extend(items)

    return all_events, all_orders, all_order_items


# ==============================================================================
# MAIN GENERATION
# ==============================================================================


def generate_baseline_data() -> GeneratedData:
    """Generate clean baseline data with no anomalies."""
    print("Generating baseline data...")

    # Static seed data
    categories = generate_categories()
    print(f"  Generated {len(categories)} categories")

    products = generate_products(categories)
    print(f"  Generated {len(products)} products")

    users = generate_users()
    print(f"  Generated {len(users)} users")

    # Dynamic data per day
    all_events = []
    all_orders = []
    all_order_items = []

    # Daily variation in traffic
    daily_events_target = {
        0: 65_000,  # Mon
        1: 60_000,  # Tue
        2: 62_000,  # Wed
        3: 68_000,  # Thu
        4: 80_000,  # Fri
        5: 85_000,  # Sat
        6: 75_000,  # Sun
    }

    for day_offset in range(7):
        current_day = SIMULATION_START + timedelta(days=day_offset)
        day_of_week = current_day.weekday()
        target = daily_events_target.get(day_of_week, TARGET_EVENTS_PER_DAY)

        events, orders, items = generate_daily_sessions(current_day, users, products, target)
        all_events.extend(events)
        all_orders.extend(orders)
        all_order_items.extend(items)

        print(f"  Day {day_offset + 1} ({current_day}): {len(events)} events, {len(orders)} orders")

    return GeneratedData(
        categories=categories,
        products=products,
        users=users,
        orders=all_orders,
        order_items=all_order_items,
        events=all_events,
    )


# ==============================================================================
# ANOMALY INJECTION
# ==============================================================================


def get_day_number(dt: datetime) -> int:
    """Get 1-indexed day number from datetime."""
    return (dt.date() - SIMULATION_START).days + 1


def inject_null_spike(
    orders: list[Order],
    start_day: int = 3,
    end_day: int = 5,
    null_rate: float = 0.95,  # High rate for v2.3.1 bug - almost all affected
) -> tuple[list[Order], list[str]]:
    """
    Inject NULL values into orders.user_id for mobile app v2.3.1 only.

    Scenario: Mobile app v2.3.1 has a bug where the checkout API call
    doesn't include the user authentication token, causing NULL user_ids.
    This only affects mobile_app channel with app_version "2.3.1".
    Users on v2.3.0 or web are not affected.
    """
    modified = []
    affected_ids = []

    for order in orders:
        day = get_day_number(order.created_at)

        # Bug only affects mobile app v2.3.1 during the affected period
        is_buggy_version = (
            order.channel == "mobile_app"
            and order.app_version == "2.3.1"
            and start_day <= day <= end_day
        )

        if is_buggy_version and random.random() < null_rate:
            # Create new order with NULL user_id (bug doesn't pass auth token)
            modified.append(
                Order(
                    order_id=order.order_id,
                    user_id=None,  # Bug: auth token not passed
                    status=order.status,
                    total_amount=order.total_amount,
                    discount_amount=order.discount_amount,
                    shipping_cost=order.shipping_cost,
                    payment_method=order.payment_method,
                    created_at=order.created_at,
                    updated_at=order.updated_at,
                    channel=order.channel,
                    platform=order.platform,
                    app_version=order.app_version,
                    session_id=order.session_id,
                )
            )
            affected_ids.append(order.order_id)
        else:
            modified.append(order)

    return modified, affected_ids


def inject_volume_drop(
    events: list[Event],
    day: int = 5,
    drop_rate: float = 0.80,
) -> list[Event]:
    """
    Remove events to simulate tracking failure for EU users.

    Scenario: CDN misconfiguration blocked tracking pixel for EU users.
    """
    return [
        e
        for e in events
        if not (
            get_day_number(e.created_at) == day
            and e.country in EU_COUNTRIES
            and random.random() < drop_rate
        )
    ]


def inject_volume_drop_two_days(
    events: list[Event],
    start_day: int = 5,
    end_day: int = 6,
    drop_rate: float = 0.80,
) -> list[Event]:
    """
    Remove events for multiple days (days 5-6).

    Scenario: CDN misconfiguration blocked tracking pixel for EU users.
    """
    return [
        e
        for e in events
        if not (
            start_day <= get_day_number(e.created_at) <= end_day
            and e.country in EU_COUNTRIES
            and random.random() < drop_rate
        )
    ]


def inject_duplicates(
    order_items: list[OrderItem],
    day: int = 6,
    duplicate_rate: float = 0.15,
) -> tuple[list[OrderItem], list[str]]:
    """
    Duplicate order_items to simulate retry bug.

    Scenario: Retry logic doesn't check idempotency, network timeout caused duplicates.
    """
    result = []
    affected_order_ids = set()

    for item in order_items:
        result.append(item)

        if get_day_number(item.created_at) == day and random.random() < duplicate_rate:
            # Duplicate with new ID but same order_id/product_id
            duplicate = OrderItem(
                order_item_id=str(uuid4()),
                order_id=item.order_id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                created_at=item.created_at,
            )
            result.append(duplicate)
            affected_order_ids.add(item.order_id)

    return result, list(affected_order_ids)


def inject_late_arriving(
    events: list[Event],
    source_day: int = 2,
    arrival_day: int = 5,
    late_rate: float = 0.03,
) -> list[Event]:
    """
    Mark some events as late-arriving.

    Scenario: Mobile app queues events offline, batch uploaded after reconnect.
    """
    result = []

    for event in events:
        if get_day_number(event.created_at) == source_day and random.random() < late_rate:
            # Event created on day 2 but arrives on day 5
            arrival_time = datetime.combine(
                SIMULATION_START + timedelta(days=arrival_day - 1),
                datetime.min.time().replace(
                    hour=random.randint(8, 20), minute=random.randint(0, 59)
                ),
            )
            result.append(
                Event(
                    event_id=event.event_id,
                    user_id=event.user_id,
                    session_id=event.session_id,
                    event_type=event.event_type,
                    event_properties=event.event_properties,
                    page_url=event.page_url,
                    referrer=event.referrer,
                    device_type=event.device_type,
                    country=event.country,
                    created_at=event.created_at,
                    inserted_at=arrival_time,
                )
            )
        else:
            # Normal event - inserted_at equals created_at
            result.append(
                Event(
                    event_id=event.event_id,
                    user_id=event.user_id,
                    session_id=event.session_id,
                    event_type=event.event_type,
                    event_properties=event.event_properties,
                    page_url=event.page_url,
                    referrer=event.referrer,
                    device_type=event.device_type,
                    country=event.country,
                    created_at=event.created_at,
                    inserted_at=event.created_at,
                )
            )

    return result


def inject_orphaned_records(
    orders: list[Order],
    users: list[User],
    day: int = 4,
    orphan_rate: float = 0.08,
) -> tuple[list[Order], list[User], list[str]]:
    """
    Create orders referencing deleted users.

    Scenario: User deletion job ran before order archival job.
    """
    # Find user_ids from day 4 orders that will be orphaned
    users_to_delete = set()
    affected_order_ids = []

    for order in orders:
        if (
            get_day_number(order.created_at) == day
            and order.user_id
            and random.random() < orphan_rate
        ):
            users_to_delete.add(order.user_id)
            affected_order_ids.append(order.order_id)

    # Remove those users
    filtered_users = [u for u in users if u.user_id not in users_to_delete]

    return orders, filtered_users, affected_order_ids


def inject_schema_drift(products: list[Product], drift_rate: float = 0.28) -> list[dict[str, Any]]:
    """
    Simulate schema drift by returning products with mixed price types.

    ~28% of products have price as string with currency (simulating new import job).
    This returns a list of dicts to allow mixed types.
    """
    result = []

    for product in products:
        product_dict = {
            "product_id": product.product_id,
            "name": product.name,
            "category_id": product.category_id,
            "cost": float(product.cost),
            "stock_qty": product.stock_qty,
            "is_active": product.is_active,
            "created_at": product.created_at,
        }

        # ~28% of products have string price (from new import job)
        if random.random() < drift_rate:
            # String price with currency
            product_dict["price"] = f"{product.price} USD"
        else:
            product_dict["price"] = float(product.price)

        result.append(product_dict)

    return result


# ==============================================================================
# DATA EXPORT
# ==============================================================================


def data_to_dataframes(data: GeneratedData) -> dict[str, pl.DataFrame]:
    """Convert generated data to Polars DataFrames."""
    categories_df = pl.DataFrame(
        [
            {
                "category_id": c.category_id,
                "name": c.name,
                "parent_id": c.parent_id,
                "slug": c.slug,
            }
            for c in data.categories
        ]
    )

    products_df = pl.DataFrame(
        [
            {
                "product_id": p.product_id,
                "name": p.name,
                "category_id": p.category_id,
                "price": float(p.price),
                "cost": float(p.cost),
                "stock_qty": p.stock_qty,
                "is_active": p.is_active,
                "created_at": p.created_at,
            }
            for p in data.products
        ]
    )

    users_df = pl.DataFrame(
        [
            {
                "user_id": u.user_id,
                "email": u.email,
                "created_at": u.created_at,
                "country": u.country,
                "device_type": u.device_type,
                "is_premium": u.is_premium,
                "lifetime_value": float(u.lifetime_value),
            }
            for u in data.users
        ]
    )

    orders_df = pl.DataFrame(
        [
            {
                "order_id": o.order_id,
                "user_id": o.user_id,
                "status": o.status,
                "total_amount": float(o.total_amount),
                "discount_amount": float(o.discount_amount),
                "shipping_cost": float(o.shipping_cost),
                "payment_method": o.payment_method,
                "created_at": o.created_at,
                "updated_at": o.updated_at,
            }
            for o in data.orders
        ]
    )

    order_items_df = pl.DataFrame(
        [
            {
                "order_item_id": oi.order_item_id,
                "order_id": oi.order_id,
                "product_id": oi.product_id,
                "quantity": oi.quantity,
                "unit_price": float(oi.unit_price),
                "created_at": oi.created_at,
            }
            for oi in data.order_items
        ]
    )

    events_df = pl.DataFrame(
        [
            {
                "event_id": e.event_id,
                "user_id": e.user_id,
                "session_id": e.session_id,
                "event_type": e.event_type,
                "event_properties": json.dumps(e.event_properties),
                "page_url": e.page_url,
                "referrer": e.referrer,
                "device_type": e.device_type,
                "country": e.country,
                "created_at": e.created_at,
                "inserted_at": e.inserted_at if e.inserted_at else e.created_at,
            }
            for e in data.events
        ]
    )

    return {
        "categories": categories_df,
        "products": products_df,
        "users": users_df,
        "orders": orders_df,
        "order_items": order_items_df,
        "events": events_df,
    }


def write_parquet_files(dataframes: dict[str, pl.DataFrame], output_dir: Path) -> dict[str, int]:
    """Write DataFrames to Parquet files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    row_counts = {}

    for name, df in dataframes.items():
        file_path = output_dir / f"{name}.parquet"
        df.write_parquet(file_path, compression="snappy")
        row_counts[name] = len(df)
        print(f"    Wrote {name}.parquet ({len(df):,} rows)")

    return row_counts


def create_manifest(
    name: str,
    description: str,
    row_counts: dict[str, int],
    anomalies: list[dict[str, Any]],
    ground_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create manifest.json for a fixture."""
    return {
        "name": name,
        "description": description,
        "created_at": datetime.now(tz=None).isoformat() + "Z",
        "simulation_period": {
            "start": SIMULATION_START.isoformat(),
            "end": SIMULATION_END.isoformat(),
        },
        "tables": {
            table: {"row_count": count, "file": f"{table}.parquet"}
            for table, count in row_counts.items()
        },
        "anomalies": anomalies,
        "ground_truth": ground_truth or {},
    }


# ==============================================================================
# FIXTURE GENERATION
# ==============================================================================


def generate_all_fixtures():
    """Generate all fixture sets."""
    print("=" * 60)
    print("Dataing Demo Fixtures Generator")
    print("=" * 60)

    # Generate baseline data
    baseline_data = generate_baseline_data()
    baseline_dfs = data_to_dataframes(baseline_data)

    # 1. Baseline (clean data)
    print("\n[1/7] Writing baseline fixture...")
    baseline_dir = OUTPUT_DIR / "baseline"
    row_counts = write_parquet_files(baseline_dfs, baseline_dir)
    manifest = create_manifest(
        "baseline",
        "Clean e-commerce data with no anomalies",
        row_counts,
        [],
    )
    with open(baseline_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # 2. NULL Spike
    print("\n[2/7] Writing null_spike fixture...")
    null_spike_orders, affected_ids = inject_null_spike(baseline_data.orders)
    null_spike_data = GeneratedData(
        categories=baseline_data.categories,
        products=baseline_data.products,
        users=baseline_data.users,
        orders=null_spike_orders,
        order_items=baseline_data.order_items,
        events=baseline_data.events,
    )
    null_spike_dfs = data_to_dataframes(null_spike_data)
    null_spike_dir = OUTPUT_DIR / "null_spike"
    row_counts = write_parquet_files(null_spike_dfs, null_spike_dir)
    manifest = create_manifest(
        "null_spike",
        "Mobile app bug causes NULL user_id in orders",
        row_counts,
        [
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
                    "confidence": 0.95,
                },
                "investigation_hints": {
                    "differentiating_queries": [
                        "GROUP BY channel to see mobile_app vs web NULL rates",
                        "GROUP BY app_version to see v2.3.1 vs v2.3.0 NULL rates",
                        "GROUP BY platform to see ios vs android patterns",
                        "JOIN events ON session_id to correlate with app behavior",
                    ],
                    "smoking_gun": (
                        "NULLs occur almost exclusively on channel='mobile_app' "
                        "AND app_version='2.3.1'. Web and v2.3.0 users unaffected."
                    ),
                    "schema_columns": ["channel", "platform", "app_version", "session_id"],
                },
            }
        ],
        {"affected_order_ids": affected_ids[:100], "affected_row_count": len(affected_ids)},
    )
    with open(null_spike_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # 3. Volume Drop
    print("\n[3/7] Writing volume_drop fixture...")
    volume_drop_events = inject_volume_drop_two_days(baseline_data.events)
    volume_drop_data = GeneratedData(
        categories=baseline_data.categories,
        products=baseline_data.products,
        users=baseline_data.users,
        orders=baseline_data.orders,
        order_items=baseline_data.order_items,
        events=volume_drop_events,
    )
    volume_drop_dfs = data_to_dataframes(volume_drop_data)
    volume_drop_dir = OUTPUT_DIR / "volume_drop"
    row_counts = write_parquet_files(volume_drop_dfs, volume_drop_dir)
    events_dropped = len(baseline_data.events) - len(volume_drop_events)
    manifest = create_manifest(
        "volume_drop",
        "CDN misconfiguration blocked tracking pixel for EU users",
        row_counts,
        [
            {
                "type": "volume_drop",
                "table": "events",
                "column": None,
                "start_day": 5,
                "end_day": 6,
                "severity": 0.80,
                "root_cause": "CDN misconfiguration blocked tracking pixel for EU countries",
                "expected_detection": {
                    "pattern_type": "VOLUME_DROP",
                    "confidence": 0.95,
                },
            }
        ],
        {"events_dropped": events_dropped, "affected_countries": EU_COUNTRIES},
    )
    with open(volume_drop_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # 4. Schema Drift
    print("\n[4/7] Writing schema_drift fixture...")
    # For schema drift, we need special handling - write products with mixed types
    schema_drift_products = inject_schema_drift(baseline_data.products)
    schema_drift_dir = OUTPUT_DIR / "schema_drift"
    schema_drift_dir.mkdir(parents=True, exist_ok=True)

    # Write other tables normally
    for name, df in baseline_dfs.items():
        if name != "products":
            df.write_parquet(schema_drift_dir / f"{name}.parquet", compression="snappy")
            print(f"    Wrote {name}.parquet ({len(df):,} rows)")

    # Write products with mixed price types (as strings to preserve format)
    products_df = pl.DataFrame(schema_drift_products)
    # Cast price to string to show the anomaly
    products_df = products_df.with_columns(pl.col("price").cast(pl.Utf8).alias("price"))
    products_df.write_parquet(schema_drift_dir / "products.parquet", compression="snappy")
    print(f"    Wrote products.parquet ({len(products_df):,} rows)")

    row_counts = {name: len(df) for name, df in baseline_dfs.items()}
    row_counts["products"] = len(products_df)

    string_prices = sum(1 for p in schema_drift_products if isinstance(p["price"], str))
    manifest = create_manifest(
        "schema_drift",
        "New product import job inserts price as string with currency",
        row_counts,
        [
            {
                "type": "schema_drift",
                "table": "products",
                "column": "price",
                "start_day": 4,
                "severity": 0.28,
                "root_cause": "New product import job doesn't cast types properly",
                "expected_detection": {
                    "pattern_type": "SCHEMA_DRIFT",
                    "confidence": 0.90,
                },
            }
        ],
        {"string_price_count": string_prices, "total_products": len(schema_drift_products)},
    )
    with open(schema_drift_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # 5. Duplicates
    print("\n[5/7] Writing duplicates fixture...")
    dup_order_items, affected_order_ids = inject_duplicates(baseline_data.order_items)
    duplicates_data = GeneratedData(
        categories=baseline_data.categories,
        products=baseline_data.products,
        users=baseline_data.users,
        orders=baseline_data.orders,
        order_items=dup_order_items,
        events=baseline_data.events,
    )
    duplicates_dfs = data_to_dataframes(duplicates_data)
    duplicates_dir = OUTPUT_DIR / "duplicates"
    row_counts = write_parquet_files(duplicates_dfs, duplicates_dir)
    manifest = create_manifest(
        "duplicates",
        "Retry logic creates duplicate order_items",
        row_counts,
        [
            {
                "type": "duplicates",
                "table": "order_items",
                "column": "(order_id, product_id)",
                "day": 6,
                "severity": 0.15,
                "root_cause": "Retry logic doesn't check for idempotency",
                "expected_detection": {
                    "pattern_type": "DUPLICATES",
                    "confidence": 0.95,
                },
            }
        ],
        {
            "affected_order_ids": affected_order_ids[:50],
            "affected_order_count": len(affected_order_ids),
            "duplicate_items": len(dup_order_items) - len(baseline_data.order_items),
        },
    )
    with open(duplicates_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # 6. Late Arriving
    print("\n[6/7] Writing late_arriving fixture...")
    late_events = inject_late_arriving(baseline_data.events)
    late_data = GeneratedData(
        categories=baseline_data.categories,
        products=baseline_data.products,
        users=baseline_data.users,
        orders=baseline_data.orders,
        order_items=baseline_data.order_items,
        events=late_events,
    )
    late_dfs = data_to_dataframes(late_data)
    late_dir = OUTPUT_DIR / "late_arriving"
    row_counts = write_parquet_files(late_dfs, late_dir)

    # Count late arrivals
    late_count = sum(
        1
        for e in late_events
        if e.inserted_at and e.created_at and e.inserted_at.date() != e.created_at.date()
    )

    manifest = create_manifest(
        "late_arriving",
        "Mobile app queues events offline, batch uploaded later",
        row_counts,
        [
            {
                "type": "late_arriving",
                "table": "events",
                "column": "created_at vs inserted_at",
                "source_day": 2,
                "arrival_day": 5,
                "severity": 0.03,
                "root_cause": "Mobile app queues events offline",
                "expected_detection": {
                    "pattern_type": "LATE_ARRIVING",
                    "confidence": 0.85,
                },
            }
        ],
        {"late_event_count": late_count},
    )
    with open(late_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # 7. Orphaned Records
    print("\n[7/7] Writing orphaned_records fixture...")
    orphan_orders, orphan_users, affected_ids = inject_orphaned_records(
        baseline_data.orders, baseline_data.users
    )
    orphan_data = GeneratedData(
        categories=baseline_data.categories,
        products=baseline_data.products,
        users=orphan_users,
        orders=orphan_orders,
        order_items=baseline_data.order_items,
        events=baseline_data.events,
    )
    orphan_dfs = data_to_dataframes(orphan_data)
    orphan_dir = OUTPUT_DIR / "orphaned_records"
    row_counts = write_parquet_files(orphan_dfs, orphan_dir)
    manifest = create_manifest(
        "orphaned_records",
        "User deletion job ran before order archival",
        row_counts,
        [
            {
                "type": "orphaned_records",
                "table": "orders",
                "column": "user_id",
                "day": 4,
                "severity": 0.08,
                "root_cause": "User deletion job ran before order archival job",
                "expected_detection": {
                    "pattern_type": "REFERENTIAL_INTEGRITY",
                    "confidence": 0.95,
                },
            }
        ],
        {
            "affected_order_ids": affected_ids[:50],
            "orphaned_order_count": len(affected_ids),
            "deleted_user_count": len(baseline_data.users) - len(orphan_users),
        },
    )
    with open(orphan_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print("\n" + "=" * 60)
    print("All fixtures generated successfully!")
    print(f"Output directory: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    generate_all_fixtures()
