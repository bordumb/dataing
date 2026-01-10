-- Migration: 012_agent_memories.sql
-- Description: Add pgvector extension and agent_memories table for vector memory storage
-- Date: 2026-01-10

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Agent memories table with vector embeddings
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,

    -- Content
    content TEXT NOT NULL,
    conversation_id TEXT,
    tags TEXT[] DEFAULT '{}',

    -- Vector embedding (dimension configurable, default 1536 for OpenAI ada-002)
    embedding vector(1536),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT agent_memories_content_not_empty CHECK (content <> '')
);

-- HNSW index for fast approximate nearest neighbor search
-- Using cosine distance to match semantic similarity behavior
CREATE INDEX IF NOT EXISTS idx_agent_memories_embedding
    ON agent_memories USING hnsw (embedding vector_cosine_ops);

-- Tenant isolation index (critical for multi-tenant queries)
CREATE INDEX IF NOT EXISTS idx_agent_memories_tenant
    ON agent_memories(tenant_id);

-- Agent filtering index (compound for common query pattern)
CREATE INDEX IF NOT EXISTS idx_agent_memories_agent
    ON agent_memories(tenant_id, agent_id);

-- Tag filtering (GIN index for array containment queries)
CREATE INDEX IF NOT EXISTS idx_agent_memories_tags
    ON agent_memories USING gin(tags);

-- Documentation
COMMENT ON TABLE agent_memories IS 'Vector memory store for agent context and learning';
COMMENT ON COLUMN agent_memories.embedding IS 'Vector embedding (1536 dims default for OpenAI text-embedding-3-small)';
COMMENT ON COLUMN agent_memories.tags IS 'Array of tags for filtering memories';
