"""Tests for memory data models."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from bond.tools.memory._models import (
    CreateMemoryRequest,
    DeleteMemoryRequest,
    Error,
    GetMemoryRequest,
    Memory,
    SearchMemoriesRequest,
    SearchResult,
)

# Shared test tenant ID
TEST_TENANT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


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
            tenant_id=TEST_TENANT_ID,
        )
        assert request.content == "Remember this"
        assert request.agent_id == "agent-1"
        assert request.tenant_id == TEST_TENANT_ID
        assert request.embedding is None
        assert request.embedding_model is None

    def test_creates_request_with_embedding(self) -> None:
        """Test request creation with pre-computed embedding."""
        embedding = [0.1, 0.2, 0.3]
        request = CreateMemoryRequest(
            content="Remember this",
            agent_id="agent-1",
            tenant_id=TEST_TENANT_ID,
            embedding=embedding,
            embedding_model="custom-model",
        )
        assert request.embedding == embedding
        assert request.embedding_model == "custom-model"

    def test_requires_tenant_id(self) -> None:
        """Test that tenant_id is required."""
        with pytest.raises(ValueError):
            CreateMemoryRequest(
                content="Remember this",
                agent_id="agent-1",
            )


class TestSearchMemoriesRequest:
    """Tests for SearchMemoriesRequest model."""

    def test_creates_request_with_defaults(self) -> None:
        """Test request creation with default values."""
        request = SearchMemoriesRequest(
            query="find something",
            tenant_id=TEST_TENANT_ID,
        )
        assert request.query == "find something"
        assert request.tenant_id == TEST_TENANT_ID
        assert request.top_k == 10
        assert request.score_threshold is None
        assert request.tags is None

    def test_validates_top_k_range(self) -> None:
        """Test that top_k is validated."""
        # Valid range
        request = SearchMemoriesRequest(
            query="test",
            tenant_id=TEST_TENANT_ID,
            top_k=50,
        )
        assert request.top_k == 50

        # Invalid: too low
        with pytest.raises(ValueError):
            SearchMemoriesRequest(
                query="test",
                tenant_id=TEST_TENANT_ID,
                top_k=0,
            )

        # Invalid: too high
        with pytest.raises(ValueError):
            SearchMemoriesRequest(
                query="test",
                tenant_id=TEST_TENANT_ID,
                top_k=101,
            )

    def test_requires_tenant_id(self) -> None:
        """Test that tenant_id is required."""
        with pytest.raises(ValueError):
            SearchMemoriesRequest(query="find something")


class TestDeleteMemoryRequest:
    """Tests for DeleteMemoryRequest model."""

    def test_creates_request(self) -> None:
        """Test request creation."""
        memory_id = uuid4()
        request = DeleteMemoryRequest(
            memory_id=memory_id,
            tenant_id=TEST_TENANT_ID,
        )
        assert request.memory_id == memory_id
        assert request.tenant_id == TEST_TENANT_ID

    def test_requires_tenant_id(self) -> None:
        """Test that tenant_id is required."""
        with pytest.raises(ValueError):
            DeleteMemoryRequest(memory_id=uuid4())


class TestGetMemoryRequest:
    """Tests for GetMemoryRequest model."""

    def test_creates_request(self) -> None:
        """Test request creation."""
        memory_id = uuid4()
        request = GetMemoryRequest(
            memory_id=memory_id,
            tenant_id=TEST_TENANT_ID,
        )
        assert request.memory_id == memory_id
        assert request.tenant_id == TEST_TENANT_ID

    def test_requires_tenant_id(self) -> None:
        """Test that tenant_id is required."""
        with pytest.raises(ValueError):
            GetMemoryRequest(memory_id=uuid4())


class TestError:
    """Tests for Error model."""

    def test_creates_error(self) -> None:
        """Test error creation."""
        error = Error(description="Something went wrong")
        assert error.description == "Something went wrong"
