-- Issue hub threads (docs/specs/0001_issue_chat.md, epic fn-70).
-- One shared thread per issue plus private scratch threads. Messages hold human
-- comments, agent replies and system events in one timeline. `rev` comes from a
-- global sequence and moves on every insert and update, so streams can resume
-- from it; `touched_at` (clock time, not transaction time) lets a poller re-read
-- rows that committed late. issue_comments moves into threads in 038.
-- If fn-59 lands first, tenant_id should reference organizations(id) instead.

CREATE TABLE issue_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('shared', 'scratch')),
    owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((kind = 'shared') = (owner_user_id IS NULL))
);
CREATE UNIQUE INDEX issue_threads_one_shared ON issue_threads (issue_id) WHERE kind = 'shared';
CREATE INDEX issue_threads_owner ON issue_threads (issue_id, owner_user_id)
    WHERE kind = 'scratch';

CREATE SEQUENCE issue_thread_messages_rev_seq;

CREATE TABLE issue_thread_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    thread_id UUID NOT NULL REFERENCES issue_threads(id) ON DELETE CASCADE,
    seq BIGINT NOT NULL,
    rev BIGINT NOT NULL DEFAULT nextval('issue_thread_messages_rev_seq'),
    author_kind TEXT NOT NULL CHECK (author_kind IN ('user', 'agent', 'system')),
    author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    requested_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    request_message_id UUID REFERENCES issue_thread_messages(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'comment', 'agent_reply', 'brief', 'steer', 'investigation', 'event', 'published')),
    body_md TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN (
        'queued', 'streaming', 'complete', 'error', 'cancelled')),
    asks_agent BOOLEAN NOT NULL DEFAULT FALSE,
    reply_to_id UUID REFERENCES issue_thread_messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    touched_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    edited_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    UNIQUE (thread_id, seq)
);
CREATE INDEX issue_thread_messages_rev ON issue_thread_messages (thread_id, rev);
CREATE INDEX issue_thread_messages_touched ON issue_thread_messages (thread_id, touched_at);
-- One agent reply per request, so a retried turn reuses its reply
CREATE UNIQUE INDEX issue_thread_messages_one_reply ON issue_thread_messages (request_message_id)
    WHERE request_message_id IS NOT NULL;
-- Running turns per person (the API allows three)
CREATE INDEX issue_thread_messages_running ON issue_thread_messages (requested_by_user_id)
    WHERE status IN ('queued', 'streaming');

CREATE OR REPLACE FUNCTION bump_issue_thread_message_rev() RETURNS trigger AS $$
BEGIN
    NEW.rev := nextval('issue_thread_messages_rev_seq');
    NEW.touched_at := clock_timestamp();
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER issue_thread_messages_bump_rev
    BEFORE UPDATE ON issue_thread_messages
    FOR EACH ROW EXECUTE FUNCTION bump_issue_thread_message_rev();

CREATE TABLE agent_query_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES issue_thread_messages(id) ON DELETE CASCADE,
    tool_call_id TEXT NOT NULL,
    datasource_id UUID NOT NULL,
    sql TEXT NOT NULL,
    dialect TEXT NOT NULL,
    columns JSONB NOT NULL DEFAULT '[]',
    rows JSONB NOT NULL DEFAULT '[]',
    row_count INTEGER NOT NULL DEFAULT 0,
    truncated BOOLEAN NOT NULL DEFAULT FALSE,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX agent_query_results_message ON agent_query_results (message_id);

CREATE TABLE investigation_steers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    issue_id UUID REFERENCES issues(id) ON DELETE SET NULL,
    message_id UUID REFERENCES issue_thread_messages(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'add_context', 'rule_out', 'add_hypothesis', 'stop_and_synthesize')),
    text TEXT NOT NULL DEFAULT '',
    hypothesis_id TEXT,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'rejected')),
    applied_phase TEXT,
    outcome TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMPTZ
);
CREATE INDEX investigation_steers_investigation ON investigation_steers (investigation_id, created_at);

-- What the create form collects (observed date, column) and used to drop
ALTER TABLE issues ADD COLUMN context JSONB NOT NULL DEFAULT '{}';

-- The editable brief replaces the free-text focus prompt (dropped with the
-- code that still writes it, in a later migration)
ALTER TABLE issue_investigation_runs
    ADD COLUMN brief JSONB,
    ADD COLUMN source_thread_id UUID REFERENCES issue_threads(id) ON DELETE SET NULL,
    ADD COLUMN parent_run_id UUID REFERENCES issue_investigation_runs(id) ON DELETE SET NULL;

UPDATE issue_investigation_runs AS run
SET brief = jsonb_strip_nulls(jsonb_build_object(
    'version', 1,
    'symptom', issue.title,
    'notes', run.focus_prompt))
FROM issues AS issue
WHERE issue.id = run.issue_id;

ALTER TABLE issue_investigation_runs
    ALTER COLUMN brief SET DEFAULT '{"version": 1}',
    ALTER COLUMN brief SET NOT NULL;

-- Every existing issue gets its shared thread
INSERT INTO issue_threads (tenant_id, issue_id, kind)
SELECT tenant_id, id, 'shared' FROM issues;
