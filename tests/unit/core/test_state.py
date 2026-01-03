"""Unit tests for InvestigationState."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dataing.core.domain_types import AnomalyAlert, SchemaContext, TableSchema, LineageContext
from dataing.core.state import Event, InvestigationState


class TestEvent:
    """Tests for Event."""

    def test_create_event(self) -> None:
        """Test creating an event."""
        event = Event(
            type="investigation_started",
            timestamp=datetime.now(timezone.utc),
            data={"dataset_id": "public.orders"},
        )

        assert event.type == "investigation_started"
        assert "dataset_id" in event.data

    def test_event_is_frozen(self) -> None:
        """Test that event is immutable."""
        event = Event(
            type="investigation_started",
            timestamp=datetime.now(timezone.utc),
            data={},
        )

        with pytest.raises(Exception):
            event.type = "modified"


class TestInvestigationState:
    """Tests for InvestigationState."""

    @pytest.fixture
    def alert(self) -> AnomalyAlert:
        """Return a sample anomaly alert."""
        return AnomalyAlert(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            severity="high",
        )

    @pytest.fixture
    def state(self, alert: AnomalyAlert) -> InvestigationState:
        """Return a sample investigation state."""
        return InvestigationState(id="inv-001", alert=alert)

    def test_create_state(self, alert: AnomalyAlert) -> None:
        """Test creating investigation state."""
        state = InvestigationState(id="inv-001", alert=alert)

        assert state.id == "inv-001"
        assert state.alert == alert
        assert state.events == []

    def test_status_pending_when_no_events(self, state: InvestigationState) -> None:
        """Test status is pending when no events."""
        assert state.status == "pending"

    def test_status_completed(self, state: InvestigationState) -> None:
        """Test status is completed after synthesis."""
        event = Event(
            type="synthesis_completed",
            timestamp=datetime.now(timezone.utc),
            data={},
        )
        state.events.append(event)

        assert state.status == "completed"

    def test_status_failed(self, state: InvestigationState) -> None:
        """Test status is failed after failure event."""
        event = Event(
            type="investigation_failed",
            timestamp=datetime.now(timezone.utc),
            data={"error": "Something went wrong"},
        )
        state.events.append(event)

        assert state.status == "failed"

    def test_status_in_progress(self, state: InvestigationState) -> None:
        """Test status is in_progress during investigation."""
        event = Event(
            type="hypothesis_generated",
            timestamp=datetime.now(timezone.utc),
            data={},
        )
        state.events.append(event)

        assert state.status == "in_progress"

    def test_get_retry_count(self, state: InvestigationState) -> None:
        """Test counting retry attempts."""
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
            Event(
                type="reflexion_attempted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h002"},
            ),
        ]
        state.events = events

        assert state.get_retry_count("h001") == 2
        assert state.get_retry_count("h002") == 1
        assert state.get_retry_count("h003") == 0

    def test_get_query_count(self, state: InvestigationState) -> None:
        """Test counting total queries."""
        events = [
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT 1"},
            ),
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h002", "query": "SELECT 2"},
            ),
        ]
        state.events = events

        assert state.get_query_count() == 2

    def test_get_hypothesis_query_count(self, state: InvestigationState) -> None:
        """Test counting queries per hypothesis."""
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
            Event(
                type="query_submitted",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h002", "query": "SELECT 3"},
            ),
        ]
        state.events = events

        assert state.get_hypothesis_query_count("h001") == 2
        assert state.get_hypothesis_query_count("h002") == 1

    def test_get_failed_queries(self, state: InvestigationState) -> None:
        """Test getting failed queries."""
        events = [
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT invalid"},
            ),
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={"hypothesis_id": "h001", "query": "SELECT also_invalid"},
            ),
        ]
        state.events = events

        failed = state.get_failed_queries("h001")

        assert len(failed) == 2
        assert "SELECT invalid" in failed
        assert "SELECT also_invalid" in failed

    def test_get_all_queries(self, state: InvestigationState) -> None:
        """Test getting all queries for a hypothesis."""
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
        state.events = events

        queries = state.get_all_queries("h001")

        assert len(queries) == 2
        assert "SELECT 1" in queries
        assert "SELECT 2" in queries

    def test_get_consecutive_failures(self, state: InvestigationState) -> None:
        """Test counting consecutive failures."""
        events = [
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
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={},
            ),
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={},
            ),
        ]
        state.events = events

        assert state.get_consecutive_failures() == 3

    def test_get_consecutive_failures_reset(self, state: InvestigationState) -> None:
        """Test that consecutive failures reset on success."""
        events = [
            Event(
                type="query_failed",
                timestamp=datetime.now(timezone.utc),
                data={},
            ),
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
        state.events = events

        assert state.get_consecutive_failures() == 1

    def test_append_event(self, state: InvestigationState) -> None:
        """Test appending an event returns new state."""
        event = Event(
            type="investigation_started",
            timestamp=datetime.now(timezone.utc),
            data={},
        )

        new_state = state.append_event(event)

        assert len(new_state.events) == 1
        assert len(state.events) == 0  # Original unchanged
        assert new_state.id == state.id

    def test_with_context(self, state: InvestigationState) -> None:
        """Test setting context returns new state."""
        schema = SchemaContext(
            tables=(
                TableSchema(
                    table_name="public.orders",
                    columns=("id",),
                ),
            )
        )
        lineage = LineageContext(
            target="public.orders",
            upstream=(),
            downstream=(),
        )

        new_state = state.with_context(schema_context=schema, lineage_context=lineage)

        assert new_state.schema_context == schema
        assert new_state.lineage_context == lineage
        assert state.schema_context is None  # Original unchanged
