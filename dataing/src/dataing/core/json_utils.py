"""JSON serialization utilities.

This module provides a robust, centralized way to serialize Python objects
to JSON strings, handling complex types like UUID, datetime, date, and set
automatically via Pydantic V2.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

# Create a generic adapter for Any type - reused across all functions
_any_adapter = TypeAdapter(Any)


def to_json_string(obj: Any) -> str:
    """Robustly serialize any object to a JSON string.

    Uses Pydantic's underlying Rust serializer (pydantic-core) to handle
    standard Python types (datetime, date, UUID, Decimal, set, etc.)
    that the standard library's json.dumps() chokes on.

    Args:
        obj: The object to serialize.

    Returns:
        A JSON string.
    """
    return _any_adapter.dump_json(obj).decode("utf-8")


def to_json_safe(obj: Any) -> Any:
    """Convert any object to JSON-safe Python types.

    Uses Pydantic's underlying Rust serializer (pydantic-core) to convert
    standard Python types (datetime, date, UUID, Decimal, set, etc.) to
    their JSON-safe equivalents (strings, lists, etc.).

    This is useful when you need JSON-compatible data but not as a string,
    e.g., for Temporal activity results or database JSON columns.

    Examples:
        >>> to_json_safe(date(2024, 1, 15))
        '2024-01-15'
        >>> to_json_safe([{"id": UUID("..."), "created": datetime.now()}])
        [{"id": "...", "created": "2024-01-15T12:00:00"}]

    Args:
        obj: The object to convert.

    Returns:
        The object with all values converted to JSON-safe types.
    """
    return _any_adapter.dump_python(obj, mode="json")
