"""Tests for the Temporal worker entrypoint."""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import structlog
from cryptography.fernet import Fernet

from dataing.adapters.datasource.sql.base import SQLAdapter
from dataing.entrypoints import temporal_worker
from dataing.entrypoints.temporal_worker import TenantAdapterCache

# SGR color codes that ConsoleRenderer and Rich put around each field.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

TENANT_A = uuid4()
TENANT_B = uuid4()
ENCRYPTION_KEY = Fernet.generate_key().decode()


def build_adapter(encryption_key: str) -> None:
    """Fail with a secret held in a frame local, like get_adapter() does."""
    raise RuntimeError("adapter construction failed")


class TestWorkerLogging:
    """Tests for the logging configured by the worker entrypoint."""

    def setup_method(self) -> None:
        """Reset structlog so the test covers main()'s own logging setup."""
        # Other tests may have built the API app in this process, and create_app()
        # configures structlog. The worker must not depend on that.
        structlog.reset_defaults()

    def teardown_method(self) -> None:
        """Reset structlog configuration after each test."""
        structlog.reset_defaults()

    @pytest.mark.parametrize("log_format", ["console", "json"])
    def test_structlog_exception_output_hides_frame_locals(
        self,
        log_format: str,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Worker-side structlog tracebacks do not render frame locals such as encryption keys."""
        # Generated at runtime so the value never appears in rendered source lines.
        secret = f"secret-{uuid.uuid4().hex[:12]}"
        monkeypatch.setenv("LOG_FORMAT", log_format)
        # Wide enough that a rendered secret is never wrapped across lines and missed.
        monkeypatch.setenv("COLUMNS", "200")

        async def fake_run_worker() -> None:
            try:
                build_adapter(secret)
            except RuntimeError:
                structlog.get_logger(__name__).exception("adapter_failed")

        # The real run_worker() needs a Temporal server; main() still does its own setup.
        monkeypatch.setattr(temporal_worker, "run_worker", fake_run_worker)
        temporal_worker.main()

        output = capsys.readouterr().out
        assert "adapter_failed" in output
        assert "adapter construction failed" in output
        assert secret not in output

    @pytest.mark.parametrize("log_format", ["console", "json"])
    def test_worker_failure_is_logged_once_without_frame_locals(
        self,
        log_format: str,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """main() logs a crashed worker once, via its stdlib logger, with no frame locals."""
        secret = f"secret-{uuid.uuid4().hex[:12]}"
        monkeypatch.setenv("LOG_FORMAT", log_format)
        monkeypatch.setenv("COLUMNS", "200")

        async def fake_run_worker() -> None:
            build_adapter(secret)

        monkeypatch.setattr(temporal_worker, "run_worker", fake_run_worker)
        # Exiting instead of re-raising keeps the interpreter from printing the traceback
        # a second time, unformatted, on stderr.
        with pytest.raises(SystemExit) as exit_info:
            temporal_worker.main()

        assert exit_info.value.code == 1
        output = ANSI_ESCAPE.sub("", capsys.readouterr().out)
        assert "Worker failed: adapter construction failed" in output
        assert output.count("Traceback (most recent call last)") == 1
        assert secret not in output

    def test_json_worker_failure_is_one_json_line(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With LOG_FORMAT=json, main()'s stdlib failure log is JSON, traceback included."""
        monkeypatch.setenv("LOG_FORMAT", "json")

        async def fake_run_worker() -> None:
            raise RuntimeError("temporal unreachable")

        monkeypatch.setattr(temporal_worker, "run_worker", fake_run_worker)
        with pytest.raises(SystemExit):
            temporal_worker.main()

        entry = json.loads(capsys.readouterr().out)
        assert entry["logger"] == "dataing.entrypoints.temporal_worker"
        assert entry["level"] == "error"
        assert entry["event"] == "Worker failed: temporal unreachable"
        assert entry["exception"].endswith("RuntimeError: temporal unreachable")

    @pytest.mark.usefixtures("unset_http_client_log_levels")
    def test_worker_keeps_http_client_loggers_at_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main()'s logging setup quiets httpx and httpcore: webhook URLs carry secrets."""

        async def fake_run_worker() -> None:
            return None

        # The real run_worker() needs a Temporal server; main() still does its own setup.
        monkeypatch.setattr(temporal_worker, "run_worker", fake_run_worker)
        temporal_worker.main()

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


class FakeAppDb:
    """AppDatabase stand-in holding a data_sources table."""

    def __init__(self, *sources: dict[str, Any]) -> None:
        """Initialize with datasource rows."""
        self._sources = {source["id"]: source for source in sources}
        self.lookups: list[tuple[UUID, UUID]] = []

    async def get_data_source(self, data_source_id: UUID, tenant_id: UUID) -> dict[str, Any] | None:
        """Mirror AppDatabase.get_data_source (WHERE id = $1 AND tenant_id = $2)."""
        self.lookups.append((data_source_id, tenant_id))
        source = self._sources.get(data_source_id)
        if source is None or source["tenant_id"] != tenant_id:
            return None
        return source


def _datasource(tenant_id: UUID, *, is_active: bool = True) -> dict[str, Any]:
    config = json.dumps({"path": f"/data/{tenant_id}"}).encode()
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "name": "warehouse",
        "type": "duckdb",
        "is_active": is_active,
        "connection_config_encrypted": Fernet(ENCRYPTION_KEY.encode()).encrypt(config).decode(),
    }


