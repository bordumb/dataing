"""Confine in-process DuckDB connections to a data source's own location.

File sources (local, S3, GCS, HDFS) and the DuckDB source run investigation SQL on an
in-process DuckDB connection. An LLM writes that SQL, and data values can steer it.
SQL validation cannot tell a source's own files from any other path:
``read_csv('/etc/passwd')`` and ``read_parquet('s3://other-bucket/...')`` are both
ordinary SELECTs.

Adapters therefore open their connection with :func:`connection_config` and, once their
own setup (extensions, credentials, views) is done, call :func:`confine`. From then on
DuckDB refuses files and URLs outside the source's location, refuses to load
extensions, and refuses any change to its settings.

The allowlist check needs DuckDB 1.4.4 to 1.4.x. Those releases resolve ``.`` and
``..`` in both local paths and URLs before comparing. 1.4.3 and earlier let
``<dir>/./../`` escape. 1.5.x resolves local paths but not ``s3://`` or ``gs://``
URLs, and ``..`` in a URL still reaches other prefixes and buckets. Symlinks inside
a source directory are followed. :func:`confine` refuses other releases.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from collections.abc import Sequence
from typing import Any

# DuckDB releases whose allowlist check holds, as [lowest, first excluded). Keep in
# step with the duckdb requirement in pyproject.toml.
_SUPPORTED_DUCKDB = ((1, 4, 4), (1, 5, 0))


def connection_config() -> dict[str, Any]:
    """Build the ``duckdb.connect`` config for a connection that will be confined.

    The connection ignores secrets persisted on the host, and spills to a temporary
    directory of its own. DuckDB keeps its spill directory readable after
    :func:`confine`, so a shared one would expose other connections' spilled data.
    DuckDB creates the directory on first spill and removes it on close.

    Returns:
        Config for ``duckdb.connect(..., config=...)``.
    """
    spill_directory = os.path.join(tempfile.gettempdir(), f"dataing-duckdb-{uuid.uuid4().hex}")
    return {"allow_persistent_secrets": False, "temp_directory": spill_directory}


def confine(conn: Any, *, directories: Sequence[str]) -> None:
    """Restrict a connection to reading inside ``directories`` and lock its settings.

    Call this once the adapter's own setup is done. Afterwards the connection cannot
    load extensions or change any setting.

    Args:
        conn: DuckDB connection opened with :func:`connection_config`.
        directories: Local directories or URL prefixes (e.g. ``s3://bucket/prefix/``)
            whose contents stay readable. Empty for a source with no files of its own.

    Raises:
        RuntimeError: If the installed DuckDB's allowlist check can be escaped.
    """
    _require_supported_duckdb()
    conn.execute("SET allowed_directories = ?", [list(directories)])
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")


def _require_supported_duckdb() -> None:
    """Fail loudly rather than run a sandbox that queries can escape."""
    import duckdb

    version: str = duckdb.__version__
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    release = tuple(int(part) for part in match.groups()) if match else (0, 0, 0)
    lowest, first_excluded = _SUPPORTED_DUCKDB
    if not lowest <= release < first_excluded:
        raise RuntimeError(
            f"DuckDB {version} cannot confine queries to a data source's files: its "
            "allowed_directories check can be escaped. Install duckdb>=1.4.4,<1.5."
        )
