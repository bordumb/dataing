"""Demo seed data.

Run with: python -m dataing.demo.seed
Or automatically on startup when DATADR_DEMO_MODE=true
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dataing.models.api_key import ApiKey
from dataing.models.data_source import DataSource, DataSourceType
from dataing.models.tenant import Tenant

logger = logging.getLogger(__name__)

# Demo IDs - stable UUIDs for idempotent seeding
DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEMO_API_KEY_ID = UUID("00000000-0000-0000-0000-000000000002")
DEMO_DATASOURCE_ID = UUID("00000000-0000-0000-0000-000000000003")

# Demo API key (for testing)
DEMO_API_KEY_VALUE = "dd_demo_12345"
DEMO_API_KEY_PREFIX = "dd_demo_"
DEMO_API_KEY_HASH = hashlib.sha256(DEMO_API_KEY_VALUE.encode()).hexdigest()

# Default fixture path (relative to repo root)
DEFAULT_FIXTURE_PATH = "./demo/fixtures/null_spike"


def get_fixture_path() -> str:
    """Get the fixture path from environment or use default."""
    return os.getenv("DATADR_FIXTURE_PATH", DEFAULT_FIXTURE_PATH)


def get_encryption_key() -> bytes:
    """Get encryption key for connection config.

    In demo mode, uses a hardcoded key. In production, should come from env.
    """
    demo_key = os.getenv("DATADR_ENCRYPTION_KEY")
    if demo_key:
        return demo_key.encode()
    # Generate a demo key (in production, this should be a real secret)
    return Fernet.generate_key()


async def seed_demo_data(session: AsyncSession) -> None:
    """Seed demo data if not already present.

    Idempotent - safe to run multiple times.

    Args:
        session: SQLAlchemy async session.
    """
    # Check if already seeded
    result = await session.execute(select(Tenant).where(Tenant.id == DEMO_TENANT_ID))
    existing_tenant = result.scalar_one_or_none()

    if existing_tenant:
        logger.info("Demo data already seeded, skipping")
        return

    logger.info("Seeding demo data...")

    # Create demo tenant
    tenant = Tenant(
        id=DEMO_TENANT_ID,
        name="Demo Account",
        slug="demo",
        settings={"plan_tier": "enterprise"},
    )
    session.add(tenant)

    # Create demo API key
    api_key = ApiKey(
        id=DEMO_API_KEY_ID,
        tenant_id=DEMO_TENANT_ID,
        key_hash=DEMO_API_KEY_HASH,
        key_prefix=DEMO_API_KEY_PREFIX,
        name="Demo API Key",
        scopes=["read", "write", "admin"],
        is_active=True,
    )
    session.add(api_key)

    # Create demo data source (DuckDB pointing to fixtures)
    fixture_path = get_fixture_path()
    encryption_key = get_encryption_key()

    # For DuckDB, the config just needs the path
    connection_config = {
        "path": fixture_path,
        "read_only": True,
    }

    encrypted_config = DataSource.encrypt_connection_config(connection_config, encryption_key)

    data_source = DataSource(
        id=DEMO_DATASOURCE_ID,
        tenant_id=DEMO_TENANT_ID,
        name="E-Commerce Demo",
        type=DataSourceType.DUCKDB,
        connection_config_encrypted=encrypted_config,
        is_default=True,
        is_active=True,
        last_health_check_status="healthy",
    )
    session.add(data_source)

    await session.commit()

    logger.info("Demo data seeded successfully")
    logger.info(f"  Tenant: {tenant.name} (id: {tenant.id})")
    logger.info(f"  API Key: {DEMO_API_KEY_VALUE}")
    logger.info(f"  Data Source: {data_source.name} (path: {fixture_path})")


async def verify_demo_fixtures() -> bool:
    """Verify that demo fixtures exist.

    Returns:
        True if fixtures exist, False otherwise.
    """
    fixture_path = Path(get_fixture_path())

    if not fixture_path.exists():
        logger.warning(f"Demo fixtures not found at: {fixture_path}")
        return False

    # Check for required parquet files
    required_files = ["orders.parquet", "users.parquet", "events.parquet"]
    for filename in required_files:
        if not (fixture_path / filename).exists():
            logger.warning(f"Missing fixture file: {filename}")
            return False

    logger.info(f"Demo fixtures verified at: {fixture_path}")
    return True


if __name__ == "__main__":
    """Allow running seed script directly for testing."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def main() -> None:
        """Run demo seeding with a temporary database session."""
        # Get database URL from env
        db_url = os.getenv(
            "DATADR_DB_URL", "postgresql+asyncpg://datadr:datadr@localhost:5432/datadr_demo"
        )

        engine = create_async_engine(db_url)
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            await seed_demo_data(session)

    asyncio.run(main())
