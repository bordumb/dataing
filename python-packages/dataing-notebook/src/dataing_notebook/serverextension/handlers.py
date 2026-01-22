"""Jupyter Server Extension handlers for Dataing.

Provides HTTP handlers for:
- Token proxy (fetches/refreshes API tokens from backend)
- Handshake (returns backend URL and configuration)
- Request proxy (forwards requests to backend with authentication)

Security: All handlers inherit from APIHandler (jupyter-server 2.0+)
which provides authentication via `current_user` property and XSRF protection.
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
# In jupyter-server 2.0+, use APIHandler instead of JupyterHandler
# for proper authentication handling (get_current_user is deprecated)
try:
    from jupyter_server.base.handlers import APIHandler as JupyterHandler

    HAS_JUPYTER_SERVER = True
except ImportError:
    # Fallback for testing without jupyter_server
    HAS_JUPYTER_SERVER = False
    JupyterHandler = tornado.web.RequestHandler  # type: ignore[misc,assignment]

# Environment variables for configuration
ENV_BACKEND_URL = "DATAING_BACKEND_URL"
ENV_API_KEY = "DATAING_API_KEY"  # pragma: allowlist secret
ENV_JUPYTERHUB_SERVICE_URL = "JUPYTERHUB_SERVICE_URL"
ENV_JUPYTERHUB_API_TOKEN = "JUPYTERHUB_API_TOKEN"

# Default backend URL
DEFAULT_BACKEND_URL = "http://localhost:8000"


def get_backend_url() -> str:
    """Get the Dataing backend URL.

    Checks in order:
    1. DATAING_BACKEND_URL environment variable
    2. Default localhost URL

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

    Uses the credential module's precedence order:
    1. Session-only memory store
    2. OS keyring
    3. Environment variable

    Returns:
        API key string or None.
    """
    from dataing_notebook.serverextension.credentials import get_credential

    return get_credential()


def is_jupyterhub_environment() -> bool:
    """Check if running in JupyterHub.

    Returns:
        True if JupyterHub environment detected.
    """
    return ENV_JUPYTERHUB_SERVICE_URL in os.environ


class BaseHandler(JupyterHandler if HAS_JUPYTER_SERVER else tornado.web.RequestHandler):  # type: ignore[misc]
    """Base handler with authentication and common functionality.

    When jupyter_server is available, this inherits from APIHandler
    which provides authentication and XSRF protection. CORS headers
    are not set as requests should be same-origin from JupyterLab.

    Note: In jupyter-server 2.0+, we use APIHandler instead of JupyterHandler.
    Authentication is handled automatically by the APIHandler - we do NOT
    manually check current_user as that triggers deprecated get_current_user().
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
                        "message": "No API key configured. Set DATAING_API_KEY env var.",
                    }
                )
            )

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


class CredentialHandler(BaseHandler):
    """Handler for /dataing/credentials endpoint.

    Manages credential storage with three modes:
    - keychain: Stored in OS keychain via keyring library
    - env_var: Read from DATAING_API_KEY environment variable
    - session: Stored in memory only (cleared on server restart)

    Security:
    - Actual credential values are NEVER returned
    - XSRF protection is ENABLED (unlike StateHandler)
    """

    async def get(self) -> None:
        """Get current credential status (never returns actual key).

        Returns:
            {mode: "keychain"|"env_var"|"session", stored: bool, explanation: str}
        """
        from dataing_notebook.serverextension.credentials import get_credential_status

        status = get_credential_status()
        self.write(
            json_encode(
                {
                    "mode": status.mode.value,
                    "stored": status.stored,
                    "explanation": status.explanation,
                }
            )
        )

    async def post(self) -> None:
        """Store a credential.

        Request body:
            {api_key: "...", persist: bool}

        persist=true: Use keychain if available, else session
        persist=false: Force session-only storage
        """
        from dataing_notebook.serverextension.credentials import store_credential

        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            self.set_status(400)
            self.write(json_encode({"error": "Invalid JSON"}))
            return

        api_key = body.get("api_key")
        if not api_key:
            self.set_status(400)
            self.write(json_encode({"error": "api_key is required"}))
            return

        persist = body.get("persist", True)

        status = store_credential(api_key, persist=persist)
        self.write(
            json_encode(
                {
                    "success": True,
                    "mode": status.mode.value,
                    "stored": status.stored,
                    "explanation": status.explanation,
                }
            )
        )

    async def delete(self) -> None:
        """Clear stored credentials (both keychain and session).

        Returns:
            Updated credential status.
        """
        from dataing_notebook.serverextension.credentials import delete_credential

        status = delete_credential()
        self.write(
            json_encode(
                {
                    "success": True,
                    "mode": status.mode.value,
                    "stored": status.stored,
                    "explanation": status.explanation,
                }
            )
        )


