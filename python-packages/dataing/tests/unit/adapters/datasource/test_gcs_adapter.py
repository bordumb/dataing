"""Tests for how the GCS adapter authenticates to Google Cloud Storage.

connect() installs DuckDB's httpfs extension, so the tests that connect skip when it
cannot be downloaded. Reading objects needs a real bucket, so the tests check the
secret the connection holds rather than fetching data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import duckdb
import pytest

from dataing.adapters.datasource.errors import MissingRequiredFieldError
from dataing.adapters.datasource.filesystem.gcs import GCS_CONFIG_SCHEMA, GCSAdapter

HMAC_ACCESS_ID = "GOOG1EEXAMPLEACCESSID"
HMAC_SECRET = "example-hmac-secret"


@pytest.fixture(scope="module")
def httpfs() -> None:
    """Skip when DuckDB's httpfs extension is unavailable (e.g. offline)."""
    conn = duckdb.connect()
    try:
        conn.execute("INSTALL httpfs")
        conn.execute("LOAD httpfs")
    except duckdb.Error as e:
        pytest.skip(f"DuckDB httpfs extension unavailable: {e}")
    finally:
        conn.close()


def gcs_config(prefix: str = "warehouse/") -> dict[str, Any]:
    """GCS source config for the acme-data bucket."""
    return {
        "bucket": "acme-data",
        "prefix": prefix,
        "hmac_access_id": HMAC_ACCESS_ID,
        "hmac_secret": HMAC_SECRET,
    }


async def secret_offered(adapter: GCSAdapter, path: str) -> bool:
    """Whether DuckDB would authenticate a request for ``path`` with a stored secret."""
    result = await adapter.execute_query(f"SELECT name FROM which_secret('{path}', 'gcs')")
    return result.row_count == 1


@pytest.fixture
async def adapter(httpfs: None) -> AsyncIterator[GCSAdapter]:
    """A connected adapter for gs://acme-data/warehouse/."""
    gcs = GCSAdapter(gcs_config())
    await gcs.connect()
    yield gcs
    await gcs.disconnect()


class TestGCSConfigSchema:
    """The connection form asks for the credential the adapter uses."""

    def test_asks_for_an_hmac_key(self) -> None:
        """Sources authenticate with an HMAC key, not a service account JSON file."""
        fields = {field.name: field for field in GCS_CONFIG_SCHEMA.fields}

        assert fields["hmac_access_id"].required
        assert fields["hmac_secret"].required
        assert fields["hmac_secret"].type == "secret"
        assert "credentials_json" not in fields


class TestGCSAdapterCredentials:
    """connect() stores the HMAC key as a DuckDB secret scoped to the source."""

    async def test_connect_stores_the_hmac_key_as_a_gcs_secret(self, adapter: GCSAdapter) -> None:
        """The connection holds one GCS secret, keyed by the configured access ID."""
        result = await adapter.execute_query("SELECT type, secret_string FROM duckdb_secrets()")

        assert result.row_count == 1
        assert result.rows[0]["type"] == "gcs"
        assert f"key_id={HMAC_ACCESS_ID};" in result.rows[0]["secret_string"]

    @pytest.mark.parametrize(
        ("prefix", "location"),
        [
            ("warehouse/", "gs://acme-data/warehouse/"),
            ("/warehouse", "gs://acme-data/warehouse/"),
            ("", "gs://acme-data/"),
        ],
    )
    async def test_secret_is_scoped_to_the_configured_prefix(
        self, httpfs: None, prefix: str, location: str
    ) -> None:
        """The secret's scope is the source's bucket prefix."""
        gcs = GCSAdapter(gcs_config(prefix))
        await gcs.connect()
        try:
            result = await gcs.execute_query("SELECT scope FROM duckdb_secrets()")
        finally:
            await gcs.disconnect()

        assert result.rows == [{"scope": [location]}]

    async def test_credentials_are_only_offered_for_the_prefix(self, adapter: GCSAdapter) -> None:
        """DuckDB picks the key for paths under the prefix and for no other path."""
        assert await secret_offered(adapter, "gs://acme-data/warehouse/orders.csv")
        assert await secret_offered(adapter, "gs://acme-data/warehouse/2024/01/orders.parquet")
        assert not await secret_offered(adapter, "gs://acme-data/finance/salaries.csv")
        assert not await secret_offered(adapter, "gs://acme-data/warehouse-archive/orders.csv")
        assert not await secret_offered(adapter, "gs://other-bucket/warehouse/orders.csv")

    async def test_secret_cannot_be_read_back(self, adapter: GCSAdapter) -> None:
        """Neither current settings nor duckdb_secrets() return the HMAC secret."""
        settings = await adapter.execute_query("SELECT name, value FROM duckdb_settings()")
        s3_secret = await adapter.execute_query(
            "SELECT current_setting('s3_secret_access_key') AS value"
        )
        secrets = await adapter.execute_query("SELECT * FROM duckdb_secrets()")

        assert secrets.row_count == 1
        assert HMAC_SECRET not in str(settings.rows)
        assert HMAC_SECRET not in str(s3_secret.rows)
        assert HMAC_SECRET not in str(secrets.rows)
        with pytest.raises(duckdb.InvalidInputException, match="unredacted secrets is disabled"):
            await adapter.execute_query("SELECT * FROM duckdb_secrets(redact=false)")

    @pytest.mark.parametrize("field", ["hmac_access_id", "hmac_secret"])
    async def test_connect_requires_both_parts_of_the_hmac_key(self, field: str) -> None:
        """A missing access ID or secret is rejected, naming the missing field."""
        config = gcs_config()
        config[field] = ""

        with pytest.raises(MissingRequiredFieldError) as excinfo:
            await GCSAdapter(config).connect()

        assert excinfo.value.details == {"field": field}
