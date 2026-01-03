"""Unit tests for PII scanner and redactor."""

from __future__ import annotations

import pytest

from dataing.safety.pii import (
    contains_pii,
    redact_dict,
    redact_pii,
    scan_for_pii,
)


class TestScanForPII:
    """Tests for scan_for_pii."""

    def test_detect_email(self) -> None:
        """Test email detection."""
        result = scan_for_pii("Contact me at john.doe@example.com")

        assert "email" in result

    def test_detect_ssn(self) -> None:
        """Test SSN detection."""
        result = scan_for_pii("SSN: 123-45-6789")

        assert "ssn" in result

    def test_detect_credit_card(self) -> None:
        """Test credit card detection."""
        result = scan_for_pii("Card: 4111-1111-1111-1111")

        assert "credit_card" in result

    def test_detect_credit_card_no_dashes(self) -> None:
        """Test credit card detection without dashes."""
        result = scan_for_pii("Card: 4111111111111111")

        assert "credit_card" in result

    def test_detect_phone(self) -> None:
        """Test phone number detection."""
        result = scan_for_pii("Call me at 555-123-4567")

        assert "phone" in result

    def test_detect_phone_with_dots(self) -> None:
        """Test phone number detection with dots."""
        result = scan_for_pii("Phone: 555.123.4567")

        assert "phone" in result

    def test_detect_zip_code(self) -> None:
        """Test ZIP code detection."""
        result = scan_for_pii("ZIP: 12345")

        assert "zip_code" in result

    def test_detect_zip_plus_4(self) -> None:
        """Test ZIP+4 code detection."""
        result = scan_for_pii("ZIP: 12345-6789")

        assert "zip_code" in result

    def test_detect_multiple_pii(self) -> None:
        """Test detecting multiple PII types."""
        result = scan_for_pii("Email: test@example.com, SSN: 123-45-6789, Phone: 555-123-4567")

        assert "email" in result
        assert "ssn" in result
        assert "phone" in result

    def test_no_pii_detected(self) -> None:
        """Test text without PII."""
        result = scan_for_pii("Hello world! This is a test message.")

        assert result == []

    def test_no_duplicates(self) -> None:
        """Test that same type is not duplicated."""
        result = scan_for_pii("Email: a@b.com and c@d.com")

        assert result.count("email") == 1


class TestContainsPII:
    """Tests for contains_pii."""

    def test_returns_true_when_pii_found(self) -> None:
        """Test returns True when PII is found."""
        assert contains_pii("Email: test@example.com") is True

    def test_returns_false_when_no_pii(self) -> None:
        """Test returns False when no PII is found."""
        assert contains_pii("Hello world") is False


class TestRedactPII:
    """Tests for redact_pii."""

    def test_redact_email(self) -> None:
        """Test email redaction."""
        result = redact_pii("Contact: john@example.com")

        assert "[REDACTED_EMAIL]" in result
        assert "john@example.com" not in result

    def test_redact_ssn(self) -> None:
        """Test SSN redaction."""
        result = redact_pii("SSN: 123-45-6789")

        assert "[REDACTED_SSN]" in result
        assert "123-45-6789" not in result

    def test_redact_credit_card(self) -> None:
        """Test credit card redaction."""
        result = redact_pii("Card: 4111-1111-1111-1111")

        assert "[REDACTED_CREDIT_CARD]" in result
        assert "4111" not in result

    def test_redact_phone(self) -> None:
        """Test phone number redaction."""
        result = redact_pii("Phone: 555-123-4567")

        assert "[REDACTED_PHONE]" in result
        assert "555-123-4567" not in result

    def test_redact_zip(self) -> None:
        """Test ZIP code redaction."""
        result = redact_pii("ZIP: 12345")

        assert "[REDACTED_ZIP_CODE]" in result
        assert "12345" not in result

    def test_redact_multiple(self) -> None:
        """Test redacting multiple PII types."""
        result = redact_pii("Email: test@example.com, SSN: 123-45-6789")

        assert "[REDACTED_EMAIL]" in result
        assert "[REDACTED_SSN]" in result
        assert "test@example.com" not in result
        assert "123-45-6789" not in result

    def test_preserves_non_pii(self) -> None:
        """Test that non-PII text is preserved."""
        result = redact_pii("Name: John Doe, Email: john@example.com")

        assert "Name: John Doe" in result
        assert "[REDACTED_EMAIL]" in result


class TestRedactDict:
    """Tests for redact_dict."""

    def test_redact_string_values(self) -> None:
        """Test redacting string values."""
        data = {
            "name": "John",
            "email": "john@example.com",
        }

        result = redact_dict(data)

        assert result["name"] == "John"
        assert "[REDACTED_EMAIL]" in result["email"]

    def test_convert_non_string_values(self) -> None:
        """Test converting non-string values to strings."""
        data = {
            "count": 42,
            "active": True,
            "ratio": 3.14,
        }

        result = redact_dict(data)

        assert result["count"] == "42"
        assert result["active"] == "True"
        assert result["ratio"] == "3.14"

    def test_handle_none_values(self) -> None:
        """Test handling None values."""
        data = {"value": None}

        result = redact_dict(data)

        assert result["value"] == ""

    def test_redact_pii_in_any_key(self) -> None:
        """Test that PII in any key's value is redacted."""
        data = {
            "user_info": "SSN: 123-45-6789",
            "contact": "Call 555-123-4567",
        }

        result = redact_dict(data)

        assert "[REDACTED_SSN]" in result["user_info"]
        assert "[REDACTED_PHONE]" in result["contact"]