class ConnectionTestHandler(BaseHandler):
    """Handler for /dataing/connection/test endpoint.

    Tests connection to a Dataing backend before saving credentials.
    This allows the wizard to validate URL and API key before committing.
    """

    async def post(self) -> None:
        """Test connection to a backend.

        Request body:
            {base_url: "https://...", api_key: "..."}

        Returns:
            {success: true} on success
            {success: false, error: "message"} on failure
        """
        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            self.set_status(400)
            self.write(json_encode({"success": False, "error": "Invalid JSON"}))
            return

        base_url = body.get("base_url")
        api_key = body.get("api_key")

        if not base_url:
            self.set_status(400)
            self.write(json_encode({"success": False, "error": "base_url is required"}))
            return

        if not api_key:
            self.set_status(400)
            self.write(json_encode({"success": False, "error": "api_key is required"}))
            return

        # Normalize URL
        base_url = base_url.rstrip("/")

        # Test connection by calling /health endpoint
        http_client = tornado.httpclient.AsyncHTTPClient()
        try:
            response = await http_client.fetch(
                f"{base_url}/health",
                method="GET",
                headers={
                    "X-API-Key": api_key,
                    "Accept": "application/json",
                },
                raise_error=False,
                request_timeout=10,  # 10 second timeout
            )

            if response.code == 200:
                self.write(json_encode({"success": True}))
            elif response.code == 401:
                self.write(json_encode({"success": False, "error": "Invalid API key"}))
            elif response.code == 403:
                self.write(json_encode({"success": False, "error": "API key not authorized"}))
            elif response.code == 404:
                self.write(
                    json_encode({"success": False, "error": "Backend not found at this URL"})
                )
            else:
                self.write(
                    json_encode(
                        {
                            "success": False,
                            "error": f"Backend returned error: {response.code}",
                        }
                    )
                )

        except tornado.httpclient.HTTPClientError as e:
            # Connection errors
            error_msg = self._get_friendly_error(str(e))
            self.write(json_encode({"success": False, "error": error_msg}))
        except Exception as e:
            # Other errors
            error_msg = self._get_friendly_error(str(e))
            self.write(json_encode({"success": False, "error": error_msg}))

    def _get_friendly_error(self, error: str) -> str:
        """Convert technical errors to user-friendly messages."""
        error_lower = error.lower()

        if "connection refused" in error_lower:
            return "Cannot connect to backend. Is the server running?"
        if "name or service not known" in error_lower or "nodename nor servname" in error_lower:
            return "Cannot resolve backend hostname. Check the URL."
        if "timed out" in error_lower or "timeout" in error_lower:
            return "Connection timed out. Backend may be unreachable."
        if "ssl" in error_lower or "certificate" in error_lower:
            return "SSL/TLS error. Check if HTTPS is configured correctly."

        # Generic fallback - avoid exposing raw errors
        return f"Connection failed: {error[:100]}"


class SSEProxyHandler(BaseHandler):
    """Handler for /dataing/sse/* endpoint.

    Proxies Server-Sent Events (SSE) streams from the Dataing backend.
    This handler streams events from the backend to the client in real-time,
    solving CORS issues when the backend and JupyterLab are on different origins.
    """

    def set_default_headers(self) -> None:
        """Set headers for SSE streaming."""
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")

    async def get(self, path: str = "") -> None:
        """Stream SSE events from backend."""
        backend_url = get_backend_url()
        api_key = get_api_key()

        # Build target URL
        target_url = urljoin(backend_url + "/", path.lstrip("/"))
        if self.request.query:
            target_url = f"{target_url}?{self.request.query}"

        # Build headers
        headers = {
            "Accept": "text/event-stream",
        }
        if api_key:
            headers["X-API-Key"] = api_key

        http_client = tornado.httpclient.AsyncHTTPClient()

        # Use streaming callback to forward events
        try:

            def handle_chunk(chunk: bytes) -> None:
                """Forward chunks to client."""
                try:
                    self.write(chunk)
                    self.flush()
                except Exception:
                    pass  # Connection may be closed

            await http_client.fetch(
                target_url,
                method="GET",
                headers=headers,
                streaming_callback=handle_chunk,
                request_timeout=0,  # No timeout for SSE
                raise_error=False,
            )
        except tornado.httpclient.HTTPClientError as e:
            self.set_status(e.code)
            self.write(f"event: error\ndata: {str(e)}\n\n")
        except Exception as e:
            self.set_status(500)
            self.write(f"event: error\ndata: Proxy error: {str(e)}\n\n")


