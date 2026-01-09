"""Unit tests for CircuitBreaker."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dataing.core.exceptions import CircuitBreakerTripped
from dataing.core.state import Event
from dataing.safety.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = CircuitBreakerConfig()

        assert config.max_total_queries == 50
        assert config.max_queries_per_hypothesis == 5
        assert config.max_retries_per_hypothesis == 2
        assert config.max_consecutive_failures == 3
        assert config.max_duration_seconds == 600

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            max_total_queries=10,
            max_queries_per_hypothesis=2,
        )

        assert config.max_total_queries == 10
        assert config.max_queries_per_hypothesis == 2

    def test_frozen(self) -> None:
        """Test that config is immutable."""
        config = CircuitBreakerConfig()

        with pytest.raises(Exception):
            config.max_total_queries = 100


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.fixture
    def breaker(self) -> CircuitBreaker:
        """Return a circuit breaker with default config."""
        return CircuitBreaker()

    @pytest.fixture
    def strict_breaker(self) -> CircuitBreaker:
        """Return a circuit breaker with strict limits."""
        return CircuitBreaker(
            CircuitBreakerConfig(
                max_total_queries=3,
                max_queries_per_hypothesis=2,
                max_retries_per_hypothesis=1,
                max_consecutive_failures=2,
            )
        )

    def test_init_default_config(self, breaker: CircuitBreaker) -> None:
        """Test initialization with default config."""
        assert breaker.config.max_total_queries == 50

    def test_init_custom_config(self, strict_breaker: CircuitBreaker) -> None:
        """Test initialization with custom config."""
        assert strict_breaker.config.max_total_queries == 3

    def test_check_passes_with_no_events(self, breaker: CircuitBreaker) -> None:
        """Test check passes with no events."""
        breaker.check([], "h001")  # Should not raise

    def test_check_total_queries_limit(self, strict_breaker: CircuitBreaker) -> None:
        """Test total query limit check."""
        events = [
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": f"h{i:03d}", "query": f"SELECT {i}"},
            )
            for i in range(3)
        ]

        with pytest.raises(CircuitBreakerTripped) as exc_info:
            strict_breaker.check(events, "h004")

        assert "Total query limit reached" in str(exc_info.value)

    def test_check_hypothesis_queries_limit(
        self,
        strict_breaker: CircuitBreaker,
    ) -> None:
        """Test per-hypothesis query limit check."""
        events = [
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": f"SELECT {i}"},
            )
            for i in range(2)
        ]

        with pytest.raises(CircuitBreakerTripped) as exc_info:
            strict_breaker.check(events, "h001")

        assert "Hypothesis query limit reached" in str(exc_info.value)

    def test_check_hypothesis_retries_limit(
        self,
        strict_breaker: CircuitBreaker,
    ) -> None:
        """Test per-hypothesis retry limit check."""
        events = [
            Event(
                type="reflexion_attempted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001"},
            )
        ]

        with pytest.raises(CircuitBreakerTripped) as exc_info:
            strict_breaker.check(events, "h001")

        assert "Hypothesis retry limit reached" in str(exc_info.value)

    def test_check_consecutive_failures_limit(
        self,
        strict_breaker: CircuitBreaker,
    ) -> None:
        """Test consecutive failures limit check."""
        events = [
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={},
            )
            for _ in range(2)
        ]

        with pytest.raises(CircuitBreakerTripped) as exc_info:
            strict_breaker.check(events)

        assert "Consecutive failure limit reached" in str(exc_info.value)

    def test_check_consecutive_failures_reset_on_success(
        self,
        strict_breaker: CircuitBreaker,
    ) -> None:
        """Test that consecutive failures reset on success."""
        events = [
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={},
            ),
            Event(
                type="query_succeeded",
                timestamp=datetime.now(timezone.utc),
                data={},
            ),
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={},
            ),
        ]

        # Should not raise - only 1 consecutive failure
        strict_breaker.check(events)

    def test_check_duplicate_queries(self, breaker: CircuitBreaker) -> None:
        """Test duplicate query detection."""
        events = [
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 1"},
            ),
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 1"},
            ),
        ]

        with pytest.raises(CircuitBreakerTripped) as exc_info:
            breaker.check(events, "h001")

        assert "Duplicate query detected" in str(exc_info.value)

    def test_check_different_queries_ok(self, breaker: CircuitBreaker) -> None:
        """Test that different queries don't trigger duplicate detection."""
        events = [
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 1"},
            ),
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 2"},
            ),
        ]

        breaker.check(events, "h001")  # Should not raise

    def test_check_other_hypothesis_doesnt_count(
        self,
        strict_breaker: CircuitBreaker,
    ) -> None:
        """Test that events from other hypotheses don't count."""
        events = [
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 1"},
            ),
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 2"},
            ),
        ]

        # Checking for h002 - should not hit h001's limit
        strict_breaker.check(events, "h002")  # Should not raise

    def test_check_without_hypothesis_id(self, breaker: CircuitBreaker) -> None:
        """Test check without hypothesis_id only checks global limits."""
        events = [
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={},
            ),
        ]

        # Should only check global limits
        breaker.check(events)  # Should not raise
