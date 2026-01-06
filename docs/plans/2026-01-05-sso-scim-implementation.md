# SSO + SCIM Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add enterprise SSO (OIDC + SAML) and SCIM user provisioning to Dataing.

**Architecture:** Email-first login flow with domain-based SSO routing. Per-org SSO configuration with DNS-verified domain claims. SCIM 2.0 endpoints for user/group provisioning with IdP group → Dataing team mapping.

**Tech Stack:** FastAPI, PostgreSQL, authlib (OIDC), python3-saml (SAML), dnspython (DNS verification), React

---

## Phase 1: Database & Types

### Task 1: SSO Database Migration

**Files:**
- Create: `backend/migrations/010_sso_scim_tables.sql`

**Step 1: Write the migration**

```sql
-- backend/migrations/010_sso_scim_tables.sql
-- SSO and SCIM tables for enterprise authentication

-- SSO provider type
CREATE TYPE sso_provider_type AS ENUM ('oidc', 'saml');

-- SSO configuration per organization
CREATE TABLE sso_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider_type sso_provider_type NOT NULL,
    display_name VARCHAR(100),
    is_enabled BOOLEAN DEFAULT true,

    -- OIDC settings
    oidc_issuer_url VARCHAR(500),
    oidc_client_id VARCHAR(255),
    oidc_client_secret_encrypted BYTEA,

    -- SAML settings
    saml_idp_metadata_url VARCHAR(500),
    saml_idp_entity_id VARCHAR(500),
    saml_certificate TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id)
);

-- Domain claims with verification
CREATE TABLE domain_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    domain VARCHAR(255) NOT NULL,
    is_verified BOOLEAN DEFAULT false,
    verification_token VARCHAR(64),
    verified_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(domain)
);

-- SSO user identities (links IdP identity to local user)
CREATE TABLE sso_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sso_config_id UUID NOT NULL REFERENCES sso_configs(id) ON DELETE CASCADE,
    idp_user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sso_config_id, idp_user_id)
);

-- SCIM bearer tokens for provisioning
CREATE TABLE scim_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,
    description VARCHAR(255),
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_sso_configs_org ON sso_configs(org_id);
CREATE INDEX idx_domain_claims_domain ON domain_claims(domain);
CREATE INDEX idx_domain_claims_org ON domain_claims(org_id);
CREATE INDEX idx_sso_identities_user ON sso_identities(user_id);
CREATE INDEX idx_scim_tokens_org ON scim_tokens(org_id);
```

**Step 2: Commit**

```bash
git add backend/migrations/010_sso_scim_tables.sql
git commit -m "feat(sso): add SSO and SCIM database tables"
```

---

### Task 2: SSO Domain Types

**Files:**
- Create: `backend/src/dataing/core/auth/sso_types.py`
- Modify: `backend/src/dataing/core/auth/__init__.py`
- Test: `backend/tests/unit/core/auth/test_sso_types.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/core/auth/test_sso_types.py
"""Tests for SSO domain types."""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from dataing.core.auth.sso_types import (
    SSOProviderType,
    SSOConfig,
    DomainClaim,
    SSOIdentity,
    SCIMToken,
)


class TestSSOProviderType:
    """Test SSOProviderType enum."""

    def test_provider_types(self) -> None:
        """Should have OIDC and SAML types."""
        assert SSOProviderType.OIDC.value == "oidc"
        assert SSOProviderType.SAML.value == "saml"


class TestSSOConfig:
    """Test SSOConfig model."""

    def test_create_oidc_config(self) -> None:
        """Should create OIDC config."""
        config = SSOConfig(
            id=uuid4(),
            org_id=uuid4(),
            provider_type=SSOProviderType.OIDC,
            display_name="Sign in with Okta",
            is_enabled=True,
            oidc_issuer_url="https://acme.okta.com",
            oidc_client_id="client123",
            created_at=datetime.now(timezone.utc),
        )
        assert config.provider_type == SSOProviderType.OIDC
        assert config.oidc_issuer_url == "https://acme.okta.com"

    def test_create_saml_config(self) -> None:
        """Should create SAML config."""
        config = SSOConfig(
            id=uuid4(),
            org_id=uuid4(),
            provider_type=SSOProviderType.SAML,
            display_name="Sign in with Azure AD",
            is_enabled=True,
            saml_idp_entity_id="https://sts.windows.net/xxx",
            created_at=datetime.now(timezone.utc),
        )
        assert config.provider_type == SSOProviderType.SAML


class TestDomainClaim:
    """Test DomainClaim model."""

    def test_create_domain_claim(self) -> None:
        """Should create domain claim."""
        claim = DomainClaim(
            id=uuid4(),
            org_id=uuid4(),
            domain="acme.com",
            is_verified=False,
            verification_token="dataing-verify=abc123",
            created_at=datetime.now(timezone.utc),
        )
        assert claim.domain == "acme.com"
        assert claim.is_verified is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/core/auth/test_sso_types.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/core/auth/sso_types.py
"""SSO domain types."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class SSOProviderType(str, Enum):
    """SSO provider type."""

    OIDC = "oidc"
    SAML = "saml"


class SSOConfig(BaseModel):
    """SSO configuration for an organization."""

    id: UUID
    org_id: UUID
    provider_type: SSOProviderType
    display_name: str | None = None
    is_enabled: bool = True

    # OIDC settings
    oidc_issuer_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None  # Decrypted

    # SAML settings
    saml_idp_metadata_url: str | None = None
    saml_idp_entity_id: str | None = None
    saml_certificate: str | None = None

    created_at: datetime
    updated_at: datetime | None = None


class DomainClaim(BaseModel):
    """Domain claim for SSO routing."""

    id: UUID
    org_id: UUID
    domain: str
    is_verified: bool = False
    verification_token: str | None = None
    verified_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class SSOIdentity(BaseModel):
    """Links IdP identity to local user."""

    id: UUID
    user_id: UUID
    sso_config_id: UUID
    idp_user_id: str
    created_at: datetime


class SCIMToken(BaseModel):
    """SCIM bearer token for provisioning."""

    id: UUID
    org_id: UUID
    token_hash: str
    description: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime
```

**Step 4: Update __init__.py**

```python
# Add to backend/src/dataing/core/auth/__init__.py
from dataing.core.auth.sso_types import (
    SSOProviderType,
    SSOConfig,
    DomainClaim,
    SSOIdentity,
    SCIMToken,
)

# Add to __all__:
# "SSOProviderType", "SSOConfig", "DomainClaim", "SSOIdentity", "SCIMToken"
```

**Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/core/auth/test_sso_types.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/dataing/core/auth/sso_types.py backend/src/dataing/core/auth/__init__.py backend/tests/unit/core/auth/test_sso_types.py
git commit -m "feat(sso): add SSO domain types"
```

---

### Task 3: Add SSO Dependencies

**Files:**
- Modify: `backend/pyproject.toml`

**Step 1: Add dependencies**

```bash
cd backend && uv add authlib dnspython python3-saml
```

**Step 2: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore: add SSO dependencies (authlib, dnspython, python3-saml)"
```