class ProxyHandler(BaseHandler):
    """Handler for /dataing/proxy/* endpoint.

    Proxies requests to the Dataing backend with authentication.
    The API key is injected server-side, never exposed to the client.
    """

    def prepare(self) -> None:
        """Prepare the request (called before GET/POST/etc)."""
        self.backend_url = get_backend_url()
        self.api_key = get_api_key()

    async def _proxy_request(self, method: str, path: str) -> None:
        """Proxy a request to the backend.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Path to proxy (without /dataing/proxy prefix)
        """
        # Build target URL, preserving query string
        target_url = urljoin(self.backend_url + "/", path.lstrip("/"))
        if self.request.query:
            target_url = f"{target_url}?{self.request.query}"

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

    async def patch(self, path: str = "") -> None:
        """Handle PATCH requests."""
        await self._proxy_request("PATCH", path)


# In-memory state storage for notebook state sync
_notebook_state: dict[str, Any] = {
    "attached_datasource": None,
    "bundle_id": None,
    "bundle_hash": None,
    "current_run_id": None,
}


class StateHandler(BaseHandler):
    """Handler for /dataing/state endpoint.

    Stores and retrieves notebook state for frontend sync.
    This allows the notebook magic to communicate state changes
    to the JupyterLab sidebar without using comms.

    Note: XSRF is disabled for this endpoint because the kernel
    sends POST requests without XSRF tokens. This is safe because:
    - The state is local to this Jupyter session only
    - No sensitive operations or external calls are made
    """

    def check_xsrf_cookie(self) -> None:
        """Skip XSRF check for kernel-to-extension communication."""
        pass

    async def get(self) -> None:
        """Get current notebook state."""
        self.write(json_encode(_notebook_state))

    async def post(self) -> None:
        """Update notebook state."""
        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            body = {}

        # Update state with provided values
        if "attached_datasource" in body:
            _notebook_state["attached_datasource"] = body["attached_datasource"]
        if "bundle_id" in body:
            _notebook_state["bundle_id"] = body["bundle_id"]
        if "bundle_hash" in body:
            _notebook_state["bundle_hash"] = body["bundle_hash"]
        if "current_run_id" in body:
            _notebook_state["current_run_id"] = body["current_run_id"]

        self.write(json_encode({"success": True, "state": _notebook_state}))

    async def delete(self) -> None:
        """Clear notebook state."""
        _notebook_state["attached_datasource"] = None
        _notebook_state["bundle_id"] = None
        _notebook_state["bundle_hash"] = None
        _notebook_state["current_run_id"] = None
        self.write(json_encode({"success": True}))


class CommandConnectHandler(BaseHandler):
    """Handler for /dataing/command/connect endpoint.

    Implements versioned connect command for the state machine.
    """

    async def post(self) -> None:
        """Execute connect command."""
        from dataing_notebook.serverextension.state import (
            StaleVersionError,
            StateTransitionError,
            get_workspace_manager,
        )

        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            self.set_status(400)
            self.write(json_encode({"error": "Invalid JSON"}))
            return

        workspace_id = body.get("workspace_id")
        kernel_id = body.get("kernel_id")
        base_url = body.get("base_url")
        expected_version = body.get("expected_version")
        credential_mode = body.get("credential_mode", "none")

        if not workspace_id or not kernel_id:
            self.set_status(400)
            self.write(json_encode({"error": "workspace_id and kernel_id required"}))
            return

        if not base_url:
            base_url = get_backend_url()

        manager = get_workspace_manager()

        try:
            state = manager.connect(
                workspace_id=workspace_id,
                kernel_id=kernel_id,
                base_url=base_url,
                credential_mode=credential_mode,
                expected_version=expected_version,
            )
            self.write(json_encode(state.to_dict()))

        except StaleVersionError as e:
            self.set_status(409)
            self.write(
                json_encode(
                    {
                        "error": "stale_state",
                        "current_state": e.current_state,
                        "current_version": e.current,
                    }
                )
            )
        except StateTransitionError as e:
            self.set_status(400)
            self.write(
                json_encode(
                    {
                        "error": "invalid_state",
                        "current_state": e.current_state.value,
                        "allowed": e.allowed_commands,
                    }
                )
            )


