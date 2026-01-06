"""Tests for DNS verification service."""

from unittest.mock import MagicMock, patch

from dataing.core.sso import (
    VerificationToken,
    generate_verification_instructions,
    verify_domain_dns,
)
from dataing.core.sso.dns_verification import DNS_RECORD_PREFIX, TOKEN_PREFIX


class TestVerificationToken:
    """Tests for VerificationToken."""

    def test_generate_creates_token(self) -> None:
        """Generate creates a verification token."""
        token = VerificationToken.generate("acme.com")

        assert token.token is not None
        assert len(token.token) == 64  # 32 bytes hex = 64 chars

    def test_generate_correct_dns_record(self) -> None:
        """Generate creates correct DNS record name."""
        token = VerificationToken.generate("acme.com")

        assert token.dns_record == f"{DNS_RECORD_PREFIX}.acme.com"

    def test_generate_correct_dns_value(self) -> None:
        """Generate creates correct DNS value."""
        token = VerificationToken.generate("acme.com")

        assert token.dns_value.startswith(TOKEN_PREFIX)
        assert token.token in token.dns_value

    def test_generate_unique_tokens(self) -> None:
        """Generate creates unique tokens each time."""
        token1 = VerificationToken.generate("acme.com")
        token2 = VerificationToken.generate("acme.com")

        assert token1.token != token2.token


class TestVerifyDomainDns:
    """Tests for verify_domain_dns function."""

    async def test_returns_true_when_token_matches(self) -> None:
        """Returns True when DNS TXT record matches expected token."""
        mock_rdata = MagicMock()
        mock_rdata.strings = [f"{TOKEN_PREFIX}abc123".encode()]

        mock_answers = [mock_rdata]

        with patch("dns.resolver.resolve", return_value=mock_answers):
            result = await verify_domain_dns("acme.com", "abc123")

        assert result is True

    async def test_returns_false_when_token_mismatch(self) -> None:
        """Returns False when DNS TXT record doesn't match."""
        mock_rdata = MagicMock()
        mock_rdata.strings = [f"{TOKEN_PREFIX}wrong-token".encode()]

        mock_answers = [mock_rdata]

        with patch("dns.resolver.resolve", return_value=mock_answers):
            result = await verify_domain_dns("acme.com", "abc123")

        assert result is False

    async def test_returns_false_on_nxdomain(self) -> None:
        """Returns False when domain doesn't exist."""
        import dns.resolver

        with patch("dns.resolver.resolve", side_effect=dns.resolver.NXDOMAIN):
            result = await verify_domain_dns("nonexistent.com", "abc123")

        assert result is False

    async def test_returns_false_on_no_answer(self) -> None:
        """Returns False when no TXT record exists."""
        import dns.resolver

        with patch("dns.resolver.resolve", side_effect=dns.resolver.NoAnswer):
            result = await verify_domain_dns("acme.com", "abc123")

        assert result is False

    async def test_returns_false_on_exception(self) -> None:
        """Returns False on unexpected exception."""
        with patch("dns.resolver.resolve", side_effect=RuntimeError("DNS error")):
            result = await verify_domain_dns("acme.com", "abc123")

        assert result is False


class TestGenerateVerificationInstructions:
    """Tests for generate_verification_instructions function."""

    def test_includes_domain(self) -> None:
        """Instructions include the domain name."""
        instructions = generate_verification_instructions("acme.com", "abc123")

        assert "acme.com" in instructions

    def test_includes_record_name(self) -> None:
        """Instructions include the DNS record name."""
        instructions = generate_verification_instructions("acme.com", "abc123")

        assert f"{DNS_RECORD_PREFIX}.acme.com" in instructions

    def test_includes_token(self) -> None:
        """Instructions include the verification token."""
        instructions = generate_verification_instructions("acme.com", "abc123")

        assert "abc123" in instructions
        assert TOKEN_PREFIX in instructions

    def test_includes_txt_type(self) -> None:
        """Instructions specify TXT record type."""
        instructions = generate_verification_instructions("acme.com", "abc123")

        assert "TXT" in instructions
