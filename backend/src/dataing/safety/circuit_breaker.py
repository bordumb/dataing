"""Circuit Breaker - Safety limits to prevent runaway execution.

This module implements the circuit breaker pattern to prevent
investigations from consuming excessive resources or entering
infinite loops.

All checks are performed before each query execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from dataing.core.exceptions import CircuitBreakerTripped
from dataing.core.state import Event


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker limits.

    All limits are designed to be generous enough for normal
    investigations but strict enough to prevent runaway execution.

    Attributes:
        max_total_queries: Maximum queries across all hypotheses.
        max_queries_per_hypothesis: Maximum queries for a single hypothesis.
        max_retries_per_hypothesis: Maximum retry attempts per hypothesis.
        max_consecutive_failures: Maximum consecutive query failures.
        max_duration_seconds: Maximum investigation duration.
    """

    max_total_queries: int = 50
    max_queries_per_hypothesis: int = 5
    max_retries_per_hypothesis: int = 2
    max_consecutive_failures: int = 3
    max_duration_seconds: int = 600  # 10 minutes


class CircuitBreaker:
    """Safety limits to prevent runaway execution.

    Checks are performed before each query execution.
    Any limit violation raises CircuitBreakerTripped.

    Usage:
        breaker = CircuitBreaker(CircuitBreakerConfig())
        breaker.check(state.events, hypothesis_id)  # Raises if limit exceeded
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        """Initialize circuit breaker.

        Args:
            config: Configuration for limits. Uses defaults if not provided.
        """
        self.config = config or CircuitBreakerConfig()

    def check(self, events: list[Event], hypothesis_id: str | None = None) -> None:
        """Check all circuit breaker conditions.

        This method should be called before executing each query.
        It checks all safety conditions and raises an exception
        if any limit is exceeded.

        Args:
            events: List of all events in the investigation.
            hypothesis_id: Optional hypothesis ID for per-hypothesis checks.

        Raises:
            CircuitBreakerTripped: If any limit exceeded.
        """
        self._check_total_queries(events)
        self._check_consecutive_failures(events)
        self._check_duplicate_queries(events, hypothesis_id)

        if hypothesis_id:
            self._check_hypothesis_queries(events, hypothesis_id)
            self._check_hypothesis_retries(events, hypothesis_id)

    def _check_total_queries(self, events: list[Event]) -> None:
        """Check if total query limit is exceeded.

        Args:
            events: List of all events.

        Raises:
            CircuitBreakerTripped: If limit exceeded.
        """
        count = sum(1 for e in events if e.type == "query_submitted")
        if count >= self.config.max_total_queries:
            raise CircuitBreakerTripped(
                f"Total query limit reached: {count}/{self.config.max_total_queries}"
            )

    def _check_hypothesis_queries(self, events: list[Event], hypothesis_id: str) -> None:
        """Check if per-hypothesis query limit is exceeded.

        Args:
            events: List of all events.
            hypothesis_id: ID of the hypothesis.

        Raises:
            CircuitBreakerTripped: If limit exceeded.
        """
        count = sum(
            1
            for e in events
            if e.type == "query_submitted" and e.data.get("hypothesis_id") == hypothesis_id
        )
        if count >= self.config.max_queries_per_hypothesis:
            raise CircuitBreakerTripped(
                f"Hypothesis query limit reached: {count}/{self.config.max_queries_per_hypothesis}"
            )

    def _check_hypothesis_retries(self, events: list[Event], hypothesis_id: str) -> None:
        """Check if per-hypothesis retry limit is exceeded.

        Args:
            events: List of all events.
            hypothesis_id: ID of the hypothesis.

        Raises:
            CircuitBreakerTripped: If limit exceeded.
        """
        count = sum(
            1
            for e in events
            if e.type == "reflexion_attempted" and e.data.get("hypothesis_id") == hypothesis_id
        )
        if count >= self.config.max_retries_per_hypothesis:
            raise CircuitBreakerTripped(
                f"Hypothesis retry limit reached: {count}/{self.config.max_retries_per_hypothesis}"
            )

    def _check_consecutive_failures(self, events: list[Event]) -> None:
        """Check if consecutive failure limit is exceeded.

        Args:
            events: List of all events.

        Raises:
            CircuitBreakerTripped: If limit exceeded.
        """
        consecutive = 0
        for event in reversed(events):
            if event.type == "query_failed":
                consecutive += 1
            elif event.type == "query_succeeded":
                break

        if consecutive >= self.config.max_consecutive_failures:
            raise CircuitBreakerTripped(f"Consecutive failure limit reached: {consecutive}")

    def _check_duplicate_queries(
        self, events: list[Event], hypothesis_id: str | None
    ) -> None:
        """Detect if same query is being generated repeatedly (stall).

        This catches situations where the LLM keeps generating
        the same failing query, indicating a stall condition.

        Args:
            events: List of all events.
            hypothesis_id: ID of the hypothesis.

        Raises:
            CircuitBreakerTripped: If duplicate detected.
        """
        if not hypothesis_id:
            return

        queries = [
            e.data.get("query", "")
            for e in events
            if e.type == "query_submitted" and e.data.get("hypothesis_id") == hypothesis_id
        ]

        if len(queries) >= 2 and queries[-1] == queries[-2]:
            raise CircuitBreakerTripped("Duplicate query detected - investigation stalled")
