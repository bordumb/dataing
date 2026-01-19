"""Memory toolset for Bond agents.

Provides semantic memory storage and retrieval using vector databases.
Default backend: pgvector (PostgreSQL) for unified infrastructure.
"""

from bond.tools.memory._models import (
    CreateMemoryRequest,
    DeleteMemoryRequest,
    Error,
    GetMemoryRequest,
    Memory,
    SearchMemoriesRequest,
    SearchResult,
)
from bond.tools.memory._protocols import AgentMemoryProtocol
from bond.tools.memory.backends import (
    MemoryBackendType,
    PgVectorMemoryStore,
    QdrantMemoryStore,
    create_memory_backend,
)
from bond.tools.memory.tools import memory_toolset

__all__ = [
    # Protocol
    "AgentMemoryProtocol",
    # Models
    "Memory",
    "SearchResult",
    "CreateMemoryRequest",
    "SearchMemoriesRequest",
    "DeleteMemoryRequest",
    "GetMemoryRequest",
    "Error",
    # Toolset
    "memory_toolset",
    # Backend factory
    "MemoryBackendType",
    "create_memory_backend",
    # Backend implementations
    "PgVectorMemoryStore",
    "QdrantMemoryStore",
]
