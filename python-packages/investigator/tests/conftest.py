"""Common test fixtures for investigator tests."""

from __future__ import annotations

import json
from typing import Any

import pytest


@pytest.fixture
def basic_scope() -> dict[str, Any]:
    """Create a basic scope for testing."""
    # Must match the Rust Scope struct exactly
    return {
        "user_id": "test-user",
        "tenant_id": "test-tenant",
        "permissions": ["orders", "customers"],
    }


@pytest.fixture
def start_event(basic_scope: dict[str, Any]) -> str:
    """Create a Start event JSON string."""
    return json.dumps({
        "type": "Start",
        "payload": {
            "objective": "Test investigation",
            "scope": basic_scope,
        },
    })


@pytest.fixture
def mock_tool_executor():
    """Create a mock tool executor for testing."""

    async def executor(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "get_schema":
            return {"tables": [{"name": "orders", "columns": ["id", "amount"]}]}
        elif tool_name == "generate_hypotheses":
            return [{"id": "h1", "title": "Test hypothesis"}]
        elif tool_name == "evaluate_hypothesis":
            return {"supported": True, "confidence": 0.9}
        elif tool_name == "synthesize":
            return {"insight": "Test insight"}
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    return executor
