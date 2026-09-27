"""Keep local data sources inside the directory the operator set aside for them.

Local file, DuckDB and SQLite sources, and dbt manifests, read files on the hosts
that run the API and the Temporal worker, from a path that a tenant types in. Left
unchecked, ``/`` would make the whole host the source's own location, and a symlink
could lead anywhere.

The operator names one directory in ``DATAING_LOCAL_DATA_ROOT``. A source's path must
resolve inside it, with symlinks followed on both sides, when the source is saved and
again each time an adapter connects. A relative path is taken relative to that
directory, so the API and the worker resolve it the same way whatever their working
directories. While the variable is unset, local sources are refused altogether.
"""

from __future__ import annotations

import os

from dataing.adapters.datasource.errors import InvalidConfigError

LOCAL_DATA_ROOT_ENV = "DATAING_LOCAL_DATA_ROOT"


def require_local_data_root() -> str:
    """Return the local data root, refusing local sources while it is unset.

    Returns:
        The root directory, with symlinks resolved.

    Raises:
        InvalidConfigError: If ``DATAING_LOCAL_DATA_ROOT`` is unset or blank.
    """
    root = os.environ.get(LOCAL_DATA_ROOT_ENV, "").strip()
    if not root:
        raise InvalidConfigError(
            message=(
                "Local data sources are disabled on this server. To enable them, an "
                f"operator must set {LOCAL_DATA_ROOT_ENV} to the directory they may read."
            ),
            field="path",
        )
    return os.path.realpath(root)


def resolve_local_path(path: object) -> str:
    """Resolve a local source's configured path, which must lie inside the local data root.

    Args:
        path: The ``path`` from the source's configuration. A relative path is taken
            relative to the root.

    Returns:
        The path with symlinks resolved. Callers use it rather than ``path`` from then
        on, so a symlink changed after the check cannot redirect them.

    Raises:
        InvalidConfigError: If the root is unset, or ``path`` is missing, malformed,
            or resolves outside the root.
    """
    root = require_local_data_root()
    if not isinstance(path, str) or not path:
        raise InvalidConfigError(message="A local data source needs a path.", field="path")
    try:
        resolved = os.path.realpath(os.path.join(root, path))
    except ValueError as e:  # e.g. an embedded NUL character
        raise InvalidConfigError(message=f"Invalid path {path!r}: {e}", field="path") from e
    if os.path.commonpath([root, resolved]) != root:
        raise InvalidConfigError(
            message=(
                f"Path {path!r} is outside the directory this server allows local data "
                f"sources to read ({LOCAL_DATA_ROOT_ENV})."
            ),
            field="path",
        )
    return resolved
