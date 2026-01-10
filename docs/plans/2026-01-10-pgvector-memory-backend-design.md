# pgvector Memory Backend Design

**Date**: 2026-01-10
**Status**: Ready for implementation

## Overview

Consolidate vector memory storage from Qdrant to PostgreSQL + pgvector, leveraging the existing database infrastructure for simplified operations, transactional consistency, and native tenant isolation.

## Motivation

| Problem | Solution |
|---------|----------|
| Split brain (relational in Postgres, vectors in Qdrant) | Single database for all data |
| Eventual consistency across systems | Atomic transactions, CASCADE deletes |
| Separate infrastructure to manage | Zero new infra (uses existing Postgres) |
| Custom tenant filtering in Qdrant | Native SQL `WHERE tenant_id = $1` |

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backend location | `bond/src/bond/tools/memory/backends/pgvector.py` | Follows existing structure |
| Protocol | Implements `AgentMemoryProtocol` | No new abstractions needed |
| Embedding | Reuses PydanticAI `Embedder` | Same as Qdrant, keeps observability |
| Connection | Accepts `asyncpg.Pool` | Injected from dataing's AppDatabase |
| Dimensions | Configurable, default 1536 | Supports OpenAI ada-002 default |
| Tenancy | `tenant_id` required on all operations | Security + performance |
| Backend selection | Factory with env var, default pgvector | Keep Qdrant as option |

## Protocol Update

All `AgentMemoryProtocol` methods now require `tenant_id: UUID`:

```python
class AgentMemoryProtocol(Protocol):
    async def store(
        self,
        content: str,
        agent_id: str,
        *,
        tenant_id: UUID,  # Required
        conversation_id: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> Memory | Error: ...

    async def search(
        self,
        query: str,
        *,
        tenant_id: UUID,  # Required
        top_k: int = 10,
        score_threshold: float | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        embedding_model: str | None = None,
    ) -> list[SearchResult] | Error: ...

    async def delete(
        self,
        memory_id: UUID,
        *,
        tenant_id: UUID,
    ) -> bool | Error: ...

    async def get(
        self,
        memory_id: UUID,
        *,
        tenant_id: UUID,
    ) -> Memory | None | Error: ...
```

## Database Migration

**File:** `dataing/migrations/012_agent_memories.sql`

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Agent memories table with vector embeddings
CREATE TABLE agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,

    -- Content
    content TEXT NOT NULL,
    conversation_id TEXT,
    tags TEXT[] DEFAULT '{}',

    -- Vector embedding (dimension configurable, default 1536 for OpenAI)
    embedding vector(1536),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Ensure we can filter efficiently
    CONSTRAINT agent_memories_content_not_empty CHECK (content <> '')
);

-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX idx_agent_memories_embedding
    ON agent_memories USING hnsw (embedding vector_cosine_ops);

-- Tenant isolation index
CREATE INDEX idx_agent_memories_tenant ON agent_memories(tenant_id);

-- Agent filtering index
CREATE INDEX idx_agent_memories_agent ON agent_memories(tenant_id, agent_id);

-- Tag filtering (GIN index for array containment)
CREATE INDEX idx_agent_memories_tags ON agent_memories USING gin(tags);

