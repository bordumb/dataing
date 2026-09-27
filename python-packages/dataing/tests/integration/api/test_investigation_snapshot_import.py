"""Integration tests for POST /investigations/import on the migrated schema."""

from __future__ import annotations

import json
import shutil
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.snapshot_builder import SnapshotBuilder
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.investigations import get_app_db, router

pytestmark = pytest.mark.integration


async def _create_tenant(db: AppDatabase) -> UUID:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    return tenant_id


async def _export_archive(investigation_id: UUID, status: str) -> bytes:
    """Build an archive the way GET /investigations/{id}/snapshot does."""
    archive_path = await SnapshotBuilder(str(investigation_id)).build(
        investigation_state={"status": status, "source_instance": None, "tenant_id": None},
        evidence_items=[],
    )
    try:
        return archive_path.read_bytes()
    finally:
        shutil.rmtree(archive_path.parent)


async def _import_archive(db: AppDatabase, tenant_id: UUID, archive: bytes) -> httpx.Response:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: db
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="test",
        tenant_name="Test Tenant",
        user_id=None,
        scopes=["write"],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/v1/investigations/import",
            files={"file": ("snapshot.tar.gz", archive, "application/gzip")},
        )


async def test_import_stores_the_archive_as_a_completed_replay(migrated_db: AppDatabase) -> None:
    """An exported archive imports as a new, completed replay of the original."""
    tenant_id = await _create_tenant(migrated_db)
    original_id = uuid4()
    archive = await _export_archive(original_id, status="completed")

    response = await _import_archive(migrated_db, tenant_id, archive)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "investigation_id": body["investigation_id"],
        "status": "imported",
        "original_investigation_id": str(original_id),
        "evidence_count": 0,
        "is_replay": True,
    }
    row = await migrated_db.fetch_one(
        "SELECT tenant_id, status, outcome FROM investigations WHERE id = $1",
        UUID(body["investigation_id"]),
    )
    assert row is not None
    assert row["tenant_id"] == tenant_id
    assert row["status"] == "completed"
    outcome = json.loads(row["outcome"])
    assert outcome["status"] == "completed"
    assert outcome["is_replay"] is True
    assert outcome["original_investigation_id"] == str(original_id)
