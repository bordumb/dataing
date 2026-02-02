-- Migration: 036_memory_audit_log.sql
-- Description: Add audit logging table for agent memory operations (EE compliance feature)
-- Date: 2026-02-02
-- Note: Table schema is in CE, but logging code is EE-only

-- Audit log for memory operations (compliance requirement for regulated industries)
CREATE TABLE IF NOT EXISTS memory_access_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID REFERENCES agent_memories(id) ON DELETE SET NULL,
    tenant_id UUID NOT NULL,
    actor_id UUID,  -- user or agent that performed action
    operation TEXT NOT NULL CHECK (operation IN ('create', 'search', 'delete', 'get')),
    query_text TEXT,  -- for search operations, the search query
    result_count INT,  -- number of results returned
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_memory_access_log_tenant
    ON memory_access_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_memory_access_log_time
    ON memory_access_log(accessed_at);
CREATE INDEX IF NOT EXISTS idx_memory_access_log_memory
    ON memory_access_log(memory_id) WHERE memory_id IS NOT NULL;

-- Documentation
COMMENT ON TABLE memory_access_log IS
    'Audit trail for agent memory operations - EE compliance feature for regulated industries';
COMMENT ON COLUMN memory_access_log.actor_id IS
    'UUID of user or agent that performed the operation';
COMMENT ON COLUMN memory_access_log.query_text IS
    'Search query text (consider encrypting if may contain PII)';