COMMENT ON TABLE agent_memories IS 'Vector memory store for agent context and learning';
COMMENT ON COLUMN agent_memories.embedding IS 'Vector embedding (1536 dims for OpenAI ada-002)';
```

## PgVectorMemoryStore Implementation

**File:** `bond/src/bond/tools/memory/backends/pgvector.py`

```python
"""PostgreSQL + pgvector memory backend."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from asyncpg import Pool
from pydantic_ai.embeddings import Embedder

from bond.tools.memory._models import Error, Memory, SearchResult


class PgVectorMemoryStore:
    """pgvector-backed memory store using PydanticAI Embedder."""

    def __init__(
        self,
        pool: Pool,
        table_name: str = "agent_memories",
        embedding_model: str = "openai:text-embedding-3-small",
    ) -> None:
        self._pool = pool
        self._table = table_name
        self._embedder = Embedder(embedding_model)

    async def _embed(self, text: str) -> list[float]:
        result = await self._embedder.embed_query(text)
        return list(result.embeddings[0])

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
        try:
            vector = embedding if embedding else await self._embed(content)
            memory_id = uuid4()
            created_at = datetime.now(UTC)

            await self._pool.execute(
                f"""
                INSERT INTO {self._table}
                (id, tenant_id, agent_id, content, conversation_id, tags, embedding, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                memory_id, tenant_id, agent_id, content,
                conversation_id, tags or [], str(vector), created_at,
            )

            return Memory(
                id=memory_id, content=content, created_at=created_at,
                agent_id=agent_id, conversation_id=conversation_id, tags=tags or [],
            )
        except Exception as e:
            return Error(description=f"Failed to store memory: {e}")

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
        try:
            query_vector = await self._embed(query)

            conditions = ["tenant_id = $1"]
            args: list = [tenant_id, str(query_vector), top_k]

            if agent_id:
                conditions.append(f"agent_id = ${len(args) + 1}")
                args.append(agent_id)

            if tags:
                conditions.append(f"tags @> ${len(args) + 1}")
                args.append(tags)

            where_clause = " AND ".join(conditions)
            score_filter = f"AND (1 - (embedding <=> $2)) >= {score_threshold}" if score_threshold else ""

            rows = await self._pool.fetch(
                f"""
                SELECT id, content, conversation_id, tags, agent_id, created_at,
                       1 - (embedding <=> $2) AS score
                FROM {self._table}
                WHERE {where_clause} {score_filter}
                ORDER BY embedding <=> $2
                LIMIT $3
                """,
                *args,
            )

            return [
                SearchResult(
                    memory=Memory(
                        id=row["id"], content=row["content"], created_at=row["created_at"],
                        agent_id=row["agent_id"], conversation_id=row["conversation_id"],
                        tags=list(row["tags"]),
                    ),
                    score=row["score"],
                )
                for row in rows
            ]
        except Exception as e:
            return Error(description=f"Failed to search memories: {e}")

    async def delete(self, memory_id: UUID, *, tenant_id: UUID) -> bool | Error:
        try:
            result = await self._pool.execute(
                f"DELETE FROM {self._table} WHERE id = $1 AND tenant_id = $2",
                memory_id, tenant_id,
            )
            return "DELETE 1" in result
        except Exception as e:
            return Error(description=f"Failed to delete memory: {e}")

    async def get(self, memory_id: UUID, *, tenant_id: UUID) -> Memory | None | Error:
        try:
            row = await self._pool.fetchrow(
                f"""
                SELECT id, content, conversation_id, tags, agent_id, created_at
                FROM {self._table}
                WHERE id = $1 AND tenant_id = $2
                """,
                memory_id, tenant_id,
            )

            if not row:
                return None

            return Memory(
                id=row["id"], content=row["content"], created_at=row["created_at"],
                agent_id=row["agent_id"], conversation_id=row["conversation_id"],
                tags=list(row["tags"]),
            )
        except Exception as e:
            return Error(description=f"Failed to retrieve memory: {e}")
```

## Backend Factory

**File:** `bond/src/bond/tools/memory/backends/__init__.py`

```python
"""Memory backend implementations."""

from enum import Enum
from asyncpg import Pool

from bond.tools.memory.backends.pgvector import PgVectorMemoryStore
from bond.tools.memory.backends.qdrant import QdrantMemoryStore


class MemoryBackendType(str, Enum):
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"


def create_memory_backend(
    backend_type: MemoryBackendType = MemoryBackendType.PGVECTOR,
    *,
    pool: Pool | None = None,
    table_name: str = "agent_memories",
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    collection_name: str = "memories",
    embedding_model: str = "openai:text-embedding-3-small",
) -> PgVectorMemoryStore | QdrantMemoryStore:
    if backend_type == MemoryBackendType.PGVECTOR:
        if pool is None:
            raise ValueError("pgvector backend requires asyncpg Pool")
        return PgVectorMemoryStore(pool=pool, table_name=table_name, embedding_model=embedding_model)
    else:
        return QdrantMemoryStore(
            collection_name=collection_name, embedding_model=embedding_model,
            qdrant_url=qdrant_url, qdrant_api_key=qdrant_api_key,
        )
```

## Files to Modify

| File | Action |
|------|--------|
| `dataing/migrations/012_agent_memories.sql` | Create |
| `bond/src/bond/tools/memory/backends/__init__.py` | Create |
| `bond/src/bond/tools/memory/backends/pgvector.py` | Create |
| `bond/src/bond/tools/memory/backends/qdrant.py` | Create (move from backends.py) |
| `bond/src/bond/tools/memory/_protocols.py` | Modify (add tenant_id) |
| `bond/src/bond/tools/memory/backends.py` | Delete |
| `bond/src/bond/tools/memory/__init__.py` | Modify (update exports) |
| `bond/src/bond/tools/memory/tools.py` | Modify (pass tenant_id) |

## Testing

| Test | Purpose |
|------|---------|
| `test_pgvector_store.py` | Unit tests with test database |
| `test_qdrant_store.py` | Update for tenant_id |
| `test_backend_factory.py` | Factory creates correct backend |

## Configuration

```bash
# Backend selection (default: pgvector)
MEMORY_BACKEND=pgvector

# pgvector uses existing DATABASE_URL

# Qdrant (optional)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=optional
```
