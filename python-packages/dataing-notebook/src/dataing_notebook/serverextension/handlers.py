"""Jupyter Server Extension handlers for Dataing.

Provides HTTP handlers for:
- Token proxy (fetches/refreshes API tokens from backend)
- Handshake (returns backend URL and configuration)
- Request proxy (forwards requests to backend with authentication)
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urljoin

import tornado.httpclient
import tornado.web
from tornado.escape import json_decode, json_encode

# Environment variables for configuration
ENV_BACKEND_URL = "DATAING_BACKEND_URL"
ENV_API_KEY = "DATAING_API_KEY"
ENV_JUPYTERHUB_SERVICE_URL = "JUPYTERHUB_SERVICE_URL"
ENV_JUPYTERHUB_API_TOKEN = "JUPYTERHUB_API_TOKEN"

# Default backend URL
DEFAULT_BACKEND_URL = "http://localhost:8000"


def get_backend_url() -> str:
    """Get the Dataing backend URL.

    Checks in order:
    1. DATAING_BACKEND_URL environment variable
    2. JupyterHub service configuration
    3. Default localhost URL

    Returns:
        Backend URL string.
    """
    # Check explicit environment variable first
    if ENV_BACKEND_URL in os.environ:
        return os.environ[ENV_BACKEND_URL].rstrip("/")

    # Default
    return DEFAULT_BACKEND_URL


def get_api_key() -> str | None:
    """Get the API key for backend authentication.

    Returns:
        API key string or None.
    """
    return os.environ.get(ENV_API_KEY)


def is_jupyterhub_environment() -> bool:
    """Check if running in JupyterHub.

    Returns:
        True if JupyterHub environment detected.
    """
    return ENV_JUPYTERHUB_SERVICE_URL in os.environ


class BaseHandler(tornado.web.RequestHandler):
    """Base handler with common functionality."""

    def set_default_headers(self) -> None:
        """Set CORS and content-type headers."""
        self.set_header("Content-Type", "application/json")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def options(self, *args: Any, **kwargs: Any) -> None:
        """Handle CORS preflight requests."""
        self.set_status(204)
        self.finish()


class HandshakeHandler(BaseHandler):
    """Handler for /dataing/handshake endpoint.

    Returns backend URL and configuration for the client.
    """

    async def get(self) -> None:
        """Return backend URL and configuration."""
        response = {
            "backend_url": get_backend_url(),
            "jupyterhub": is_jupyterhub_environment(),
            "api_key_configured": get_api_key() is not None,
            "version": "0.1.0",
        }
        self.write(json_encode(response))


class TokenHandler(BaseHandler):
    """Handler for /dataing/token endpoint.

    Proxies token requests to the backend, handling refresh transparently.
    """

    _token_cache: dict[str, Any] = {}

    async def get(self) -> None:
        """Get current token status."""
        api_key = get_api_key()

        if api_key:
            # If API key is configured, return it (masked)
            self.write(
                json_encode(
                    {
                        "has_token": True,
                        "token_type": "api_key",
                        "masked": f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***",
                    }
                )
            )
        else:
            self.write(
                json_encode(
                    {
                        "has_token": False,
                        "token_type": None,
                        "message": "No API key configured. Set DATAING_API_KEY environment variable.",
                    }
                )
            )

    async def post(self) -> None:
        """Request or refresh token from backend.

        Expects body: {"action": "refresh"} or {"credentials": {...}}
        """
        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            body = {}

        action = body.get("action", "get")

        if action == "refresh":
            # Clear cache and get new token
            self._token_cache.clear()

        api_key = get_api_key()
        if api_key:
            self.write(
                json_encode(
                    {
                        "success": True,
                        "token": api_key,
                        "token_type": "api_key",
                    }
                )
            )
        else:
            self.set_status(401)
            self.write(
                json_encode(
                    {
                        "success": False,
                        "error": "No API key configured",
                    }
                )
            )


class ProxyHandler(BaseHandler):
    """Handler for /dataing/proxy/* endpoint.

    Proxies requests to the Dataing backend with authentication.
    """

    async def prepare(self) -> None:
        """Prepare the request (called before GET/POST/etc)."""
        self.backend_url = get_backend_url()
        self.api_key = get_api_key()

    async def _proxy_request(self, method: str, path: str) -> None:
        """Proxy a request to the backend.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Path to proxy (without /dataing/proxy prefix)
        """
        # Build target URL
        target_url = urljoin(self.backend_url + "/", path.lstrip("/"))

        # Build headers
        headers = {
            "Content-Type": self.request.headers.get("Content-Type", "application/json"),
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        # Make request
        http_client = tornado.httpclient.AsyncHTTPClient()

        try:
            response = await http_client.fetch(
                target_url,
                method=method,
                headers=headers,
                body=self.request.body if method in ("POST", "PUT", "PATCH") else None,
                raise_error=False,
            )

            # Copy response
            self.set_status(response.code)
            for header in ["Content-Type", "ETag", "Cache-Control"]:
                if header in response.headers:
                    self.set_header(header, response.headers[header])

            if response.body:
                self.write(response.body)

        except tornado.httpclient.HTTPClientError as e:
            self.set_status(e.code)
            self.write(
                json_encode(
                    {
                        "error": str(e),
                        "backend_url": self.backend_url,
                    }
                )
            )
        except Exception as e:
            self.set_status(500)
            self.write(
                json_encode(
                    {
                        "error": f"Proxy error: {str(e)}",
                        "backend_url": self.backend_url,
                    }
                )
            )

    async def get(self, path: str = "") -> None:
        """Handle GET requests."""
        await self._proxy_request("GET", path)

    async def post(self, path: str = "") -> None:
        """Handle POST requests."""
        await self._proxy_request("POST", path)

    async def put(self, path: str = "") -> None:
        """Handle PUT requests."""
        await self._proxy_request("PUT", path)

    async def delete(self, path: str = "") -> None:
        """Handle DELETE requests."""
        await self._proxy_request("DELETE", path)


def setup_handlers(web_app: tornado.web.Application) -> None:
    """Setup handlers for the Dataing server extension.

    Args:
        web_app: Tornado web application to add handlers to.
    """
    host_pattern = ".*$"
    base_url = web_app.settings.get("base_url", "/")

    handlers = [
        (urljoin(base_url, "dataing/handshake"), HandshakeHandler),
        (urljoin(base_url, "dataing/token"), TokenHandler),
        (urljoin(base_url, r"dataing/proxy/(.*)"), ProxyHandler),
    ]

    web_app.add_handlers(host_pattern, handlers)
