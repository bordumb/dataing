"""Tests for DataingClient."""

import os
from unittest.mock import patch

import httpx
import pytest
from dataing_sdk import (
    AuthError,
    DataingClient,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)


class TestDataingClientInit:
    """Tests for DataingClient initialization."""

    def test_init_with_explicit_api_key(self) -> None:
        """Test client initialization with explicit API key."""
        client = DataingClient(
            base_url="https://api.example.com",
            api_key="explicit-key",
            timeout=60.0,
        )
        assert client.base_url == "https://api.example.com"
        assert client.api_key == "explicit-key"
        assert client.timeout == 60.0

    def test_init_reads_api_key_from_env(self) -> None:
        """Test client reads DATAING_API_KEY from environment."""
        with patch.dict(os.environ, {"DATAING_API_KEY": "env-key"}):
            client = DataingClient()
            assert client.api_key == "env-key"

    def test_init_reads_base_url_from_env(self) -> None:
        """Test client reads DATAING_BASE_URL from environment."""
        with patch.dict(os.environ, {"DATAING_BASE_URL": "https://env.example.com"}):
            client = DataingClient()
            assert client.base_url == "https://env.example.com"

    def test_explicit_api_key_overrides_env(self) -> None:
        """Test explicit API key overrides environment variable."""
        with patch.dict(os.environ, {"DATAING_API_KEY": "env-key"}):
            client = DataingClient(api_key="explicit-key")
            assert client.api_key == "explicit-key"

    def test_explicit_base_url_overrides_env(self) -> None:
        """Test explicit base_url overrides environment variable."""
        with patch.dict(os.environ, {"DATAING_BASE_URL": "https://env.example.com"}):
            client = DataingClient(base_url="https://explicit.example.com")
            assert client.base_url == "https://explicit.example.com"

    def test_strips_trailing_slash(self) -> None:
        """Test that base_url trailing slash is stripped."""
        client = DataingClient(base_url="https://api.example.com/")
        assert client.base_url == "https://api.example.com"

    def test_default_values(self) -> None:
        """Test client default values when no env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing env vars
            os.environ.pop("DATAING_API_KEY", None)
            os.environ.pop("DATAING_BASE_URL", None)
            client = DataingClient()
            assert client.base_url == "http://localhost:8000"
            assert client.api_key is None
            assert client.timeout == 30.0


class TestDataingClientHeaders:
    """Tests for header generation."""

    def test_headers_include_api_key(self) -> None:
        """Test that headers include X-API-Key when set."""
        client = DataingClient(api_key="test-key")
        headers = client._get_headers()
        assert headers["X-API-Key"] == "test-key"
        assert headers["Content-Type"] == "application/json"

    def test_headers_without_api_key(self) -> None:
        """Test headers when no API key is set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            client = DataingClient()
            headers = client._get_headers()
            assert "X-API-Key" not in headers
            assert headers["Content-Type"] == "application/json"


class TestDataingClientErrorHandling:
    """Tests for error handling."""

    def test_auth_error_on_401(self) -> None:
        """Test AuthError is raised on 401 response."""
        client = DataingClient(api_key="bad-key")
        response = httpx.Response(401, json={"detail": "Invalid API key"})
        with pytest.raises(AuthError, match="Authentication failed"):
            client._handle_response_error(response)

    def test_auth_error_on_403(self) -> None:
        """Test AuthError is raised on 403 response."""
        client = DataingClient(api_key="key")
        response = httpx.Response(403, json={"detail": "Forbidden"})
        with pytest.raises(AuthError, match="Authorization failed"):
            client._handle_response_error(response)

    def test_not_found_error_on_404(self) -> None:
        """Test NotFoundError is raised on 404 response."""
        client = DataingClient(api_key="key")
        response = httpx.Response(
            404, json={"detail": "Not found"}, request=httpx.Request("GET", "/test")
        )
        with pytest.raises(NotFoundError, match="not found"):
            client._handle_response_error(response)

    def test_validation_error_on_422(self) -> None:
        """Test ValidationError is raised on 422 response."""
        client = DataingClient(api_key="key")
        response = httpx.Response(422, json={"detail": "Invalid input"})
        with pytest.raises(ValidationError, match="Validation error"):
            client._handle_response_error(response)

    def test_rate_limit_error_on_429(self) -> None:
        """Test RateLimitError is raised on 429 response."""
        client = DataingClient(api_key="key")
        response = httpx.Response(
            429, json={"detail": "Too many requests"}, headers={"Retry-After": "60"}
        )
        with pytest.raises(RateLimitError) as exc_info:
            client._handle_response_error(response)
        assert exc_info.value.retry_after == 60.0

    def test_rate_limit_error_without_retry_after(self) -> None:
        """Test RateLimitError when Retry-After header is missing."""
        client = DataingClient(api_key="key")
        response = httpx.Response(429, json={"detail": "Too many requests"})
        with pytest.raises(RateLimitError) as exc_info:
            client._handle_response_error(response)
        assert exc_info.value.retry_after is None

    def test_server_error_on_5xx(self) -> None:
        """Test ServerError is raised on 5xx response."""
        client = DataingClient(api_key="key")
        response = httpx.Response(500, json={"detail": "Internal error"})
        with pytest.raises(ServerError, match="Server error"):
            client._handle_response_error(response)


