-- Unified comment votes table
CREATE TABLE comment_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    comment_type VARCHAR(50) NOT NULL CHECK (comment_type IN ('schema', 'knowledge')),
    comment_id UUID NOT NULL,
    user_id UUID NOT NULL,
    vote INT NOT NULL CHECK (vote IN (1, -1)),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(comment_type, comment_id, user_id)
);

CREATE INDEX idx_comment_votes_lookup ON comment_votes(comment_type, comment_id);
