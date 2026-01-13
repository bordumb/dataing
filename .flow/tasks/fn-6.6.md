# fn-6.6 Link Existing Users on SSO Login

## Description

Handle the case where a user already exists with password auth and logs in via SSO for the first time. Link the accounts by email.

## Implementation

1. During SSO callback, after validating ID token:
2. Check if `sso_identities` record exists for this `idp_user_id`
3. If not, check if user exists with same email
4. If user exists: create `sso_identities` link, use existing user
5. If not: create new user (JIT provision)

## Key Files

- `dataing-ee/src/dataing_ee/entrypoints/api/routes/sso.py` - Callback logic
- `dataing-ee/src/dataing_ee/adapters/sso/repository.py` - SSO identity CRUD

## Edge Cases

- Multiple orgs claiming same domain (shouldn't happen with verification)
- User email changed at IdP since last login
- User manually linked to different IdP user

## Security

- Only link if IdP-provided email is verified (`email_verified: true`)
- Log account linking for audit trail
## Acceptance
- [ ] Existing users linked by email on first SSO login
- [ ] SSO identity record created with correct `user_id`
- [ ] Only links if IdP email is verified
- [ ] Subsequent SSO logins use existing link
- [ ] Audit log entry for account linking
- [ ] Unit tests for linking scenarios
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
