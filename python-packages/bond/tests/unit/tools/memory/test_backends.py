"""Tests for memory backends."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from bond.tools.memory._models import Error, Memory, SearchResult
from bond.tools.memory.backends import (
    MemoryBackendType,
    PgVectorMemoryStore,
    QdrantMemoryStore,
    create_memory_backend,
)

# Shared test tenant ID
TEST_TENANT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


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
            tenant_id=TEST_TENANT_ID,
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
            tenant_id=TEST_TENANT_ID,
            conversation_id="conv-123",
        )

        assert isinstance(result, Memory)
        assert result.conversation_id == "conv-123"

    async def test_search_finds_similar_memories(self, store: QdrantMemoryStore) -> None:
        """Test semantic search returns similar memories."""
        # Store some memories
        await store.store(
            content="User prefers dark mode",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )
        await store.store(
            content="User likes compact view",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )
        await store.store(
            content="Project deadline is March 15",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )

        # Search for UI preferences
        results = await store.search(
            query="UI theme preferences",
            tenant_id=TEST_TENANT_ID,
            top_k=2,
        )

        assert isinstance(results, list)
        assert len(results) <= 2
        # Dark mode should be most relevant
        if results:
            assert isinstance(results[0], SearchResult)
            assert (
                "dark mode" in results[0].memory.content.lower()
                or "compact" in results[0].memory.content.lower()
            )

    async def test_search_filters_by_agent_id(self, store: QdrantMemoryStore) -> None:
        """Test search can filter by agent_id."""
        await store.store(
            content="Memory from agent1",
            agent_id="agent1",
            tenant_id=TEST_TENANT_ID,
        )
        await store.store(
            content="Memory from agent2",
            agent_id="agent2",
            tenant_id=TEST_TENANT_ID,
        )

        results = await store.search(
            query="memory",
            tenant_id=TEST_TENANT_ID,
            agent_id="agent1",
        )

        assert isinstance(results, list)
        for result in results:
            assert result.memory.agent_id == "agent1"

    async def test_search_filters_by_tags(self, store: QdrantMemoryStore) -> None:
        """Test search can filter by tags."""
        await store.store(
            content="UI preference",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
            tags=["ui"],
        )
        await store.store(
            content="API endpoint",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
            tags=["api"],
        )

        results = await store.search(
            query="preference",
            tenant_id=TEST_TENANT_ID,
            tags=["ui"],
        )

        assert isinstance(results, list)
        for result in results:
            assert "ui" in result.memory.tags

    async def test_search_with_score_threshold(self, store: QdrantMemoryStore) -> None:
        """Test search respects score threshold."""
        await store.store(
            content="User prefers dark mode",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )
        await store.store(
            content="Completely unrelated content about cats",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )

        # High threshold should filter low-relevance results
        results = await store.search(
            query="dark theme preferences",
            tenant_id=TEST_TENANT_ID,
            score_threshold=0.5,
        )

        assert isinstance(results, list)
        for result in results:
            assert result.score >= 0.5

    async def test_get_returns_memory_by_id(self, store: QdrantMemoryStore) -> None:
        """Test retrieving a specific memory by ID."""
        stored = await store.store(
            content="Find me later",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )
        assert isinstance(stored, Memory)

        retrieved = await store.get(stored.id, tenant_id=TEST_TENANT_ID)

        assert isinstance(retrieved, Memory)
        assert retrieved.id == stored.id
        assert retrieved.content == "Find me later"

    async def test_get_returns_none_for_unknown_id(self, store: QdrantMemoryStore) -> None:
        """Test get returns None for non-existent memory."""
        result = await store.get(uuid4(), tenant_id=TEST_TENANT_ID)

        assert result is None

    async def test_get_returns_none_for_wrong_tenant(self, store: QdrantMemoryStore) -> None:
        """Test get returns None when memory belongs to different tenant."""
        stored = await store.store(
            content="Tenant A memory",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )
        assert isinstance(stored, Memory)

        # Try to get with different tenant
        other_tenant = UUID("660e8400-e29b-41d4-a716-446655440000")
        retrieved = await store.get(stored.id, tenant_id=other_tenant)

        assert retrieved is None

    async def test_delete_removes_memory(self, store: QdrantMemoryStore) -> None:
        """Test deleting a memory."""
        stored = await store.store(
            content="Delete me",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )
        assert isinstance(stored, Memory)

        result = await store.delete(stored.id, tenant_id=TEST_TENANT_ID)

        assert result is True

        # Verify it's gone
        retrieved = await store.get(stored.id, tenant_id=TEST_TENANT_ID)
        assert retrieved is None

    async def test_store_with_precomputed_embedding(self, store: QdrantMemoryStore) -> None:
        """Test storing memory with pre-computed embedding."""
        # 384 is the dimension for all-MiniLM-L6-v2 (the default model)
        dim = 384
        embedding = [0.1] * dim

        result = await store.store(
            content="Pre-embedded content",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
            embedding=embedding,
        )

        assert isinstance(result, Memory)
        assert result.content == "Pre-embedded content"

    async def test_tenant_isolation(self, store: QdrantMemoryStore) -> None:
        """Test that memories are isolated by tenant."""
        tenant_a = UUID("550e8400-e29b-41d4-a716-446655440000")
        tenant_b = UUID("660e8400-e29b-41d4-a716-446655440000")

        # Store memories for each tenant
        await store.store(
            content="Tenant A secret",
            agent_id="agent",
            tenant_id=tenant_a,
        )
        await store.store(
            content="Tenant B secret",
            agent_id="agent",
            tenant_id=tenant_b,
        )

        # Search should only return tenant's own memories
        results_a = await store.search(
            query="secret",
            tenant_id=tenant_a,
        )
        results_b = await store.search(
            query="secret",
            tenant_id=tenant_b,
        )

        assert isinstance(results_a, list)
        assert isinstance(results_b, list)

        # Verify tenant isolation
        for r in results_a:
            assert "Tenant A" in r.memory.content or r.memory.content == "Tenant A secret"
        for r in results_b:
            assert "Tenant B" in r.memory.content or r.memory.content == "Tenant B secret"


class TestPgVectorMemoryStore:
    """Tests for PgVectorMemoryStore backend (mocked)."""

    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        """Create a mocked asyncpg Pool."""
        pool = MagicMock()
        pool.execute = AsyncMock()
        pool.fetch = AsyncMock(return_value=[])
        pool.fetchrow = AsyncMock(return_value=None)
        return pool

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        """Create a mocked embedder."""
        embedder = MagicMock()
        embed_result = MagicMock()
        embed_result.embeddings = [[0.1] * 1536]
        embedder.embed_query = AsyncMock(return_value=embed_result)
        return embedder

    @pytest.fixture
    def store(self, mock_pool: MagicMock, mock_embedder: MagicMock) -> PgVectorMemoryStore:
        """Create a PgVectorMemoryStore with mocked dependencies."""
        with patch("bond.tools.memory.backends.pgvector.Embedder") as MockEmbedder:
            MockEmbedder.return_value = mock_embedder
            return PgVectorMemoryStore(pool=mock_pool)

    async def test_store_creates_memory(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that store executes INSERT and returns Memory."""
        result = await store.store(
            content="Test content",
            agent_id="test-agent",
            tenant_id=TEST_TENANT_ID,
            tags=["test"],
        )

        assert isinstance(result, Memory)
        assert result.content == "Test content"
        assert result.agent_id == "test-agent"
        assert result.tags == ["test"]
        mock_pool.execute.assert_called_once()

    async def test_store_with_conversation_id(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test storing memory with conversation context."""
        result = await store.store(
            content="Discussion",
            agent_id="assistant",
            tenant_id=TEST_TENANT_ID,
            conversation_id="conv-123",
        )

        assert isinstance(result, Memory)
        assert result.conversation_id == "conv-123"

    async def test_store_with_precomputed_embedding(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test storing memory with pre-computed embedding skips embed call."""
        embedding = [0.1] * 1536

        result = await store.store(
            content="Pre-embedded",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
            embedding=embedding,
        )

        assert isinstance(result, Memory)
        # Should have called execute with the provided embedding
        mock_pool.execute.assert_called_once()

    async def test_store_returns_error_on_failure(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that store returns Error on database failure."""
        mock_pool.execute.side_effect = Exception("DB connection failed")

        result = await store.store(
            content="Will fail",
            agent_id="agent",
            tenant_id=TEST_TENANT_ID,
        )

        assert isinstance(result, Error)
        assert "Failed to store memory" in result.description

    async def test_search_returns_results(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that search returns SearchResult list."""
        # Mock database response
        mock_row = {
            "id": uuid4(),
            "content": "Found content",
            "conversation_id": None,
            "tags": ["test"],
            "agent_id": "agent",
            "created_at": datetime.now(UTC),
            "score": 0.85,
        }
        mock_pool.fetch.return_value = [mock_row]

        results = await store.search(
            query="find content",
            tenant_id=TEST_TENANT_ID,
        )

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].memory.content == "Found content"
        assert results[0].score == 0.85

    async def test_search_with_filters(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test search with agent_id and tags filters."""
        mock_pool.fetch.return_value = []

        await store.search(
            query="test",
            tenant_id=TEST_TENANT_ID,
            agent_id="specific-agent",
            tags=["important"],
        )

        # Verify query was called with filters
        call_args = mock_pool.fetch.call_args
        assert call_args is not None
        query = call_args[0][0]
        assert "agent_id = " in query
        assert "tags @>" in query

    async def test_search_returns_error_on_failure(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that search returns Error on database failure."""
        mock_pool.fetch.side_effect = Exception("Query failed")

        result = await store.search(
            query="test",
            tenant_id=TEST_TENANT_ID,
        )

        assert isinstance(result, Error)
        assert "Failed to search memories" in result.description

    async def test_get_returns_memory(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that get returns Memory when found."""
        memory_id = uuid4()
        mock_pool.fetchrow.return_value = {
            "id": memory_id,
            "content": "Found",
            "conversation_id": "conv-1",
            "tags": ["tag1"],
            "agent_id": "agent",
            "created_at": datetime.now(UTC),
        }

        result = await store.get(memory_id, tenant_id=TEST_TENANT_ID)

        assert isinstance(result, Memory)
        assert result.id == memory_id
        assert result.content == "Found"

    async def test_get_returns_none_when_not_found(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that get returns None when not found."""
        mock_pool.fetchrow.return_value = None

        result = await store.get(uuid4(), tenant_id=TEST_TENANT_ID)

        assert result is None

    async def test_get_returns_error_on_failure(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that get returns Error on database failure."""
        mock_pool.fetchrow.side_effect = Exception("Query failed")

        result = await store.get(uuid4(), tenant_id=TEST_TENANT_ID)

        assert isinstance(result, Error)
        assert "Failed to retrieve memory" in result.description

    async def test_delete_returns_true_on_success(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that delete returns True when row is deleted."""
        mock_pool.execute.return_value = "DELETE 1"

        result = await store.delete(uuid4(), tenant_id=TEST_TENANT_ID)

        assert result is True

    async def test_delete_returns_false_when_not_found(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that delete returns False when row not found."""
        mock_pool.execute.return_value = "DELETE 0"

        result = await store.delete(uuid4(), tenant_id=TEST_TENANT_ID)

        assert result is False

    async def test_delete_returns_error_on_failure(
        self, store: PgVectorMemoryStore, mock_pool: MagicMock
    ) -> None:
        """Test that delete returns Error on database failure."""
        mock_pool.execute.side_effect = Exception("Delete failed")

        result = await store.delete(uuid4(), tenant_id=TEST_TENANT_ID)

        assert isinstance(result, Error)
        assert "Failed to delete memory" in result.description


class TestBackendFactory:
    """Tests for create_memory_backend factory function."""

    def test_pgvector_requires_pool(self) -> None:
        """Test that pgvector backend raises ValueError without pool."""
        with pytest.raises(ValueError, match="pgvector backend requires asyncpg Pool"):
            create_memory_backend(backend_type=MemoryBackendType.PGVECTOR, pool=None)

    def test_pgvector_creates_store_with_pool(self) -> None:
        """Test that pgvector backend is created with pool."""
        mock_pool = MagicMock()

        with patch("bond.tools.memory.backends.pgvector.Embedder"):
            store = create_memory_backend(
                backend_type=MemoryBackendType.PGVECTOR,
                pool=mock_pool,
            )

        assert isinstance(store, PgVectorMemoryStore)

    def test_pgvector_uses_custom_table_name(self) -> None:
        """Test that pgvector backend uses custom table name."""
        mock_pool = MagicMock()

        with patch("bond.tools.memory.backends.pgvector.Embedder"):
            store = create_memory_backend(
                backend_type=MemoryBackendType.PGVECTOR,
                pool=mock_pool,
                table_name="custom_memories",
            )

        assert store._table == "custom_memories"

    def test_qdrant_creates_store(self) -> None:
        """Test that qdrant backend is created."""
        store = create_memory_backend(backend_type=MemoryBackendType.QDRANT)

        assert isinstance(store, QdrantMemoryStore)

    def test_qdrant_uses_custom_collection(self) -> None:
        """Test that qdrant backend uses custom collection name."""
        store = create_memory_backend(
            backend_type=MemoryBackendType.QDRANT,
            collection_name="custom_collection",
        )

        assert store._collection == "custom_collection"

    def test_default_backend_is_pgvector(self) -> None:
        """Test that default backend type is pgvector."""
        mock_pool = MagicMock()

        with patch("bond.tools.memory.backends.pgvector.Embedder"):
            store = create_memory_backend(pool=mock_pool)

        assert isinstance(store, PgVectorMemoryStore)

    def test_embedding_model_passed_to_backend(self) -> None:
        """Test that embedding model is passed to backend."""
        store = create_memory_backend(
            backend_type=MemoryBackendType.QDRANT,
            embedding_model="openai:text-embedding-3-small",
        )

        # The embedder is created with the specified model
        assert store._embedder is not None
