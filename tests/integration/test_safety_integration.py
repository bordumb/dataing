"""Integration tests for safety features."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dataing.core.exceptions import CircuitBreakerTripped, QueryValidationError
from dataing.core.state import Event
from dataing.safety.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from dataing.safety.pii import contains_pii, redact_pii
from dataing.safety.validator import add_limit_if_missing, validate_query


class TestSafetyIntegration:
    """Integration tests for safety features working together."""

    def test_query_validation_with_pii_check(self) -> None:
        """Test that queries are validated and PII is checked."""
        # Query with potential PII
        query = "SELECT email FROM users WHERE email = 'john@example.com' LIMIT 10"

        # Validate query is safe
        validate_query(query)

        # Check for PII in query
        assert contains_pii(query) is True

        # Redact PII
        redacted = redact_pii(query)
        assert "[REDACTED_EMAIL]" in redacted
        assert "john@example.com" not in redacted

    def test_circuit_breaker_with_validation(self) -> None:
        """Test circuit breaker works with query validation."""
        breaker = CircuitBreaker(
            CircuitBreakerConfig(
                max_total_queries=3,
                max_consecutive_failures=2,
            )
        )

        events = []

        # Simulate successful queries
        for i in range(2):
            query = f"SELECT * FROM table{i} LIMIT 10"
            validate_query(query)  # Validate first

            events.append(
                Event(
                    type="query_submitted",
                    timestamp=datetime.now(timezone.utc),
                    data={"query": query},
                )
            )
            events.append(
                Event(
                    type="query_succeeded",
                    timestamp=datetime.now(timezone.utc),
                    data={},
                )
            )

        # Should be fine so far
        breaker.check(events)

        # Add one more query to hit limit
        events.append(
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"query": "SELECT 1 LIMIT 1"},
            )
        )

        # Should trip circuit breaker
        with pytest.raises(CircuitBreakerTripped):
            breaker.check(events)

    def test_unsafe_query_rejected_before_circuit_breaker(self) -> None:
        """Test that unsafe queries are rejected before reaching circuit breaker."""
        breaker = CircuitBreaker(CircuitBreakerConfig())

        unsafe_queries = [
            "DROP TABLE users",
            "DELETE FROM orders",
            "UPDATE users SET admin = true",
        ]

        for query in unsafe_queries:
            # Should be rejected by validator first
            with pytest.raises(QueryValidationError):
                validate_query(query)

            # Circuit breaker never gets called for invalid queries

    def test_limit_added_before_execution(self) -> None:
        """Test that LIMIT is added to queries without it."""
        query = "SELECT * FROM users"

        # Add limit
        safe_query = add_limit_if_missing(query, limit=1000)

        # Now validate
        validate_query(safe_query)

        # Should pass validation
        assert "LIMIT" in safe_query.upper()

    def test_consecutive_failures_trigger_breaker(self) -> None:
        """Test that consecutive failures trigger circuit breaker."""
        breaker = CircuitBreaker(
            CircuitBreakerConfig(
                max_consecutive_failures=3,
            )
        )

        events = [
            Event(
                type="query_succeeded",
                timestamp=datetime.now(timezone.utc),
                data={},
            ),
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={"error": "Timeout"},
            ),
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={"error": "Connection error"},
            ),
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={"error": "Unknown"},
            ),
        ]

        with pytest.raises(CircuitBreakerTripped) as exc_info:
            breaker.check(events)

        assert "Consecutive failure" in str(exc_info.value)

    def test_pii_redaction_in_query_results(self) -> None:
        """Test PII redaction in simulated query results."""
        # Simulate query result with PII
        result_data = {
            "user_email": "john.doe@example.com",
            "user_phone": "555-123-4567",
            "user_ssn": "123-45-6789",
            "order_total": 99.99,
        }

        # Redact each field
        redacted_data = {}
        for key, value in result_data.items():
            if isinstance(value, str):
                redacted_data[key] = redact_pii(value)
            else:
                redacted_data[key] = value

        # Verify redaction
        assert "[REDACTED_EMAIL]" in redacted_data["user_email"]
        assert "[REDACTED_PHONE]" in redacted_data["user_phone"]
        assert "[REDACTED_SSN]" in redacted_data["user_ssn"]
        assert redacted_data["order_total"] == 99.99  # Unchanged

    def test_hypothesis_retry_limit(self) -> None:
        """Test per-hypothesis retry limit."""
        breaker = CircuitBreaker(
            CircuitBreakerConfig(
                max_retries_per_hypothesis=2,
            )
        )

        events = [
            Event(
                type="reflexion_attempted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001"},
            ),
            Event(
                type="reflexion_attempted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001"},
            ),
        ]

        # Should trip on third attempt
        with pytest.raises(CircuitBreakerTripped) as exc_info:
            breaker.check(events, "h001")

        assert "retry limit" in str(exc_info.value).lower()

    def test_duplicate_query_detection(self) -> None:
        """Test detection of stalled queries."""
        breaker = CircuitBreaker(CircuitBreakerConfig())

        # Same query twice in a row for same hypothesis
        events = [
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 1 LIMIT 10"},
            ),
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 1 LIMIT 10"},
            ),
        ]

        with pytest.raises(CircuitBreakerTripped) as exc_info:
            breaker.check(events, "h001")

        assert "Duplicate query" in str(exc_info.value)
