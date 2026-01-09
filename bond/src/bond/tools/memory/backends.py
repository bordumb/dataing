"""Memory backend implementations.

This module provides concrete implementations of AgentMemoryProtocol.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from bond.tools.memory._models import Error, Memory, SearchResult


class QdrantMemoryStore:
    """Qdrant-backed memory store with local embeddings.

    Uses Qdrant for vector storage and sentence-transformers for
    local embedding generation (no API costs).

    Example:
        # In-memory for development/testing
        store = QdrantMemoryStore()

        # Persistent for production
        store = QdrantMemoryStore(qdrant_url="http://localhost:6333")

        # Custom embedding model
        store = QdrantMemoryStore(embedding_model="all-mpnet-base-v2")
    """

    def __init__(
        self,
        collection_name: str = "memories",
        embedding_model: str = "all-MiniLM-L6-v2",
        qdrant_url: str | None = None,
    ) -> None:
        """Initialize the Qdrant memory store.

        Args:
            collection_name: Name of the Qdrant collection.
            embedding_model: Default sentence-transformers model for embeddings.
            qdrant_url: Qdrant server URL. None = in-memory (for dev/testing).
        """
        self._collection = collection_name
        self._default_model = embedding_model
        self._models: dict[str, SentenceTransformer] = {}
        self._client = (
            QdrantClient(url=qdrant_url) if qdrant_url else QdrantClient(":memory:")
        )
        self._ensure_collection()

    def _get_model(self, model_name: str | None) -> SentenceTransformer:
        """Lazy-load and cache embedding models."""
        name = model_name or self._default_model
        if name not in self._models:
            self._models[name] = SentenceTransformer(name)
        return self._models[name]

    def _embed(self, text: str, model_name: str | None = None) -> list[float]:
        """Generate embedding for text."""
        model = self._get_model(model_name)
        embedding = model.encode(text)
        result: list[float] = embedding.tolist()
        return result

    def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection not in collections:
            model = self._get_model(None)
            dim = model.get_sentence_embedding_dimension()
            if dim is None:
                dim = 384  # Default for all-MiniLM-L6-v2
            self._client.create_collection(
                self._collection,
                vectors_config=VectorParams(
                    size=dim,
                    distance=Distance.COSINE,
                ),
            )

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
            final_embedding = embedding or self._embed(content, embedding_model)
            memory = Memory(
                id=uuid4(),
                content=content,
                created_at=datetime.now(UTC),
                agent_id=agent_id,
                conversation_id=conversation_id,
                tags=tags or [],
            )
            self._client.upsert(
                self._collection,
                [
                    PointStruct(
                        id=str(memory.id),
                        vector=final_embedding,
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
            embedding = self._embed(query, embedding_model)
            filters = self._build_filters(tags, agent_id)

            # Use query_points (qdrant-client >= 1.7.0)
            response = self._client.query_points(
                self._collection,
                query=embedding,
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
            self._client.delete(
                self._collection,
                points_selector=[str(memory_id)],
            )
            return True
        except Exception as e:
            return Error(description=f"Failed to delete memory: {e}")

    async def get(self, memory_id: UUID) -> Memory | None | Error:
        """Retrieve a specific memory by ID."""
        try:
            results = self._client.retrieve(
                self._collection,
                ids=[str(memory_id)],
            )
            if results:
                return Memory(**results[0].payload)
            return None
        except Exception as e:
            return Error(description=f"Failed to retrieve memory: {e}")
