"""Tests for password recovery adapters."""

import pytest
from dataing.adapters.auth.recovery_admin import AdminContactRecoveryAdapter
from dataing.adapters.auth.recovery_console import ConsoleRecoveryAdapter
from dataing.core.auth.recovery import PasswordRecoveryAdapter


class TestConsoleRecoveryAdapter:
    """Tests for ConsoleRecoveryAdapter."""

    def test_implements_protocol(self) -> None:
        """Adapter implements the PasswordRecoveryAdapter protocol."""
        adapter = ConsoleRecoveryAdapter(frontend_url="http://localhost:3000")
        assert isinstance(adapter, PasswordRecoveryAdapter)

    async def test_get_recovery_method_returns_console_type(self) -> None:
        """get_recovery_method returns console type."""
        adapter = ConsoleRecoveryAdapter(frontend_url="http://localhost:3000")
        method = await adapter.get_recovery_method("test@example.com")

        assert method.type == "console"
        assert "console" in method.message.lower()

    async def test_initiate_recovery_returns_true(self, capsys: pytest.CaptureFixture) -> None:
        """initiate_recovery prints to console and returns True."""
        adapter = ConsoleRecoveryAdapter(frontend_url="http://localhost:3000")

        result = await adapter.initiate_recovery(
            user_email="test@example.com",
            token="test-token-123",
            reset_url="http://localhost:3000/reset-password?token=test-token-123",
        )

        assert result is True

        # Check output was printed
        captured = capsys.readouterr()
        assert "PASSWORD RESET" in captured.out
        assert "test@example.com" in captured.out
        assert "http://localhost:3000/reset-password?token=test-token-123" in captured.out


class TestAdminContactRecoveryAdapter:
    """Tests for AdminContactRecoveryAdapter."""

    def test_implements_protocol(self) -> None:
        """Adapter implements the PasswordRecoveryAdapter protocol."""
        adapter = AdminContactRecoveryAdapter()
        assert isinstance(adapter, PasswordRecoveryAdapter)

    async def test_get_recovery_method_returns_admin_contact_type(self) -> None:
        """get_recovery_method returns admin_contact type."""
        adapter = AdminContactRecoveryAdapter()
        method = await adapter.get_recovery_method("test@example.com")

        assert method.type == "admin_contact"
        assert "SSO" in method.message or "administrator" in method.message

    async def test_get_recovery_method_includes_admin_email(self) -> None:
        """get_recovery_method includes admin email when provided."""
        adapter = AdminContactRecoveryAdapter(admin_email="admin@example.com")
        method = await adapter.get_recovery_method("test@example.com")

        assert method.admin_email == "admin@example.com"

    async def test_get_recovery_method_no_admin_email(self) -> None:
        """get_recovery_method has no admin_email when not provided."""
        adapter = AdminContactRecoveryAdapter()
        method = await adapter.get_recovery_method("test@example.com")

        assert method.admin_email is None

    async def test_initiate_recovery_returns_true(self) -> None:
        """initiate_recovery logs and returns True."""
        adapter = AdminContactRecoveryAdapter(admin_email="admin@example.com")

        result = await adapter.initiate_recovery(
            user_email="test@example.com",
            token="test-token-123",
            reset_url="http://localhost:3000/reset-password?token=test-token-123",
        )

        assert result is True
