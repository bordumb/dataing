# Bond Agent Framework Design

**Date:** 2026-01-09
**Status:** Approved
**Author:** Brainstorming session

## Overview

Bond is a generic agent runtime package that provides the foundation for building AI agents. Named after James Bond (a skilled agent that gets things done, and "bonding" = connecting), it is designed to be reusable beyond the dataing project.

## Package Structure

```
bond/                           # Generic agent runtime (new package)
├── pyproject.toml
├── src/
│   └── bond/
│       ├── __init__.py         # Exports: BondAgent, StreamHandlers, ToolCallEvent
│       ├── agent.py            # Core agent class
│       └── tools/
│           └── memory/
│               ├── __init__.py
│               ├── _protocols.py    # AgentMemoryProtocol
│               ├── models.py        # Memory, SearchResult, request models
│               ├── tools.py         # PydanticAI tools using RunContext
│               └── vector_store.py  # QdrantMemoryStore implementation
│
dataing/                        # Data quality domain (existing)
dataing-ee/                     # Enterprise features (existing)
```

**Dependency Direction:**
```
bond → dataing → dataing-ee
```

Bond is the foundation layer with no dependencies on dataing. The dataing package imports and extends Bond for data quality investigation agents.

## BondAgent Class API

```python
# bond/src/bond/agent.py
"""Core agent runtime."""

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from pydantic_ai import Agent, Tool
from pydantic_ai.messages import ModelMessage

T = TypeVar("T")
DepsT = TypeVar("DepsT")


@dataclass
class ToolCallEvent:
    """Event emitted when agent calls a tool."""
    name: str
    args: dict[str, Any]


@dataclass
class StreamHandlers:
    """Callbacks for streaming agent responses."""
    on_text: Callable[[str], None] | None = None
    on_tool_call: Callable[[ToolCallEvent], None] | None = None
    on_thinking: Callable[[str], None] | None = None
    json_mode: bool = False  # For WebSocket/SSE serialization


class BondAgent(Generic[T, DepsT]):
    """Generic agent runtime wrapping PydanticAI."""

    def __init__(
        self,
        name: str,
        instructions: str,
        model: str,
        *,
        toolsets: list[list[Tool[DepsT]]] | None = None,
        deps: DepsT | None = None,
        output_type: type[T] = str,
        max_retries: int = 3,
    ):
        """Initialize agent with configuration."""
        ...

    async def ask(
        self,
        prompt: str,
        *,
        handlers: StreamHandlers | None = None,
        dynamic_instructions: str | None = None,
    ) -> T:
        """Send prompt and get response with optional streaming."""
        ...

    def get_message_history(self) -> list[ModelMessage]:
        """Get current conversation history."""
        ...

    def set_message_history(self, history: list[ModelMessage]) -> None:
        """Replace conversation history."""
        ...

    def clear_history(self) -> None:
        """Clear conversation history."""
        ...

    def clone_with_history(self, history: list[ModelMessage]) -> "BondAgent[T, DepsT]":
        """Create new agent instance with given history (for branching)."""
        ...
```

## Memory Tool - Models

```python
# bond/src/bond/tools/memory/models.py
"""Memory data models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class Memory(BaseModel):
    """A stored memory."""
    id: UUID
    content: str
    created_at: datetime
    agent_id: str
    conversation_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Memory with similarity score."""
    memory: Memory
    score: float


class CreateMemoryRequest(BaseModel):
    """Request to create a memory."""
    content: str
    agent_id: str
    conversation_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None  # Optional, Bond generates if not provided
    embedding_model: str | None = None    # Override default model


class SearchMemoriesRequest(BaseModel):
    """Request to search memories."""
    query: str
    top_k: int = 10
    score_threshold: float | None = None
    tags: list[str] | None = None
    agent_id: str | None = None
    embedding_model: str | None = None
```

## Memory Protocol

