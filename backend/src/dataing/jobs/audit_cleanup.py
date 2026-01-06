"""Audit log cleanup job.

Run via: python -m dataing.jobs.audit_cleanup
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import asyncpg
import structlog

from dataing.adapters.audit import AuditRepository

logger = structlog.get_logger()

RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "730"))  # 2 years


async def main() -> None:
    """Run audit log cleanup."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return

    logger.info("Connecting to database...")
    pool = await asyncpg.create_pool(database_url)

    if pool is None:
        logger.error("Failed to create database pool")
        return

    try:
        repo = AuditRepository(pool=pool)
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)

        logger.info(f"Deleting audit logs older than {cutoff.isoformat()}")
        count = await repo.delete_before(cutoff)

        logger.info(f"Deleted {count} audit log entries")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
