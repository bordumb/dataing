"""Tests for memory data models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from bond.tools.memory._models import (
    CreateMemoryRequest,
    Error,
    Memory,
    SearchMemoriesRequest,
    SearchResult,
)


class TestMemory:
    """Tests for Memory model."""

    def test_creates_memory_with_required_fields(self) -> None:
        """Test memory creation with required fields."""
        memory = Memory(
            id=uuid4(),
            content="Test content",
            created_at=datetime.now(UTC),
            agent_id="test-agent",
        )
        assert memory.content == "Test content"
        assert memory.agent_id == "test-agent"
        assert memory.conversation_id is None
        assert memory.tags == []

    def test_creates_memory_with_all_fields(self) -> None:
        """Test memory creation with all fields."""
        memory = Memory(
            id=uuid4(),
            content="Test content",
            created_at=datetime.now(UTC),
            agent_id="test-agent",
            conversation_id="conv-123",
            tags=["tag1", "tag2"],
        )
        assert memory.conversation_id == "conv-123"
        assert memory.tags == ["tag1", "tag2"]


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_creates_search_result(self) -> None:
        """Test search result creation."""
        memory = Memory(
            id=uuid4(),
            content="Test",
            created_at=datetime.now(UTC),
            agent_id="agent",
        )
        result = SearchResult(memory=memory, score=0.95)
        assert result.memory == memory
        assert result.score == 0.95


class TestCreateMemoryRequest:
    """Tests for CreateMemoryRequest model."""

    def test_creates_request_with_required_fields(self) -> None:
        """Test request creation with required fields."""
        request = CreateMemoryRequest(
            content="Remember this",
            agent_id="agent-1",
        )
        assert request.content == "Remember this"
        assert request.agent_id == "agent-1"
        assert request.embedding is None
        assert request.embedding_model is None

    def test_creates_request_with_embedding(self) -> None:
        """Test request creation with pre-computed embedding."""
        embedding = [0.1, 0.2, 0.3]
        request = CreateMemoryRequest(
            content="Remember this",
            agent_id="agent-1",
            embedding=embedding,
            embedding_model="custom-model",
        )
        assert request.embedding == embedding
        assert request.embedding_model == "custom-model"


class TestSearchMemoriesRequest:
    """Tests for SearchMemoriesRequest model."""

    def test_creates_request_with_defaults(self) -> None:
        """Test request creation with default values."""
        request = SearchMemoriesRequest(query="find something")
        assert request.query == "find something"
        assert request.top_k == 10
        assert request.score_threshold is None
        assert request.tags is None

    def test_validates_top_k_range(self) -> None:
        """Test that top_k is validated."""
        # Valid range
        request = SearchMemoriesRequest(query="test", top_k=50)
        assert request.top_k == 50

        # Invalid: too low
        with pytest.raises(ValueError):
            SearchMemoriesRequest(query="test", top_k=0)

        # Invalid: too high
        with pytest.raises(ValueError):
            SearchMemoriesRequest(query="test", top_k=101)


class TestError:
    """Tests for Error model."""

    def test_creates_error(self) -> None:
        """Test error creation."""
        error = Error(description="Something went wrong")
        assert error.description == "Something went wrong"
