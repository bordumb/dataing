"""Memory toolset for Bond agents.

Provides semantic memory storage and retrieval using vector databases.
"""

from bond.tools.memory._models import (
    CreateMemoryRequest,
    Error,
    Memory,
    SearchMemoriesRequest,
    SearchResult,
)
from bond.tools.memory._protocols import AgentMemoryProtocol
from bond.tools.memory.backends import QdrantMemoryStore
from bond.tools.memory.tools import memory_toolset

__all__ = [
    # Protocol
    "AgentMemoryProtocol",
    # Models
    "Memory",
    "SearchResult",
    "CreateMemoryRequest",
    "SearchMemoriesRequest",
    "Error",
    # Toolset
    "memory_toolset",
    # Backends
    "QdrantMemoryStore",
]
