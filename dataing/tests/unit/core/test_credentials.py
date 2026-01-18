"""Unit tests for the CredentialsService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from dataing.core.credentials import CredentialsService, DecryptedCredentials


@pytest.fixture
def mock_app_db() -> AsyncMock:
    """Create a mock app database."""
    return AsyncMock()


@pytest.fixture
def mock_encryption_key() -> bytes:
    """Create a mock encryption key."""
    # This is a valid Fernet key for testing
    return b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M="


class TestDecryptedCredentials:
    """Tests for DecryptedCredentials dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating credentials with basic fields."""
        creds = DecryptedCredentials(
            username="testuser",
            password="testpass",
        )

        assert creds.username == "testuser"
        assert creds.password == "testpass"
        assert creds.role is None
        assert creds.warehouse is None
        assert creds.extra is None

    def test_full_creation(self) -> None:
        """Test creating credentials with all fields."""
        creds = DecryptedCredentials(
            username="testuser",
            password="testpass",
            role="ANALYST",
            warehouse="COMPUTE_WH",
            extra={"account": "my_account"},
        )

        assert creds.role == "ANALYST"
        assert creds.warehouse == "COMPUTE_WH"
        assert creds.extra == {"account": "my_account"}

    def test_frozen(self) -> None:
        """Test that DecryptedCredentials is frozen."""
        creds = DecryptedCredentials(
            username="testuser",
            password="testpass",
        )

        with pytest.raises(AttributeError):
            creds.username = "newuser"  # type: ignore[misc]


class TestCredentialsServiceEncryption:
    """Tests for credentials encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self, mock_app_db: AsyncMock) -> None:
        """Test that encryption and decryption are inverses."""
        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            original = {
                "username": "testuser",
                "password": "secretpass",
                "role": "ANALYST",
                "warehouse": "COMPUTE_WH",
            }

            encrypted = service.encrypt_credentials(original)
            decrypted = service.decrypt_credentials(encrypted)

            assert decrypted.username == "testuser"
            assert decrypted.password == "secretpass"
            assert decrypted.role == "ANALYST"
            assert decrypted.warehouse == "COMPUTE_WH"

    def test_encrypt_produces_bytes(self, mock_app_db: AsyncMock) -> None:
        """Test that encryption produces bytes."""
        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            encrypted = service.encrypt_credentials({
                "username": "test",
                "password": "test",
            })

            assert isinstance(encrypted, bytes)

    def test_extra_fields_preserved(self, mock_app_db: AsyncMock) -> None:
        """Test that extra fields are preserved in decryption."""
        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            original = {
                "username": "testuser",
                "password": "secretpass",
                "custom_field": "custom_value",
                "another_field": 123,
            }

            encrypted = service.encrypt_credentials(original)
            decrypted = service.decrypt_credentials(encrypted)

            assert decrypted.extra is not None
            assert decrypted.extra["custom_field"] == "custom_value"
            assert decrypted.extra["another_field"] == 123


class TestCredentialsServiceGetCredentials:
    """Tests for CredentialsService.get_credentials method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        mock_app_db: AsyncMock,
    ) -> None:
        """Test that None is returned when credentials not found."""
        mock_app_db.get_user_credentials.return_value = None

        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            result = await service.get_credentials(
                user_id=uuid.uuid4(),
                datasource_id=uuid.uuid4(),
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_decrypted_credentials(
        self,
        mock_app_db: AsyncMock,
    ) -> None:
        """Test that credentials are decrypted and returned."""
        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            # Create encrypted credentials
            encrypted = service.encrypt_credentials({
                "username": "testuser",
                "password": "testpass",
            })

            mock_app_db.get_user_credentials.return_value = {
                "credentials_encrypted": encrypted,
            }

            result = await service.get_credentials(
                user_id=uuid.uuid4(),
                datasource_id=uuid.uuid4(),
            )

            assert result is not None
            assert result.username == "testuser"
            assert result.password == "testpass"


class TestCredentialsServiceSaveCredentials:
    """Tests for CredentialsService.save_credentials method."""

    @pytest.mark.asyncio
    async def test_saves_encrypted_credentials(
        self,
        mock_app_db: AsyncMock,
    ) -> None:
        """Test that credentials are encrypted and saved."""
        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            user_id = uuid.uuid4()
            datasource_id = uuid.uuid4()

            await service.save_credentials(
                user_id=user_id,
                datasource_id=datasource_id,
                credentials={
                    "username": "testuser",
                    "password": "testpass",
                },
            )

            mock_app_db.upsert_user_credentials.assert_called_once()
            call_kwargs = mock_app_db.upsert_user_credentials.call_args.kwargs
            assert call_kwargs["user_id"] == user_id
            assert call_kwargs["datasource_id"] == datasource_id
            assert call_kwargs["db_username"] == "testuser"
            assert isinstance(call_kwargs["credentials_encrypted"], bytes)


class TestCredentialsServiceDeleteCredentials:
    """Tests for CredentialsService.delete_credentials method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(
        self,
        mock_app_db: AsyncMock,
    ) -> None:
        """Test that True is returned when credentials deleted."""
        mock_app_db.delete_user_credentials.return_value = True

        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            result = await service.delete_credentials(
                user_id=uuid.uuid4(),
                datasource_id=uuid.uuid4(),
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self,
        mock_app_db: AsyncMock,
    ) -> None:
        """Test that False is returned when credentials not found."""
        mock_app_db.delete_user_credentials.return_value = False

        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            result = await service.delete_credentials(
                user_id=uuid.uuid4(),
                datasource_id=uuid.uuid4(),
            )

            assert result is False


class TestCredentialsServiceGetStatus:
    """Tests for CredentialsService.get_status method."""

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_not_found(
        self,
        mock_app_db: AsyncMock,
    ) -> None:
        """Test status when credentials not configured."""
        mock_app_db.get_user_credentials.return_value = None

        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            status = await service.get_status(
                user_id=uuid.uuid4(),
                datasource_id=uuid.uuid4(),
            )

            assert status["configured"] is False
            assert status["db_username"] is None
            assert status["last_used_at"] is None
            assert status["created_at"] is None

    @pytest.mark.asyncio
    async def test_returns_configured_when_found(
        self,
        mock_app_db: AsyncMock,
    ) -> None:
        """Test status when credentials are configured."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mock_app_db.get_user_credentials.return_value = {
            "db_username": "testuser",
            "last_used_at": now,
            "created_at": now,
        }

        with patch(
            "dataing.core.credentials.get_encryption_key",
            return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
        ):
            service = CredentialsService(mock_app_db)

            status = await service.get_status(
                user_id=uuid.uuid4(),
                datasource_id=uuid.uuid4(),
            )

            assert status["configured"] is True
            assert status["db_username"] == "testuser"
            assert status["last_used_at"] == now
            assert status["created_at"] == now
