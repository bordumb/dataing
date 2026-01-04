"""Tests for the lineage adapter registry."""

import pytest

from dataing.adapters.lineage import (
    DatasetId,
    LineageProviderType,
    get_lineage_registry,
)
from dataing.adapters.lineage.exceptions import LineageProviderNotFoundError


def test_registry_has_all_providers():
    """Test that all expected providers are registered."""
    registry = get_lineage_registry()

    expected = [
        LineageProviderType.DBT,
        LineageProviderType.OPENLINEAGE,
        LineageProviderType.AIRFLOW,
        LineageProviderType.DAGSTER,
        LineageProviderType.DATAHUB,
        LineageProviderType.STATIC_SQL,
    ]

    for provider in expected:
        assert registry.is_registered(provider), f"Provider {provider} not registered"


def test_registry_list_providers():
    """Test listing all providers."""
    registry = get_lineage_registry()
    providers = registry.list_providers()

    assert len(providers) >= 6
    assert all(p.provider_type in LineageProviderType for p in providers)


def test_registry_get_definition():
    """Test getting provider definitions."""
    registry = get_lineage_registry()

    dbt_def = registry.get_definition(LineageProviderType.DBT)
    assert dbt_def is not None
    assert dbt_def.display_name == "dbt"
    assert dbt_def.capabilities.supports_column_lineage is True


def test_registry_create_adapter():
    """Test creating an adapter from registry."""
    registry = get_lineage_registry()

    # Create dbt adapter
    adapter = registry.create("dbt", {
        "manifest_path": "/path/to/manifest.json",
        "target_platform": "snowflake",
    })

    assert adapter is not None
    assert adapter.provider_info.provider == LineageProviderType.DBT


def test_registry_create_unknown_provider():
    """Test that creating unknown provider raises error."""
    registry = get_lineage_registry()

    with pytest.raises(LineageProviderNotFoundError):
        registry.create("unknown_provider", {})


def test_dataset_id_from_urn():
    """Test parsing DatasetId from URN strings."""
    # Simple format
    ds1 = DatasetId.from_urn("snowflake://db.schema.table")
    assert ds1.platform == "snowflake"
    assert ds1.name == "db.schema.table"

    # DataHub format
    ds2 = DatasetId.from_urn(
        "urn:li:dataset:(urn:li:dataPlatform:postgres,mydb.public.users,PROD)"
    )
    assert ds2.platform == "postgres"
    assert ds2.name == "mydb.public.users"

    # Simple name
    ds3 = DatasetId.from_urn("my_table")
    assert ds3.platform == "unknown"
    assert ds3.name == "my_table"


def test_dataset_id_str():
    """Test DatasetId string representation."""
    ds = DatasetId(platform="snowflake", name="analytics.public.orders")
    assert str(ds) == "snowflake://analytics.public.orders"
