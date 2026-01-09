"""Tests for password hashing utilities."""

from dataing.core.auth.password import hash_password, verify_password


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password_returns_hash(self) -> None:
        """Should return a bcrypt hash."""
        hashed = hash_password("mypassword123")
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_hash_password_different_each_time(self) -> None:
        """Same password should produce different hashes (salted)."""
        hash1 = hash_password("mypassword123")
        hash2 = hash_password("mypassword123")
        assert hash1 != hash2

    def test_verify_password_correct(self) -> None:
        """Should return True for correct password."""
        hashed = hash_password("mypassword123")
        assert verify_password("mypassword123", hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Should return False for incorrect password."""
        hashed = hash_password("mypassword123")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self) -> None:
        """Should return False for empty password."""
        hashed = hash_password("mypassword123")
        assert verify_password("", hashed) is False
