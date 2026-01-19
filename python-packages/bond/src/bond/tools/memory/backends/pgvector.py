"""PostgreSQL + pgvector memory backend.

Uses existing asyncpg pool from dataing for zero additional infrastructure.
Provides transactional consistency with application data.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from asyncpg import Pool
from pydantic_ai.embeddings import Embedder

from bond.tools.memory._models import Error, Memory, SearchResult


class PgVectorMemoryStore:
    """pgvector-backed memory store using PydanticAI Embedder.

    Benefits over Qdrant:
    - No separate infrastructure (uses existing Postgres)
    - Transactional consistency (CASCADE deletes, atomic commits)
    - Native tenant isolation via SQL WHERE clauses
    - Unified backup/restore with application data

    Example:
        # Inject pool from dataing's AppDatabase
        store = PgVectorMemoryStore(pool=app_db.pool)

        # With OpenAI embeddings
        store = PgVectorMemoryStore(
            pool=app_db.pool,
            embedding_model="openai:text-embedding-3-small",
        )
    """

    def __init__(
        self,
        pool: Pool,
        table_name: str = "agent_memories",
        embedding_model: str = "openai:text-embedding-3-small",
    ) -> None:
        """Initialize the pgvector memory store.

        Args:
            pool: asyncpg connection pool (typically from AppDatabase).
            table_name: Name of the memories table.
            embedding_model: PydanticAI embedding model string.
        """
        self._pool = pool
        self._table = table_name
        self._embedder = Embedder(embedding_model)

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding using PydanticAI Embedder.

        This is non-blocking (runs in thread pool) and instrumented.
        """
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
        """Store memory with transactional guarantee."""
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
                memory_id,
                tenant_id,
                agent_id,
                content,
                conversation_id,
                tags or [],
                str(vector),  # pgvector accepts string representation
                created_at,
            )

            return Memory(
                id=memory_id,
                content=content,
                created_at=created_at,
                agent_id=agent_id,
                conversation_id=conversation_id,
                tags=tags or [],
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
        """Semantic search using cosine similarity.

        Note: Postgres '<=>' operator returns distance (0=same, 2=opposite).
        We convert distance to similarity (1 - distance) for the interface.
        """
        try:
            query_vector = await self._embed(query)

            # Build query with filters
            conditions = ["tenant_id = $1"]
            args: list[object] = [tenant_id, str(query_vector), top_k]

            if agent_id:
                conditions.append(f"agent_id = ${len(args) + 1}")
                args.append(agent_id)

            if tags:
                conditions.append(f"tags @> ${len(args) + 1}")
                args.append(tags)

            where_clause = " AND ".join(conditions)

            # Score threshold filter (cosine similarity = 1 - distance)
            score_filter = ""
            if score_threshold:
                score_filter = f"AND (1 - (embedding <=> $2)) >= {score_threshold}"

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
                        id=row["id"],
                        content=row["content"],
                        created_at=row["created_at"],
                        agent_id=row["agent_id"],
                        conversation_id=row["conversation_id"],
                        tags=list(row["tags"]) if row["tags"] else [],
                    ),
                    score=row["score"],
                )
                for row in rows
            ]
        except Exception as e:
            return Error(description=f"Failed to search memories: {e}")

    async def delete(self, memory_id: UUID, *, tenant_id: UUID) -> bool | Error:
        """Hard delete a specific memory (scoped to tenant for safety)."""
        try:
            result = await self._pool.execute(
                f"DELETE FROM {self._table} WHERE id = $1 AND tenant_id = $2",
                memory_id,
                tenant_id,
            )
            # asyncpg returns "DELETE N" where N is row count
            return "DELETE 1" in result
        except Exception as e:
            return Error(description=f"Failed to delete memory: {e}")

    async def get(self, memory_id: UUID, *, tenant_id: UUID) -> Memory | None | Error:
        """Retrieve a specific memory by ID (scoped to tenant)."""
        try:
            row = await self._pool.fetchrow(
                f"""
                SELECT id, content, conversation_id, tags, agent_id, created_at
                FROM {self._table}
                WHERE id = $1 AND tenant_id = $2
                """,
                memory_id,
                tenant_id,
            )

            if not row:
                return None

            return Memory(
                id=row["id"],
                content=row["content"],
                created_at=row["created_at"],
                agent_id=row["agent_id"],
                conversation_id=row["conversation_id"],
                tags=list(row["tags"]) if row["tags"] else [],
            )
        except Exception as e:
            return Error(description=f"Failed to retrieve memory: {e}")