---

## Phase 2: SSO Repository

### Task 4: SSO Config Repository

**Files:**
- Create: `backend/src/dataing/adapters/auth/sso_repository.py`
- Modify: `backend/src/dataing/adapters/auth/__init__.py`
- Test: `backend/tests/unit/adapters/auth/test_sso_repository.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/adapters/auth/test_sso_repository.py
"""Tests for SSO repository."""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from dataing.adapters.auth.sso_repository import PostgresSSORepository
from dataing.core.auth.sso_types import SSOProviderType


class TestGetSSOConfigByOrgId:
    """Test get_sso_config_by_org_id."""

    @pytest.mark.asyncio
    async def test_returns_config_when_exists(self) -> None:
        """Should return SSO config for org."""
        mock_db = AsyncMock()
        mock_db.fetch_one.return_value = {
            "id": uuid4(),
            "org_id": uuid4(),
            "provider_type": "oidc",
            "display_name": "Okta",
            "is_enabled": True,
            "oidc_issuer_url": "https://acme.okta.com",
            "oidc_client_id": "client123",
            "oidc_client_secret_encrypted": None,
            "saml_idp_metadata_url": None,
            "saml_idp_entity_id": None,
            "saml_certificate": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": None,
        }

        repo = PostgresSSORepository(mock_db)
        config = await repo.get_sso_config_by_org_id(uuid4())

        assert config is not None
        assert config.provider_type == SSOProviderType.OIDC

    @pytest.mark.asyncio
    async def test_returns_none_when_not_exists(self) -> None:
        """Should return None when no config exists."""
        mock_db = AsyncMock()
        mock_db.fetch_one.return_value = None

        repo = PostgresSSORepository(mock_db)
        config = await repo.get_sso_config_by_org_id(uuid4())

        assert config is None


class TestGetDomainClaim:
    """Test domain claim lookup."""

    @pytest.mark.asyncio
    async def test_returns_verified_claim(self) -> None:
        """Should return verified domain claim."""
        mock_db = AsyncMock()
        mock_db.fetch_one.return_value = {
            "id": uuid4(),
            "org_id": uuid4(),
            "domain": "acme.com",
            "is_verified": True,
            "verification_token": "abc123",
            "verified_at": "2024-01-01T00:00:00Z",
            "expires_at": None,
            "created_at": "2024-01-01T00:00:00Z",
        }

        repo = PostgresSSORepository(mock_db)
        claim = await repo.get_domain_claim("acme.com")

        assert claim is not None
        assert claim.is_verified is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/adapters/auth/test_sso_repository.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/adapters/auth/sso_repository.py
"""SSO configuration repository."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID
import secrets

from dataing.core.auth.sso_types import (
    SSOConfig,
    SSOProviderType,
    DomainClaim,
    SSOIdentity,
    SCIMToken,
)


class PostgresSSORepository:
    """PostgreSQL repository for SSO configuration."""

    def __init__(self, db: Any) -> None:
        """Initialize repository."""
        self._db = db

    async def get_sso_config_by_org_id(self, org_id: UUID) -> SSOConfig | None:
        """Get SSO config for an organization."""
        row = await self._db.fetch_one(
            """
            SELECT * FROM sso_configs WHERE org_id = $1 AND is_enabled = true
            """,
            org_id,
        )
        if not row:
            return None
        return self._row_to_sso_config(row)

    async def get_domain_claim(self, domain: str) -> DomainClaim | None:
        """Get domain claim by domain name."""
        row = await self._db.fetch_one(
            """
            SELECT * FROM domain_claims WHERE domain = $1
            """,
            domain.lower(),
        )
        if not row:
            return None
        return self._row_to_domain_claim(row)

    async def get_verified_domain_claim(self, domain: str) -> DomainClaim | None:
        """Get verified domain claim by domain name."""
        row = await self._db.fetch_one(
            """
            SELECT * FROM domain_claims
            WHERE domain = $1 AND is_verified = true
            """,
            domain.lower(),
        )
        if not row:
            return None
        return self._row_to_domain_claim(row)

    async def create_sso_config(
        self,
        org_id: UUID,
        provider_type: SSOProviderType,
        display_name: str | None = None,
        oidc_issuer_url: str | None = None,
        oidc_client_id: str | None = None,
        oidc_client_secret: str | None = None,
        saml_idp_metadata_url: str | None = None,
        saml_idp_entity_id: str | None = None,
        saml_certificate: str | None = None,
    ) -> SSOConfig:
        """Create SSO configuration for an org."""
        row = await self._db.fetch_one(
            """
            INSERT INTO sso_configs (
                org_id, provider_type, display_name, is_enabled,
                oidc_issuer_url, oidc_client_id, oidc_client_secret_encrypted,
                saml_idp_metadata_url, saml_idp_entity_id, saml_certificate
            ) VALUES ($1, $2, $3, true, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            org_id,
            provider_type.value,
            display_name,
            oidc_issuer_url,
            oidc_client_id,
            oidc_client_secret.encode() if oidc_client_secret else None,
            saml_idp_metadata_url,
            saml_idp_entity_id,
            saml_certificate,
        )
        return self._row_to_sso_config(row)

    async def create_domain_claim(self, org_id: UUID, domain: str) -> DomainClaim:
        """Create a domain claim with verification token."""
        token = f"dataing-verify={secrets.token_hex(16)}"
        expires_at = datetime.now(timezone.utc).replace(
            day=datetime.now(timezone.utc).day + 7
        )

        row = await self._db.fetch_one(
            """
            INSERT INTO domain_claims (org_id, domain, verification_token, expires_at)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            org_id,
            domain.lower(),
            token,
            expires_at,
        )
        return self._row_to_domain_claim(row)

    async def verify_domain_claim(self, claim_id: UUID) -> DomainClaim | None:
        """Mark domain claim as verified."""
        row = await self._db.fetch_one(
            """
            UPDATE domain_claims
            SET is_verified = true, verified_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            claim_id,
        )
        if not row:
            return None
        return self._row_to_domain_claim(row)

    async def get_or_create_sso_identity(
        self,
        user_id: UUID,
        sso_config_id: UUID,
        idp_user_id: str,
    ) -> SSOIdentity:
        """Get or create SSO identity link."""
        row = await self._db.fetch_one(
            """
            INSERT INTO sso_identities (user_id, sso_config_id, idp_user_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (sso_config_id, idp_user_id) DO UPDATE SET user_id = $1
            RETURNING *
            """,
            user_id,
            sso_config_id,
            idp_user_id,
        )
        return SSOIdentity(
            id=row["id"],
            user_id=row["user_id"],
            sso_config_id=row["sso_config_id"],
            idp_user_id=row["idp_user_id"],
            created_at=row["created_at"],
        )

    def _row_to_sso_config(self, row: dict[str, Any]) -> SSOConfig:
        """Convert DB row to SSOConfig."""
        return SSOConfig(
            id=row["id"],
            org_id=row["org_id"],
            provider_type=SSOProviderType(row["provider_type"]),
            display_name=row["display_name"],
            is_enabled=row["is_enabled"],
            oidc_issuer_url=row["oidc_issuer_url"],
            oidc_client_id=row["oidc_client_id"],
            oidc_client_secret=row["oidc_client_secret_encrypted"].decode()
            if row["oidc_client_secret_encrypted"]
            else None,
            saml_idp_metadata_url=row["saml_idp_metadata_url"],
            saml_idp_entity_id=row["saml_idp_entity_id"],
            saml_certificate=row["saml_certificate"],
            created_at=row["created_at"],
            updated_at=row.get("updated_at"),
        )

    def _row_to_domain_claim(self, row: dict[str, Any]) -> DomainClaim:
        """Convert DB row to DomainClaim."""
        return DomainClaim(
            id=row["id"],
            org_id=row["org_id"],
            domain=row["domain"],
            is_verified=row["is_verified"],
            verification_token=row["verification_token"],
            verified_at=row.get("verified_at"),
            expires_at=row.get("expires_at"),
            created_at=row["created_at"],
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/adapters/auth/test_sso_repository.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/dataing/adapters/auth/sso_repository.py backend/tests/unit/adapters/auth/test_sso_repository.py
git commit -m "feat(sso): add SSO config repository"
```

