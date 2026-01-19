-- SSO State management for CSRF protection and replay prevention
-- Migration 015: SSO States

-- SSO authentication state tokens
CREATE TABLE sso_states (
    state_id VARCHAR(64) PRIMARY KEY,
    nonce VARCHAR(64) NOT NULL,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    redirect_uri VARCHAR(1000),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);

-- Index for cleanup job and org lookup
CREATE INDEX idx_sso_states_expires ON sso_states(expires_at);
CREATE INDEX idx_sso_states_org ON sso_states(org_id);

-- Comment explaining the table purpose
COMMENT ON TABLE sso_states IS 'Temporary state tokens for SSO CSRF protection. States are single-use and auto-expire.';
COMMENT ON COLUMN sso_states.state_id IS 'Cryptographically random state parameter (secrets.token_urlsafe)';
COMMENT ON COLUMN sso_states.nonce IS 'OIDC nonce for ID token replay protection';
COMMENT ON COLUMN sso_states.consumed_at IS 'Set on first callback use - prevents replay attacks';
