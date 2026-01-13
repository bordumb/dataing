# fn-6.7 Add SSO Admin Configuration Routes

## Description

Add admin routes for configuring OIDC SSO per organization. Admins need to set up IdP connection details.

## Routes

```
POST   /api/v1/admin/sso/config     - Create/update SSO config
GET    /api/v1/admin/sso/config     - Get current SSO config
DELETE /api/v1/admin/sso/config     - Disable SSO
POST   /api/v1/admin/sso/test       - Test SSO configuration
```

## Implementation

1. Add routes to `dataing-ee/src/dataing_ee/entrypoints/api/routes/settings.py`
2. Use `SSORepository` for CRUD
3. Encrypt client secret before storing (fn-6.3)
4. Test endpoint validates OIDC discovery document is reachable
5. Require `admin` role for all endpoints

## Request/Response Models

```python
class SSOConfigRequest(BaseModel):
    provider_type: Literal["oidc"] = "oidc"
    oidc_issuer_url: str
    oidc_client_id: str
    oidc_client_secret: str

class SSOConfigResponse(BaseModel):
    provider_type: str
    oidc_issuer_url: str
    oidc_client_id: str
    is_enabled: bool
    created_at: datetime
```

## Key Files

- `dataing-ee/src/dataing_ee/entrypoints/api/routes/settings.py` - Add SSO routes
- `dataing-ee/src/dataing_ee/adapters/sso/repository.py` - Existing CRUD
## Acceptance
- [ ] Create/update SSO config endpoint works
- [ ] Get SSO config returns config (without secret)
- [ ] Delete SSO config disables SSO
- [ ] Test endpoint validates IdP is reachable
- [ ] All endpoints require admin role
- [ ] Client secret encrypted on create/update
- [ ] Pydantic models for request/response
- [ ] Unit tests for CRUD operations
## Done summary
Added SSO admin configuration routes for managing OIDC settings:

Routes added:
- GET /settings/sso/config - Get current SSO configuration
- POST /settings/sso/config - Create or update SSO configuration
- DELETE /settings/sso/config - Disable SSO (preserves config for re-enabling)
- POST /settings/sso/test - Test OIDC discovery document validity

Features:
- All endpoints require admin scope
- Client secret encrypted before storage using Fernet
- Test endpoint validates IdP reachability and OIDC metadata
- Create/update handles both new and existing configurations
- Added 9 unit tests covering CRUD and test functionality
## Evidence
- Commits:
- Tests: dataing-ee/tests/unit/entrypoints/api/routes/test_settings_sso.py (9 tests)
- PRs:
