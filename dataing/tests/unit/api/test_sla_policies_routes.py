"""Unit tests for SLA Policies API routes."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from dataing.entrypoints.api.routes.sla_policies import (
    SeverityOverride,
    SLAPolicyCreate,
    SLAPolicyListResponse,
    SLAPolicyResponse,
    SLAPolicyUpdate,
)


class TestSeverityOverrideSchema:
    """Test SeverityOverride Pydantic schema."""

    def test_all_fields_optional(self) -> None:
        """Test all fields are optional."""
        override = SeverityOverride()
        assert override.time_to_acknowledge is None
        assert override.time_to_progress is None
        assert override.time_to_resolve is None

    def test_all_fields_set(self) -> None:
        """Test all fields can be set."""
        override = SeverityOverride(
            time_to_acknowledge=15,
            time_to_progress=30,
            time_to_resolve=60,
        )
        assert override.time_to_acknowledge == 15
        assert override.time_to_progress == 30
        assert override.time_to_resolve == 60


class TestSLAPolicyCreateSchema:
    """Test SLAPolicyCreate Pydantic schema."""

    def test_minimal_create(self) -> None:
        """Test creating policy with only required fields."""
        policy = SLAPolicyCreate(name="Default Policy")
        assert policy.name == "Default Policy"
        assert policy.is_default is False
        assert policy.time_to_acknowledge is None
        assert policy.time_to_progress is None
        assert policy.time_to_resolve is None
        assert policy.severity_overrides is None

    def test_full_create(self) -> None:
        """Test creating policy with all fields."""
        policy = SLAPolicyCreate(
            name="Critical SLA",
            is_default=True,
            time_to_acknowledge=60,
            time_to_progress=30,
            time_to_resolve=240,
            severity_overrides={
                "critical": SeverityOverride(
                    time_to_acknowledge=15,
                    time_to_resolve=60,
                )
            },
        )
        assert policy.name == "Critical SLA"
        assert policy.is_default is True
        assert policy.time_to_acknowledge == 60
        assert policy.time_to_progress == 30
        assert policy.time_to_resolve == 240
        assert policy.severity_overrides is not None
        assert "critical" in policy.severity_overrides

    def test_empty_name_invalid(self) -> None:
        """Test empty name is rejected."""
        with pytest.raises(ValueError):
            SLAPolicyCreate(name="")

    def test_long_name_invalid(self) -> None:
        """Test name over 100 chars is rejected."""
        with pytest.raises(ValueError):
            SLAPolicyCreate(name="x" * 101)

    def test_zero_time_invalid(self) -> None:
        """Test zero time values are rejected."""
        with pytest.raises(ValueError):
            SLAPolicyCreate(name="Test", time_to_acknowledge=0)

    def test_negative_time_invalid(self) -> None:
        """Test negative time values are rejected."""
        with pytest.raises(ValueError):
            SLAPolicyCreate(name="Test", time_to_acknowledge=-10)


class TestSLAPolicyUpdateSchema:
    """Test SLAPolicyUpdate Pydantic schema."""

    def test_all_fields_optional(self) -> None:
        """Test all fields are optional."""
        update = SLAPolicyUpdate()
        assert update.name is None
        assert update.is_default is None
        assert update.time_to_acknowledge is None
        assert update.time_to_progress is None
        assert update.time_to_resolve is None
        assert update.severity_overrides is None

    def test_partial_update(self) -> None:
        """Test partial update with some fields."""
        update = SLAPolicyUpdate(
            name="Updated Name",
            time_to_acknowledge=45,
        )
        assert update.name == "Updated Name"
        assert update.time_to_acknowledge == 45
        assert update.is_default is None

    def test_empty_name_invalid(self) -> None:
        """Test empty name is rejected."""
        with pytest.raises(ValueError):
            SLAPolicyUpdate(name="")


class TestSLAPolicyResponseSchema:
    """Test SLAPolicyResponse Pydantic schema."""

    def test_response_fields(self) -> None:
        """Test response has all expected fields."""
        now = datetime.now(UTC)
        response = SLAPolicyResponse(
            id=uuid4(),
            tenant_id=uuid4(),
            name="Test Policy",
            is_default=True,
            time_to_acknowledge=60,
            time_to_progress=30,
            time_to_resolve=120,
            severity_overrides={"critical": {"time_to_acknowledge": 15}},
            created_at=now,
            updated_at=now,
        )
        assert response.name == "Test Policy"
        assert response.is_default is True
        assert response.time_to_acknowledge == 60
        assert "critical" in response.severity_overrides

    def test_nullable_times(self) -> None:
        """Test time fields can be null."""
        now = datetime.now(UTC)
        response = SLAPolicyResponse(
            id=uuid4(),
            tenant_id=uuid4(),
            name="Minimal Policy",
            is_default=False,
            time_to_acknowledge=None,
            time_to_progress=None,
            time_to_resolve=None,
            severity_overrides={},
            created_at=now,
            updated_at=now,
        )
        assert response.time_to_acknowledge is None
        assert response.time_to_progress is None
        assert response.time_to_resolve is None


class TestSLAPolicyListResponseSchema:
    """Test SLAPolicyListResponse Pydantic schema."""

    def test_empty_list(self) -> None:
        """Test empty list response."""
        response = SLAPolicyListResponse(items=[], total=0)
        assert len(response.items) == 0
        assert response.total == 0

    def test_list_with_items(self) -> None:
        """Test list response with items."""
        now = datetime.now(UTC)
        policies = [
            SLAPolicyResponse(
                id=uuid4(),
                tenant_id=uuid4(),
                name=f"Policy {i}",
                is_default=i == 0,
                time_to_acknowledge=60,
                time_to_progress=30,
                time_to_resolve=120,
                severity_overrides={},
                created_at=now,
                updated_at=now,
            )
            for i in range(3)
        ]
        response = SLAPolicyListResponse(items=policies, total=3)
        assert len(response.items) == 3
        assert response.total == 3
        assert response.items[0].is_default is True
