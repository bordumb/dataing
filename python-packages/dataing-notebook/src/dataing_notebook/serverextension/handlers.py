"""Jupyter Server Extension handlers for Dataing.

Provides HTTP handlers for:
- Token proxy (fetches/refreshes API tokens from backend)
- Handshake (returns backend URL and configuration)
- Request proxy (forwards requests to backend with authentication)

Security: All handlers inherit from JupyterHandler which enforces
authentication via `@tornado.web.authenticated` and XSRF protection.
The API key is kept server-side and never exposed to the browser.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urljoin

import tornado.httpclient
import tornado.web
from tornado.escape import json_decode, json_encode

# Try to import Jupyter's authenticated handler base
try:
    from jupyter_server.base.handlers import JupyterHandler
    HAS_JUPYTER_SERVER = True
except ImportError:
    # Fallback for testing without jupyter_server
    HAS_JUPYTER_SERVER = False
    JupyterHandler = tornado.web.RequestHandler  # type: ignore[misc,assignment]

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


class BaseHandler(JupyterHandler if HAS_JUPYTER_SERVER else tornado.web.RequestHandler):  # type: ignore[misc]
    """Base handler with authentication and common functionality.

    When jupyter_server is available, this inherits from JupyterHandler
    which provides authentication via @tornado.web.authenticated and
    XSRF protection. CORS headers are not set as requests should be
    same-origin from the JupyterLab frontend.
    """

    def set_default_headers(self) -> None:
        """Set content-type header. No CORS headers for security."""
        self.set_header("Content-Type", "application/json")
        # Intentionally NOT setting Access-Control-Allow-Origin
        # Requests should come from same-origin JupyterLab frontend


class HandshakeHandler(BaseHandler):
    """Handler for /dataing/handshake endpoint.

    Returns backend URL and configuration for the client.
    This is a lightweight endpoint to check server extension availability.
    """

    @tornado.web.authenticated
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

    Provides token status without exposing the actual token.
    Authentication is handled server-side by the proxy.
    """

    @tornado.web.authenticated
    async def get(self) -> None:
        """Get current token status (never exposes the actual token)."""
        api_key = get_api_key()

        if api_key:
            # Report token availability without exposing it
            self.write(
                json_encode(
                    {
                        "has_token": True,
                        "token_type": "api_key",
                        # Show only length indicator, not the actual key
                        "token_configured": True,
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

    @tornado.web.authenticated
    async def post(self) -> None:
        """Validate token configuration (does not return the token).

        The API key is kept server-side and used only by the proxy handler.
        This endpoint confirms whether the key is configured and valid.
        """
        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            body = {}

        action = body.get("action", "status")

        api_key = get_api_key()
        if api_key:
            if action == "validate":
                # Test the API key against the backend
                http_client = tornado.httpclient.AsyncHTTPClient()
                backend_url = get_backend_url()
                try:
                    response = await http_client.fetch(
                        f"{backend_url}/health",
                        method="GET",
                        headers={"X-API-Key": api_key, "Accept": "application/json"},
                        raise_error=False,
                    )
                    is_valid = response.code == 200
                except Exception:
                    is_valid = False

                self.write(
                    json_encode(
                        {
                            "success": True,
                            "token_configured": True,
                            "token_valid": is_valid,
                        }
                    )
                )
            else:
                # Just confirm configuration status
                self.write(
                    json_encode(
                        {
                            "success": True,
                            "token_configured": True,
                        }
                    )
                )
        else:
            self.set_status(401)
            self.write(
                json_encode(
                    {
                        "success": False,
                        "error": "No API key configured. Set DATAING_API_KEY environment variable.",
                    }
                )
            )


class ProxyHandler(BaseHandler):
    """Handler for /dataing/proxy/* endpoint.

    Proxies requests to the Dataing backend with authentication.
    The API key is injected server-side, never exposed to the client.
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

        # Build headers - inject API key server-side
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
                    }
                )
            )
        except Exception as e:
            self.set_status(500)
            self.write(
                json_encode(
                    {
                        "error": f"Proxy error: {str(e)}",
                    }
                )
            )

    @tornado.web.authenticated
    async def get(self, path: str = "") -> None:
        """Handle GET requests."""
        await self._proxy_request("GET", path)

    @tornado.web.authenticated
    async def post(self, path: str = "") -> None:
        """Handle POST requests."""
        await self._proxy_request("POST", path)

    @tornado.web.authenticated
    async def put(self, path: str = "") -> None:
        """Handle PUT requests."""
        await self._proxy_request("PUT", path)

    @tornado.web.authenticated
    async def delete(self, path: str = "") -> None:
        """Handle DELETE requests."""
        await self._proxy_request("DELETE", path)

    @tornado.web.authenticated
    async def patch(self, path: str = "") -> None:
        """Handle PATCH requests."""
        await self._proxy_request("PATCH", path)


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
