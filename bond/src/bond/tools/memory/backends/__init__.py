"""Memory backend implementations.

Provides factory function for backend selection based on configuration.
Default: pgvector (PostgreSQL) for unified infrastructure.
"""

from enum import Enum
from typing import TYPE_CHECKING

from bond.tools.memory.backends.pgvector import PgVectorMemoryStore
from bond.tools.memory.backends.qdrant import QdrantMemoryStore

if TYPE_CHECKING:
    from asyncpg import Pool


class MemoryBackendType(str, Enum):
    """Supported memory backend types."""

    PGVECTOR = "pgvector"
    QDRANT = "qdrant"


def create_memory_backend(
    backend_type: MemoryBackendType = MemoryBackendType.PGVECTOR,
    *,
    # pgvector options
    pool: "Pool | None" = None,
    table_name: str = "agent_memories",
    # qdrant options
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    collection_name: str = "memories",
    # shared options
    embedding_model: str = "openai:text-embedding-3-small",
) -> PgVectorMemoryStore | QdrantMemoryStore:
    """Create a memory backend based on configuration.

    Args:
        backend_type: Which backend to use (default: pgvector).
        pool: asyncpg Pool (required for pgvector).
        table_name: Postgres table name (pgvector only).
        qdrant_url: Qdrant server URL (qdrant only, None = in-memory).
        qdrant_api_key: Qdrant API key (qdrant only).
        collection_name: Qdrant collection (qdrant only).
        embedding_model: Model for embeddings (both backends).

    Returns:
        Configured memory backend instance.

    Raises:
        ValueError: If pgvector selected but no pool provided.

    Example:
        # pgvector (recommended)
        memory = create_memory_backend(
            backend_type=MemoryBackendType.PGVECTOR,
            pool=app_db.pool,
        )

        # Qdrant (for specific use cases)
        memory = create_memory_backend(
            backend_type=MemoryBackendType.QDRANT,
            qdrant_url="http://localhost:6333",
        )
    """
    if backend_type == MemoryBackendType.PGVECTOR:
        if pool is None:
            raise ValueError("pgvector backend requires asyncpg Pool")
        return PgVectorMemoryStore(
            pool=pool,
            table_name=table_name,
            embedding_model=embedding_model,
        )
    else:
        return QdrantMemoryStore(
            collection_name=collection_name,
            embedding_model=embedding_model,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
        )


__all__ = [
    "MemoryBackendType",
    "PgVectorMemoryStore",
    "QdrantMemoryStore",
    "create_memory_backend",
]
