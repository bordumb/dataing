-- SSO and SCIM tables for enterprise authentication
-- Migration 007: SSO + SCIM

-- SSO provider type
CREATE TYPE sso_provider_type AS ENUM ('oidc', 'saml');

-- SSO configuration per organization
CREATE TABLE sso_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider_type sso_provider_type NOT NULL,
    display_name VARCHAR(100),
    is_enabled BOOLEAN DEFAULT true,

    -- OIDC settings
    oidc_issuer_url VARCHAR(500),
    oidc_client_id VARCHAR(255),
    oidc_client_secret_encrypted BYTEA,

    -- SAML settings
    saml_idp_metadata_url VARCHAR(500),
    saml_idp_entity_id VARCHAR(500),
    saml_certificate TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id)
);

-- Domain claims with verification
CREATE TABLE domain_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    domain VARCHAR(255) NOT NULL,
    is_verified BOOLEAN DEFAULT false,
    verification_token VARCHAR(64),
    verified_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(domain)
);

-- SSO user identities (links IdP identity to local user)
CREATE TABLE sso_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sso_config_id UUID NOT NULL REFERENCES sso_configs(id) ON DELETE CASCADE,
    idp_user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sso_config_id, idp_user_id)
);

-- SCIM bearer tokens for provisioning
CREATE TABLE scim_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,
    description VARCHAR(255),
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_sso_configs_org ON sso_configs(org_id);
CREATE INDEX idx_domain_claims_domain ON domain_claims(domain);
CREATE INDEX idx_domain_claims_org ON domain_claims(org_id);
CREATE INDEX idx_sso_identities_user ON sso_identities(user_id);
CREATE INDEX idx_scim_tokens_org ON scim_tokens(org_id);
