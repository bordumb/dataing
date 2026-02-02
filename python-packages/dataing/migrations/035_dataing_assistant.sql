-- Migration: 035_dataing_assistant.sql
-- Dataing Assistant - Chat sessions, messages, and audit logging
-- Epic fn-56: Dataing Assistant

-- =============================================================================
-- Session Table
-- =============================================================================

-- Assistant sessions - each session is linked to an investigation
CREATE TABLE assistant_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Parent/child investigation linking
    parent_investigation_id UUID REFERENCES investigations(id) ON DELETE SET NULL,
    is_parent BOOLEAN DEFAULT false,

    -- Session state
    title TEXT,  -- User-provided or auto-generated title
    token_count INTEGER DEFAULT 0,
    last_activity TIMESTAMPTZ DEFAULT NOW(),

    -- Metadata (user preferences, panel size, etc.)
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assistant_sessions_tenant ON assistant_sessions(tenant_id);
CREATE INDEX idx_assistant_sessions_user ON assistant_sessions(user_id);
CREATE INDEX idx_assistant_sessions_investigation ON assistant_sessions(investigation_id);
CREATE INDEX idx_assistant_sessions_activity ON assistant_sessions(tenant_id, last_activity DESC);

COMMENT ON TABLE assistant_sessions IS 'Chat sessions for the Dataing Assistant';
COMMENT ON COLUMN assistant_sessions.investigation_id IS 'Each session creates its own investigation';
COMMENT ON COLUMN assistant_sessions.parent_investigation_id IS 'Optional link to parent investigation for context';
COMMENT ON COLUMN assistant_sessions.is_parent IS 'Whether this session is the parent of linked investigations';

-- =============================================================================
-- Message Table
-- =============================================================================

-- Messages within sessions
CREATE TABLE assistant_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES assistant_sessions(id) ON DELETE CASCADE,

    -- Message content
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,

    -- Tool tracking (for assistant/tool messages)
    tool_calls JSONB,  -- Array of {name, arguments, result}

    -- Token usage
    token_count INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assistant_messages_session ON assistant_messages(session_id, created_at);

COMMENT ON TABLE assistant_messages IS 'Messages in Dataing Assistant sessions';
COMMENT ON COLUMN assistant_messages.tool_calls IS 'Tool calls made by assistant: [{name, arguments, result}]';

-- =============================================================================
-- Audit Log Table
-- =============================================================================

-- Audit log for security and debugging
CREATE TABLE assistant_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES assistant_sessions(id) ON DELETE CASCADE,

    -- Action details
    action TEXT NOT NULL,  -- 'file_read', 'search', 'query', 'docker_status', 'git_read'
    target TEXT NOT NULL,  -- File path, query, container name, etc.
    result_summary TEXT,   -- Brief summary of result or error

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,  -- Extra details (bytes read, lines returned, etc.)

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assistant_audit_session ON assistant_audit_log(session_id, created_at);
CREATE INDEX idx_assistant_audit_action ON assistant_audit_log(action, created_at DESC);

COMMENT ON TABLE assistant_audit_log IS 'Audit log of tool usage in Dataing Assistant';
COMMENT ON COLUMN assistant_audit_log.action IS 'Tool action: file_read, search, query, docker_status, git_read';
COMMENT ON COLUMN assistant_audit_log.target IS 'Target of action: file path, SQL query, container name, etc.';

-- =============================================================================
-- Trigger for last_activity update
-- =============================================================================

-- Auto-update last_activity when messages are added
CREATE OR REPLACE FUNCTION update_assistant_session_activity()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE assistant_sessions
    SET last_activity = NOW()
    WHERE id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER assistant_message_activity_trigger
    AFTER INSERT ON assistant_messages
    FOR EACH ROW EXECUTE FUNCTION update_assistant_session_activity();