```python
# bond/src/bond/tools/memory/_protocols.py
"""Memory protocol - interface for memory backends."""

from typing import Protocol
from uuid import UUID

from .models import Memory, SearchResult


class AgentMemoryProtocol(Protocol):
    """Protocol for memory storage backends.

    Implementations: QdrantMemoryStore, (future: PineconeMemoryStore, etc.)
    """

    async def store(
        self,
        content: str,
        agent_id: str,
        *,
        conversation_id: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> Memory:
        """Store a memory and return the created Memory object."""
        ...

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        score_threshold: float | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        embedding_model: str | None = None,
    ) -> list[SearchResult]:
        """Search memories by semantic similarity."""
        ...

    async def delete(self, memory_id: UUID) -> bool:
        """Delete a memory by ID. Returns True if deleted."""
        ...

    async def get(self, memory_id: UUID) -> Memory | None:
        """Retrieve a specific memory by ID."""
        ...
```

## Memory Tools

```python
# bond/src/bond/tools/memory/tools.py
"""Memory tools for PydanticAI agents."""

from uuid import UUID

from pydantic_ai import RunContext, Tool

from ._protocols import AgentMemoryProtocol
from .models import CreateMemoryRequest, SearchMemoriesRequest, Memory, SearchResult


async def create_memory(
    ctx: RunContext[AgentMemoryProtocol],
    request: CreateMemoryRequest,
) -> Memory:
    """Store a new memory for later retrieval."""
    return await ctx.deps.store(
        content=request.content,
        agent_id=request.agent_id,
        conversation_id=request.conversation_id,
        tags=request.tags,
        embedding=request.embedding,
        embedding_model=request.embedding_model,
    )


async def search_memories(
    ctx: RunContext[AgentMemoryProtocol],
    request: SearchMemoriesRequest,
) -> list[SearchResult]:
    """Search memories by semantic similarity."""
    return await ctx.deps.search(
        query=request.query,
        top_k=request.top_k,
        score_threshold=request.score_threshold,
        tags=request.tags,
        agent_id=request.agent_id,
        embedding_model=request.embedding_model,
    )


async def delete_memory(
    ctx: RunContext[AgentMemoryProtocol],
    memory_id: UUID,
) -> bool:
    """Delete a memory by ID."""
    return await ctx.deps.delete(memory_id)


# Export as toolset for BondAgent
memory_toolset: list[Tool[AgentMemoryProtocol]] = [
    Tool(create_memory),
    Tool(search_memories),
    Tool(delete_memory),
]
```

## Vector Store Implementation

```python
# bond/src/bond/tools/memory/vector_store.py
"""Qdrant memory store implementation."""

from datetime import datetime, UTC
from uuid import UUID, uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

from ._protocols import AgentMemoryProtocol
from .models import Memory, SearchResult


class QdrantMemoryStore:
    """Qdrant-backed memory store with local embeddings."""

    def __init__(
        self,
        collection_name: str = "memories",
        embedding_model: str = "all-MiniLM-L6-v2",
        qdrant_url: str | None = None,  # None = in-memory
    ):
        self._collection = collection_name
        self._default_model = embedding_model
        self._models: dict[str, SentenceTransformer] = {}
        self._client = QdrantClient(url=qdrant_url) if qdrant_url else QdrantClient(":memory:")
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
        return model.encode(text).tolist()

    def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection not in collections:
            model = self._get_model(None)
            self._client.create_collection(
                self._collection,
                vectors_config=VectorParams(
                    size=model.get_sentence_embedding_dimension(),
                    distance=Distance.COSINE,
                ),
            )

    def _build_filters(
        self,
        tags: list[str] | None,
        agent_id: str | None,
    ) -> Filter | None:
        """Build Qdrant filter from parameters."""
        conditions = []
        if agent_id:
            conditions.append(FieldCondition(key="agent_id", match=MatchValue(value=agent_id)))
        if tags:
            for tag in tags:
                conditions.append(FieldCondition(key="tags", match=MatchValue(value=tag)))
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
    ) -> Memory:
        """Store memory with embedding."""
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
            [PointStruct(
                id=str(memory.id),
                vector=final_embedding,
                payload=memory.model_dump(mode="json"),
            )],
        )
        return memory

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        score_threshold: float | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        embedding_model: str | None = None,
    ) -> list[SearchResult]:
        """Semantic search with optional filtering."""
        embedding = self._embed(query, embedding_model)
        filters = self._build_filters(tags, agent_id)

        results = self._client.search(
            self._collection,
            query_vector=embedding,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=filters,
        )
        return [SearchResult(memory=Memory(**r.payload), score=r.score) for r in results]

    async def delete(self, memory_id: UUID) -> bool:
        """Delete a memory by ID."""
        self._client.delete(self._collection, points_selector=[str(memory_id)])
        return True

    async def get(self, memory_id: UUID) -> Memory | None:
        """Retrieve a specific memory by ID."""
        results = self._client.retrieve(self._collection, ids=[str(memory_id)])
        if results:
            return Memory(**results[0].payload)
        return None
```