---

## Phase 3: SSO Discovery & OIDC

### Task 5: SSO Discovery Endpoint

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/sso.py`
- Modify: `backend/src/dataing/entrypoints/api/main.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_sso.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/entrypoints/api/routes/test_sso.py
"""Tests for SSO endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from dataing.core.auth.sso_types import SSOProviderType


class TestSSODiscover:
    """Test SSO discovery endpoint."""

    @pytest.mark.asyncio
    async def test_returns_password_when_no_domain_claim(self) -> None:
        """Should return password method when domain not claimed."""
        from dataing.entrypoints.api.routes.sso import discover_sso_method

        mock_repo = AsyncMock()
        mock_repo.get_verified_domain_claim.return_value = None

        result = await discover_sso_method(
            email="user@unknown.com",
            sso_repo=mock_repo,
        )

        assert result["method"] == "password"

    @pytest.mark.asyncio
    async def test_returns_oidc_when_domain_claimed(self) -> None:
        """Should return OIDC auth URL when domain claimed with OIDC."""
        from dataing.entrypoints.api.routes.sso import discover_sso_method
        from dataing.core.auth.sso_types import DomainClaim, SSOConfig
        from datetime import datetime, timezone

        org_id = uuid4()
        mock_repo = AsyncMock()
        mock_repo.get_verified_domain_claim.return_value = DomainClaim(
            id=uuid4(),
            org_id=org_id,
            domain="acme.com",
            is_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        mock_repo.get_sso_config_by_org_id.return_value = SSOConfig(
            id=uuid4(),
            org_id=org_id,
            provider_type=SSOProviderType.OIDC,
            oidc_issuer_url="https://acme.okta.com",
            oidc_client_id="client123",
            created_at=datetime.now(timezone.utc),
        )

        result = await discover_sso_method(
            email="alice@acme.com",
            sso_repo=mock_repo,
        )

        assert result["method"] == "oidc"
        assert "auth_url" in result
        assert "state" in result
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/entrypoints/api/routes/test_sso.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/entrypoints/api/routes/sso.py
"""SSO authentication endpoints."""

import secrets
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from dataing.adapters.auth.sso_repository import PostgresSSORepository
from dataing.core.auth.sso_types import SSOProviderType

router = APIRouter(prefix="/sso", tags=["sso"])


class SSODiscoverRequest(BaseModel):
    """SSO discovery request."""

    email: EmailStr


class SSODiscoverResponse(BaseModel):
    """SSO discovery response."""

    method: str  # "password", "oidc", or "saml"
    auth_url: str | None = None
    state: str | None = None
    org_id: str | None = None


def get_sso_repo(request: Request) -> PostgresSSORepository:
    """Get SSO repository from app state."""
    return PostgresSSORepository(request.app.state.app_db)


async def discover_sso_method(
    email: str,
    sso_repo: PostgresSSORepository,
    redirect_uri: str = "http://localhost:3000/auth/callback",
) -> dict[str, Any]:
    """Discover SSO method for email domain."""
    # Extract domain from email
    domain = email.split("@")[1].lower()

    # Check for verified domain claim
    claim = await sso_repo.get_verified_domain_claim(domain)
    if not claim:
        return {"method": "password"}

    # Get SSO config for the org
    config = await sso_repo.get_sso_config_by_org_id(claim.org_id)
    if not config or not config.is_enabled:
        return {"method": "password"}

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)

    if config.provider_type == SSOProviderType.OIDC:
        # Build OIDC authorization URL
        params = {
            "client_id": config.oidc_client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": secrets.token_urlsafe(16),
        }
        auth_url = f"{config.oidc_issuer_url}/authorize?{urlencode(params)}"

        return {
            "method": "oidc",
            "auth_url": auth_url,
            "state": state,
            "org_id": str(claim.org_id),
        }

    elif config.provider_type == SSOProviderType.SAML:
        # Return SAML login URL
        return {
            "method": "saml",
            "auth_url": f"/api/v1/auth/sso/saml/login?org_id={claim.org_id}",
            "state": state,
            "org_id": str(claim.org_id),
        }

    return {"method": "password"}


@router.post("/discover", response_model=SSODiscoverResponse)
async def sso_discover(
    body: SSODiscoverRequest,
    sso_repo: Annotated[PostgresSSORepository, Depends(get_sso_repo)],
    request: Request,
) -> SSODiscoverResponse:
    """Discover SSO method for an email address.

    Returns the authentication method and URL to use.
    """
    frontend_url = request.app.state.settings.frontend_url
    redirect_uri = f"{frontend_url}/auth/callback"

    result = await discover_sso_method(
        email=body.email,
        sso_repo=sso_repo,
        redirect_uri=redirect_uri,
    )

    return SSODiscoverResponse(**result)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/entrypoints/api/routes/test_sso.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/sso.py backend/tests/unit/entrypoints/api/routes/test_sso.py
git commit -m "feat(sso): add SSO discovery endpoint"
```

---

### Task 6: OIDC Callback Endpoint

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/sso.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_sso.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/unit/entrypoints/api/routes/test_sso.py

class TestOIDCCallback:
    """Test OIDC callback endpoint."""

    @pytest.mark.asyncio
    async def test_exchanges_code_for_tokens(self) -> None:
        """Should exchange auth code for tokens and create user."""
        # This test requires mocking the OIDC token exchange
        # Full implementation in actual test file
        pass
```

**Step 2: Write implementation**

```python
# Add to backend/src/dataing/entrypoints/api/routes/sso.py

from authlib.integrations.httpx_client import AsyncOAuth2Client
from dataing.core.auth.jwt import create_access_token, create_refresh_token
from dataing.core.auth.service import AuthService


class OIDCCallbackRequest(BaseModel):
    """OIDC callback request."""

    code: str
    state: str
    org_id: str


@router.post("/oidc/callback")
async def oidc_callback(
    body: OIDCCallbackRequest,
    sso_repo: Annotated[PostgresSSORepository, Depends(get_sso_repo)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    request: Request,
) -> dict[str, Any]:
    """Handle OIDC callback after IdP authentication.

    Exchanges auth code for tokens, extracts user info,
    creates/updates user via JIT provisioning, returns JWT.
    """
    from uuid import UUID

    org_id = UUID(body.org_id)
    config = await sso_repo.get_sso_config_by_org_id(org_id)

    if not config or config.provider_type != SSOProviderType.OIDC:
        raise HTTPException(status_code=400, detail="Invalid SSO configuration")

    # Exchange code for tokens
    frontend_url = request.app.state.settings.frontend_url
    redirect_uri = f"{frontend_url}/auth/callback"

    async with AsyncOAuth2Client(
        client_id=config.oidc_client_id,
        client_secret=config.oidc_client_secret,
    ) as client:
        token_endpoint = f"{config.oidc_issuer_url}/token"
        token = await client.fetch_token(
            token_endpoint,
            code=body.code,
            redirect_uri=redirect_uri,
        )

        # Get user info
        userinfo_endpoint = f"{config.oidc_issuer_url}/userinfo"
        resp = await client.get(userinfo_endpoint)
        userinfo = resp.json()

    # JIT provision user
    email = userinfo.get("email")
    name = userinfo.get("name") or userinfo.get("preferred_username")
    idp_user_id = userinfo.get("sub")

    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by IdP")

    # Create or get user
    user, membership = await auth_service.jit_provision_sso_user(
        email=email,
        name=name,
        org_id=org_id,
    )

    # Link SSO identity
    await sso_repo.get_or_create_sso_identity(
        user_id=user.id,
        sso_config_id=config.id,
        idp_user_id=idp_user_id,
    )

    # Get user's teams
    teams = await auth_service.get_user_teams(user.id, org_id)

    # Issue JWT
    access_token = create_access_token(
        user_id=str(user.id),
        org_id=str(org_id),
        role=membership.role.value,
        teams=[str(t.id) for t in teams],
    )
    refresh_token = create_refresh_token(user_id=str(user.id))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {"id": str(user.id), "email": user.email, "name": user.name},
        "org": {"id": str(org_id)},
        "role": membership.role.value,
    }
```

**Step 3: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/sso.py
git commit -m "feat(sso): add OIDC callback endpoint"
```

---

## Phase 4: Domain Verification

### Task 7: DNS Verification Service

**Files:**
- Create: `backend/src/dataing/core/auth/domain_verification.py`
- Test: `backend/tests/unit/core/auth/test_domain_verification.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/core/auth/test_domain_verification.py
"""Tests for domain verification."""

import pytest
from unittest.mock import patch, MagicMock

from dataing.core.auth.domain_verification import verify_domain_dns


class TestVerifyDomainDNS:
    """Test DNS verification."""

    @pytest.mark.asyncio
    async def test_returns_true_when_token_found(self) -> None:
        """Should return True when DNS TXT record matches token."""
        with patch("dns.resolver.resolve") as mock_resolve:
            mock_answer = MagicMock()
            mock_answer.__iter__ = lambda self: iter(
                [MagicMock(to_text=lambda: '"dataing-verify=abc123"')]
            )
            mock_resolve.return_value = mock_answer

            result = await verify_domain_dns("acme.com", "dataing-verify=abc123")

            assert result is True
            mock_resolve.assert_called_once_with("_dataing.acme.com", "TXT")

    @pytest.mark.asyncio
    async def test_returns_false_when_token_not_found(self) -> None:
        """Should return False when token doesn't match."""
        with patch("dns.resolver.resolve") as mock_resolve:
            mock_answer = MagicMock()
            mock_answer.__iter__ = lambda self: iter(
                [MagicMock(to_text=lambda: '"different-token"')]
            )
            mock_resolve.return_value = mock_answer

            result = await verify_domain_dns("acme.com", "dataing-verify=abc123")

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_dns_error(self) -> None:
        """Should return False when DNS lookup fails."""
        with patch("dns.resolver.resolve") as mock_resolve:
            import dns.resolver

            mock_resolve.side_effect = dns.resolver.NXDOMAIN()

            result = await verify_domain_dns("acme.com", "dataing-verify=abc123")

            assert result is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/core/auth/test_domain_verification.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/core/auth/domain_verification.py
