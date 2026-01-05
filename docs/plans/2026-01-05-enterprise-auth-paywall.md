# Enterprise Auth & Paywall Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build entitlements foundation (Phase 1) and basic auth system (Phase 2) to enable feature gating and org/team hierarchy.

**Architecture:** Pluggable entitlements adapter pattern with three implementations (OpenCore, Enterprise, Stripe). Auth system with org → team → user hierarchy and JWT-based authentication.

**Tech Stack:** FastAPI, PostgreSQL, PyJWT, passlib (bcrypt), Python protocols

---

## Phase 1: Entitlements Foundation

### Task 1: Feature Registry Types

**Files:**
- Create: `backend/src/dataing/core/entitlements/__init__.py`
- Create: `backend/src/dataing/core/entitlements/features.py`
- Test: `backend/tests/unit/core/entitlements/test_features.py`

**Step 1: Create test directory**

```bash
mkdir -p backend/tests/unit/core/entitlements
touch backend/tests/unit/core/entitlements/__init__.py
```

**Step 2: Write the failing test**

```python
# backend/tests/unit/core/entitlements/test_features.py
"""Tests for feature registry types."""

import pytest

from dataing.core.entitlements.features import Feature, Plan, PLAN_FEATURES


class TestFeatureEnum:
    """Test Feature enum."""

    def test_feature_values_are_strings(self) -> None:
        """Feature enum values should be lowercase strings."""
        assert Feature.SSO_OIDC.value == "sso_oidc"
        assert Feature.MAX_SEATS.value == "max_seats"

    def test_all_features_defined(self) -> None:
        """All expected features should be defined."""
        expected = {
            "sso_oidc", "sso_saml", "scim",
            "max_seats", "max_datasources", "max_investigations_per_month",
            "audit_logs", "custom_branding"
        }
        actual = {f.value for f in Feature}
        assert expected == actual


class TestPlanEnum:
    """Test Plan enum."""

    def test_plan_values(self) -> None:
        """Plan enum values should be lowercase strings."""
        assert Plan.FREE.value == "free"
        assert Plan.PRO.value == "pro"
        assert Plan.ENTERPRISE.value == "enterprise"


class TestPlanFeatures:
    """Test plan feature definitions."""

    def test_free_plan_has_limits(self) -> None:
        """Free plan should have numeric limits."""
        free = PLAN_FEATURES[Plan.FREE]
        assert free[Feature.MAX_SEATS] == 3
        assert free[Feature.MAX_DATASOURCES] == 2
        assert free[Feature.MAX_INVESTIGATIONS_PER_MONTH] == 10

    def test_free_plan_no_enterprise_features(self) -> None:
        """Free plan should not include enterprise features."""
        free = PLAN_FEATURES[Plan.FREE]
        assert Feature.SSO_OIDC not in free
        assert Feature.SCIM not in free

    def test_enterprise_plan_has_all_features(self) -> None:
        """Enterprise plan should include all features."""
        ent = PLAN_FEATURES[Plan.ENTERPRISE]
        assert ent[Feature.SSO_OIDC] is True
        assert ent[Feature.SSO_SAML] is True
        assert ent[Feature.SCIM] is True
        assert ent[Feature.AUDIT_LOGS] is True

    def test_enterprise_plan_unlimited(self) -> None:
        """Enterprise plan should have unlimited (-1) for limits."""
        ent = PLAN_FEATURES[Plan.ENTERPRISE]
        assert ent[Feature.MAX_SEATS] == -1
        assert ent[Feature.MAX_DATASOURCES] == -1
        assert ent[Feature.MAX_INVESTIGATIONS_PER_MONTH] == -1
```

**Step 3: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/entitlements/test_features.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dataing.core.entitlements'`

**Step 4: Write minimal implementation**

```python
# backend/src/dataing/core/entitlements/__init__.py
"""Entitlements module for feature gating and billing."""

from dataing.core.entitlements.features import Feature, Plan, PLAN_FEATURES

__all__ = ["Feature", "Plan", "PLAN_FEATURES"]
```

```python
# backend/src/dataing/core/entitlements/features.py
"""Feature registry and plan definitions."""

from enum import Enum


class Feature(str, Enum):
    """Features that can be gated by plan."""

    # Auth features (boolean)
    SSO_OIDC = "sso_oidc"
    SSO_SAML = "sso_saml"
    SCIM = "scim"

    # Limits (numeric, -1 = unlimited)
    MAX_SEATS = "max_seats"
    MAX_DATASOURCES = "max_datasources"
    MAX_INVESTIGATIONS_PER_MONTH = "max_investigations_per_month"

    # Future enterprise features
    AUDIT_LOGS = "audit_logs"
    CUSTOM_BRANDING = "custom_branding"


class Plan(str, Enum):
    """Available subscription plans."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Plan feature definitions - what each plan includes
PLAN_FEATURES: dict[Plan, dict[Feature, int | bool]] = {
    Plan.FREE: {
        Feature.MAX_SEATS: 3,
        Feature.MAX_DATASOURCES: 2,
        Feature.MAX_INVESTIGATIONS_PER_MONTH: 10,
    },
    Plan.PRO: {
        Feature.MAX_SEATS: 10,
        Feature.MAX_DATASOURCES: 10,
        Feature.MAX_INVESTIGATIONS_PER_MONTH: 100,
    },
    Plan.ENTERPRISE: {
        Feature.SSO_OIDC: True,
        Feature.SSO_SAML: True,
        Feature.SCIM: True,
        Feature.AUDIT_LOGS: True,
        Feature.MAX_SEATS: -1,  # unlimited
        Feature.MAX_DATASOURCES: -1,
        Feature.MAX_INVESTIGATIONS_PER_MONTH: -1,
    },
}
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/entitlements/test_features.py -v
```

