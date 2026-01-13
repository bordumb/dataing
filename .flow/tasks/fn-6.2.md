# fn-6.2 Implement Secure SSO State Management

## Description

Replace the in-memory `_sso_states` dict in `sso.py` with secure, production-ready state management. The current implementation loses state on restart and doesn't work with horizontal scaling.

## Options

1. **Database-backed** (recommended): Store in `sso_states` table with TTL
2. **Signed JWT state**: Encode state in signed token (stateless but larger URLs)
3. **Redis**: Fast but adds infrastructure dependency

## Implementation (Database approach)

1. Create `sso_states` table migration:
   - `state_id` (PK, VARCHAR)
   - `nonce` (VARCHAR, for OIDC replay protection)
   - `redirect_uri` (VARCHAR, for callback validation)
   - `org_id` (UUID, FK)
   - `created_at` (TIMESTAMP)
   - `expires_at` (TIMESTAMP, default 10 minutes)

2. Add `SSOStateRepository` with:
   - `create_state(org_id, redirect_uri) -> (state, nonce)`
   - `validate_and_consume(state, nonce) -> SSOStateData` (single-use)
   - `cleanup_expired()` (background job)

3. Update `sso.py` routes to use repository

## Key Files

- `dataing-ee/src/dataing_ee/entrypoints/api/routes/sso.py:47` - Current in-memory dict
- `dataing/migrations/` - Add new migration

## Security

- State must be single-use (consumed on callback)
- Include nonce for OIDC token replay protection
- Short TTL (10 minutes default)
- Cryptographically random state generation
## Acceptance
- [ ] Migration creates `sso_states` table
- [ ] `SSOStateRepository` implements create/validate/cleanup
- [ ] State is cryptographically random (secrets.token_urlsafe)
- [ ] Nonce generated and stored with state
- [ ] State consumed on first use (cannot replay)
- [ ] Expired states automatically invalid
- [ ] SSO routes use repository instead of in-memory dict
- [ ] Unit tests for state lifecycle
## Done summary
Implemented secure SSO state management with database-backed storage:

- Created migration 015_sso_states.sql with state_id, nonce, org_id, redirect_uri, expires_at, consumed_at
- Created SSOStateRepository with:
  - create_state(org_id, redirect_uri, ttl_seconds) - generates cryptographic state and nonce
  - validate_and_consume(state_id, nonce) - atomic single-use validation
  - get_state(state_id) - read-only lookup
  - cleanup_expired() / cleanup_consumed() - maintenance methods
- Added exception hierarchy: StateValidationError → StateNotFoundError, StateExpiredError, StateConsumedError
- Added SSOState dataclass with is_expired/is_consumed properties
- Updated SSO routes to use repository with proper error handling
- Removed in-memory _sso_states dict
- Added 17 unit tests for state lifecycle
## Evidence
- Commits:
- Tests: dataing-ee/tests/unit/adapters/sso/test_state_repository.py (17 tests), dataing-ee/tests/unit/entrypoints/api/routes/test_sso.py (9 tests)
- PRs:
