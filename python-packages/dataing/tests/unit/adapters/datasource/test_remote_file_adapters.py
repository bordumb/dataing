"""File access tests for the S3, GCS and HDFS adapters.

These adapters run queries through DuckDB's httpfs extension. connect() installs it, so
the tests skip when it cannot be downloaded. Reading the source's own objects needs a
real bucket, so the tests check what is refused and which location the connection is
confined to. test_duckdb_sandbox.py covers reads under an allowed URL prefix.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from dataing.adapters.datasource import duckdb_sandbox
from dataing.adapters.datasource.filesystem.gcs import GCSAdapter
from dataing.adapters.datasource.filesystem.hdfs import HDFSAdapter
from dataing.adapters.datasource.filesystem.s3 import S3Adapter

SECRET_KEY = "example-secret-access-key"


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


@pytest.fixture
def confined_to(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record the locations adapters confine their connections to."""
    calls: list[list[str]] = []
    confine = duckdb_sandbox.confine

    def recording_confine(conn: Any, *, directories: Sequence[str]) -> None:
        calls.append(list(directories))
        confine(conn, directories=directories)

    monkeypatch.setattr(duckdb_sandbox, "confine", recording_confine)
    return calls


@pytest.fixture
def boto3_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Stub boto3 so S3Adapter.connect() does not call AWS."""
    import boto3

    client = MagicMock()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    yield client


def s3_config(prefix: str) -> dict[str, Any]:
    """S3 source config for the acme-data bucket."""
    return {
        "bucket": "acme-data",
        "prefix": prefix,
        "region": "us-east-1",
        "access_key_id": "AKIAEXAMPLEKEYID",
        "secret_access_key": SECRET_KEY,
    }


class TestS3AdapterFileAccess:
    """An S3 source reads its own bucket prefix and nothing else."""

    @pytest.fixture
    async def adapter(
        self, httpfs: None, boto3_client: MagicMock, confined_to: list[list[str]]
    ) -> AsyncIterator[S3Adapter]:
        """A connected adapter for s3://acme-data/warehouse/."""
        s3 = S3Adapter(s3_config("warehouse/"))
        await s3.connect()
        yield s3
        await s3.disconnect()

    @pytest.mark.parametrize(
        ("prefix", "location"),
        [
            ("warehouse/", "s3://acme-data/warehouse/"),
            ("/warehouse", "s3://acme-data/warehouse/"),
            ("", "s3://acme-data/"),
        ],
    )
    async def test_confined_to_the_configured_prefix(
        self,
        httpfs: None,
        boto3_client: MagicMock,
        confined_to: list[list[str]],
        prefix: str,
        location: str,
    ) -> None:
        """The bucket prefix is the one readable location."""
        s3 = S3Adapter(s3_config(prefix))
        await s3.connect()
        await s3.disconnect()
        assert confined_to == [[location]]

    @pytest.mark.parametrize(
        "path",
        [
            "/etc/passwd",
            "s3://other-bucket/warehouse/orders.csv",
            "s3://acme-data/finance/salaries.csv",
            "s3://acme-data/warehouse/../finance/salaries.csv",
            "https://acme-data.s3.amazonaws.com/finance/salaries.csv",
        ],
    )
    async def test_refuses_paths_outside_the_prefix(self, adapter: S3Adapter, path: str) -> None:
        """Host files, other buckets and other prefixes are refused."""
        with pytest.raises(duckdb.PermissionException):
            await adapter.execute_query(f"SELECT * FROM read_csv('{path}') LIMIT 10")

    async def test_credentials_are_only_offered_for_the_prefix(self, adapter: S3Adapter) -> None:
        """The stored keys are scoped to the source's prefix."""
        own = await adapter.execute_query(
            "SELECT name FROM which_secret('s3://acme-data/warehouse/orders.csv', 's3')"
        )
        other = await adapter.execute_query(
            "SELECT name FROM which_secret('s3://other-bucket/orders.csv', 's3')"
        )
        assert own.row_count == 1
        assert other.row_count == 0

    async def test_secret_key_cannot_be_read_back(self, adapter: S3Adapter) -> None:
        """A query cannot return the stored secret access key."""
        result = await adapter.execute_query(
            "SELECT current_setting('s3_secret_access_key') AS setting, "
            "(SELECT string_agg(secret_string, ';') FROM duckdb_secrets()) AS secrets"
        )
        assert SECRET_KEY not in str(result.rows)


class TestGCSAdapterFileAccess:
    """A GCS source reads its own bucket prefix and nothing else."""

    @pytest.fixture
    async def adapter(
        self, httpfs: None, confined_to: list[list[str]]
    ) -> AsyncIterator[GCSAdapter]:
        """A connected adapter for gs://acme-data/warehouse/."""
        gcs = GCSAdapter(
            {
                "bucket": "acme-data",
                "prefix": "warehouse",
                "hmac_access_id": "GOOG1EEXAMPLEACCESSID",
                "hmac_secret": SECRET_KEY,
            }
        )
        await gcs.connect()
        yield gcs
        await gcs.disconnect()

    async def test_confined_to_the_configured_prefix(
        self, adapter: GCSAdapter, confined_to: list[list[str]]
    ) -> None:
        """The bucket prefix is the one readable location."""
        assert confined_to == [["gs://acme-data/warehouse/"]]

    @pytest.mark.parametrize(
        "path",
        [
            "/etc/passwd",
            "gs://other-bucket/warehouse/orders.csv",
            "gs://acme-data/finance/salaries.csv",
            "gs://acme-data/warehouse/../../other-bucket/orders.csv",
        ],
    )
    async def test_refuses_paths_outside_the_prefix(self, adapter: GCSAdapter, path: str) -> None:
        """Host files, other buckets and other prefixes are refused."""
        with pytest.raises(duckdb.PermissionException):
            await adapter.execute_query(f"SELECT * FROM read_csv('{path}') LIMIT 10")


class TestHDFSAdapterFileAccess:
    """An HDFS source reads its own base path and nothing else."""

    @pytest.fixture
    async def adapter(self, httpfs: None) -> AsyncIterator[HDFSAdapter]:
        """A connected adapter for hdfs://namenode:9000/warehouse."""
        hdfs = HDFSAdapter(
            {"namenode_host": "namenode", "namenode_port": 9000, "path": "/warehouse"}
        )
        await hdfs.connect()
        yield hdfs
        await hdfs.disconnect()

    async def test_own_base_path_passes_the_sandbox(self, adapter: HDFSAdapter) -> None:
        """Paths under the base path are not refused (DuckDB then finds no such file)."""
        with pytest.raises(duckdb.IOException, match="No files found"):
            await adapter.execute_query(
                "SELECT * FROM read_csv('hdfs://namenode:9000/warehouse/orders.csv') LIMIT 10"
            )

    @pytest.mark.parametrize(
        "path",
        [
            "/etc/passwd",
            "hdfs://namenode:9000/finance/salaries.csv",
            "hdfs://namenode:9000/warehouse/../finance/salaries.csv",
        ],
    )
    async def test_refuses_paths_outside_the_base_path(
        self, adapter: HDFSAdapter, path: str
    ) -> None:
        """Host files and other HDFS paths are refused."""
        with pytest.raises(duckdb.PermissionException):
            await adapter.execute_query(f"SELECT * FROM read_csv('{path}') LIMIT 10")