Expected: PASS (8 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/core/entitlements backend/tests/unit/core/entitlements
git commit -m "feat(entitlements): add feature registry and plan definitions"
```

---

### Task 2: Entitlements Adapter Protocol

**Files:**
- Create: `backend/src/dataing/core/entitlements/interfaces.py`
- Test: `backend/tests/unit/core/entitlements/test_interfaces.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/core/entitlements/test_interfaces.py
"""Tests for entitlements adapter protocol."""

import pytest
from typing import Protocol, runtime_checkable

from dataing.core.entitlements.interfaces import EntitlementsAdapter
from dataing.core.entitlements.features import Feature, Plan


class TestEntitlementsAdapterProtocol:
    """Test EntitlementsAdapter is a proper protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Protocol should be runtime checkable."""
        assert hasattr(EntitlementsAdapter, "__protocol_attrs__") or \
               isinstance(EntitlementsAdapter, type)

    def test_protocol_has_required_methods(self) -> None:
        """Protocol should define required methods."""
        # Check method signatures exist
        assert hasattr(EntitlementsAdapter, "has_feature")
        assert hasattr(EntitlementsAdapter, "get_limit")
        assert hasattr(EntitlementsAdapter, "get_usage")
        assert hasattr(EntitlementsAdapter, "check_limit")
        assert hasattr(EntitlementsAdapter, "get_plan")


class MockAdapter:
    """Mock implementation for testing protocol compliance."""

    async def has_feature(self, org_id: str, feature: Feature) -> bool:
        """Check if org has access to a feature."""
        return True

    async def get_limit(self, org_id: str, feature: Feature) -> int:
        """Get numeric limit for org."""
        return 10

    async def get_usage(self, org_id: str, feature: Feature) -> int:
        """Get current usage for org."""
        return 5

    async def check_limit(self, org_id: str, feature: Feature) -> bool:
        """Check if org is under their limit."""
        return True

    async def get_plan(self, org_id: str) -> Plan:
        """Get org's current plan."""
        return Plan.FREE


class TestProtocolCompliance:
    """Test that implementations comply with protocol."""

    def test_mock_adapter_is_protocol_compliant(self) -> None:
        """Mock adapter should be instance of protocol."""
        adapter = MockAdapter()
        assert isinstance(adapter, EntitlementsAdapter)
```

**Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/entitlements/test_interfaces.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/core/entitlements/interfaces.py
"""Protocol definitions for entitlements adapters."""

from typing import Protocol, runtime_checkable

from dataing.core.entitlements.features import Feature, Plan


@runtime_checkable
class EntitlementsAdapter(Protocol):
    """Protocol for pluggable entitlements backend.

    Implementations:
    - OpenCoreAdapter: Default free tier (no external dependencies)
    - EnterpriseAdapter: License key validation + DB entitlements
    - StripeAdapter: Stripe subscription management
    """

    async def has_feature(self, org_id: str, feature: Feature) -> bool:
        """Check if org has access to a boolean feature (SSO, SCIM, etc.).

        Args:
            org_id: Organization identifier
            feature: Feature to check

        Returns:
            True if org has access to feature
        """
        ...

    async def get_limit(self, org_id: str, feature: Feature) -> int:
        """Get numeric limit for org (-1 = unlimited).

        Args:
            org_id: Organization identifier
            feature: Feature limit to get

        Returns:
            Limit value, -1 for unlimited
        """
        ...

    async def get_usage(self, org_id: str, feature: Feature) -> int:
        """Get current usage count for a limited feature.

        Args:
            org_id: Organization identifier
            feature: Feature to get usage for

        Returns:
            Current usage count
        """
        ...

    async def check_limit(self, org_id: str, feature: Feature) -> bool:
        """Check if org is under their limit (usage < limit or unlimited).

        Args:
            org_id: Organization identifier
            feature: Feature limit to check

        Returns:
            True if under limit or unlimited
        """
        ...

    async def get_plan(self, org_id: str) -> Plan:
        """Get org's current plan.

        Args:
            org_id: Organization identifier

        Returns:
            Current plan
        """
        ...
```

Update `__init__.py`:

```python
# backend/src/dataing/core/entitlements/__init__.py
"""Entitlements module for feature gating and billing."""

from dataing.core.entitlements.features import Feature, Plan, PLAN_FEATURES
from dataing.core.entitlements.interfaces import EntitlementsAdapter

__all__ = ["Feature", "Plan", "PLAN_FEATURES", "EntitlementsAdapter"]
```

**Step 4: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/entitlements/test_interfaces.py -v
```

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/dataing/core/entitlements
git commit -m "feat(entitlements): add EntitlementsAdapter protocol"
```

---

### Task 3: OpenCore Adapter Implementation

**Files:**
- Create: `backend/src/dataing/adapters/entitlements/__init__.py`
- Create: `backend/src/dataing/adapters/entitlements/opencore.py`
- Test: `backend/tests/unit/adapters/entitlements/test_opencore.py`

**Step 1: Create test directory**

```bash
mkdir -p backend/tests/unit/adapters/entitlements
touch backend/tests/unit/adapters/entitlements/__init__.py
```

**Step 2: Write the failing test**

```python
# backend/tests/unit/adapters/entitlements/test_opencore.py
"""Tests for OpenCore entitlements adapter."""

import pytest

from dataing.adapters.entitlements.opencore import OpenCoreAdapter
from dataing.core.entitlements import Feature, Plan, EntitlementsAdapter


class TestOpenCoreAdapter:
    """Test OpenCoreAdapter implementation."""

    @pytest.fixture
    def adapter(self) -> OpenCoreAdapter:
        """Create adapter instance."""
        return OpenCoreAdapter()

    def test_implements_protocol(self, adapter: OpenCoreAdapter) -> None:
        """Adapter should implement EntitlementsAdapter protocol."""
        assert isinstance(adapter, EntitlementsAdapter)

    @pytest.mark.asyncio
    async def test_get_plan_always_free(self, adapter: OpenCoreAdapter) -> None:
        """OpenCore always returns FREE plan."""
        plan = await adapter.get_plan("any-org-id")
        assert plan == Plan.FREE

    @pytest.mark.asyncio
    async def test_has_feature_enterprise_features_false(
        self, adapter: OpenCoreAdapter
    ) -> None:
        """Enterprise features should return False."""
        assert await adapter.has_feature("org", Feature.SSO_OIDC) is False
        assert await adapter.has_feature("org", Feature.SSO_SAML) is False
        assert await adapter.has_feature("org", Feature.SCIM) is False
        assert await adapter.has_feature("org", Feature.AUDIT_LOGS) is False

    @pytest.mark.asyncio
    async def test_get_limit_returns_free_tier(
        self, adapter: OpenCoreAdapter
    ) -> None:
        """Limits should return FREE tier values."""
        assert await adapter.get_limit("org", Feature.MAX_SEATS) == 3
        assert await adapter.get_limit("org", Feature.MAX_DATASOURCES) == 2
        assert await adapter.get_limit("org", Feature.MAX_INVESTIGATIONS_PER_MONTH) == 10

    @pytest.mark.asyncio
    async def test_get_usage_returns_zero(self, adapter: OpenCoreAdapter) -> None:
        """Usage should return 0 (no tracking in open core)."""
        assert await adapter.get_usage("org", Feature.MAX_SEATS) == 0

    @pytest.mark.asyncio
    async def test_check_limit_always_true(self, adapter: OpenCoreAdapter) -> None:
        """Check limit should always return True (no enforcement in open core)."""
        assert await adapter.check_limit("org", Feature.MAX_SEATS) is True
```

**Step 3: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/adapters/entitlements/test_opencore.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4: Write minimal implementation**

```python
# backend/src/dataing/adapters/entitlements/__init__.py
"""Entitlements adapters."""

from dataing.adapters.entitlements.opencore import OpenCoreAdapter

__all__ = ["OpenCoreAdapter"]
```

```python
# backend/src/dataing/adapters/entitlements/opencore.py
"""OpenCore entitlements adapter - default free tier with no external dependencies."""

from dataing.core.entitlements import Feature, Plan, PLAN_FEATURES


class OpenCoreAdapter:
    """Default entitlements adapter for open source deployments.

    Always returns FREE tier limits. No usage tracking or enforcement.
    This allows the open source version to run without any license or billing.
    """

    async def has_feature(self, org_id: str, feature: Feature) -> bool:
        """Check if org has access to a feature.

        In open core, only features included in FREE plan are available.
        """
        free_features = PLAN_FEATURES[Plan.FREE]
        return feature in free_features and free_features[feature] is True

    async def get_limit(self, org_id: str, feature: Feature) -> int:
        """Get numeric limit for org.

        Returns FREE tier limits.
        """
        free_features = PLAN_FEATURES[Plan.FREE]
        limit = free_features.get(feature)
        if isinstance(limit, int):
            return limit
        return 0

    async def get_usage(self, org_id: str, feature: Feature) -> int:
        """Get current usage for org.

        Open core doesn't track usage - always returns 0.
        """
        return 0

    async def check_limit(self, org_id: str, feature: Feature) -> bool:
        """Check if org is under their limit.

        Open core doesn't enforce limits - always returns True.
        """
        return True

    async def get_plan(self, org_id: str) -> Plan:
        """Get org's current plan.

        Open core always returns FREE.
        """
        return Plan.FREE
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/adapters/entitlements/test_opencore.py -v
```

Expected: PASS (7 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/adapters/entitlements backend/tests/unit/adapters/entitlements
git commit -m "feat(entitlements): add OpenCoreAdapter for free tier"
```

---

### Task 4: Entitlements Dependency Injection

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/deps.py`
- Create: `backend/src/dataing/core/entitlements/config.py`
- Test: `backend/tests/unit/core/entitlements/test_config.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/core/entitlements/test_config.py
"""Tests for entitlements configuration."""

import pytest
from unittest.mock import patch

from dataing.core.entitlements.config import get_entitlements_adapter
from dataing.adapters.entitlements.opencore import OpenCoreAdapter
from dataing.core.entitlements import EntitlementsAdapter


class TestGetEntitlementsAdapter:
    """Test adapter factory function."""

    def test_returns_opencore_by_default(self) -> None:
        """Should return OpenCoreAdapter when no config is set."""
        adapter = get_entitlements_adapter()
        assert isinstance(adapter, OpenCoreAdapter)
        assert isinstance(adapter, EntitlementsAdapter)

    @patch.dict("os.environ", {"LICENSE_KEY": ""})
    def test_returns_opencore_with_empty_license(self) -> None:
        """Should return OpenCoreAdapter when license key is empty."""
        adapter = get_entitlements_adapter()
        assert isinstance(adapter, OpenCoreAdapter)

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": ""})
    def test_returns_opencore_with_empty_stripe(self) -> None:
        """Should return OpenCoreAdapter when stripe key is empty."""
        adapter = get_entitlements_adapter()
        assert isinstance(adapter, OpenCoreAdapter)
```

**Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/entitlements/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/core/entitlements/config.py
"""Entitlements adapter factory configuration."""

import os
from functools import lru_cache

from dataing.adapters.entitlements.opencore import OpenCoreAdapter
from dataing.core.entitlements.interfaces import EntitlementsAdapter


@lru_cache
def get_entitlements_adapter() -> EntitlementsAdapter:
    """Get the configured entitlements adapter.

    Selection priority:
    1. STRIPE_SECRET_KEY set -> StripeAdapter (SaaS billing)
    2. LICENSE_KEY set -> EnterpriseAdapter (self-hosted licensed)
    3. Neither set -> OpenCoreAdapter (free tier)

    Returns:
        Configured entitlements adapter instance
    """
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    license_key = os.environ.get("LICENSE_KEY", "").strip()

    if stripe_key:
        # TODO: Return StripeAdapter when implemented
        # return StripeAdapter(stripe_key)
        pass

    if license_key:
        # TODO: Return EnterpriseAdapter when implemented
        # return EnterpriseAdapter(license_key)
        pass

    return OpenCoreAdapter()
```

Update `__init__.py`:

```python
# backend/src/dataing/core/entitlements/__init__.py
"""Entitlements module for feature gating and billing."""

from dataing.core.entitlements.features import Feature, Plan, PLAN_FEATURES
from dataing.core.entitlements.interfaces import EntitlementsAdapter
from dataing.core.entitlements.config import get_entitlements_adapter

__all__ = [
    "Feature",
    "Plan",
    "PLAN_FEATURES",
    "EntitlementsAdapter",
    "get_entitlements_adapter",
]
```

**Step 4: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/entitlements/test_config.py -v
```

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/dataing/core/entitlements
git commit -m "feat(entitlements): add adapter factory with env-based selection"
```

---

### Task 5: Entitlements API Middleware

**Files:**
- Create: `backend/src/dataing/entrypoints/api/middleware/entitlements.py`
- Test: `backend/tests/unit/entrypoints/api/middleware/test_entitlements.py`

**Step 1: Create test directory**

```bash
mkdir -p backend/tests/unit/entrypoints/api/middleware
touch backend/tests/unit/entrypoints/api/middleware/__init__.py
```

**Step 2: Write the failing test**

```python
# backend/tests/unit/entrypoints/api/middleware/test_entitlements.py
"""Tests for entitlements middleware decorators."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from dataing.entrypoints.api.middleware.entitlements import (
    require_feature,
    require_under_limit,
)
from dataing.core.entitlements import Feature


class TestRequireFeature:
    """Test require_feature decorator."""

    @pytest.mark.asyncio
    async def test_allows_when_feature_enabled(self) -> None:
        """Should allow request when feature is enabled."""
        mock_adapter = AsyncMock()
        mock_adapter.has_feature.return_value = True

        @require_feature(Feature.SSO_OIDC)
        async def endpoint(org_id: str) -> str:
            return "success"

        with patch(
            "dataing.entrypoints.api.middleware.entitlements.get_entitlements_adapter",
            return_value=mock_adapter,
        ):
            result = await endpoint(org_id="org-123")

        assert result == "success"
        mock_adapter.has_feature.assert_called_once_with("org-123", Feature.SSO_OIDC)

    @pytest.mark.asyncio
    async def test_raises_403_when_feature_disabled(self) -> None:
        """Should raise 403 when feature is not enabled."""
        mock_adapter = AsyncMock()
        mock_adapter.has_feature.return_value = False

        @require_feature(Feature.SSO_OIDC)
        async def endpoint(org_id: str) -> str:
            return "success"

        with patch(
            "dataing.entrypoints.api.middleware.entitlements.get_entitlements_adapter",
            return_value=mock_adapter,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await endpoint(org_id="org-123")

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "feature_not_available"
        assert exc_info.value.detail["feature"] == "sso_oidc"


class TestRequireUnderLimit:
    """Test require_under_limit decorator."""

    @pytest.mark.asyncio
    async def test_allows_when_under_limit(self) -> None:
        """Should allow request when under limit."""
        mock_adapter = AsyncMock()
        mock_adapter.check_limit.return_value = True

        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def endpoint(org_id: str) -> str:
            return "success"

        with patch(
            "dataing.entrypoints.api.middleware.entitlements.get_entitlements_adapter",
            return_value=mock_adapter,
        ):
            result = await endpoint(org_id="org-123")

        assert result == "success"

    @pytest.mark.asyncio
    async def test_raises_403_when_over_limit(self) -> None:
        """Should raise 403 when over limit."""
        mock_adapter = AsyncMock()
        mock_adapter.check_limit.return_value = False
        mock_adapter.get_limit.return_value = 10

        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def endpoint(org_id: str) -> str:
            return "success"

        with patch(
            "dataing.entrypoints.api.middleware.entitlements.get_entitlements_adapter",
            return_value=mock_adapter,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await endpoint(org_id="org-123")

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "limit_exceeded"
        assert exc_info.value.detail["limit"] == 10
```

**Step 3: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/entrypoints/api/middleware/test_entitlements.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4: Write minimal implementation**

```bash
mkdir -p backend/src/dataing/entrypoints/api/middleware
touch backend/src/dataing/entrypoints/api/middleware/__init__.py
```

```python
# backend/src/dataing/entrypoints/api/middleware/entitlements.py
"""Entitlements middleware decorators for API routes."""

from functools import wraps
from typing import Any, Callable, TypeVar

from fastapi import HTTPException

from dataing.core.entitlements import Feature, get_entitlements_adapter

F = TypeVar("F", bound=Callable[..., Any])


def require_feature(feature: Feature) -> Callable[[F], F]:
    """Decorator to require a feature to be enabled for the org.

    Usage:
        @router.get("/sso/config")
        @require_feature(Feature.SSO_OIDC)
        async def get_sso_config(org_id: str):
            ...

    Args:
        feature: Feature that must be enabled

    Raises:
        HTTPException: 403 if feature not available
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, org_id: str, **kwargs: Any) -> Any:
            adapter = get_entitlements_adapter()
            if not await adapter.has_feature(org_id, feature):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "feature_not_available",
                        "feature": feature.value,
                        "upgrade_url": "/settings/billing",
                    },
                )
            return await func(*args, org_id=org_id, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def require_under_limit(feature: Feature) -> Callable[[F], F]:
    """Decorator to require org is under their usage limit.

    Usage:
        @router.post("/investigations")
        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def create_investigation(org_id: str):
            ...

    Args:
        feature: Feature limit to check

    Raises:
        HTTPException: 403 if over limit
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, org_id: str, **kwargs: Any) -> Any:
            adapter = get_entitlements_adapter()
            if not await adapter.check_limit(org_id, feature):
                limit = await adapter.get_limit(org_id, feature)
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "limit_exceeded",
                        "feature": feature.value,
                        "limit": limit,
                        "upgrade_url": "/settings/billing",
                    },
                )
            return await func(*args, org_id=org_id, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/entrypoints/api/middleware/test_entitlements.py -v
```

Expected: PASS (4 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/entrypoints/api/middleware backend/tests/unit/entrypoints/api/middleware
git commit -m "feat(entitlements): add require_feature and require_under_limit decorators"
```

---

### Task 6: Frontend Entitlements Context

**Files:**
- Create: `frontend/src/lib/entitlements/types.ts`
- Create: `frontend/src/lib/entitlements/context.tsx`
- Create: `frontend/src/lib/entitlements/hooks.ts`
- Test: `frontend/src/lib/entitlements/useEntitlements.test.tsx`

**Step 1: Write the failing test**

```typescript
// frontend/src/lib/entitlements/useEntitlements.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useEntitlements, EntitlementsProvider } from './index'
import type { Entitlements } from './types'
import type { ReactNode } from 'react'

const mockEntitlements: Entitlements = {
  plan: 'free',
  features: {
    sso_oidc: false,
    sso_saml: false,
    scim: false,
    audit_logs: false,
  },
  limits: {
    max_seats: { limit: 3, usage: 1 },
    max_datasources: { limit: 2, usage: 0 },
    max_investigations_per_month: { limit: 10, usage: 5 },
  },
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <EntitlementsProvider entitlements={mockEntitlements}>
      {children}
    </EntitlementsProvider>
  )
}

describe('useEntitlements', () => {
  it('returns hasFeature that checks feature availability', () => {
    const { result } = renderHook(() => useEntitlements(), { wrapper })

    expect(result.current.hasFeature('sso_oidc')).toBe(false)
    expect(result.current.hasFeature('nonexistent')).toBe(false)
  })

  it('returns isUnderLimit that checks usage limits', () => {
    const { result } = renderHook(() => useEntitlements(), { wrapper })

    // 5 < 10, so under limit
    expect(result.current.isUnderLimit('max_investigations_per_month')).toBe(true)
  })

  it('returns getUsage that shows current usage', () => {
    const { result } = renderHook(() => useEntitlements(), { wrapper })

    const usage = result.current.getUsage('max_investigations_per_month')
    expect(usage).toEqual({ limit: 10, usage: 5 })
  })

  it('returns plan', () => {
    const { result } = renderHook(() => useEntitlements(), { wrapper })
    expect(result.current.plan).toBe('free')
  })
})
```

**Step 2: Run test to verify it fails**

```bash
cd frontend && pnpm test -- --run src/lib/entitlements
```

Expected: FAIL with module not found

**Step 3: Write minimal implementation**

```bash
mkdir -p frontend/src/lib/entitlements
```

```typescript
// frontend/src/lib/entitlements/types.ts
export type Plan = 'free' | 'pro' | 'enterprise'

export interface UsageLimit {
  limit: number // -1 = unlimited
  usage: number
}

export interface Entitlements {
  plan: Plan
  features: Record<string, boolean>
  limits: Record<string, UsageLimit>
}
```

```typescript
// frontend/src/lib/entitlements/context.tsx
import { createContext, useContext, type ReactNode } from 'react'
import type { Entitlements } from './types'

const defaultEntitlements: Entitlements = {
  plan: 'free',
  features: {},
  limits: {},
}

const EntitlementsContext = createContext<Entitlements>(defaultEntitlements)

interface EntitlementsProviderProps {
  children: ReactNode
  entitlements: Entitlements
}

export function EntitlementsProvider({
  children,
  entitlements,
}: EntitlementsProviderProps) {
  return (
    <EntitlementsContext.Provider value={entitlements}>
      {children}
    </EntitlementsContext.Provider>
  )
}

export function useEntitlementsContext() {
  return useContext(EntitlementsContext)
}
```

```typescript
// frontend/src/lib/entitlements/hooks.ts
import { useCallback } from 'react'
import { useEntitlementsContext } from './context'
import type { UsageLimit, Plan } from './types'

export interface UseEntitlementsReturn {
  plan: Plan
  hasFeature: (feature: string) => boolean
  isUnderLimit: (feature: string) => boolean
  getUsage: (feature: string) => UsageLimit | undefined
}

export function useEntitlements(): UseEntitlementsReturn {
  const entitlements = useEntitlementsContext()

  const hasFeature = useCallback(
    (feature: string): boolean => {
      return entitlements.features[feature] ?? false
    },
    [entitlements.features]
  )

  const isUnderLimit = useCallback(
    (feature: string): boolean => {
      const limit = entitlements.limits[feature]
      if (!limit) return true
      if (limit.limit === -1) return true // unlimited
      return limit.usage < limit.limit
    },
    [entitlements.limits]
  )

  const getUsage = useCallback(
    (feature: string): UsageLimit | undefined => {
      return entitlements.limits[feature]
    },
    [entitlements.limits]
  )

  return {
    plan: entitlements.plan,
    hasFeature,
    isUnderLimit,
    getUsage,
  }
}
```

```typescript
// frontend/src/lib/entitlements/index.ts
export type { Entitlements, Plan, UsageLimit } from './types'
export { EntitlementsProvider } from './context'
export { useEntitlements } from './hooks'
```

**Step 4: Run test to verify it passes**

```bash
cd frontend && pnpm test -- --run src/lib/entitlements
```

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add frontend/src/lib/entitlements
git commit -m "feat(frontend): add entitlements context and useEntitlements hook"
```

---

## Phase 2: Basic Auth System

### Task 7: Auth Database Schema

**Files:**
- Create: `backend/migrations/007_auth_tables.sql`

**Step 1: Write migration**

```sql
-- backend/migrations/007_auth_tables.sql
-- Auth system tables: organizations, teams, users, memberships

-- Plan type enum
CREATE TYPE plan_type AS ENUM ('free', 'pro', 'enterprise');

-- Organization role enum
CREATE TYPE org_role AS ENUM ('owner', 'admin', 'member', 'viewer');

-- Organizations (top level - a company/customer)
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,  -- for URLs: app.dataing.io/acme
    plan plan_type DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Teams within an org (data team, finance team, subsidiaries)
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(org_id, name)
);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    password_hash VARCHAR(255),  -- null if SSO-only
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User membership in orgs with role
CREATE TABLE org_memberships (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role org_role NOT NULL DEFAULT 'member',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_id, org_id)
);

-- User membership in teams (optional, for resource scoping)
CREATE TABLE team_memberships (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_id, team_id)
);

-- Tenant entitlements (overrides for custom deals)
CREATE TABLE tenant_entitlements (
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    feature VARCHAR(50) NOT NULL,
    value JSONB NOT NULL,  -- true/false or number
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (org_id, feature)
);

-- Add team_id to datasources for team-level scoping
ALTER TABLE datasources ADD COLUMN IF NOT EXISTS team_id UUID REFERENCES teams(id);

-- Indexes for common queries
CREATE INDEX idx_org_memberships_org ON org_memberships(org_id);
CREATE INDEX idx_team_memberships_team ON team_memberships(team_id);
CREATE INDEX idx_teams_org ON teams(org_id);
CREATE INDEX idx_datasources_team ON datasources(team_id);
CREATE INDEX idx_organizations_slug ON organizations(slug);
```

**Step 2: Commit**

```bash
git add backend/migrations/007_auth_tables.sql
git commit -m "feat(auth): add auth database schema with org/team hierarchy"
```

---

### Task 8: Auth Domain Types

**Files:**
- Create: `backend/src/dataing/core/auth/__init__.py`
- Create: `backend/src/dataing/core/auth/types.py`
- Test: `backend/tests/unit/core/auth/test_types.py`

**Step 1: Create test directory**

```bash
mkdir -p backend/tests/unit/core/auth
touch backend/tests/unit/core/auth/__init__.py
```

**Step 2: Write the failing test**

```python
# backend/tests/unit/core/auth/test_types.py
"""Tests for auth domain types."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from dataing.core.auth.types import (
    User,
    Organization,
    Team,
    OrgMembership,
    OrgRole,
    TokenPayload,
)


