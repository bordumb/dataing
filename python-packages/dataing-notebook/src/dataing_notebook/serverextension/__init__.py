"""Jupyter Server Extension for Dataing.

This module provides server-side endpoints for the Dataing notebook integration:
- /dataing/token: Proxy endpoint to fetch/refresh API tokens
- /dataing/handshake: Returns backend URL and configuration
- /dataing/proxy/*: Proxies requests to the Dataing backend

Supports both JupyterHub and standalone Jupyter environments via
environment variable URL discovery.
"""

from .handlers import setup_handlers


def _load_jupyter_server_extension(serverapp):
    """Load the Jupyter server extension.

    Args:
        serverapp: JupyterLab or Jupyter Notebook server application.
    """
    setup_handlers(serverapp.web_app)
    serverapp.log.info("Dataing server extension loaded")


def _jupyter_server_extension_paths():
    """Return the server extension paths.

    Returns:
        List of extension paths.
    """
    return [{"module": "dataing_notebook.serverextension"}]


# For Jupyter Server >= 2.0
load_jupyter_server_extension = _load_jupyter_server_extension
_jupyter_server_extension_points = _jupyter_server_extension_paths