## Package Exports

```python
# bond/src/bond/__init__.py
"""Bond - Generic agent runtime."""

from .agent import BondAgent, StreamHandlers, ToolCallEvent

__all__ = ["BondAgent", "StreamHandlers", "ToolCallEvent"]


# bond/src/bond/tools/memory/__init__.py
"""Memory toolset for Bond agents."""

from ._protocols import AgentMemoryProtocol
from .models import Memory, SearchResult, CreateMemoryRequest, SearchMemoriesRequest
from .tools import memory_toolset
from .vector_store import QdrantMemoryStore

__all__ = [
    "AgentMemoryProtocol",
    "Memory", "SearchResult", "CreateMemoryRequest", "SearchMemoriesRequest",
    "memory_toolset",
    "QdrantMemoryStore",
]
```

## Usage Example

```python
from bond import BondAgent, StreamHandlers
from bond.tools.memory import memory_toolset, QdrantMemoryStore

# Create agent with memory
agent = BondAgent(
    name="assistant",
    instructions="You are helpful. Use memories to remember user preferences.",
    model="anthropic:claude-sonnet-4-20250514",
    toolsets=[memory_toolset],
    deps=QdrantMemoryStore(qdrant_url="http://localhost:6333"),
)

# Stream responses
handlers = StreamHandlers(
    on_text=lambda t: print(t, end="", flush=True),
    on_tool_call=lambda tc: print(f"\n[Tool: {tc.name}]"),
)

response = await agent.ask("Remember that I prefer dark mode", handlers=handlers)
```

## Dependencies

**bond/pyproject.toml:**
```toml
[project]
name = "bond"
version = "0.1.0"
dependencies = [
    "pydantic-ai>=0.0.14",
    "qdrant-client>=1.7.0",
    "sentence-transformers>=2.2.0",
]
```

## Design Principles

### Protocol-Oriented Architecture

Three-layer pattern used throughout:

1. **Protocol Layer** (`_protocols.py`): Interface definitions using `typing.Protocol`
2. **Backend Layer** (`vector_store.py`): Concrete implementations
3. **Toolset Layer** (`tools.py`): Agent-facing functions via `RunContext[Protocol]`

This enables:
- Swappable backends (Qdrant today, Pinecone tomorrow)
- Type-safe dependency injection
- Easy testing with mock implementations

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package name | `bond` | Generic, reusable, memorable |
| Embedding provider | sentence-transformers | Local, no API costs, fast |
| Vector store | Qdrant | Modern, supports filtering, good Python SDK |
| Search strategy | Hybrid (top-k + threshold + tags) | Flexible for different use cases |
| Embedding handling | Bond generates if not provided | Convenience with flexibility |

## Next Steps

1. Create `bond/` package structure
2. Implement `BondAgent` class
3. Implement memory toolset
4. Add tests
5. Update `dataing` to use `BondAgent` for investigation agents
