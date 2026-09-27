"""URL redaction for logs and audit records."""

from __future__ import annotations

from urllib.parse import urlsplit


def redact_url(url: str) -> str:
    """Reduce a URL to its scheme and host so it is safe to log or store.

    Incoming-webhook URLs (Slack, Microsoft Teams, Discord) embed a bearer secret
    in the path, and any URL can carry credentials in its userinfo or query string.

    Args:
        url: URL to redact.

    Returns:
        ``scheme://host``, or a placeholder when the URL has no parseable host.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid url>"
    if not parts.scheme or not parts.hostname:
        return "<invalid url>"
    return f"{parts.scheme}://{parts.hostname}"