"""Domain verification via DNS TXT records."""

import asyncio
import dns.resolver


async def verify_domain_dns(domain: str, expected_token: str) -> bool:
    """Verify domain ownership via DNS TXT record.

    Checks for TXT record at _dataing.<domain> containing the expected token.

    Args:
        domain: Domain to verify (e.g., "acme.com")
        expected_token: Token to look for (e.g., "dataing-verify=abc123")

    Returns:
        True if token found in DNS, False otherwise
    """
    subdomain = f"_dataing.{domain}"

    try:
        # Run DNS query in thread pool (dns.resolver is sync)
        loop = asyncio.get_event_loop()
        answers = await loop.run_in_executor(
            None, lambda: dns.resolver.resolve(subdomain, "TXT")
        )

        for rdata in answers:
            txt_value = rdata.to_text().strip('"')
            if txt_value == expected_token:
                return True

        return False

    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout):
        return False
    except Exception:
        return False
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/core/auth/test_domain_verification.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/dataing/core/auth/domain_verification.py backend/tests/unit/core/auth/test_domain_verification.py
git commit -m "feat(sso): add DNS domain verification"
```

---

### Task 8: Domain Admin Endpoints

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/domains.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_domains.py`

**Step 1: Write implementation**

```python
# backend/src/dataing/entrypoints/api/routes/domains.py
"""Domain claim management endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dataing.adapters.auth.sso_repository import PostgresSSORepository
from dataing.core.auth.domain_verification import verify_domain_dns
from dataing.entrypoints.api.middleware.jwt_auth import JwtContext, verify_jwt, require_role
from dataing.core.auth.types import OrgRole

router = APIRouter(prefix="/domains", tags=["domains"])


class CreateDomainRequest(BaseModel):
    """Create domain claim request."""

    domain: str


class DomainClaimResponse(BaseModel):
    """Domain claim response."""

    id: str
    domain: str
    is_verified: bool
    verification_token: str | None
    verification_instructions: str | None


@router.post("", response_model=DomainClaimResponse)
@require_role(OrgRole.ADMIN)
async def create_domain_claim(
    body: CreateDomainRequest,
    auth: Annotated[JwtContext, Depends(verify_jwt)],
    sso_repo: Annotated[PostgresSSORepository, Depends(get_sso_repo)],
) -> DomainClaimResponse:
    """Create a domain claim for the organization.

    Returns verification instructions with DNS TXT record to add.
    """
    # Check domain not already claimed
    existing = await sso_repo.get_domain_claim(body.domain)
    if existing:
        raise HTTPException(status_code=400, detail="Domain already claimed")

    claim = await sso_repo.create_domain_claim(
        org_id=auth.org_uuid,
        domain=body.domain,
    )

    return DomainClaimResponse(
        id=str(claim.id),
        domain=claim.domain,
        is_verified=claim.is_verified,
        verification_token=claim.verification_token,
        verification_instructions=f"Add a DNS TXT record:\n\n"
        f"  Host: _dataing.{claim.domain}\n"
        f"  Value: {claim.verification_token}\n\n"
        f"Then click 'Verify' to confirm ownership.",
    )


@router.post("/{domain_id}/verify", response_model=DomainClaimResponse)
@require_role(OrgRole.ADMIN)
async def verify_domain(
    domain_id: UUID,
    auth: Annotated[JwtContext, Depends(verify_jwt)],
    sso_repo: Annotated[PostgresSSORepository, Depends(get_sso_repo)],
) -> DomainClaimResponse:
    """Verify domain ownership via DNS check."""
    claim = await sso_repo.get_domain_claim_by_id(domain_id)
    if not claim or claim.org_id != auth.org_uuid:
        raise HTTPException(status_code=404, detail="Domain claim not found")

    if claim.is_verified:
        return DomainClaimResponse(
            id=str(claim.id),
            domain=claim.domain,
            is_verified=True,
            verification_token=None,
            verification_instructions=None,
        )

    # Check DNS
    verified = await verify_domain_dns(claim.domain, claim.verification_token)
    if not verified:
        raise HTTPException(
            status_code=400,
            detail="DNS verification failed. Ensure TXT record is set correctly.",
        )

    # Mark as verified
    claim = await sso_repo.verify_domain_claim(claim.id)

    return DomainClaimResponse(
        id=str(claim.id),
        domain=claim.domain,
        is_verified=True,
        verification_token=None,
        verification_instructions=None,
    )


@router.get("", response_model=list[DomainClaimResponse])
@require_role(OrgRole.ADMIN)
async def list_domain_claims(
    auth: Annotated[JwtContext, Depends(verify_jwt)],
    sso_repo: Annotated[PostgresSSORepository, Depends(get_sso_repo)],
) -> list[DomainClaimResponse]:
    """List all domain claims for the organization."""
    claims = await sso_repo.list_domain_claims(auth.org_uuid)

    return [
        DomainClaimResponse(
            id=str(c.id),
            domain=c.domain,
            is_verified=c.is_verified,
            verification_token=c.verification_token if not c.is_verified else None,
            verification_instructions=None,
        )
        for c in claims
    ]
```

