# fn-6.8 Add Domain Claim and Verification Routes

## Description

Add admin routes for claiming and verifying email domains for SSO routing.

## Routes

```
POST   /api/v1/admin/sso/domains           - Claim a domain
GET    /api/v1/admin/sso/domains           - List claimed domains
DELETE /api/v1/admin/sso/domains/{domain}  - Remove domain claim
POST   /api/v1/admin/sso/domains/{domain}/verify - Verify domain ownership
```

## Implementation

1. Add routes to `dataing-ee/src/dataing_ee/entrypoints/api/routes/settings.py`
2. Claim generates DNS verification token: `_dataing.{domain}` TXT record
3. Verify checks DNS for correct token using `dns_verification.py`
4. Use `SSORepository` for domain claim CRUD
5. Require `admin` role

## Flow

```
1. Admin claims "acme.com"
2. System generates token, returns: "Add TXT record: _dataing.acme.com = dataing-verify=abc123"
3. Admin adds DNS record
4. Admin calls /verify endpoint
5. System checks DNS, marks domain as verified
```

## Key Files

- `dataing-ee/src/dataing_ee/core/sso/dns_verification.py` - DNS checking
- `dataing-ee/src/dataing_ee/adapters/sso/repository.py` - Domain claim CRUD
## Acceptance
- [ ] Claim domain generates verification token
- [ ] List domains shows all org's claims with status
- [ ] Remove domain deletes claim
- [ ] Verify checks DNS TXT record
- [ ] Domain marked verified on successful check
- [ ] All endpoints require admin role
- [ ] Prevents claiming already-verified domains by other orgs
- [ ] Unit tests for domain claim lifecycle
## Done summary
Added domain claim and verification routes for SSO:

Routes added:
- GET /settings/sso/domains - List domain claims for organization
- POST /settings/sso/domains - Claim a domain (generates verification token)
- DELETE /settings/sso/domains/{domain} - Remove domain claim
- POST /settings/sso/domains/{domain}/verify - Verify domain ownership via DNS TXT record

Features:
- All endpoints require admin scope
- Domain claim generates unique verification token with 7-day expiry
- Verification checks DNS TXT record for _dataing-verification.domain
- Already-verified domains return success immediately
- Cannot claim domain verified by another organization
- 10 unit tests covering full domain claim lifecycle
## Evidence
- Commits:
- Tests: dataing-ee/tests/unit/entrypoints/api/routes/test_settings_sso.py (19 tests, 10 new for domains)
- PRs:
