"""Unit tests for adapter factory."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet, InvalidToken

from dataing.adapters.datasource.errors import DatasourceNotFoundError
from dataing.adapters.datasource.factory import (
    create_adapter_for_datasource,
    decrypt_config,
    get_encryption_key,
)


@pytest.fixture
def encryption_key() -> bytes:
    """Generate a test encryption key."""
    return Fernet.generate_key()


@pytest.fixture
def test_config() -> dict:
    """Sample datasource configuration."""
    return {
        "host": "localhost",
        "port": 5432,
        "database": "test_db",
        "username": "test_user",
        "password": "secret_password",
    }


@pytest.fixture
def encrypted_config(encryption_key: bytes, test_config: dict) -> str:
    """Encrypt the test configuration."""
    f = Fernet(encryption_key)
    return f.encrypt(json.dumps(test_config).encode()).decode()


class TestGetEncryptionKey:
    """Tests for get_encryption_key function."""

    def test_returns_key_from_encryption_key_env(self) -> None:
        """Test key retrieval from ENCRYPTION_KEY environment variable."""
        test_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": test_key}, clear=False):
            # Clear DATADR_ENCRYPTION_KEY if set
            with patch.dict(os.environ, {"DATADR_ENCRYPTION_KEY": ""}, clear=False):
                key = get_encryption_key()
                assert key == test_key.encode()

    def test_returns_key_from_datadr_env(self) -> None:
        """Test key retrieval from DATADR_ENCRYPTION_KEY (takes priority)."""
        test_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"DATADR_ENCRYPTION_KEY": test_key}, clear=False):
            key = get_encryption_key()
            assert key == test_key.encode()

    def test_raises_when_no_key_configured(self) -> None:
        """Test error when no encryption key is configured."""
        with patch.dict(
            os.environ,
            {"ENCRYPTION_KEY": "", "DATADR_ENCRYPTION_KEY": ""},
            clear=False,
        ):
            with pytest.raises(ValueError, match="ENCRYPTION_KEY.*must be set"):
                get_encryption_key()


class TestDecryptConfig:
    """Tests for decrypt_config function."""

    def test_decrypts_valid_config(
        self, encryption_key: bytes, test_config: dict, encrypted_config: str
    ) -> None:
        """Test successful decryption of configuration."""
        result = decrypt_config(encrypted_config, encryption_key)
        assert result == test_config

    def test_raises_on_invalid_key(self, encrypted_config: str) -> None:
        """Test error on wrong encryption key."""
        wrong_key = Fernet.generate_key()
        with pytest.raises(InvalidToken):
            decrypt_config(encrypted_config, wrong_key)

    def test_raises_on_corrupted_data(self, encryption_key: bytes) -> None:
        """Test error on corrupted encrypted data."""
        with pytest.raises(InvalidToken):
            decrypt_config("invalid_data", encryption_key)


class TestCreateAdapterForDatasource:
    """Tests for create_adapter_for_datasource function."""

    async def test_raises_when_datasource_not_found(self) -> None:
        """Test DatasourceNotFoundError when datasource doesn't exist."""
        mock_db = AsyncMock()
        mock_db.get_data_source.return_value = None

        tenant_id = uuid4()
        datasource_id = uuid4()

        with pytest.raises(DatasourceNotFoundError) as exc_info:
            await create_adapter_for_datasource(mock_db, tenant_id, datasource_id)

        assert str(datasource_id) in str(exc_info.value.details)
        mock_db.get_data_source.assert_called_once_with(datasource_id, tenant_id)

    async def test_creates_adapter_successfully(
        self, encryption_key: bytes, encrypted_config: str
    ) -> None:
        """Test successful adapter creation from stored config."""
        mock_db = AsyncMock()
        mock_db.get_data_source.return_value = {
            "id": uuid4(),
            "type": "postgresql",
            "connection_config_encrypted": encrypted_config,
        }

        mock_adapter = MagicMock()
        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = True
        mock_registry.create.return_value = mock_adapter

        tenant_id = uuid4()
        datasource_id = uuid4()

        with (
            patch.dict(
                os.environ,
                {"ENCRYPTION_KEY": encryption_key.decode()},
                clear=False,
            ),
            patch(
                "dataing.adapters.datasource.factory.get_registry",
                return_value=mock_registry,
            ),
        ):
            result = await create_adapter_for_datasource(mock_db, tenant_id, datasource_id)

        assert result == mock_adapter
        mock_registry.create.assert_called_once()

    async def test_raises_when_adapter_not_registered(
        self, encryption_key: bytes, encrypted_config: str
    ) -> None:
        """Test error when source type has no registered adapter."""
        mock_db = AsyncMock()
        mock_db.get_data_source.return_value = {
            "id": uuid4(),
            "type": "postgresql",
            "connection_config_encrypted": encrypted_config,
        }

        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = False

        tenant_id = uuid4()
        datasource_id = uuid4()

        with (
            patch.dict(
                os.environ,
                {"ENCRYPTION_KEY": encryption_key.decode()},
                clear=False,
            ),
            patch(
                "dataing.adapters.datasource.factory.get_registry",
                return_value=mock_registry,
            ),
        ):
            with pytest.raises(ValueError, match="No adapter registered"):
                await create_adapter_for_datasource(mock_db, tenant_id, datasource_id)
