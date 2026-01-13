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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
