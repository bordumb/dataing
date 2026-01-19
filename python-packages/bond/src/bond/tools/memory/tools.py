"""Memory tools for PydanticAI agents.

This module provides the agent-facing tool functions that use
RunContext to access the memory backend via dependency injection.
"""

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

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


async def create_memory(
    ctx: RunContext[AgentMemoryProtocol],
    request: CreateMemoryRequest,
) -> Memory | Error:
    """Store a new memory for later retrieval.

    Agent Usage:
        Call this tool to remember information for future conversations:
        - User preferences: "Remember that I prefer dark mode"
        - Important facts: "Note that the project deadline is March 15"
        - Context: "Store that we discussed the authentication flow"

    Example:
        create_memory({
            "content": "User prefers dark mode and compact view",
            "agent_id": "assistant",
            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
            "tags": ["preferences", "ui"]
        })

    Returns:
        The created Memory object with its ID, or an Error if storage failed.
    """
    result: Memory | Error = await ctx.deps.store(
        content=request.content,
        agent_id=request.agent_id,
        tenant_id=request.tenant_id,
        conversation_id=request.conversation_id,
        tags=request.tags,
        embedding=request.embedding,
        embedding_model=request.embedding_model,
    )
    return result


async def search_memories(
    ctx: RunContext[AgentMemoryProtocol],
    request: SearchMemoriesRequest,
) -> list[SearchResult] | Error:
    """Search memories by semantic similarity.

    Agent Usage:
        Call this tool to recall relevant information:
        - Find preferences: "What are the user's UI preferences?"
        - Recall context: "What did we discuss about authentication?"
        - Find related: "Search for memories about the project deadline"

    Example:
        search_memories({
            "query": "user interface preferences",
            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
            "top_k": 5,
            "tags": ["preferences"]
        })

    Returns:
        List of SearchResult with memories and similarity scores,
        ordered by relevance (highest score first).
    """
    result: list[SearchResult] | Error = await ctx.deps.search(
        query=request.query,
        tenant_id=request.tenant_id,
        top_k=request.top_k,
        score_threshold=request.score_threshold,
        tags=request.tags,
        agent_id=request.agent_id,
        embedding_model=request.embedding_model,
    )
    return result


async def delete_memory(
    ctx: RunContext[AgentMemoryProtocol],
    request: DeleteMemoryRequest,
) -> bool | Error:
    """Delete a memory by ID.

    Agent Usage:
        Call this tool to remove outdated or incorrect memories:
        - Remove stale: "Delete the old deadline memory"
        - Correct mistakes: "Remove the incorrect preference"

    Example:
        delete_memory({
            "memory_id": "550e8400-e29b-41d4-a716-446655440000",
            "tenant_id": "660e8400-e29b-41d4-a716-446655440000"
        })

    Returns:
        True if deleted, False if not found, or Error if deletion failed.
    """
    result: bool | Error = await ctx.deps.delete(
        request.memory_id,
        tenant_id=request.tenant_id,
    )
    return result


async def get_memory(
    ctx: RunContext[AgentMemoryProtocol],
    request: GetMemoryRequest,
) -> Memory | None | Error:
    """Retrieve a specific memory by ID.

    Agent Usage:
        Call this tool to get details of a specific memory:
        - Verify content: "Get the full text of memory X"
        - Check metadata: "What tags does memory X have?"

    Example:
        get_memory({
            "memory_id": "550e8400-e29b-41d4-a716-446655440000",
            "tenant_id": "660e8400-e29b-41d4-a716-446655440000"
        })

    Returns:
        The Memory if found, None if not found, or Error if retrieval failed.
    """
    result: Memory | None | Error = await ctx.deps.get(
        request.memory_id,
        tenant_id=request.tenant_id,
    )
    return result


# Export as toolset for BondAgent
memory_toolset: list[Tool[AgentMemoryProtocol]] = [
    Tool(create_memory),
    Tool(search_memories),
    Tool(delete_memory),
    Tool(get_memory),
]
