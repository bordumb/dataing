"""Data source related fixtures."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def sample_data_source_id() -> uuid.UUID:
    """Return a sample data source UUID."""
    return uuid.UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def sample_data_source(
    sample_tenant_id: uuid.UUID,
    sample_data_source_id: uuid.UUID,
) -> dict:
    """Return a sample data source record."""
    return {
        "id": sample_data_source_id,
        "tenant_id": sample_tenant_id,
        "name": "Test PostgreSQL",
        "type": "postgres",
        "connection_config_encrypted": "encrypted_connection_string",
        "is_default": True,
        "is_active": True,
        "last_health_check_at": datetime.now(timezone.utc),
        "last_health_check_status": "healthy",
        "created_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_investigation_id() -> uuid.UUID:
    """Return a sample investigation UUID."""
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def sample_investigation_record(
    sample_tenant_id: uuid.UUID,
    sample_investigation_id: uuid.UUID,
    sample_data_source_id: uuid.UUID,
) -> dict:
    """Return a sample investigation database record."""
    return {
        "id": sample_investigation_id,
        "tenant_id": sample_tenant_id,
        "data_source_id": sample_data_source_id,
        "created_by": None,
        "dataset_id": "public.orders",
        "metric_name": "row_count",
        "expected_value": 1000.0,
        "actual_value": 500.0,
        "deviation_pct": 50.0,
        "anomaly_date": "2024-01-15",
        "severity": "high",
        "metadata": {},
        "status": "pending",
        "events": [],
        "finding": None,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "created_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_webhook_id() -> uuid.UUID:
    """Return a sample webhook UUID."""
    return uuid.UUID("cccccccc-dddd-eeee-ffff-000000000000")


@pytest.fixture
def sample_webhook_record(
    sample_tenant_id: uuid.UUID,
    sample_webhook_id: uuid.UUID,
) -> dict:
    """Return a sample webhook database record."""
    return {
        "id": sample_webhook_id,
        "tenant_id": sample_tenant_id,
        "url": "https://example.com/webhook",
        "secret": "webhook_secret_123",
        "events": ["investigation.completed", "investigation.failed"],
        "is_active": True,
        "last_triggered_at": None,
        "last_status": None,
        "created_at": datetime.now(timezone.utc),
    }