class CommandAttachHandler(BaseHandler):
    """Handler for /dataing/command/attach endpoint."""

    async def post(self) -> None:
        """Execute attach command."""
        from dataing_notebook.serverextension.state import (
            StaleVersionError,
            StateTransitionError,
            get_workspace_manager,
        )

        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            self.set_status(400)
            self.write(json_encode({"error": "Invalid JSON"}))
            return

        workspace_id = body.get("workspace_id")
        kernel_id = body.get("kernel_id")
        asset_urn = body.get("asset_urn")
        datasource_id = body.get("datasource_id")
        datasource_name = body.get("datasource_name")
        expected_version = body.get("expected_version")

        if not workspace_id or not kernel_id:
            self.set_status(400)
            self.write(json_encode({"error": "workspace_id and kernel_id required"}))
            return

        if not asset_urn:
            self.set_status(400)
            self.write(json_encode({"error": "asset_urn is required"}))
            return

        manager = get_workspace_manager()

        try:
            state = manager.attach(
                workspace_id=workspace_id,
                kernel_id=kernel_id,
                asset_urn=asset_urn,
                datasource_id=datasource_id,
                datasource_name=datasource_name,
                expected_version=expected_version,
            )
            self.write(json_encode(state.to_dict()))

        except StaleVersionError as e:
            self.set_status(409)
            self.write(
                json_encode(
                    {
                        "error": "stale_state",
                        "current_state": e.current_state,
                        "current_version": e.current,
                    }
                )
            )
        except StateTransitionError as e:
            self.set_status(400)
            self.write(
                json_encode(
                    {
                        "error": "invalid_state",
                        "current_state": e.current_state.value,
                        "allowed": e.allowed_commands,
                    }
                )
            )


class CommandStartRunHandler(BaseHandler):
    """Handler for /dataing/command/start_run endpoint.

    Implements idempotent run creation with client_request_id.
    """

    async def post(self) -> None:
        """Execute start_run command."""
        from dataing_notebook.serverextension.state import (
            StaleVersionError,
            StateTransitionError,
            get_workspace_manager,
        )

        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            self.set_status(400)
            self.write(json_encode({"error": "Invalid JSON"}))
            return

        workspace_id = body.get("workspace_id")
        kernel_id = body.get("kernel_id")
        question = body.get("question")
        client_request_id = body.get("client_request_id")
        expected_version = body.get("expected_version")

        if not workspace_id or not kernel_id:
            self.set_status(400)
            self.write(json_encode({"error": "workspace_id and kernel_id required"}))
            return

        if not question:
            self.set_status(400)
            self.write(json_encode({"error": "question is required"}))
            return

        if not client_request_id:
            self.set_status(400)
            self.write(json_encode({"error": "client_request_id is required"}))
            return

        manager = get_workspace_manager()

        try:
            state, run_id, is_new = manager.start_run(
                workspace_id=workspace_id,
                kernel_id=kernel_id,
                question=question,
                client_request_id=client_request_id,
                expected_version=expected_version,
            )
            response = state.to_dict()
            response["run_id"] = run_id
            response["is_new"] = is_new
            self.write(json_encode(response))

        except StaleVersionError as e:
            self.set_status(409)
            self.write(
                json_encode(
                    {
                        "error": "stale_state",
                        "current_state": e.current_state,
                        "current_version": e.current,
                    }
                )
            )
        except StateTransitionError as e:
            self.set_status(400)
            self.write(
                json_encode(
                    {
                        "error": "invalid_state",
                        "current_state": e.current_state.value,
                        "allowed": e.allowed_commands,
                    }
                )
            )


class CommandClearHandler(BaseHandler):
    """Handler for /dataing/command/clear endpoint."""

    async def post(self) -> None:
        """Execute clear command."""
        from dataing_notebook.serverextension.state import (
            StaleVersionError,
            StateTransitionError,
            get_workspace_manager,
        )

        try:
            body = json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            self.set_status(400)
            self.write(json_encode({"error": "Invalid JSON"}))
            return

        workspace_id = body.get("workspace_id")
        kernel_id = body.get("kernel_id")
        expected_version = body.get("expected_version")

        if not workspace_id or not kernel_id:
            self.set_status(400)
            self.write(json_encode({"error": "workspace_id and kernel_id required"}))
            return

        manager = get_workspace_manager()

        try:
            state = manager.clear(
                workspace_id=workspace_id,
                kernel_id=kernel_id,
                expected_version=expected_version,
            )
            self.write(json_encode(state.to_dict()))

        except StaleVersionError as e:
            self.set_status(409)
            self.write(
                json_encode(
                    {
                        "error": "stale_state",
                        "current_state": e.current_state,
                        "current_version": e.current,
                    }
                )
            )
        except StateTransitionError as e:
            self.set_status(400)
            self.write(
                json_encode(
                    {
                        "error": "invalid_state",
                        "current_state": e.current_state.value,
                        "allowed": e.allowed_commands,
                    }
                )
            )


