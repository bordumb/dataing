"""Tests for auth repository protocol."""

from dataing.core.auth.repository import AuthRepository


class TestAuthRepositoryProtocol:
    """Test AuthRepository is a proper protocol."""

    def test_protocol_has_user_methods(self) -> None:
        """Protocol should define user CRUD methods."""
        assert hasattr(AuthRepository, "get_user_by_id")
        assert hasattr(AuthRepository, "get_user_by_email")
        assert hasattr(AuthRepository, "create_user")

    def test_protocol_has_org_methods(self) -> None:
        """Protocol should define org CRUD methods."""
        assert hasattr(AuthRepository, "get_org_by_id")
        assert hasattr(AuthRepository, "get_org_by_slug")
        assert hasattr(AuthRepository, "create_org")

    def test_protocol_has_membership_methods(self) -> None:
        """Protocol should define membership methods."""
        assert hasattr(AuthRepository, "get_user_org_membership")
        assert hasattr(AuthRepository, "get_user_orgs")
        assert hasattr(AuthRepository, "add_user_to_org")
