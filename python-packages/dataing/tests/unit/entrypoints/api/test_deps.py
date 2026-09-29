"""Unit tests that keep datasource secrets out of stdout, stderr, and logs."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request

from dataing.entrypoints.api import deps
from dataing.temporal.client import TemporalInvestigationClient

DATASOURCE_PASSWORD = "hunter2-do-not-log"


def assert_not_leaked(secret: str, *outputs: str) -> None:
    """Assert that neither ``secret`` nor its first 8 characters appear in any output."""
    for output in outputs:
        assert secret[:8] not in output


class FakeAppDatabase:
    """AppDatabase stand-in that serves a single data source record."""

    def __init__(self, data_source: dict[str, Any]) -> None:
        """Initialize the fake with the record to serve."""
        self._data_source = data_source

    async def get_data_source(self, data_source_id: UUID, tenant_id: UUID) -> dict[str, Any] | None:
        """Return the record when the ID matches."""
        if data_source_id == self._data_source["id"]:
            return self._data_source
        return None


class FakeAdapter:
    """Datasource adapter stand-in that records the config it was built with."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the fake adapter."""
        self.config = config
        self.connected = False

    async def connect(self) -> None:
        """Pretend to connect."""
        self.connected = True


class FakeRegistry:
    """Adapter registry stand-in that builds FakeAdapters."""

    def create(self, source_type: str, config: dict[str, Any]) -> FakeAdapter:
        """Build a FakeAdapter from the decrypted config."""
        return FakeAdapter(config)


class TestGetTenantAdapterSecrets:
    """get_tenant_adapter must never write the key or decrypted config anywhere."""

    @pytest.fixture
    def encryption_key(self) -> str:
        """Return a fresh Fernet key."""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def connection_config(self) -> dict[str, Any]:
        """Return a datasource config holding a credential."""
        return {"host": "warehouse.internal", "user": "loader", "password": DATASOURCE_PASSWORD}

    @pytest.fixture(autouse=True)
    def fake_registry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Route adapter creation to FakeRegistry."""
        monkeypatch.setattr(deps, "get_registry", FakeRegistry)

    def _request(self, config_encrypted: str, encryption_key: str) -> tuple[Request, UUID, UUID]:
        """Build a request whose app state serves one encrypted data source."""
        tenant_id, data_source_id = uuid4(), uuid4()
        app = FastAPI()
        app.state.app_db = FakeAppDatabase(
            {
                "id": data_source_id,
                "type": "postgres",
                "name": "Warehouse",
                "connection_config_encrypted": config_encrypted,
            }
        )
        app.state.adapter_cache = {}
        app.state.encryption_key = encryption_key
        return Request({"type": "http", "app": app}), tenant_id, data_source_id

    async def test_success_keeps_key_and_config_out_of_output(
        self,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
        encryption_key: str,
        connection_config: dict[str, Any],
    ) -> None:
        """Decrypting a config does not print or log the key or the plaintext config."""
        caplog.set_level(logging.DEBUG)
        plaintext = json.dumps(connection_config).encode()
        config_encrypted = Fernet(encryption_key.encode()).encrypt(plaintext).decode()
        request, tenant_id, data_source_id = self._request(config_encrypted, encryption_key)

        adapter = await deps.get_tenant_adapter(request, tenant_id, data_source_id)

        assert isinstance(adapter, FakeAdapter)
        assert adapter.config == connection_config
        assert adapter.connected
        captured = capsys.readouterr()
        outputs = (captured.out, captured.err, caplog.text)
        assert_not_leaked(encryption_key, *outputs)
        assert_not_leaked(DATASOURCE_PASSWORD, *outputs)

    async def test_decrypt_failure_keeps_key_out_of_error_and_output(
        self,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
        encryption_key: str,
        connection_config: dict[str, Any],
    ) -> None:
        """A wrong key raises RuntimeError without exposing the key or dumping a traceback."""
        caplog.set_level(logging.DEBUG)
        plaintext = json.dumps(connection_config).encode()
        encrypted_with_other_key = Fernet(Fernet.generate_key()).encrypt(plaintext).decode()
        request, tenant_id, data_source_id = self._request(encrypted_with_other_key, encryption_key)

        with pytest.raises(RuntimeError, match="Failed to decrypt connection config") as exc_info:
            await deps.get_tenant_adapter(request, tenant_id, data_source_id)

        captured = capsys.readouterr()
        outputs = (str(exc_info.value), captured.out, captured.err, caplog.text)
        assert_not_leaked(encryption_key, *outputs)
        assert "Traceback" not in captured.err


class FakeLifespanDatabase:
    """AppDatabase stand-in for lifespan startup and teardown."""

    def __init__(self, dsn: str) -> None:
        """Initialize the fake without a real pool."""
        self.pool = None

    async def connect(self) -> None:
        """Pretend to open the pool."""

    async def close(self) -> None:
        """Pretend to close the pool."""


async def fake_temporal_connect(**kwargs: Any) -> object:
    """Stand in for TemporalInvestigationClient.connect."""
    return object()


class TestLifespanSecrets:
    """App startup must never write the encryption key anywhere."""

    async def test_startup_keeps_encryption_key_out_of_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Lifespan startup loads the key without printing or logging it."""
        caplog.set_level(logging.DEBUG)
        encryption_key = Fernet.generate_key().decode()
        monkeypatch.setenv("DATADR_ENCRYPTION_KEY", encryption_key)
        monkeypatch.delenv("DATADR_DEMO_MODE", raising=False)
        monkeypatch.setattr(deps, "AppDatabase", FakeLifespanDatabase)
        monkeypatch.setattr(TemporalInvestigationClient, "connect", fake_temporal_connect)
        app = FastAPI()

        async with deps.lifespan(app):
            assert app.state.encryption_key == encryption_key

        captured = capsys.readouterr()
        assert_not_leaked(encryption_key, captured.out, captured.err, caplog.text)
