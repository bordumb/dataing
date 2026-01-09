"""Memory backend implementations.

This module provides concrete implementations of AgentMemoryProtocol
using PydanticAI Embedder for non-blocking, instrumented embeddings.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic_ai.embeddings import Embedder
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from bond.tools.memory._models import Error, Memory, SearchResult


class QdrantMemoryStore:
    """Qdrant-backed memory store using PydanticAI Embedder.

    Benefits over raw sentence-transformers:
    - Non-blocking embeddings (runs in thread pool via run_in_executor)
    - Supports OpenAI, Cohere, and Local models seamlessly
    - Automatic cost/latency tracking via OpenTelemetry
    - Zero-refactor provider swapping

    Example:
        # In-memory for development/testing (local embeddings)
        store = QdrantMemoryStore()

        # Persistent with local embeddings
        store = QdrantMemoryStore(qdrant_url="http://localhost:6333")

        # OpenAI embeddings
        store = QdrantMemoryStore(
            embedding_model="openai:text-embedding-3-small",
            qdrant_url="http://localhost:6333",
        )

        # Cohere embeddings
        store = QdrantMemoryStore(
            embedding_model="cohere:embed-english-v3.0",
            qdrant_url="http://localhost:6333",
        )
    """

    def __init__(
        self,
        collection_name: str = "memories",
        embedding_model: str = "sentence-transformers:all-MiniLM-L6-v2",
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
    ) -> None:
        """Initialize the Qdrant memory store.

        Args:
            collection_name: Name of the Qdrant collection.
            embedding_model: Embedding model string. Supports:
                - "sentence-transformers:all-MiniLM-L6-v2" (local, default)
                - "openai:text-embedding-3-small"
                - "cohere:embed-english-v3.0"
            qdrant_url: Qdrant server URL. None = in-memory (for dev/testing).
            qdrant_api_key: Optional API key for Qdrant Cloud.
        """
        self._collection = collection_name

        # PydanticAI Embedder handles model logic + instrumentation
        self._embedder = Embedder(embedding_model)

        # Use AsyncQdrantClient for true async operation
        if qdrant_url:
            self._client = AsyncQdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        else:
            self._client = AsyncQdrantClient(":memory:")

        self._initialized = False

    async def _ensure_collection(self) -> None:
        """Lazy init collection with correct dimensions."""
        if self._initialized:
            return

        # Determine dimensions dynamically by generating a dummy embedding
        # Works for ANY provider (OpenAI, Cohere, Local)
        dummy_result = await self._embedder.embed_query("warmup")
        dimensions = len(dummy_result.embeddings[0])

        # Check and create collection
        collections = await self._client.get_collections()
        exists = any(c.name == self._collection for c in collections.collections)

        if not exists:
            await self._client.create_collection(
                self._collection,
                vectors_config=VectorParams(
                    size=dimensions,
                    distance=Distance.COSINE,
                ),
            )

        self._initialized = True

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding using PydanticAI Embedder.

        This is non-blocking (runs in thread pool) and instrumented.
        """
        result = await self._embedder.embed_query(text)
        return list(result.embeddings[0])

    def _build_filters(
        self,
        tags: list[str] | None,
        agent_id: str | None,
    ) -> Filter | None:
        """Build Qdrant filter from parameters."""
        conditions: list[FieldCondition] = []
        if agent_id:
            conditions.append(
                FieldCondition(key="agent_id", match=MatchValue(value=agent_id))
            )
        if tags:
            for tag in tags:
                conditions.append(
                    FieldCondition(key="tags", match=MatchValue(value=tag))
                )
        return Filter(must=conditions) if conditions else None

    async def store(
        self,
        content: str,
        agent_id: str,
        *,
        conversation_id: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> Memory | Error:
        """Store memory with embedding."""
        try:
            await self._ensure_collection()

            # Use provided embedding or generate one
            vector = embedding if embedding else await self._embed(content)

            memory = Memory(
                id=uuid4(),
                content=content,
                created_at=datetime.now(UTC),
                agent_id=agent_id,
                conversation_id=conversation_id,
                tags=tags or [],
            )

            await self._client.upsert(
                self._collection,
                points=[
                    PointStruct(
                        id=str(memory.id),
                        vector=vector,
                        payload=memory.model_dump(mode="json"),
                    )
                ],
            )
            return memory
        except Exception as e:
            return Error(description=f"Failed to store memory: {e}")

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        score_threshold: float | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        embedding_model: str | None = None,
    ) -> list[SearchResult] | Error:
        """Semantic search with optional filtering."""
        try:
            await self._ensure_collection()

            query_vector = await self._embed(query)
            filters = self._build_filters(tags, agent_id)

            # Use query_points (qdrant-client >= 1.7.0)
            response = await self._client.query_points(
                self._collection,
                query=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=filters,
            )

            return [
                SearchResult(memory=Memory(**r.payload), score=r.score)
                for r in response.points
            ]
        except Exception as e:
            return Error(description=f"Failed to search memories: {e}")

    async def delete(self, memory_id: UUID) -> bool | Error:
        """Delete a memory by ID."""
        try:
            await self._ensure_collection()
            await self._client.delete(
                self._collection,
                points_selector=[str(memory_id)],
            )
            return True
        except Exception as e:
            return Error(description=f"Failed to delete memory: {e}")

    async def get(self, memory_id: UUID) -> Memory | None | Error:
        """Retrieve a specific memory by ID."""
        try:
            await self._ensure_collection()
            results = await self._client.retrieve(
                self._collection,
                ids=[str(memory_id)],
            )
            if results:
                return Memory(**results[0].payload)
            return None
        except Exception as e:
            return Error(description=f"Failed to retrieve memory: {e}")