class TestUser:
    """Test User model."""

    def test_create_user(self) -> None:
        """Should create user with required fields."""
        user = User(
            id=uuid4(),
            email="test@example.com",
            name="Test User",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        assert user.email == "test@example.com"
        assert user.password_hash is None

    def test_user_password_hash_optional(self) -> None:
        """Password hash should be optional for SSO users."""
        user = User(
            id=uuid4(),
            email="sso@example.com",
            name="SSO User",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        assert user.password_hash is None


class TestOrganization:
    """Test Organization model."""

    def test_create_org(self) -> None:
        """Should create org with slug."""
        org = Organization(
            id=uuid4(),
            name="Acme Corp",
            slug="acme",
            plan="free",
            created_at=datetime.now(timezone.utc),
        )
        assert org.slug == "acme"
        assert org.plan == "free"


class TestOrgRole:
    """Test OrgRole enum."""

    def test_role_values(self) -> None:
        """Roles should have correct string values."""
        assert OrgRole.OWNER.value == "owner"
        assert OrgRole.ADMIN.value == "admin"
        assert OrgRole.MEMBER.value == "member"
        assert OrgRole.VIEWER.value == "viewer"


class TestTokenPayload:
    """Test TokenPayload for JWT."""

    def test_create_token_payload(self) -> None:
        """Should create token payload with required claims."""
        user_id = uuid4()
        org_id = uuid4()
        payload = TokenPayload(
            sub=str(user_id),
            org_id=str(org_id),
            role="admin",
            teams=["team-1", "team-2"],
            exp=1234567890,
            iat=1234567800,
        )
        assert payload.sub == str(user_id)
        assert payload.role == "admin"
        assert len(payload.teams) == 2
```

**Step 3: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_types.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4: Write minimal implementation**

```python
# backend/src/dataing/core/auth/__init__.py
"""Auth domain types and utilities."""

from dataing.core.auth.types import (
    User,
    Organization,
    Team,
    OrgMembership,
    TeamMembership,
    OrgRole,
    TokenPayload,
)

__all__ = [
    "User",
    "Organization",
    "Team",
    "OrgMembership",
    "TeamMembership",
    "OrgRole",
    "TokenPayload",
]
```

```python
# backend/src/dataing/core/auth/types.py
"""Auth domain types."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, EmailStr


class OrgRole(str, Enum):
    """Organization membership roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(BaseModel):
    """User domain model."""

    id: UUID
    email: EmailStr
    name: str | None = None
    password_hash: str | None = None  # None for SSO-only users
    is_active: bool = True
    created_at: datetime


class Organization(BaseModel):
    """Organization domain model."""

    id: UUID
    name: str
    slug: str
    plan: str = "free"
    created_at: datetime


class Team(BaseModel):
    """Team domain model."""

    id: UUID
    org_id: UUID
    name: str
    created_at: datetime


class OrgMembership(BaseModel):
    """User's membership in an organization."""

    user_id: UUID
    org_id: UUID
    role: OrgRole
    created_at: datetime


class TeamMembership(BaseModel):
    """User's membership in a team."""

    user_id: UUID
    team_id: UUID
    created_at: datetime


class TokenPayload(BaseModel):
    """JWT token payload claims."""

    sub: str  # user_id
    org_id: str
    role: str
    teams: list[str]
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_types.py -v
```

Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/core/auth backend/tests/unit/core/auth
git commit -m "feat(auth): add auth domain types (User, Org, Team, Token)"
```

---

### Task 9: Password Hashing Utility

**Files:**
- Create: `backend/src/dataing/core/auth/password.py`
- Test: `backend/tests/unit/core/auth/test_password.py`

**Step 1: Add passlib dependency**

```bash
cd backend && uv add "passlib[bcrypt]"
```

**Step 2: Write the failing test**

```python
# backend/tests/unit/core/auth/test_password.py
"""Tests for password hashing utilities."""

import pytest

from dataing.core.auth.password import hash_password, verify_password


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password_returns_hash(self) -> None:
        """Should return a bcrypt hash."""
        hashed = hash_password("mypassword123")
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_hash_password_different_each_time(self) -> None:
        """Same password should produce different hashes (salted)."""
        hash1 = hash_password("mypassword123")
        hash2 = hash_password("mypassword123")
        assert hash1 != hash2

    def test_verify_password_correct(self) -> None:
        """Should return True for correct password."""
        hashed = hash_password("mypassword123")
        assert verify_password("mypassword123", hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Should return False for incorrect password."""
        hashed = hash_password("mypassword123")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self) -> None:
        """Should return False for empty password."""
        hashed = hash_password("mypassword123")
        assert verify_password("", hashed) is False
```

**Step 3: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_password.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4: Write minimal implementation**

```python
# backend/src/dataing/core/auth/password.py
"""Password hashing utilities using bcrypt."""

from passlib.context import CryptContext

# Use bcrypt with default rounds (12)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hash string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash.

    Args:
        plain_password: Plain text password to check
        hashed_password: Bcrypt hash to check against

    Returns:
        True if password matches hash
    """
    if not plain_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)
```

Update `__init__.py`:

```python
# backend/src/dataing/core/auth/__init__.py
"""Auth domain types and utilities."""

from dataing.core.auth.types import (
    User,
    Organization,
    Team,
    OrgMembership,
    TeamMembership,
    OrgRole,
    TokenPayload,
)
from dataing.core.auth.password import hash_password, verify_password

__all__ = [
    "User",
    "Organization",
    "Team",
    "OrgMembership",
    "TeamMembership",
    "OrgRole",
    "TokenPayload",
    "hash_password",
    "verify_password",
]
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_password.py -v
```

Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/core/auth backend/pyproject.toml backend/uv.lock
git commit -m "feat(auth): add password hashing with bcrypt"
```

---

### Task 10: JWT Token Service

**Files:**
- Create: `backend/src/dataing/core/auth/jwt.py`
- Test: `backend/tests/unit/core/auth/test_jwt.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/core/auth/test_jwt.py
"""Tests for JWT token service."""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import patch

from dataing.core.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenError,
)
from dataing.core.auth.types import TokenPayload


class TestCreateAccessToken:
    """Test access token creation."""

    def test_creates_valid_jwt(self) -> None:
        """Should create a valid JWT string."""
        user_id = uuid4()
        org_id = uuid4()

        token = create_access_token(
            user_id=str(user_id),
            org_id=str(org_id),
            role="admin",
            teams=["team-1"],
        )

        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has 3 parts separated by dots
        assert len(token.split(".")) == 3

    def test_token_contains_claims(self) -> None:
        """Token should contain correct claims."""
        user_id = str(uuid4())
        org_id = str(uuid4())

        token = create_access_token(
            user_id=user_id,
            org_id=org_id,
            role="member",
            teams=["team-1", "team-2"],
        )

        payload = decode_token(token)
        assert payload.sub == user_id
        assert payload.org_id == org_id
        assert payload.role == "member"
        assert payload.teams == ["team-1", "team-2"]


class TestDecodeToken:
    """Test token decoding."""

    def test_decode_valid_token(self) -> None:
        """Should decode a valid token."""
        token = create_access_token(
            user_id="user-123",
            org_id="org-456",
            role="admin",
            teams=[],
        )

        payload = decode_token(token)
        assert isinstance(payload, TokenPayload)
        assert payload.sub == "user-123"

    def test_decode_expired_token_raises(self) -> None:
        """Should raise TokenError for expired token."""
        # Create token that's already expired
        with patch("dataing.core.auth.jwt.datetime") as mock_dt:
            # Set current time to 2 hours ago so token is created expired
            past = datetime.now(timezone.utc) - timedelta(hours=2)
            mock_dt.now.return_value = past
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            token = create_access_token(
                user_id="user-123",
                org_id="org-456",
                role="admin",
                teams=[],
            )

        with pytest.raises(TokenError) as exc_info:
            decode_token(token)

        assert "expired" in str(exc_info.value).lower()

    def test_decode_invalid_token_raises(self) -> None:
        """Should raise TokenError for invalid token."""
        with pytest.raises(TokenError):
            decode_token("invalid.token.here")


class TestRefreshToken:
    """Test refresh token creation."""

    def test_refresh_token_longer_expiry(self) -> None:
        """Refresh token should have longer expiry than access token."""
        access = create_access_token(
            user_id="user-123",
            org_id="org-456",
            role="admin",
            teams=[],
        )
        refresh = create_refresh_token(user_id="user-123")

        access_payload = decode_token(access)
        refresh_payload = decode_token(refresh)

        # Refresh should expire later than access
        assert refresh_payload.exp > access_payload.exp
```

**Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_jwt.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/core/auth/jwt.py
"""JWT token creation and validation."""

import os
from datetime import datetime, timezone, timedelta

import jwt

from dataing.core.auth.types import TokenPayload


class TokenError(Exception):
    """Raised when token validation fails."""

    pass


# Configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_access_token(
    user_id: str,
    org_id: str,
    role: str,
    teams: list[str],
) -> str:
    """Create a short-lived access token.

    Args:
        user_id: User identifier
        org_id: Organization identifier
        role: User's role in the org
        teams: List of team IDs user belongs to

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "teams": teams,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token.

    Args:
        user_id: User identifier

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "org_id": "",  # Refresh tokens don't carry org context
        "role": "",
        "teams": [],
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "type": "refresh",
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token.

    Args:
        token: Encoded JWT string

    Returns:
        Decoded token payload

    Raises:
        TokenError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenPayload(
            sub=payload["sub"],
            org_id=payload["org_id"],
            role=payload["role"],
            teams=payload["teams"],
            exp=payload["exp"],
            iat=payload["iat"],
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise TokenError(f"Invalid token: {e}")
```

Update `__init__.py`:

```python
# backend/src/dataing/core/auth/__init__.py
"""Auth domain types and utilities."""

from dataing.core.auth.types import (
    User,
    Organization,
    Team,
    OrgMembership,
    TeamMembership,
    OrgRole,
    TokenPayload,
)
from dataing.core.auth.password import hash_password, verify_password
from dataing.core.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenError,
)

__all__ = [
    "User",
    "Organization",
    "Team",
    "OrgMembership",
    "TeamMembership",
    "OrgRole",
    "TokenPayload",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "TokenError",
]
```

**Step 4: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_jwt.py -v
```

Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add backend/src/dataing/core/auth
git commit -m "feat(auth): add JWT token service with access/refresh tokens"
```

---

## Summary

This plan covers **Phase 1 (Entitlements Foundation)** and the beginning of **Phase 2 (Basic Auth)**:

### Phase 1 Complete:
1. Feature registry types (Feature, Plan, PLAN_FEATURES)
2. EntitlementsAdapter protocol
3. OpenCoreAdapter implementation
4. Adapter factory with env-based selection
5. API middleware decorators (require_feature, require_under_limit)
6. Frontend entitlements context and hooks

### Phase 2 Started:
7. Auth database schema (organizations, teams, users, memberships)
8. Auth domain types (User, Organization, Team, Token)
9. Password hashing with bcrypt
10. JWT token service

### Remaining Tasks (Phase 2 continued):
- Auth repository (CRUD for users, orgs, teams)
- Login/register endpoints
- JWT auth middleware
- RBAC permission checking
- Frontend auth context

### Future Phases:
- Phase 3: API key migration
- Phase 4: OIDC SSO
- Phase 5: SAML + SCIM
- Phase 6: Stripe billing
