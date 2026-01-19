"""Unit tests for TenantService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from dataing.services.tenant import TenantInfo, TenantService


class TestTenantService:
    """Tests for TenantService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database."""
        mock = AsyncMock()
        mock.create_tenant.return_value = {
            "id": uuid.uuid4(),
            "name": "Test Tenant",
            "slug": "test-tenant",
            "settings": {},
        }
        mock.get_tenant_by_slug.return_value = None
        mock.get_tenant.return_value = None
        return mock

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> TenantService:
        """Return a tenant service."""
        return TenantService(db=mock_db)

    async def test_create_tenant(
        self,
        service: TenantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test creating a tenant."""
        result = await service.create_tenant(name="Test Tenant")

        assert isinstance(result, TenantInfo)
        assert result.name == "Test Tenant"
        assert result.slug == "test-tenant"
        mock_db.create_tenant.assert_called_once()

    async def test_create_tenant_custom_slug(
        self,
        service: TenantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test creating tenant with custom slug."""
        mock_db.create_tenant.return_value = {
            "id": uuid.uuid4(),
            "name": "Test",
            "slug": "custom-slug",
            "settings": {},
        }

        result = await service.create_tenant(
            name="Test",
            slug="custom-slug",
        )

        assert result.slug == "custom-slug"

    async def test_create_tenant_unique_slug(
        self,
        service: TenantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test that duplicate slugs get a counter appended."""
        # First call returns existing tenant, second returns None
        mock_db.get_tenant_by_slug.side_effect = [
            {"id": uuid.uuid4(), "slug": "test-tenant"},  # Exists
            None,  # test-tenant-1 doesn't exist
        ]
        mock_db.create_tenant.return_value = {
            "id": uuid.uuid4(),
            "name": "Test Tenant",
            "slug": "test-tenant-1",
            "settings": {},
        }

        result = await service.create_tenant(name="Test Tenant")

        assert result.slug == "test-tenant-1"

    async def test_get_tenant(
        self,
        service: TenantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test getting a tenant by ID."""
        tenant_id = uuid.uuid4()
        mock_db.get_tenant.return_value = {
            "id": tenant_id,
            "name": "Test",
            "slug": "test",
            "settings": {},
        }

        result = await service.get_tenant(tenant_id)

        assert result is not None
        assert result.id == tenant_id

    async def test_get_tenant_not_found(
        self,
        service: TenantService,
    ) -> None:
        """Test getting non-existent tenant."""
        result = await service.get_tenant(uuid.uuid4())

        assert result is None

    async def test_get_tenant_by_slug(
        self,
        service: TenantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test getting a tenant by slug."""
        mock_db.get_tenant_by_slug.return_value = {
            "id": uuid.uuid4(),
            "name": "Test",
            "slug": "test-slug",
            "settings": {},
        }

        result = await service.get_tenant_by_slug("test-slug")

        assert result is not None
        assert result.slug == "test-slug"

    async def test_get_tenant_by_slug_not_found(
        self,
        service: TenantService,
    ) -> None:
        """Test getting tenant by non-existent slug."""
        result = await service.get_tenant_by_slug("nonexistent")

        assert result is None

    async def test_update_tenant_settings(
        self,
        service: TenantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test updating tenant settings."""
        tenant_id = uuid.uuid4()
        mock_db.execute_returning.return_value = {
            "id": tenant_id,
            "name": "Test",
            "slug": "test",
            "settings": {"feature_enabled": True},
        }

        result = await service.update_tenant_settings(
            tenant_id,
            {"feature_enabled": True},
        )

        assert result is not None
        assert result.settings["feature_enabled"] is True

    async def test_update_tenant_settings_not_found(
        self,
        service: TenantService,
        mock_db: AsyncMock,
    ) -> None:
        """Test updating non-existent tenant."""
        mock_db.execute_returning.return_value = None

        result = await service.update_tenant_settings(
            uuid.uuid4(),
            {"setting": "value"},
        )

        assert result is None

    def test_generate_slug(self, service: TenantService) -> None:
        """Test slug generation."""
        assert service._generate_slug("Test Tenant") == "test-tenant"
        assert service._generate_slug("  Spaces  ") == "spaces"
        assert service._generate_slug("Special!@#Chars") == "special-chars"
        assert service._generate_slug("UPPERCASE") == "uppercase"

    def test_generate_slug_truncates(self, service: TenantService) -> None:
        """Test that slug is truncated to 50 chars."""
        long_name = "A" * 100
        slug = service._generate_slug(long_name)

        assert len(slug) <= 50


class TestTenantInfo:
    """Tests for TenantInfo."""

    def test_create_tenant_info(self) -> None:
        """Test creating tenant info."""
        info = TenantInfo(
            id=uuid.uuid4(),
            name="Test Tenant",
            slug="test-tenant",
            settings={"key": "value"},
        )

        assert info.name == "Test Tenant"
        assert info.slug == "test-tenant"
        assert info.settings["key"] == "value"