@pytest.fixture
def registry() -> Iterator[MagicMock]:
    """Stub the adapter registry so no real datasource connection is made."""
    with patch("dataing.entrypoints.temporal_worker.get_registry") as get_registry:
        registry = MagicMock()
        registry.create.side_effect = lambda ds_type, config: AsyncMock(
            spec=SQLAdapter, name=config["path"]
        )
        get_registry.return_value = registry
        yield registry


async def test_owner_gets_connected_adapter(registry: MagicMock) -> None:
    """A tenant's own datasource resolves to a connected adapter."""
    source = _datasource(TENANT_A)
    cache = TenantAdapterCache(FakeAppDb(source), ENCRYPTION_KEY)

    adapter = await cache.get_adapter(tenant_id=str(TENANT_A), datasource_id=str(source["id"]))

    registry.create.assert_called_once_with("duckdb", {"path": f"/data/{TENANT_A}"})
    adapter.connect.assert_awaited_once()


async def test_other_tenants_datasource_is_not_found(registry: MagicMock) -> None:
    """Naming another tenant's datasource ID fails before any config is decrypted."""
    source = _datasource(TENANT_B)
    cache = TenantAdapterCache(FakeAppDb(source), ENCRYPTION_KEY)

    with pytest.raises(ValueError, match="not found"):
        await cache.get_adapter(tenant_id=str(TENANT_A), datasource_id=str(source["id"]))

    registry.create.assert_not_called()


async def test_cached_adapter_is_not_served_to_another_tenant(registry: MagicMock) -> None:
    """An adapter cached for tenant B is never handed to tenant A."""
    source = _datasource(TENANT_B)
    cache = TenantAdapterCache(FakeAppDb(source), ENCRYPTION_KEY)
    await cache.get_adapter(tenant_id=str(TENANT_B), datasource_id=str(source["id"]))

    with pytest.raises(ValueError, match="not found"):
        await cache.get_adapter(tenant_id=str(TENANT_A), datasource_id=str(source["id"]))

    assert registry.create.call_count == 1


async def test_inactive_datasource_is_rejected(registry: MagicMock) -> None:
    """Deactivated datasources are not usable by the worker."""
    source = _datasource(TENANT_A, is_active=False)
    cache = TenantAdapterCache(FakeAppDb(source), ENCRYPTION_KEY)

    with pytest.raises(ValueError, match="not found or inactive"):
        await cache.get_adapter(tenant_id=str(TENANT_A), datasource_id=str(source["id"]))

    registry.create.assert_not_called()


async def test_adapter_is_reused_for_same_tenant_and_datasource(registry: MagicMock) -> None:
    """Repeat lookups for the same (tenant, datasource) hit the cache."""
    source = _datasource(TENANT_A)
    db = FakeAppDb(source)
    cache = TenantAdapterCache(db, ENCRYPTION_KEY)

    first = await cache.get_adapter(tenant_id=str(TENANT_A), datasource_id=str(source["id"]))
    second = await cache.get_adapter(tenant_id=str(TENANT_A), datasource_id=str(source["id"]))

    assert first is second
    assert db.lookups == [(source["id"], TENANT_A)]
