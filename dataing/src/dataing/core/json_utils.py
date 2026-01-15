"""JSON serialization utilities.

This module provides a robust, centralized way to serialize Python objects
to JSON strings, handling complex types like UUID, datetime, date, and set
automatically via Pydantic V2.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

# Create a generic adapter for Any type
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
    # model_dump_json handles everything Pydantic knows about
    return _any_adapter.dump_json(obj).decode("utf-8")
