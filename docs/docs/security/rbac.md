# RBAC & SSO

dataing provides flexible authentication and fine-grained authorization to secure access to your data quality platform.

---

## Authentication Methods

### API Keys

The simplest way to authenticate programmatic access:

```bash
# Create an API key
curl -X POST https://api.dataing.io/v1/api-keys \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{"name": "CI Pipeline", "scopes": ["read", "write"]}'

# Use the API key
curl https://api.dataing.io/v1/investigations \
  -H "X-API-Key: ddr_abc123..."
```

**API key features:**

- Secure random generation with `ddr_` prefix
- Keys are hashed before storage (SHA-256)
- Optional expiration dates
- Scoped permissions (`read`, `write`)
- Key rotation without downtime

### JWT Tokens

For user sessions and interactive access:

```python
# JWT claims structure
{
    "sub": "user_id",
    "tenant_id": "org_123",
    "email": "user@company.com",
    "roles": ["admin"],
    "exp": 1234567890
}
```

### SSO Integration <span class="enterprise-badge">Enterprise</span>

Enterprise Edition supports identity provider integration:

| Protocol | Status | Providers |
|----------|--------|-----------|
| OIDC | GA | Okta, Auth0, Azure AD, Google |
| SAML 2.0 | GA | Okta, OneLogin, Azure AD |

Configure SSO in your organization settings:

```yaml
# Example OIDC configuration
sso:
  provider: oidc
  issuer: https://your-org.okta.com
  client_id: 0oa1234567890
  client_secret: ${OIDC_CLIENT_SECRET}
  scopes:
    - openid
    - profile
    - email
```

---

## Authorization Model

### Role Hierarchy

dataing uses a hierarchical role model:

| Role | Permissions | Use Case |
|------|-------------|----------|
| **Owner** | Full access + billing | Organization creator |
| **Admin** | Manage users, settings, all data | Platform administrators |
| **Member** | Read/write investigations | Data engineers, analysts |

```python
# Role definitions from rbac/types.py
class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
```

### Permission Levels

Fine-grained permissions control access to specific resources:

| Permission | Capabilities |
|------------|--------------|
| `read` | View investigations, read results |
| `write` | Create investigations, add comments |
| `admin` | Manage datasources, users, settings |

### Permission Grants

Permissions can be granted to users or teams, scoped to:

- **Resources** - Specific investigations or reports
- **Tags** - All resources with a given tag
- **Datasources** - Access to specific data connections

```python
# Permission grant structure
@dataclass
class PermissionGrant:
    user_id: UUID | None      # Grant to user
    team_id: UUID | None      # ...or to team
    resource_type: str        # "investigation", "datasource"
    resource_id: UUID | None  # Specific resource
    tag_id: UUID | None       # ...or all tagged resources
    permission: Permission    # read, write, admin
```

---

## Tenant Isolation

Every request is scoped to a tenant. Data from different organizations is strictly isolated:

```python
# All database queries include tenant_id
SELECT * FROM investigations
WHERE tenant_id = $1 AND id = $2
LIMIT 100;
```

**Isolation guarantees:**

- Database-level row filtering
- API key tied to single tenant
- No cross-tenant data access
- Audit logging per tenant

---

## SCIM Provisioning <span class="enterprise-badge">Enterprise</span>

Enterprise Edition supports automated user lifecycle management via SCIM 2.0:

### Supported Operations

| Operation | Endpoint | Description |
|-----------|----------|-------------|
| List users | `GET /scim/v2/Users` | Paginated user list |
| Get user | `GET /scim/v2/Users/:id` | Single user details |
| Create user | `POST /scim/v2/Users` | Provision new user |
| Update user | `PATCH /scim/v2/Users/:id` | Modify attributes |
| Delete user | `DELETE /scim/v2/Users/:id` | Deprovision user |
| List groups | `GET /scim/v2/Groups` | Team list |
| Sync groups | `PATCH /scim/v2/Groups/:id` | Update team members |

### Team Synchronization

Teams in dataing can be linked to identity provider groups:

```python
@dataclass
class Team:
    id: UUID
    org_id: UUID
    name: str
    external_id: str | None  # IDP group ID
    is_scim_managed: bool    # True if synced from IDP
```

When `is_scim_managed` is true:

- Members are synced automatically from the identity provider
- Manual member changes are rejected
- Deleting the IDP group removes the team

---

## API Key Management

### Creating Keys

```bash
# Create a read-only key
curl -X POST /v1/api-keys \
  -d '{"name": "Analytics Reader", "scopes": ["read"]}'

# Create a key with expiration
curl -X POST /v1/api-keys \
  -d '{"name": "Temp Access", "scopes": ["read", "write"], "expires_in_days": 30}'
```

### Rotating Keys

```bash
# Rotate key (revoke old, create new with same settings)
curl -X POST /v1/api-keys/{key_id}/rotate
```

Rotation is atomic - the new key is created before the old one is revoked, ensuring no downtime.

### Revoking Keys

```bash
# Revoke immediately
curl -X DELETE /v1/api-keys/{key_id}
```

Revoked keys return `401 Unauthorized` immediately.

---

## Best Practices

!!! tip "Least Privilege"
    Grant the minimum permissions needed. Use `read` scope for dashboards, `write` only for CI/CD pipelines.

!!! tip "Key Rotation"
    Rotate API keys every 90 days. Use the built-in rotation endpoint to avoid downtime.

!!! tip "SSO for Users"
    Use SSO for interactive users, API keys for service accounts. This ensures proper offboarding when employees leave.

!!! tip "Tag-Based Access"
    Use tags to group related resources, then grant permissions to tags instead of individual resources.