class WorkspaceStateHandler(BaseHandler):
    """Handler for /dataing/workspace/state endpoint.

    Gets current workspace state by workspace_id and kernel_id.
    """

    async def get(self) -> None:
        """Get current workspace state."""
        from dataing_notebook.serverextension.state import get_workspace_manager

        workspace_id = self.get_query_argument("workspace_id", None)
        kernel_id = self.get_query_argument("kernel_id", None)

        if not workspace_id or not kernel_id:
            self.set_status(400)
            self.write(json_encode({"error": "workspace_id and kernel_id required"}))
            return

        manager = get_workspace_manager()
        state = manager.get_state(workspace_id, kernel_id)
        self.write(json_encode(state.to_dict()))


class SnippetHandler(BaseHandler):
    """Handler for /dataing/snippet endpoint.

    Returns reproducible magic command snippets for the current GUI state.
    Used by the sidebar "Copy snippet" button.
    """

    async def get(self) -> None:
        """Generate magic commands for current state.

        Returns:
            {
                snippet: "# Magic commands...",
                description: "Human-readable summary"
            }
        """
        from dataing_notebook.serverextension.credentials import (
            get_credential_status,
        )

        backend_url = get_backend_url()
        cred_status = get_credential_status()
        attached = _notebook_state.get("attached_datasource")

        # Build snippet
        lines = []
        lines.append("# Dataing notebook setup")
        lines.append("")

        # Connect command
        lines.append(f"%dataing connect --base-url {backend_url}")

        # Auth comment based on mode
        mode = cred_status.mode.value
        if mode == "env_var":
            lines.append("# API key: using DATAING_API_KEY environment variable")
        elif mode == "keychain":
            lines.append("# API key: stored in OS keychain")
        else:
            lines.append("# API key: session only (must be re-entered)")

        # Attach command if attached
        if attached:
            lines.append("")
            lines.append(f"%dataing attach {attached}")

        snippet = "\n".join(lines)

        # Build description
        desc_parts = [f"Connect to {backend_url}"]
        if attached:
            desc_parts.append(f", attach to {attached}")

        self.write(
            json_encode(
                {
                    "snippet": snippet,
                    "description": "".join(desc_parts),
                }
            )
        )


def setup_handlers(web_app: tornado.web.Application) -> None:
    """Setup handlers for the Dataing server extension.

    Args:
        web_app: Tornado web application to add handlers to.
    """
    from jupyter_server.utils import url_path_join

    host_pattern = ".*$"
    base_url = web_app.settings.get("base_url", "/")

    handlers = [
        (url_path_join(base_url, "dataing", "handshake"), HandshakeHandler),
        (url_path_join(base_url, "dataing", "token"), TokenHandler),
        (url_path_join(base_url, "dataing", "credentials"), CredentialHandler),
        (url_path_join(base_url, "dataing", "connection", "test"), ConnectionTestHandler),
        (url_path_join(base_url, "dataing", "snippet"), SnippetHandler),
        (url_path_join(base_url, "dataing", "state"), StateHandler),
        # Versioned command endpoints
        (url_path_join(base_url, "dataing", "command", "connect"), CommandConnectHandler),
        (url_path_join(base_url, "dataing", "command", "attach"), CommandAttachHandler),
        (url_path_join(base_url, "dataing", "command", "start_run"), CommandStartRunHandler),
        (url_path_join(base_url, "dataing", "command", "clear"), CommandClearHandler),
        (url_path_join(base_url, "dataing", "workspace", "state"), WorkspaceStateHandler),
        # Proxy handlers
        (url_path_join(base_url, r"dataing/sse/(.*)"), SSEProxyHandler),
        (url_path_join(base_url, r"dataing/proxy/(.*)"), ProxyHandler),
    ]

    web_app.add_handlers(host_pattern, handlers)
