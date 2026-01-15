"""Tests for correlation ID middleware."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dataing.telemetry.correlation import CorrelationMiddleware


def homepage(request: Request) -> PlainTextResponse:
    """Test endpoint that returns the correlation ID from request state."""
    correlation_id = getattr(request.state, "correlation_id", "not-set")
    return PlainTextResponse(f"correlation_id={correlation_id}")


@pytest.fixture
def app() -> Starlette:
    """Create test Starlette app with correlation middleware."""
    app = Starlette(
        routes=[Route("/", homepage)],
    )
    app.add_middleware(CorrelationMiddleware)
    return app


@pytest.fixture
def client(app: Starlette) -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_generates_correlation_id_when_not_provided(client: TestClient) -> None:
    """Correlation ID is generated when not in request headers."""
    response = client.get("/")

    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers

    # Verify it's a valid UUID
    correlation_id = response.headers["X-Correlation-ID"]
    uuid.UUID(correlation_id)  # Raises if invalid

    # Verify same ID in response body (from request.state)
    assert f"correlation_id={correlation_id}" in response.text


def test_uses_provided_x_correlation_id(client: TestClient) -> None:
    """X-Correlation-ID header is used when provided."""
    provided_id = "test-correlation-123"
    response = client.get("/", headers={"X-Correlation-ID": provided_id})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == provided_id
    assert f"correlation_id={provided_id}" in response.text


def test_uses_provided_x_request_id(client: TestClient) -> None:
    """X-Request-ID header is used as fallback when X-Correlation-ID not provided."""
    provided_id = "request-id-456"
    response = client.get("/", headers={"X-Request-ID": provided_id})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == provided_id
    assert f"correlation_id={provided_id}" in response.text


def test_x_correlation_id_takes_precedence_over_x_request_id(
    client: TestClient,
) -> None:
    """X-Correlation-ID takes precedence when both headers provided."""
    correlation_id = "correlation-789"
    request_id = "request-000"

    response = client.get(
        "/",
        headers={
            "X-Correlation-ID": correlation_id,
            "X-Request-ID": request_id,
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert f"correlation_id={correlation_id}" in response.text


def test_sets_span_attribute_when_span_active() -> None:
    """Correlation ID is set as span attribute when a span is recording."""
    mock_span = MagicMock()
    mock_span.is_recording.return_value = True

    with patch("dataing.telemetry.correlation.trace.get_current_span") as mock_get_span:
        mock_get_span.return_value = mock_span

        app = Starlette(
            routes=[Route("/", homepage)],
        )
        app.add_middleware(CorrelationMiddleware)
        client = TestClient(app)

        correlation_id = "span-test-id"
        response = client.get("/", headers={"X-Correlation-ID": correlation_id})

        assert response.status_code == 200
        mock_span.set_attribute.assert_called_once_with("correlation_id", correlation_id)


def test_skips_span_attribute_when_no_span() -> None:
    """No error when no active span."""
    with patch("dataing.telemetry.correlation.trace.get_current_span") as mock_get_span:
        mock_get_span.return_value = None

        app = Starlette(
            routes=[Route("/", homepage)],
        )
        app.add_middleware(CorrelationMiddleware)
        client = TestClient(app)

        response = client.get("/")

        # Should complete without error
        assert response.status_code == 200


def test_skips_span_attribute_when_span_not_recording() -> None:
    """No error when span exists but is not recording."""
    mock_span = MagicMock()
    mock_span.is_recording.return_value = False

    with patch("dataing.telemetry.correlation.trace.get_current_span") as mock_get_span:
        mock_get_span.return_value = mock_span

        app = Starlette(
            routes=[Route("/", homepage)],
        )
        app.add_middleware(CorrelationMiddleware)
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200
        mock_span.set_attribute.assert_not_called()
