# fn-6.9 SSO Integration Tests

## Description

Add integration tests for the complete SSO flow from discovery to authenticated session.

## Test Scenarios

1. **Happy path**: Discovery -> IdP redirect -> Callback -> JWT issued
2. **New user JIT**: First SSO login creates user
3. **Existing user link**: Password user logs in via SSO, accounts linked
4. **Invalid state**: Callback with wrong/expired state rejected
5. **Invalid token**: Callback with invalid ID token rejected
6. **Unconfigured domain**: Discovery returns password method
7. **Unverified domain**: Discovery returns password method

## Implementation

1. Create `dataing-ee/tests/integration/sso/test_sso_flow.py`
2. Mock external IdP responses (OIDC discovery, token exchange)
3. Use test database with SSO config and domain claims
4. Verify JWT tokens issued are valid with CE middleware

## Key Files

- New: `dataing-ee/tests/integration/sso/test_sso_flow.py`
- `dataing-ee/tests/unit/adapters/sso/test_oidc_provider.py` - Existing unit tests pattern
## Acceptance
- [ ] Happy path test passes
- [ ] JIT provisioning test passes
- [ ] Account linking test passes
- [ ] Invalid state rejected
- [ ] Invalid token rejected
- [ ] Unconfigured domain handled
- [ ] Tests use mocked IdP responses
- [ ] All tests pass in CI
## Done summary
Added integration tests for the complete SSO flow:

Test Coverage:
- Discovery endpoint: 4 tests (unknown domain, unverified domain, verified domain, disabled SSO)
- Callback endpoint: 8 tests (invalid state, consumed state, JIT provisioning, account linking, unverified email rejection, existing SSO identity reuse, invalid token, expired token)

Total: 12 integration tests

Features tested:
- Discovery returns password for unknown/unverified domains
- Discovery returns OIDC auth URL for verified domains with SSO configured
- Callback rejects invalid or already-consumed state (CSRF protection)
- Callback JIT provisions new users on first SSO login
- Callback links existing users when email is verified by IdP
- Callback rejects account linking when IdP email is unverified (security)
- Callback reuses existing SSO identity for returning users
- Callback rejects invalid or expired ID tokens
## Evidence
- Commits:
- Tests: dataing-ee/tests/integration/sso/test_sso_flow.py (12 tests)
- PRs:
