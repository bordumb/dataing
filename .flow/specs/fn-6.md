# SSO (OIDC) Implementation for Enterprise

## Overview

Implement Single Sign-On (SSO) via OIDC for enterprise customers. This is a **major enterprise blocker** - tables exist but no routes/logic are wired.

**Scope**: OIDC only (SAML deferred to separate epic). All code in `dataing-ee/`.

## Current State

**Exists (DONE)**:
- Database tables: `sso_configs`, `domain_claims`, `sso_identities`, `scim_tokens` (`dataing/migrations/007_sso_scim_tables.sql`)
- Core types: `SSOConfig`, `DomainClaim`, `SSOIdentity` (`dataing-ee/src/dataing_ee/core/sso/types.py`)
- OIDC Provider: Discovery, auth URL, token exchange (`dataing-ee/src/dataing_ee/adapters/sso/oidc_provider.py`)
- Repositories: SSO, SCIM (`dataing-ee/src/dataing_ee/adapters/sso/repository.py`)
- DNS verification logic (`dataing-ee/src/dataing_ee/core/sso/dns_verification.py`)

**Missing (TODO)**:
- SSO discovery endpoint (returns hardcoded `{"method": "password"}`)
- SSO callback endpoint (returns 501)
- State management (in-memory dict, not production-ready)
- ID token JWT signature verification
- Client secret encryption
- Admin routes for SSO configuration
- Domain claim/verification routes
- JIT user provisioning with existing user linking

## Approach

1. **Fix security issues first**: ID token validation, state management, secret encryption
2. **Wire existing adapters to routes**: Discovery, callback with JIT provisioning
3. **Add admin routes**: SSO config, domain claims
4. **Handle edge cases**: Existing user linking, error handling

## Key Files

| File | Purpose |
|------|---------|
| `dataing-ee/src/dataing_ee/entrypoints/api/routes/sso.py` | SSO routes (stubs) |
| `dataing-ee/src/dataing_ee/adapters/sso/oidc_provider.py` | OIDC flow implementation |
| `dataing-ee/src/dataing_ee/adapters/sso/repository.py` | SSO config/domain CRUD |
| `dataing/src/dataing/core/auth/service.py` | CE AuthService (reuse for user creation) |
| `dataing/src/dataing/core/auth/jwt.py` | JWT creation (reuse) |

## Reusable Code

- **CE AuthService** (`dataing/src/dataing/core/auth/service.py`): Use for JIT user provisioning
- **CE jwt.py** (`dataing/src/dataing/core/auth/jwt.py`): Use `create_access_token`, `create_refresh_token`
- **OIDCProvider** (`dataing-ee/src/dataing_ee/adapters/sso/oidc_provider.py`): Already implemented, just wire to routes

## Quick Commands

```bash
# Run EE backend
just dev-backend

# Run EE tests
just test-ee

# Smoke test - SSO discovery should return OIDC URL for configured domain
curl -X POST http://localhost:8000/api/v1/auth/sso/discover \
  -H "Content-Type: application/json" \
  -d '{"email": "user@configured-domain.com"}'
```

## Acceptance Criteria

- [ ] SSO discovery returns OIDC auth URL for verified domains
- [ ] SSO callback exchanges code, provisions user, returns JWT
- [ ] Existing users linked by email on first SSO login
- [ ] ID tokens validated with JWKS signature verification
- [ ] State parameters stored securely (not in-memory dict)
- [ ] Client secrets encrypted at rest
- [ ] Admin can configure OIDC for their org
- [ ] Admin can claim and verify domains
- [ ] All SSO routes require appropriate authentication/authorization
- [ ] Unit and integration tests pass

## Security Requirements

- ID token JWT signature verification via JWKS
- State parameter with CSRF protection and expiry
- Nonce validation to prevent token replay
- Client secret encryption (Fernet/AES-GCM)
- Domain verification required before SSO routing
- Audit logging for SSO events

## Open Questions

1. **Redis for state?** Or database? Or signed JWT state tokens?
2. **Default role for JIT users?** Currently SCIM uses `member`
3. **Force SSO mode?** Can admins disable password login per org?

## References

- Existing OIDC provider: `dataing-ee/src/dataing_ee/adapters/sso/oidc_provider.py:1-213`
- SSO routes (stubs): `dataing-ee/src/dataing_ee/entrypoints/api/routes/sso.py:1-144`
- Migration: `dataing/migrations/007_sso_scim_tables.sql:1-69`
- CE Auth: `dataing/src/dataing/core/auth/service.py:1-406`
- Authlib docs: https://docs.authlib.org/en/latest/client/httpx.html