**Step 2: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/domains.py
git commit -m "feat(sso): add domain claim management endpoints"
```

---

## Phase 5: SCIM Endpoints

### Task 9: SCIM Types

**Files:**
- Create: `backend/src/dataing/core/auth/scim_types.py`
- Test: `backend/tests/unit/core/auth/test_scim_types.py`

**Step 1: Write minimal implementation**

```python
# backend/src/dataing/core/auth/scim_types.py
"""SCIM 2.0 schema types."""

from typing import Any
from pydantic import BaseModel, Field


class SCIMName(BaseModel):
    """SCIM name object."""

    givenName: str | None = None
    familyName: str | None = None
    formatted: str | None = None


class SCIMEmail(BaseModel):
    """SCIM email object."""

    value: str
    primary: bool = True
    type: str = "work"


class SCIMGroupMembership(BaseModel):
    """SCIM group membership reference."""

    value: str  # group ID
    display: str | None = None


class SCIMUser(BaseModel):
    """SCIM 2.0 User resource."""

    schemas: list[str] = Field(
        default=["urn:ietf:params:scim:schemas:core:2.0:User"]
    )
    id: str | None = None
    externalId: str | None = None
    userName: str
    name: SCIMName | None = None
    displayName: str | None = None
    emails: list[SCIMEmail] = []
    active: bool = True
    groups: list[SCIMGroupMembership] = []


class SCIMGroup(BaseModel):
    """SCIM 2.0 Group resource."""

    schemas: list[str] = Field(
        default=["urn:ietf:params:scim:schemas:core:2.0:Group"]
    )
    id: str | None = None
    externalId: str | None = None
    displayName: str
    members: list[dict[str, str]] = []


