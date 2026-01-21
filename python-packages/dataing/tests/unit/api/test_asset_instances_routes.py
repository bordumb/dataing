"""Unit tests for Asset Instances Search API routes."""

import base64
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from dataing.entrypoints.api.app import app


class TestAssetInstancesSearch:
    """Test asset instances search endpoint."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database with asset instance search capability."""
        mock_db = AsyncMock()
        mock_db.get_api_key_by_hash.return_value = {
            "id": uuid4(),
            "tenant_id": uuid4(),
            "user_id": uuid4(),
            "scopes": ["read", "write"],
            "expires_at": None,
            "tenant_slug": "test-tenant",
            "tenant_name": "Test Tenant",
        }
        mock_db.update_api_key_last_used.return_value = None
        return mock_db

    @pytest.fixture
    def client(self, mock_db: AsyncMock) -> TestClient:
        """Create test client with mocked database."""
        app.state.app_db = mock_db
        return TestClient(app)

    def test_search_returns_results(self, client: TestClient, mock_db: AsyncMock) -> None:
        """Test search returns matching asset instances."""
        datasource_id = uuid4()
        dataset_id = uuid4()

        mock_db.search_asset_instances.return_value = (
            [
                {
                    "id": dataset_id,
                    "datasource_id": datasource_id,
                    "native_path": "public.orders",
                    "name": "orders",
                    "table_type": "table",
                    "schema_name": "public",
                    "catalog_name": None,
                    "row_count": 1000,
                    "column_count": 10,
                    "datasource_name": "Production DB",
                    "platform": "postgres",
                    "match_reason": "name_prefix",
                }
            ],
            None,  # no next cursor
            1,  # total hint
        )

        response = client.get(
            "/api/v1/asset-instances/search?q=orders",
            headers={"X-API-Key": "test_key_12345"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["display_name"] == "orders"
        assert data["results"][0]["datasource_id"] == str(datasource_id)
        assert data["results"][0]["platform"] == "postgres"
        assert data["results"][0]["match_reason"] == "name_prefix"
        assert "urn:dataing:postgres:" in data["results"][0]["asset_urn"]
        assert data["next_cursor"] is None
        assert data["total_hint"] == 1

    def test_search_with_pagination_cursor(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Test search respects pagination cursor."""
        datasource_id = uuid4()
        dataset_id = uuid4()
        next_cursor = base64.b64encode(
            f"public.users|{datasource_id}|{dataset_id}".encode()
        ).decode()

        mock_db.search_asset_instances.return_value = (
            [
                {
                    "id": dataset_id,
                    "datasource_id": datasource_id,
                    "native_path": "public.users",
                    "name": "users",
                    "table_type": "table",
                    "schema_name": "public",
                    "catalog_name": None,
                    "row_count": 500,
                    "column_count": 5,
                    "datasource_name": "Production DB",
                    "platform": "postgres",
                    "match_reason": "name_prefix",
                }
            ],
            next_cursor,
            10,
        )

        response = client.get(
            "/api/v1/asset-instances/search?q=u&limit=1",
            headers={"X-API-Key": "test_key_12345"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["next_cursor"] == next_cursor
        assert data["total_hint"] == 10

    def test_search_with_datasource_filter(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Test search can be filtered to a single datasource."""
        datasource_id = uuid4()

        mock_db.search_asset_instances.return_value = ([], None, 0)

        response = client.get(
            f"/api/v1/asset-instances/search?q=orders&datasource_id={datasource_id}",
            headers={"X-API-Key": "test_key_12345"},
        )

        assert response.status_code == 200
        # Verify the datasource_id was passed to the database method
        mock_db.search_asset_instances.assert_called_once()
        call_kwargs = mock_db.search_asset_instances.call_args
        assert call_kwargs.kwargs.get("datasource_id") == datasource_id

    def test_search_requires_query_param(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Test search requires q parameter."""
        response = client.get(
            "/api/v1/asset-instances/search",
            headers={"X-API-Key": "test_key_12345"},
        )

        assert response.status_code == 422  # Validation error

    def test_search_query_min_length(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Test search query must be at least 1 character."""
        response = client.get(
            "/api/v1/asset-instances/search?q=",
            headers={"X-API-Key": "test_key_12345"},
        )

        assert response.status_code == 422

    def test_search_limit_max_100(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Test search limit is capped at 100."""
        mock_db.search_asset_instances.return_value = ([], None, 0)

        response = client.get(
            "/api/v1/asset-instances/search?q=test&limit=200",
            headers={"X-API-Key": "test_key_12345"},
        )

        # FastAPI will reject limit > 100 due to le=100 constraint
        assert response.status_code == 422

    def test_search_returns_cross_datasource_results(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Test search returns results from multiple datasources."""
        ds1_id = uuid4()
        ds2_id = uuid4()

        mock_db.search_asset_instances.return_value = (
            [
                {
                    "id": uuid4(),
                    "datasource_id": ds1_id,
                    "native_path": "public.orders",
                    "name": "orders",
                    "table_type": "table",
                    "schema_name": "public",
                    "catalog_name": None,
                    "row_count": 1000,
                    "column_count": 10,
                    "datasource_name": "Production Postgres",
                    "platform": "postgres",
                    "match_reason": "name_prefix",
                },
                {
                    "id": uuid4(),
                    "datasource_id": ds2_id,
                    "native_path": "analytics.orders",
                    "name": "orders",
                    "table_type": "table",
                    "schema_name": "analytics",
                    "catalog_name": None,
                    "row_count": 5000,
                    "column_count": 15,
                    "datasource_name": "Analytics Snowflake",
                    "platform": "snowflake",
                    "match_reason": "name_prefix",
                },
            ],
            None,
            2,
        )

        response = client.get(
            "/api/v1/asset-instances/search?q=orders",
            headers={"X-API-Key": "test_key_12345"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2

        # Verify results are from different datasources
        datasource_ids = {r["datasource_id"] for r in data["results"]}
        assert len(datasource_ids) == 2
        assert str(ds1_id) in datasource_ids
        assert str(ds2_id) in datasource_ids

        # Verify URNs include platform
        urns = [r["asset_urn"] for r in data["results"]]
        assert any("postgres" in urn for urn in urns)
        assert any("snowflake" in urn for urn in urns)

    def test_search_requires_auth(self, mock_db: AsyncMock) -> None:
        """Test search requires API key authentication."""
        app.state.app_db = mock_db
        client = TestClient(app)

        response = client.get("/api/v1/asset-instances/search?q=orders")

        assert response.status_code == 401
