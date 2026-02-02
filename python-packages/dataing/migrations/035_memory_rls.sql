-- Migration: 035_memory_rls.sql
-- Description: Add Row-Level Security (RLS) to agent_memories for tenant isolation
-- Date: 2026-02-02

-- Enable RLS on agent_memories table
ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY;

-- Policy: users can only access their tenant's memories
-- Uses PostgreSQL session variable app.current_tenant set by application
CREATE POLICY tenant_isolation ON agent_memories
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- Force RLS for table owner as well (defense-in-depth)
-- This ensures even superusers must set tenant context unless they explicitly bypass
ALTER TABLE agent_memories FORCE ROW LEVEL SECURITY;

-- Documentation
COMMENT ON POLICY tenant_isolation ON agent_memories IS
    'Enforces tenant isolation - queries must SET app.current_tenant before accessing memories';
