# fn-6.5 Wire SSO Callback with JIT Provisioning

## Description

Wire the SSO callback endpoint to exchange auth code, validate tokens, and provision users. Currently returns 501 Not Implemented.

## Implementation

1. Validate and consume state parameter (via SSOStateRepository)
2. Exchange auth code for tokens using `OIDCProvider.exchange_code()`
3. Validate ID token (via fn-6.1 JWT verification)
4. Extract user info (email, name, sub)
5. Look up or create SSO identity in `sso_identities`
6. JIT provision user if new (via CE AuthService)
7. Issue JWT tokens (access + refresh) using CE `jwt.py`
8. Return tokens to frontend

## Key Files

- `dataing-ee/src/dataing_ee/entrypoints/api/routes/sso.py:88-125` - Current stub
- `dataing-ee/src/dataing_ee/adapters/sso/oidc_provider.py:117-179` - Code exchange
- `dataing/src/dataing/core/auth/service.py` - User creation
- `dataing/src/dataing/core/auth/jwt.py` - Token creation

## JIT Provisioning

- If SSO identity exists: get linked user, issue tokens
- If SSO identity doesn't exist but user with email exists: link and issue tokens (fn-6.6)
- If neither exists: create user, create SSO identity, issue tokens

## Security

- Validate nonce matches stored nonce
- Validate state matches stored state
- Only accept verified email addresses from IdP
## Acceptance
- [ ] Callback validates and consumes state
- [ ] Auth code exchanged for tokens
- [ ] ID token validated (signature, claims, nonce)
- [ ] SSO identity created/updated in database
- [ ] New users JIT provisioned with `member` role
- [ ] JWT tokens issued compatible with CE middleware
- [ ] Errors return appropriate HTTP status codes
- [ ] Unit tests for happy path and error cases
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