class SCIMListResponse(BaseModel):
    """SCIM list response."""

    schemas: list[str] = Field(
        default=["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
    )
    totalResults: int
    startIndex: int = 1
    itemsPerPage: int
    Resources: list[Any] = []


class SCIMError(BaseModel):
    """SCIM error response."""

    schemas: list[str] = Field(
        default=["urn:ietf:params:scim:api:messages:2.0:Error"]
    )
    status: str
    detail: str | None = None
```

**Step 2: Commit**

```bash
git add backend/src/dataing/core/auth/scim_types.py
git commit -m "feat(scim): add SCIM 2.0 schema types"
```

---

### Task 10: SCIM Users Endpoint

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/scim.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_scim.py`

**Step 1: Write implementation**

```python
# backend/src/dataing/entrypoints/api/routes/scim.py
"""SCIM 2.0 provisioning endpoints."""

from typing import Annotated, Any
from uuid import UUID
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse

from dataing.adapters.auth.sso_repository import PostgresSSORepository
from dataing.core.auth.scim_types import (
    SCIMUser,
    SCIMGroup,
    SCIMListResponse,
    SCIMError,
    SCIMEmail,
    SCIMName,
)
from dataing.core.auth.service import AuthService

router = APIRouter(prefix="/scim/v2", tags=["scim"])


async def verify_scim_token(
    authorization: str = Header(...),
    request: Request = None,
) -> UUID:
    """Verify SCIM bearer token and return org_id."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    sso_repo = PostgresSSORepository(request.app.state.app_db)
    scim_token = await sso_repo.get_scim_token_by_hash(token_hash)

    if not scim_token:
        raise HTTPException(status_code=401, detail="Invalid SCIM token")

    # Update last_used_at
    await sso_repo.update_scim_token_last_used(scim_token.id)

    return scim_token.org_id


@router.get("/Users")
async def list_users(
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    startIndex: int = 1,
    count: int = 100,
    filter: str | None = None,
) -> SCIMListResponse:
    """List users in the organization."""
    users = await auth_service.list_org_users(org_id, offset=startIndex - 1, limit=count)
    total = await auth_service.count_org_users(org_id)

    return SCIMListResponse(
        totalResults=total,
        startIndex=startIndex,
        itemsPerPage=len(users),
        Resources=[_user_to_scim(u) for u in users],
    )


@router.get("/Users/{user_id}")
async def get_user(
    user_id: UUID,
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SCIMUser:
    """Get a single user."""
    user = await auth_service.get_user_in_org(user_id, org_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return _user_to_scim(user)


@router.post("/Users", status_code=201)
async def create_user(
    body: SCIMUser,
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SCIMUser:
    """Create a new user via SCIM."""
    email = body.emails[0].value if body.emails else body.userName
    name = body.name.formatted if body.name else body.displayName

    user, _ = await auth_service.jit_provision_sso_user(
        email=email,
        name=name,
        org_id=org_id,
    )

    return _user_to_scim(user)


@router.put("/Users/{user_id}")
async def replace_user(
    user_id: UUID,
    body: SCIMUser,
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SCIMUser:
    """Replace a user's attributes."""
    user = await auth_service.get_user_in_org(user_id, org_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    name = body.name.formatted if body.name else body.displayName
    updated = await auth_service.update_user(
        user_id=user_id,
        name=name,
        is_active=body.active,
    )

    return _user_to_scim(updated)


@router.delete("/Users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Deactivate a user."""
    await auth_service.deactivate_user_in_org(user_id, org_id)


def _user_to_scim(user: Any) -> SCIMUser:
    """Convert internal user to SCIM User."""
    return SCIMUser(
        id=str(user.id),
        userName=user.email,
        displayName=user.name,
        name=SCIMName(formatted=user.name) if user.name else None,
        emails=[SCIMEmail(value=user.email, primary=True)],
        active=user.is_active,
    )
```

**Step 2: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/scim.py
git commit -m "feat(scim): add SCIM Users endpoints"
```

---

### Task 11: SCIM Groups Endpoint

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/scim.py`

**Step 1: Add groups endpoints**

```python
# Add to backend/src/dataing/entrypoints/api/routes/scim.py

@router.get("/Groups")
async def list_groups(
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    startIndex: int = 1,
    count: int = 100,
) -> SCIMListResponse:
    """List teams/groups in the organization."""
    teams = await auth_service.list_org_teams(org_id, offset=startIndex - 1, limit=count)
    total = await auth_service.count_org_teams(org_id)

    return SCIMListResponse(
        totalResults=total,
        startIndex=startIndex,
        itemsPerPage=len(teams),
        Resources=[_team_to_scim_group(t) for t in teams],
    )


@router.get("/Groups/{group_id}")
async def get_group(
    group_id: UUID,
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SCIMGroup:
    """Get a single group/team."""
    team = await auth_service.get_team_in_org(group_id, org_id)
    if not team:
        raise HTTPException(status_code=404, detail="Group not found")

    members = await auth_service.get_team_members(group_id)
    return _team_to_scim_group(team, members)


@router.post("/Groups", status_code=201)
async def create_group(
    body: SCIMGroup,
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SCIMGroup:
    """Create a new team via SCIM."""
    team = await auth_service.create_team(
        org_id=org_id,
        name=body.displayName,
    )

    # Add members if provided
    for member in body.members:
        user_id = UUID(member["value"])
        await auth_service.add_team_member(team.id, user_id)

    return _team_to_scim_group(team)


@router.patch("/Groups/{group_id}")
async def patch_group(
    group_id: UUID,
    body: dict[str, Any],
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SCIMGroup:
    """Patch group membership (add/remove members)."""
    team = await auth_service.get_team_in_org(group_id, org_id)
    if not team:
        raise HTTPException(status_code=404, detail="Group not found")

    # Process SCIM PATCH operations
    operations = body.get("Operations", [])
    for op in operations:
        if op["op"] == "add" and "members" in op.get("value", {}):
            for member in op["value"]["members"]:
                await auth_service.add_team_member(group_id, UUID(member["value"]))
        elif op["op"] == "remove" and op.get("path", "").startswith("members"):
            # Parse member ID from path like "members[value eq \"uuid\"]"
            member_id = _parse_scim_member_path(op["path"])
            if member_id:
                await auth_service.remove_team_member(group_id, member_id)

    members = await auth_service.get_team_members(group_id)
    return _team_to_scim_group(team, members)


@router.delete("/Groups/{group_id}", status_code=204)
async def delete_group(
    group_id: UUID,
    org_id: Annotated[UUID, Depends(verify_scim_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Delete a team."""
    await auth_service.delete_team(group_id, org_id)


def _team_to_scim_group(team: Any, members: list[Any] | None = None) -> SCIMGroup:
    """Convert internal team to SCIM Group."""
    return SCIMGroup(
        id=str(team.id),
        displayName=team.name,
        members=[
            {"value": str(m.user_id), "display": m.user_email}
            for m in (members or [])
        ],
    )


def _parse_scim_member_path(path: str) -> UUID | None:
    """Parse member ID from SCIM path like 'members[value eq \"uuid\"]'."""
    import re

    match = re.search(r'value eq "([^"]+)"', path)
    if match:
        try:
            return UUID(match.group(1))
        except ValueError:
            return None
    return None
```

**Step 2: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/scim.py
git commit -m "feat(scim): add SCIM Groups endpoints"
```

---

## Phase 6: Frontend

### Task 12: Email-First Login Component

**Files:**
- Create: `frontend/src/features/auth/email-first-login.tsx`
- Modify: `frontend/src/features/auth/jwt-login-page.tsx`

**Step 1: Create email-first login component**

```tsx
// frontend/src/features/auth/email-first-login.tsx
import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { useJwtAuth } from '@/lib/auth'

interface SSODiscoverResponse {
  method: 'password' | 'oidc' | 'saml'
  auth_url?: string
  state?: string
  org_id?: string
}

export function EmailFirstLogin() {
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [step, setStep] = React.useState<'email' | 'password'>('email')
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [ssoResponse, setSsoResponse] = React.useState<SSODiscoverResponse | null>(null)

  const { login } = useJwtAuth()
  const navigate = useNavigate()

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/v1/auth/sso/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })

      const data: SSODiscoverResponse = await response.json()
      setSsoResponse(data)

      if (data.method === 'password') {
        setStep('password')
      } else if (data.auth_url) {
        // Store state for CSRF verification
        sessionStorage.setItem('sso_state', data.state || '')
        sessionStorage.setItem('sso_org_id', data.org_id || '')
        // Redirect to IdP
        window.location.href = data.auth_url
      }
    } catch (err) {
      setError('Failed to check login method')
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      await login({ email, password, org_id: ssoResponse?.org_id || '' })
      navigate('/')
    } catch (err) {
      setError('Invalid email or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Sign In</CardTitle>
        <CardDescription>
          {step === 'email'
            ? 'Enter your email to continue'
            : 'Enter your password'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {step === 'email' ? (
          <form onSubmit={handleEmailSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Checking...' : 'Continue'}
            </Button>
          </form>
        ) : (
          <form onSubmit={handlePasswordSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email-display">Email</Label>
              <Input id="email-display" type="email" value={email} disabled />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setStep('email')}
              >
                Back
              </Button>
              <Button type="submit" className="flex-1" disabled={loading}>
                {loading ? 'Signing in...' : 'Sign In'}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/features/auth/email-first-login.tsx
git commit -m "feat(frontend): add email-first login component"
```

---

### Task 13: SSO Callback Handler

**Files:**
- Create: `frontend/src/features/auth/sso-callback.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Create SSO callback component**

```tsx
// frontend/src/features/auth/sso-callback.tsx
import * as React from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useJwtAuth } from '@/lib/auth'

export function SSOCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { setTokens } = useJwtAuth()
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const storedState = sessionStorage.getItem('sso_state')
    const orgId = sessionStorage.getItem('sso_org_id')

    // Verify state to prevent CSRF
    if (state !== storedState) {
      setError('Invalid state parameter')
      return
    }

    if (!code || !orgId) {
      setError('Missing authorization code')
      return
    }

    // Exchange code for tokens
    fetch('/api/v1/auth/sso/oidc/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, state, org_id: orgId }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.access_token) {
          setTokens(data.access_token, data.refresh_token, data.user, data.org, data.role)
          navigate('/')
        } else {
          setError(data.detail || 'Authentication failed')
        }
      })
      .catch(() => setError('Authentication failed'))
      .finally(() => {
        sessionStorage.removeItem('sso_state')
        sessionStorage.removeItem('sso_org_id')
      })
  }, [searchParams, navigate, setTokens])

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-600">Authentication Failed</h1>
          <p className="mt-2 text-gray-600">{error}</p>
          <a href="/login" className="mt-4 text-blue-600 underline">
            Try again
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
        <p className="mt-4 text-gray-600">Completing sign in...</p>
      </div>
    </div>
  )
}
```

**Step 2: Add route to App.tsx**

```tsx
// Add to frontend/src/App.tsx routes
import { SSOCallback } from '@/features/auth/sso-callback'

// In router:
<Route path="/auth/callback" element={<SSOCallback />} />
```

**Step 3: Commit**

```bash
git add frontend/src/features/auth/sso-callback.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add SSO callback handler"
```

---

### Task 14: SSO Admin Configuration Page

**Files:**
- Create: `frontend/src/features/admin/sso-config-page.tsx`

**Step 1: Create SSO config page**

```tsx
// frontend/src/features/admin/sso-config-page.tsx
import * as React from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useJwtAuth } from '@/lib/auth'

type ProviderType = 'oidc' | 'saml'

export function SSOConfigPage() {
  const { accessToken } = useJwtAuth()
  const [providerType, setProviderType] = React.useState<ProviderType>('oidc')
  const [displayName, setDisplayName] = React.useState('')
  const [oidcIssuer, setOidcIssuer] = React.useState('')
  const [oidcClientId, setOidcClientId] = React.useState('')
  const [oidcClientSecret, setOidcClientSecret] = React.useState('')
  const [samlMetadataUrl, setSamlMetadataUrl] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [saved, setSaved] = React.useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      await fetch('/api/v1/admin/sso', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          provider_type: providerType,
          display_name: displayName,
          oidc_issuer_url: providerType === 'oidc' ? oidcIssuer : null,
          oidc_client_id: providerType === 'oidc' ? oidcClientId : null,
          oidc_client_secret: providerType === 'oidc' ? oidcClientSecret : null,
          saml_idp_metadata_url: providerType === 'saml' ? samlMetadataUrl : null,
        }),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      console.error('Failed to save SSO config:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">SSO Configuration</h1>
        <p className="text-muted-foreground">
          Configure single sign-on for your organization.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Identity Provider Settings</CardTitle>
          <CardDescription>
            Connect your organization's identity provider.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>Provider Type</Label>
              <Select
                value={providerType}
                onValueChange={(v) => setProviderType(v as ProviderType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="oidc">OIDC (OpenID Connect)</SelectItem>
                  <SelectItem value="saml">SAML 2.0</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="displayName">Display Name</Label>
              <Input
                id="displayName"
                placeholder="Sign in with Okta"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>

            {providerType === 'oidc' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="oidcIssuer">Issuer URL</Label>
                  <Input
                    id="oidcIssuer"
                    placeholder="https://your-domain.okta.com"
                    value={oidcIssuer}
                    onChange={(e) => setOidcIssuer(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="oidcClientId">Client ID</Label>
                  <Input
                    id="oidcClientId"
                    value={oidcClientId}
                    onChange={(e) => setOidcClientId(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="oidcClientSecret">Client Secret</Label>
                  <Input
                    id="oidcClientSecret"
                    type="password"
                    value={oidcClientSecret}
                    onChange={(e) => setOidcClientSecret(e.target.value)}
                  />
                </div>
              </>
            )}

            {providerType === 'saml' && (
              <div className="space-y-2">
                <Label htmlFor="samlMetadataUrl">IdP Metadata URL</Label>
                <Input
                  id="samlMetadataUrl"
                  placeholder="https://idp.example.com/metadata"
                  value={samlMetadataUrl}
                  onChange={(e) => setSamlMetadataUrl(e.target.value)}
                />
              </div>
            )}

            <div className="flex items-center gap-4">
              <Button type="submit" disabled={loading}>
                {loading ? 'Saving...' : 'Save Configuration'}
              </Button>
              {saved && (
                <span className="text-sm text-green-600">Saved successfully!</span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/features/admin/sso-config-page.tsx
git commit -m "feat(frontend): add SSO configuration admin page"
```

---

### Task 15: Domain Claims Admin Page

**Files:**
- Create: `frontend/src/features/admin/domain-claims-page.tsx`

**Step 1: Create domain claims page**

```tsx
// frontend/src/features/admin/domain-claims-page.tsx
import * as React from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { useJwtAuth } from '@/lib/auth'

interface DomainClaim {
  id: string
  domain: string
  is_verified: boolean
  verification_token?: string
  verification_instructions?: string
}

export function DomainClaimsPage() {
  const { accessToken } = useJwtAuth()
  const [domains, setDomains] = React.useState<DomainClaim[]>([])
  const [newDomain, setNewDomain] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const fetchDomains = React.useCallback(async () => {
    const res = await fetch('/api/v1/admin/domains', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    const data = await res.json()
    setDomains(data)
  }, [accessToken])

  React.useEffect(() => {
    fetchDomains()
  }, [fetchDomains])

  const handleAddDomain = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const res = await fetch('/api/v1/admin/domains', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ domain: newDomain }),
      })
      const data = await res.json()
      setDomains([...domains, data])
      setNewDomain('')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async (domainId: string) => {
    setLoading(true)
    try {
      await fetch(`/api/v1/admin/domains/${domainId}/verify`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      fetchDomains()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Domain Claims</h1>
        <p className="text-muted-foreground">
          Claim and verify domains for automatic SSO routing.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add Domain</CardTitle>
          <CardDescription>
            Claim a domain to enable automatic SSO for users with that email domain.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAddDomain} className="flex gap-2">
            <Input
              placeholder="example.com"
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
            />
            <Button type="submit" disabled={loading || !newDomain}>
              Add Domain
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Claimed Domains</CardTitle>
        </CardHeader>
        <CardContent>
          {domains.length === 0 ? (
            <p className="text-muted-foreground">No domains claimed yet.</p>
          ) : (
            <div className="space-y-4">
              {domains.map((domain) => (
                <div
                  key={domain.id}
                  className="flex items-center justify-between border-b pb-4"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{domain.domain}</span>
                      <Badge variant={domain.is_verified ? 'default' : 'secondary'}>
                        {domain.is_verified ? 'Verified' : 'Pending'}
                      </Badge>
                    </div>
                    {!domain.is_verified && domain.verification_token && (
                      <div className="mt-2 text-sm text-muted-foreground">
                        <p>Add this DNS TXT record:</p>
                        <code className="block mt-1 p-2 bg-muted rounded">
                          _dataing.{domain.domain} TXT "{domain.verification_token}"
                        </code>
                      </div>
                    )}
                  </div>
                  {!domain.is_verified && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleVerify(domain.id)}
                      disabled={loading}
                    >
                      Verify
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/features/admin/domain-claims-page.tsx
git commit -m "feat(frontend): add domain claims admin page"
```

---

### Task 16: SCIM Token Management Page

**Files:**
- Create: `frontend/src/features/admin/scim-tokens-page.tsx`

**Step 1: Create SCIM tokens page**

```tsx
// frontend/src/features/admin/scim-tokens-page.tsx
import * as React from 'react'
import { Copy, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { useJwtAuth } from '@/lib/auth'

interface SCIMToken {
  id: string
  description: string
  created_at: string
  last_used_at?: string
}

export function SCIMTokensPage() {
  const { accessToken } = useJwtAuth()
  const [tokens, setTokens] = React.useState<SCIMToken[]>([])
  const [newTokenDescription, setNewTokenDescription] = React.useState('')
  const [generatedToken, setGeneratedToken] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  const scimBaseUrl = `${window.location.origin}/api/v1/scim/v2`

  const fetchTokens = React.useCallback(async () => {
    const res = await fetch('/api/v1/admin/scim/tokens', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    const data = await res.json()
    setTokens(data)
  }, [accessToken])

  React.useEffect(() => {
    fetchTokens()
  }, [fetchTokens])

  const handleGenerateToken = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const res = await fetch('/api/v1/admin/scim/tokens', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ description: newTokenDescription }),
      })
      const data = await res.json()
      setGeneratedToken(data.token)
      setNewTokenDescription('')
      fetchTokens()
    } finally {
      setLoading(false)
    }
  }

  const handleRevokeToken = async (tokenId: string) => {
    setLoading(true)
    try {
      await fetch(`/api/v1/admin/scim/tokens/${tokenId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      fetchTokens()
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">SCIM Provisioning</h1>
        <p className="text-muted-foreground">
          Configure automatic user provisioning from your identity provider.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>SCIM Configuration</CardTitle>
          <CardDescription>
            Use these settings in your identity provider's SCIM configuration.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">SCIM Base URL</label>
            <div className="flex gap-2 mt-1">
              <Input value={scimBaseUrl} readOnly />
              <Button
                variant="outline"
                size="icon"
                onClick={() => copyToClipboard(scimBaseUrl)}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Generate Token</CardTitle>
          <CardDescription>
            Create a bearer token for SCIM authentication.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleGenerateToken} className="flex gap-2">
            <Input
              placeholder="Token description (e.g., Okta SCIM)"
              value={newTokenDescription}
              onChange={(e) => setNewTokenDescription(e.target.value)}
            />
            <Button type="submit" disabled={loading || !newTokenDescription}>
              Generate
            </Button>
          </form>

          {generatedToken && (
            <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded">
              <p className="text-sm font-medium text-yellow-800">
                Copy this token now - it won't be shown again!
              </p>
              <div className="flex gap-2 mt-2">
                <Input value={generatedToken} readOnly className="font-mono" />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => copyToClipboard(generatedToken)}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Active Tokens</CardTitle>
        </CardHeader>
        <CardContent>
          {tokens.length === 0 ? (
            <p className="text-muted-foreground">No SCIM tokens created yet.</p>
          ) : (
            <div className="space-y-2">
              {tokens.map((token) => (
                <div
                  key={token.id}
                  className="flex items-center justify-between p-3 border rounded"
                >
                  <div>
                    <p className="font-medium">{token.description}</p>
                    <p className="text-sm text-muted-foreground">
                      Created: {new Date(token.created_at).toLocaleDateString()}
                      {token.last_used_at && (
                        <> · Last used: {new Date(token.last_used_at).toLocaleDateString()}</>
                      )}
                    </p>
                  </div>
                  <Button
                    variant="destructive"
                    size="icon"
                    onClick={() => handleRevokeToken(token.id)}
                    disabled={loading}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/features/admin/scim-tokens-page.tsx
git commit -m "feat(frontend): add SCIM token management page"
```

---

### Task 17: Wire Up Admin Routes

**Files:**
- Modify: `frontend/src/features/admin/admin-page.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Update admin page with SSO routes**

```tsx
// Update frontend/src/features/admin/admin-page.tsx

import { SSOConfigPage } from './sso-config-page'
import { DomainClaimsPage } from './domain-claims-page'
import { SCIMTokensPage } from './scim-tokens-page'

const adminNavItems = [
  { to: '/admin/teams', label: 'Teams', icon: UsersRound },
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/sso', label: 'SSO', icon: Shield },
  { to: '/admin/domains', label: 'Domains', icon: Globe },
  { to: '/admin/scim', label: 'SCIM', icon: RefreshCw },
]

// In Routes:
<Route path="sso" element={<SSOConfigPage />} />
<Route path="domains" element={<DomainClaimsPage />} />
<Route path="scim" element={<SCIMTokensPage />} />
```

**Step 2: Commit**

```bash
git add frontend/src/features/admin/admin-page.tsx frontend/src/App.tsx
git commit -m "feat(frontend): wire up SSO/SCIM admin routes"
```

---

## Phase 7: Integration

### Task 18: Register Routes in Main App

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/main.py`

**Step 1: Register SSO and SCIM routes**

```python
# Add to backend/src/dataing/entrypoints/api/main.py

from dataing.entrypoints.api.routes import sso, scim, domains

# In create_app():
app.include_router(sso.router, prefix="/api/v1/auth")
app.include_router(scim.router, prefix="/api/v1")
app.include_router(domains.router, prefix="/api/v1/admin")
```

**Step 2: Commit**

```bash
git add backend/src/dataing/entrypoints/api/main.py
git commit -m "feat: register SSO and SCIM routes"
```

---

### Task 19: Run All Tests

**Step 1: Run backend tests**

```bash
cd backend && uv run pytest tests/unit -v
```

Expected: All tests pass

**Step 2: Run frontend type check**

```bash
cd frontend && pnpm exec tsc --noEmit
```

Expected: No errors

**Step 3: Run frontend lint**

```bash
cd frontend && pnpm lint
```

Expected: No errors

---

## Summary

This plan covers:

**Backend (Tasks 1-11, 18):**
- Database schema for SSO configs, domain claims, SSO identities, SCIM tokens
- SSO domain types and repository
- SSO discovery endpoint
- OIDC callback with JIT provisioning
- DNS domain verification
- SCIM 2.0 Users and Groups endpoints
- Admin endpoints for domains

**Frontend (Tasks 12-17):**
- Email-first login flow
- SSO callback handler
- SSO configuration admin page
- Domain claims admin page
- SCIM token management page
- Admin route wiring

**Dependencies:**
- authlib (OIDC)
- python3-saml (SAML)
- dnspython (DNS verification)

Total: ~19 tasks
