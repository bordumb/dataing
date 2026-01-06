# Feature Gates by Plan

This document outlines the features available on each plan tier.

## Plan Comparison

| Feature | Free | Pro | Enterprise |
|---------|------|-----|------------|
| **Seats** | 3 | 10 | Unlimited |
| **Data Sources** | 2 | 10 | Unlimited |
| **Investigations/Month** | 10 | 100 | Unlimited |
| **SSO (OIDC)** | - | - | Yes |
| **SSO (SAML)** | - | - | Yes |
| **SCIM Provisioning** | - | - | Yes |
| **Audit Logs** | - | - | Yes |

## Implementation Details

### Limit-Based Features

These features use the `@require_under_limit` decorator to check current usage against plan limits:

- **MAX_SEATS** - Number of users in an organization
- **MAX_DATASOURCES** - Number of connected data sources
- **MAX_INVESTIGATIONS_PER_MONTH** - Rolling 30-day investigation count

When a limit is reached, the API returns `403 Forbidden` with:
```json
{
  "detail": "Plan limit reached for <feature>. Please upgrade your plan.",
  "upgrade_required": true,
  "feature": "<feature_name>"
}
```

### Boolean Features

These features use the `@require_feature` decorator to check if a feature is enabled:

- **SSO_OIDC** - OpenID Connect single sign-on
- **SSO_SAML** - SAML 2.0 single sign-on
- **SCIM** - System for Cross-domain Identity Management (user provisioning)
- **AUDIT_LOGS** - Access to audit log events

When a feature is not available, the API returns `403 Forbidden` with:
```json
{
  "detail": "<feature> is only available on Enterprise plan. Please upgrade.",
  "upgrade_required": true,
  "feature": "<feature_name>"
}
```

## Frontend Handling

The frontend intercepts 403 responses with `upgrade_required: true` and displays an upgrade modal. This allows users to:
1. See which feature requires an upgrade
2. Contact sales for Enterprise features
3. View plan comparison

## Code References

- Feature definitions: `backend/src/dataing/core/entitlements/features.py`
- Entitlements middleware: `backend/src/dataing/entrypoints/api/middleware/entitlements.py`
- Entitlements service: `backend/src/dataing/core/entitlements/service.py`
- Database adapter: `backend/src/dataing/adapters/entitlements/database.py`
