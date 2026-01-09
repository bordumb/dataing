"""Tests for memory backends."""

import pytest

from bond.tools.memory._models import Error, Memory, SearchResult
from bond.tools.memory.backends import QdrantMemoryStore


class TestQdrantMemoryStore:
    """Tests for QdrantMemoryStore backend."""

    @pytest.fixture
    def store(self) -> QdrantMemoryStore:
        """Create an in-memory Qdrant store for testing."""
        return QdrantMemoryStore()

    async def test_store_creates_memory(self, store: QdrantMemoryStore) -> None:
        """Test that store creates a memory with generated embedding."""
        result = await store.store(
            content="Remember user prefers dark mode",
            agent_id="test-agent",
            tags=["preferences"],
        )

        assert isinstance(result, Memory)
        assert result.content == "Remember user prefers dark mode"
        assert result.agent_id == "test-agent"
        assert result.tags == ["preferences"]
        assert result.id is not None
        assert result.created_at is not None

    async def test_store_with_conversation_id(self, store: QdrantMemoryStore) -> None:
        """Test storing memory with conversation context."""
        result = await store.store(
            content="Discussion about auth flow",
            agent_id="assistant",
            conversation_id="conv-123",
        )

        assert isinstance(result, Memory)
        assert result.conversation_id == "conv-123"

    async def test_search_finds_similar_memories(self, store: QdrantMemoryStore) -> None:
        """Test semantic search returns similar memories."""
        # Store some memories
        await store.store(content="User prefers dark mode", agent_id="agent")
        await store.store(content="User likes compact view", agent_id="agent")
        await store.store(content="Project deadline is March 15", agent_id="agent")

        # Search for UI preferences
        results = await store.search(query="UI theme preferences", top_k=2)

        assert isinstance(results, list)
        assert len(results) <= 2
        # Dark mode should be most relevant
        if results:
            assert isinstance(results[0], SearchResult)
            assert "dark mode" in results[0].memory.content.lower() or "compact" in results[0].memory.content.lower()

    async def test_search_filters_by_agent_id(self, store: QdrantMemoryStore) -> None:
        """Test search can filter by agent_id."""
        await store.store(content="Memory from agent1", agent_id="agent1")
        await store.store(content="Memory from agent2", agent_id="agent2")

        results = await store.search(query="memory", agent_id="agent1")

        assert isinstance(results, list)
        for result in results:
            assert result.memory.agent_id == "agent1"

    async def test_search_filters_by_tags(self, store: QdrantMemoryStore) -> None:
        """Test search can filter by tags."""
        await store.store(content="UI preference", agent_id="agent", tags=["ui"])
        await store.store(content="API endpoint", agent_id="agent", tags=["api"])

        results = await store.search(query="preference", tags=["ui"])

        assert isinstance(results, list)
        for result in results:
            assert "ui" in result.memory.tags

    async def test_search_with_score_threshold(self, store: QdrantMemoryStore) -> None:
        """Test search respects score threshold."""
        await store.store(content="User prefers dark mode", agent_id="agent")
        await store.store(content="Completely unrelated content about cats", agent_id="agent")

        # High threshold should filter low-relevance results
        results = await store.search(
            query="dark theme preferences",
            score_threshold=0.5,
        )

        assert isinstance(results, list)
        for result in results:
            assert result.score >= 0.5

    async def test_get_returns_memory_by_id(self, store: QdrantMemoryStore) -> None:
        """Test retrieving a specific memory by ID."""
        stored = await store.store(content="Find me later", agent_id="agent")
        assert isinstance(stored, Memory)

        retrieved = await store.get(stored.id)

        assert isinstance(retrieved, Memory)
        assert retrieved.id == stored.id
        assert retrieved.content == "Find me later"

    async def test_get_returns_none_for_unknown_id(self, store: QdrantMemoryStore) -> None:
        """Test get returns None for non-existent memory."""
        from uuid import uuid4

        result = await store.get(uuid4())

        assert result is None

    async def test_delete_removes_memory(self, store: QdrantMemoryStore) -> None:
        """Test deleting a memory."""
        stored = await store.store(content="Delete me", agent_id="agent")
        assert isinstance(stored, Memory)

        result = await store.delete(stored.id)

        assert result is True

        # Verify it's gone
        retrieved = await store.get(stored.id)
        assert retrieved is None

    async def test_store_with_precomputed_embedding(self, store: QdrantMemoryStore) -> None:
        """Test storing memory with pre-computed embedding."""
        # Get expected dimension from model
        model = store._get_model(None)
        dim = model.get_sentence_embedding_dimension() or 384
        embedding = [0.1] * dim

        result = await store.store(
            content="Pre-embedded content",
            agent_id="agent",
            embedding=embedding,
        )

        assert isinstance(result, Memory)
        assert result.content == "Pre-embedded content"

    async def test_search_with_custom_embedding_model(self, store: QdrantMemoryStore) -> None:
        """Test search with different embedding model."""
        # Store with default model
        await store.store(content="Default model content", agent_id="agent")

        # Search with same model (should work)
        results = await store.search(
            query="content",
            embedding_model="all-MiniLM-L6-v2",  # Same as default
        )

        assert isinstance(results, list)