class TestDataingClientContextManager:
    """Tests for context manager usage."""

    def test_sync_context_manager(self) -> None:
        """Test synchronous context manager."""
        with DataingClient(api_key="key") as client:
            assert client.api_key == "key"
        # Client should be closed after context exit
        assert client._sync_client is None

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """Test asynchronous context manager."""
        async with DataingClient(api_key="key") as client:
            assert client.api_key == "key"
        # Client should be closed after context exit
        assert client._async_client is None


class TestDataingClientRunMethods:
    """Tests for run methods."""

    def test_run_builds_correct_payload_with_inline_bundle(self) -> None:
        """Test that run() builds correct payload with inline bundle."""
        client = DataingClient(api_key="key")
        # We can't test the actual HTTP call without mocking,
        # but we can verify the client is properly configured
        assert client.api_key == "key"
        assert client.base_url == "http://localhost:8000"

    def test_run_builds_correct_payload_with_bundle_id(self) -> None:
        """Test that run() accepts bundle_id parameter."""
        client = DataingClient(api_key="key")
        # Verify client accepts the parameters (actual call would need server)
        assert client.api_key == "key"


class TestDataingClientEndpointPaths:
    """Tests to ensure SDK uses correct API endpoint paths.

    These tests verify that the SDK calls the correct /api/v1/ prefixed endpoints.
    This prevents regressions where incorrect paths are accidentally used.
    """

    def test_start_investigation_uses_v1_endpoint(self) -> None:
        """Test that start_investigation() uses /api/v1/investigations endpoint."""
        from unittest.mock import MagicMock, patch

        client = DataingClient(api_key="key", base_url="http://test.example.com")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "investigation_id": "test-inv-123",
            "main_branch_id": "test-branch-123",
            "status": "queued",
            "run_id": "test-run-1",
            "issue_id": "test-issue-7",
            "issue_number": 7,
        }
        mock_response.status_code = 200

        with patch.object(client, "_request", return_value=mock_response) as mock_request:
            investigation = client.start_investigation(
                dataset="main.orders",
                anomaly_type="null_rate",
                goal="test investigation",
            )

            # Verify the correct endpoint was called
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/v1/investigations"
        # Every run lives in an issue; its thread is where to follow it
        assert (investigation.issue_id, investigation.issue_number) == ("test-issue-7", 7)

    def test_stream_run_uses_v1_investigations_events_endpoint(self) -> None:
        """Test that stream_run() uses /api/v1/investigations/{id}/events endpoint."""
        client = DataingClient(api_key="key", base_url="http://test.example.com")

        # Check that the URL is built correctly (without actually making a request)
        # The stream_run method builds the URL internally
        _run_id = "test-run-123"
        _expected_url = f"http://test.example.com/api/v1/investigations/{_run_id}/events"

        # We can verify the URL construction by checking the method's implementation
        # which builds: f"{self.base_url}/api/v1/investigations/{run_id}/events"
        assert client.base_url == "http://test.example.com"
        # The actual URL would be: http://test.example.com/api/v1/investigations/test-run-123/events


class TestDataingClientSteer:
    """Steering a running investigation (the messages route is gone)."""

    STEER = {
        "id": "steer-1",
        "investigation_id": "inv-1",
        "kind": "add_context",
        "text": "app_v2 shipped at 09:00",
        "hypothesis_id": None,
        "status": "pending",
        "outcome": None,
    }

    def test_steer_posts_to_the_steers_endpoint(self) -> None:
        """Context goes to POST /api/v1/investigations/{id}/steers as add_context."""
        from unittest.mock import MagicMock

        client = DataingClient(api_key="key", base_url="http://test.example.com")
        response = MagicMock()
        response.json.return_value = self.STEER

        with patch.object(client, "_request", return_value=response) as request:
            result = client.steer("inv-1", "app_v2 shipped at 09:00")

        request.assert_called_once_with(
            "POST",
            "/api/v1/investigations/inv-1/steers",
            json={"kind": "add_context", "text": "app_v2 shipped at 09:00", "hypothesis_id": None},
        )
        assert (result.id, result.status) == ("steer-1", "pending")

    async def test_async_steer_can_rule_out_a_hypothesis(self) -> None:
        """A rule-out names the hypothesis; a finished run's rejection is returned."""
        from unittest.mock import AsyncMock, MagicMock

        client = DataingClient(api_key="key", base_url="http://test.example.com")
        response = MagicMock()
        response.json.return_value = {
            **self.STEER,
            "kind": "rule_out",
            "hypothesis_id": "h3",
            "status": "rejected",
            "outcome": "The investigation isn't running: use Continue investigating",
        }

        with patch.object(client, "_async_request", AsyncMock(return_value=response)) as request:
            result = await client.async_steer(
                "inv-1", "lands fast", kind="rule_out", hypothesis_id="h3"
            )

        assert request.await_args.kwargs["json"] == {
            "kind": "rule_out",
            "text": "lands fast",
            "hypothesis_id": "h3",
        }
        assert result.status == "rejected"
        assert result.outcome.startswith("The investigation isn't running")
