"""Memory protocol - interface for memory backends.

All operations are scoped to a tenant for multi-tenant isolation.
This ensures memories are always scoped correctly and enables
efficient indexing on tenant boundaries.
"""

from typing import Protocol
from uuid import UUID

from bond.tools.memory._models import Error, Memory, SearchResult


class AgentMemoryProtocol(Protocol):
    """Protocol for memory storage backends.

    All operations require tenant_id for multi-tenant isolation.
    This ensures memories are always scoped correctly and enables
    efficient indexing on tenant boundaries.

    Implementations:
        - PgVectorMemoryStore: PostgreSQL + pgvector (default)
        - QdrantMemoryStore: Qdrant vector database
    """

    async def store(
        self,
        content: str,
        agent_id: str,
        *,
        tenant_id: UUID,
        conversation_id: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> Memory | Error:
        """Store a memory and return the created Memory object.

        Args:
            content: The text content to store.
            agent_id: ID of the agent creating this memory.
            tenant_id: Tenant UUID for multi-tenant isolation (required).
            conversation_id: Optional conversation context.
            tags: Optional tags for filtering.
            embedding: Pre-computed embedding (backend generates if None).
            embedding_model: Override default embedding model.

        Returns:
            The created Memory on success, or Error on failure.
        """
        ...

    async def search(
        self,
        query: str,
        *,
        tenant_id: UUID,
        top_k: int = 10,
        score_threshold: float | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        embedding_model: str | None = None,
    ) -> list[SearchResult] | Error:
        """Search memories by semantic similarity.

        Args:
            query: Search query text.
            tenant_id: Tenant UUID for multi-tenant isolation (required).
            top_k: Maximum number of results.
            score_threshold: Minimum similarity score to include.
            tags: Filter by memories with these tags.
            agent_id: Filter by creating agent.
            embedding_model: Override default embedding model.

        Returns:
            List of SearchResult ordered by similarity, or Error on failure.
        """
        ...

    async def delete(self, memory_id: UUID, *, tenant_id: UUID) -> bool | Error:
        """Delete a memory by ID.

        Args:
            memory_id: The UUID of the memory to delete.
            tenant_id: Tenant UUID for multi-tenant isolation (required).

        Returns:
            True if deleted, False if not found, or Error on failure.
        """
        ...

    async def get(self, memory_id: UUID, *, tenant_id: UUID) -> Memory | None | Error:
        """Retrieve a specific memory by ID.

        Args:
            memory_id: The UUID of the memory to retrieve.
            tenant_id: Tenant UUID for multi-tenant isolation (required).

        Returns:
            The Memory if found, None if not found, or Error on failure.
        """
        ...
