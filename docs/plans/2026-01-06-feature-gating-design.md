# Feature Gating Design

**Goal:** Enforce plan-based access control for Enterprise features and usage limits, with frontend upgrade prompts.

## Decisions

- **Visibility:** Users can see settings pages, gated on action (not hidden)
- **Limit behavior:** Hard block at limit with 1-2 grace period for downgrades
- **Upgrade paths:** Pro limits → billing page (self-serve), Enterprise features → Contact Sales

## Phases

### Phase 1: MVP Feature Gating

#### Backend Route Gating

| Feature | Routes | Gate Type |
|---------|--------|-----------|
| AUDIT_LOGS | `/api/v1/audit-logs/*` | `@require_feature` (done) |
| SSO_OIDC | `POST /api/v1/sso/oidc/config` | `@require_feature` |
| SSO_SAML | `POST /api/v1/sso/saml/config` | `@require_feature` |
| SCIM | `POST /api/v1/scim/enable` | `@require_feature` |
| MAX_SEATS | `POST /api/v1/teams/*/members` | `@require_under_limit` |
| MAX_DATASOURCES | `POST /api/v1/datasources` | `@require_under_limit` |
| MAX_INVESTIGATIONS | `POST /api/v1/investigations` | `@require_under_limit` |

#### 403 Response Format

```json
{
  "error": "feature_not_available",
  "feature": "sso_oidc",
  "message": "SSO requires an Enterprise plan.",
  "upgrade_url": "/settings/billing",
  "contact_sales": true
}
```

For limits:
```json
{
  "error": "limit_exceeded",
  "feature": "max_seats",
  "limit": 3,
  "usage": 3,
  "message": "You've reached your limit of 3 seats.",
  "upgrade_url": "/settings/billing",
  "contact_sales": false
}
```

#### Frontend Upgrade Modal

- Global 403 interceptor in API client
- `<UpgradeRequiredModal />` component
- Content driven by error response:
  - `contact_sales: true` → "Contact Sales" button
  - `contact_sales: false` → "Upgrade" button → `/settings/billing`
  - Shows usage bar when `limit` + `usage` present

#### Phase 1 Tasks

1. Fix entitlements middleware tests (update mocks for request-based adapter)
2. Apply `@require_under_limit` to creation routes (investigations, datasources, members)
3. Add `contact_sales` field to 403 responses
4. Create `<UpgradeRequiredModal />` component
5. Add global 403 interceptor in API client
6. Manual test with free/pro/enterprise orgs

### Phase 2: Usage Visibility

- Usage meters in Settings ("3/10 seats", "5/10 datasources")
- Warning banners at 80% threshold
- Grace period logic for downgrades (allow 1-2 over limit temporarily)

### Phase 3: Admin & Notifications

- Admin dashboard showing all orgs' plans and usage
- Email notifications at 80% and 100% of limits
- Usage trends/history
