
import pytest
from dataing.adapters.db.app_db import AppDatabase

@pytest.mark.asyncio
async def test_simple_query():
    db = AppDatabase(dsn="postgresql://dataing:dataing@localhost:5432/dataing_demo")
    await db.connect()
    try:
        val = await db.fetch_one("SELECT 1 as val")
        assert val["val"] == 1
    finally:
        await db.close()
