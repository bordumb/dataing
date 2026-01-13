# fn-6.1 Add ID Token JWT Signature Verification

## Description

Add proper JWT signature verification to the OIDC ID token parsing in `OIDCProvider`. Currently `parse_id_token_claims()` decodes the JWT without verifying the signature, which is a security vulnerability.

## Implementation

1. Add PyJWKClient to fetch JWKS from IdP's `jwks_uri`
2. Update `parse_id_token_claims()` to:
   - Fetch signing key from JWKS using `kid` header
   - Verify signature using PyJWT with RS256 algorithm
   - Validate standard claims: `iss`, `aud`, `exp`, `iat`
   - Validate `nonce` claim matches stored nonce

## Key Files

- `dataing-ee/src/dataing_ee/adapters/sso/oidc_provider.py:182-212` - Current unverified parsing
- PyJWT docs: https://pyjwt.readthedocs.io/en/stable/usage.html#retrieve-rsa-signing-keys-from-a-jwks-endpoint

## Notes

- JWKS endpoint is available from OIDC discovery document (`jwks_uri`)
- Cache JWKS with reasonable TTL (e.g., 1 hour) to avoid fetching on every request
- Handle key rotation gracefully (refetch on `kid` mismatch)
## Acceptance
- [ ] `parse_id_token_claims()` verifies JWT signature via JWKS
- [ ] Standard claims validated: `iss`, `aud`, `exp`, `iat`
- [ ] `nonce` claim validated against stored nonce
- [ ] JWKS cached with configurable TTL
- [ ] Key rotation handled (refetch on `kid` mismatch)
- [ ] Invalid/expired tokens raise appropriate exceptions
- [ ] Unit tests cover valid token, expired token, wrong issuer, wrong audience, invalid signature
## Done summary
Added JWT signature verification via JWKS to OIDCProvider:

- Added `verify_id_token()` method that validates JWT signature using PyJWKClient
- Added JWKS caching with configurable TTL (default 1 hour)
- Validates standard claims: iss, aud, exp, iat, sub (required)
- Validates nonce claim when provided (for replay protection)
- Handles key rotation gracefully by refetching JWKS on kid mismatch
- Added exception hierarchy: SSOTokenError → InvalidSignatureError, InvalidClaimsError, TokenExpiredError
- Added JWKSCache dataclass for managing cache state
- Added comprehensive unit tests (8 new test cases)
## Evidence
- Commits:
- Tests: dataing-ee/tests/unit/adapters/sso/test_oidc_provider.py::TestVerifyIdToken (6 tests), dataing-ee/tests/unit/adapters/sso/test_oidc_provider.py::TestJWKSCaching (2 tests)
- PRs:
