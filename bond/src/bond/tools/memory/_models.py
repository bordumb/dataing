"""Memory data models."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class Memory(BaseModel):
    """A stored memory unit.

    Memories are the fundamental storage unit in Bond's memory system.
    Each memory has content, metadata for filtering, and an embedding
    for semantic search.
    """

    id: Annotated[
        UUID,
        Field(description="Unique identifier for this memory"),
    ]

    content: Annotated[
        str,
        Field(description="The actual content of the memory"),
    ]

    created_at: Annotated[
        datetime,
        Field(description="When this memory was created"),
    ]

    agent_id: Annotated[
        str,
        Field(description="ID of the agent that created this memory"),
    ]

    conversation_id: Annotated[
        str | None,
        Field(description="Optional conversation context for this memory"),
    ] = None

    tags: Annotated[
        list[str],
        Field(description="Tags for filtering memories"),
    ] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Memory with similarity score from search."""

    memory: Annotated[
        Memory,
        Field(description="The matched memory"),
    ]

    score: Annotated[
        float,
        Field(description="Similarity score (higher is more similar)"),
    ]


class CreateMemoryRequest(BaseModel):
    """Request to create a new memory.

    The agent provides content and metadata. Embeddings can be
    pre-computed or left for the backend to generate.
    """

    content: Annotated[
        str,
        Field(description="Content to store as a memory"),
    ]

    agent_id: Annotated[
        str,
        Field(description="ID of the agent creating this memory"),
    ]

    tenant_id: Annotated[
        UUID,
        Field(description="Tenant UUID for multi-tenant isolation"),
    ]

    conversation_id: Annotated[
        str | None,
        Field(description="Optional conversation context"),
    ] = None

    tags: Annotated[
        list[str],
        Field(description="Tags for categorizing and filtering"),
    ] = Field(default_factory=list)

    embedding: Annotated[
        list[float] | None,
        Field(description="Pre-computed embedding (Bond generates if not provided)"),
    ] = None

    embedding_model: Annotated[
        str | None,
        Field(description="Override default embedding model for this operation"),
    ] = None


class SearchMemoriesRequest(BaseModel):
    """Request to search memories by semantic similarity.

    Supports hybrid search: top-k results filtered by score threshold
    and optional tag/agent filtering.
    """

    query: Annotated[
        str,
        Field(description="Search query text"),
    ]

    tenant_id: Annotated[
        UUID,
        Field(description="Tenant UUID for multi-tenant isolation"),
    ]

    top_k: Annotated[
        int,
        Field(description="Maximum number of results to return", ge=1, le=100),
    ] = 10

    score_threshold: Annotated[
        float | None,
        Field(description="Minimum similarity score (0-1) to include in results"),
    ] = None

    tags: Annotated[
        list[str] | None,
        Field(description="Filter by memories containing these tags"),
    ] = None

    agent_id: Annotated[
        str | None,
        Field(description="Filter by agent that created the memories"),
    ] = None

    embedding_model: Annotated[
        str | None,
        Field(description="Override default embedding model for this search"),
    ] = None


class DeleteMemoryRequest(BaseModel):
    """Request to delete a memory by ID."""

    memory_id: Annotated[
        UUID,
        Field(description="UUID of the memory to delete"),
    ]

    tenant_id: Annotated[
        UUID,
        Field(description="Tenant UUID for multi-tenant isolation"),
    ]


class GetMemoryRequest(BaseModel):
    """Request to retrieve a memory by ID."""

    memory_id: Annotated[
        UUID,
        Field(description="UUID of the memory to retrieve"),
    ]

    tenant_id: Annotated[
        UUID,
        Field(description="Tenant UUID for multi-tenant isolation"),
    ]


class Error(BaseModel):
    """Error response from memory operations.

    Used as union return type: `Memory | Error` or `list[SearchResult] | Error`
    """

    description: Annotated[
        str,
        Field(description="Error message explaining what went wrong"),
    ]
