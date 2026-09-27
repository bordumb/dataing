"""Unit tests for URL redaction."""

from __future__ import annotations

import pytest

from dataing.safety.urls import redact_url


class TestRedactUrl:
    """Tests for redact_url."""

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://hooks.slack.com/services/T000/B000/SECRETTOKEN", "https://hooks.slack.com"),
            (
                "https://bot:SECRETPASS@hooks.example.com:8443/p?sig=SECRETQUERY#SECRETFRAG",
                "https://hooks.example.com",
            ),
            ("postgresql://user:SECRETPASS@db.internal:5432/app", "postgresql://db.internal"),
        ],
        ids=["path", "userinfo_port_query_fragment", "non_http_scheme"],
    )
    def test_keeps_only_scheme_and_host(self, url: str, expected: str) -> None:
        """Test that everything except the scheme and host is dropped."""
        assert redact_url(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "hooks.example.com/services/T000/B000/SECRETTOKEN",
            "https://[hooks.example.com/services/T000/B000/SECRETTOKEN",
            "",
        ],
        ids=["missing_scheme", "unparseable", "empty"],
    )
    def test_returns_placeholder_without_parseable_host(self, url: str) -> None:
        """Test that a URL without a parseable host is never echoed back."""
        assert redact_url(url) == "<invalid url>"
