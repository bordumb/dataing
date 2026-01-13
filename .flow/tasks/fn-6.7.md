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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
