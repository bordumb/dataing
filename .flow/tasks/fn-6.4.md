# fn-6.4 Wire SSO Discovery Endpoint

## Description

Wire the SSO discovery endpoint to actually look up domain claims and return OIDC auth URL. Currently returns hardcoded `{"method": "password"}`.

## Implementation

1. Extract email domain from request
2. Query `domain_claims` for verified domain claim
3. If found, get associated `sso_configs` for the org
4. Generate OIDC auth URL using `OIDCProvider.get_authorization_url()`
5. Store state using `SSOStateRepository` (from fn-6.2)
6. Return `{"method": "oidc", "auth_url": "..."}`
7. If no SSO configured, return `{"method": "password"}`

## Key Files

- `dataing-ee/src/dataing_ee/entrypoints/api/routes/sso.py:73-85` - Current stub
- `dataing-ee/src/dataing_ee/adapters/sso/repository.py` - Domain/config queries
- `dataing-ee/src/dataing_ee/adapters/sso/oidc_provider.py:89-115` - Auth URL generation

## Flow

```
POST /auth/sso/discover {"email": "user@acme.com"}
  -> Extract domain "acme.com"
  -> Query domain_claims WHERE domain = "acme.com" AND is_verified = true
  -> If found, get sso_configs WHERE org_id = claim.org_id
  -> Generate auth URL with state/nonce
  -> Return {"method": "oidc", "auth_url": "https://idp.example.com/authorize?..."}
```
## Acceptance
- [ ] Discovery extracts email domain correctly
- [ ] Queries verified domain claims
- [ ] Returns OIDC auth URL for configured domains
- [ ] Returns `{"method": "password"}` for unconfigured domains
- [ ] State and nonce stored via SSOStateRepository
- [ ] Auth URL includes all required OIDC parameters
- [ ] Unit tests for discovery with/without SSO config
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
