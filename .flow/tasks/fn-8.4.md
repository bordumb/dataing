# fn-8.4 Create security trust page (security.md)

## Description

Create a comprehensive security section with three pages for B2B buyers (CISOs, Data Engineers).

### Create Files

- `docs/docs/security/data-privacy.md`
- `docs/docs/security/rbac.md`
- `docs/docs/security/compliance.md`

### data-privacy.md Content

1. **Read-Only Promise:**
   - SELECT-only queries, LIMIT clause always enforced
   - Reference: `validator.py` FORBIDDEN_STATEMENTS list
   - "We only read metadata, not rows"

2. **PII Protection:**
   - PII detection (email, SSN, CC, phone)
   - Automatic masking before LLM processing
   - Reference: `pii.py`

3. **LLM Data Handling:**
   - What data is sent to Anthropic
   - No training on customer data

### rbac.md Content

1. **Authentication:**
   - API key authentication
   - JWT tokens
   - SSO/OIDC/SAML (EE)

2. **Authorization:**
   - Role hierarchy (Viewer, Editor, Admin)
   - Tenant isolation
   - Reference: `auth.py`, `rbac.py`

3. **SCIM Provisioning (EE):**
   - User lifecycle management
   - Group sync

### compliance.md Content

1. **SOC 2 Type II:**
   - Planned certification timeline
   - Control framework

2. **Self-Hosting Option:**
   - On-premise deployment
   - Data never leaves your network

3. **Data Residency:**
   - Future EU/US region options

### Source Code References

- `/dataing/src/dataing/safety/validator.py`
- `/dataing/src/dataing/safety/pii.py`
- `/dataing/src/dataing/services/auth.py`
- `/dataing-ee/src/dataing_ee/adapters/audit/`
## Acceptance
- [ ] `security/data-privacy.md` exists with read-only promise
- [ ] `security/rbac.md` exists with auth/authz details
- [ ] `security/compliance.md` exists with SOC 2 roadmap
- [ ] PII detection types listed (email, SSN, CC, phone)
- [ ] Circuit breaker limits documented (50 queries, 10 min)
- [ ] SSO/RBAC mentioned as EE features
- [ ] No false compliance claims (SOC 2 marked as "planned")
- [ ] Self-hosting option mentioned
- [ ] All pages render in both themes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
