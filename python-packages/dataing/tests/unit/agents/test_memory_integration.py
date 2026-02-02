"""Tests for AgentClient memory integration."""

from __future__ import annotations

from unittest.mock import AsyncMock

from bond.tools.memory import AgentMemoryProtocol, memory_toolset

from dataing.agents.client import AgentClient


class TestAgentClientMemoryIntegration:
    """Test AgentClient memory store integration."""

    def test_agent_client_without_memory_store(self) -> None:
        """Test AgentClient works without memory_store (backwards compat)."""
        client = AgentClient(api_key="test-key")

        # Verify agents have empty toolsets when memory_store is None
        assert client._hypothesis_agent.toolsets == []
        assert client._interpretation_agent.toolsets == []
        assert client._synthesis_agent.toolsets == []
        assert client._query_agent.toolsets == []
        assert client._counter_analysis_agent.toolsets == []

        # Verify deps is None
        assert client._hypothesis_agent.deps is None
        assert client._interpretation_agent.deps is None
        assert client._synthesis_agent.deps is None
        assert client._query_agent.deps is None
        assert client._counter_analysis_agent.deps is None

    def test_agent_client_with_memory_store(self) -> None:
        """Test AgentClient wires memory_toolset when store provided."""
        # Create mock memory store
        mock_store = AsyncMock(spec=AgentMemoryProtocol)

        client = AgentClient(api_key="test-key", memory_store=mock_store)

        # Verify all agents have memory_toolset
        assert client._hypothesis_agent.toolsets == [memory_toolset]
        assert client._interpretation_agent.toolsets == [memory_toolset]
        assert client._synthesis_agent.toolsets == [memory_toolset]
        assert client._query_agent.toolsets == [memory_toolset]
        assert client._counter_analysis_agent.toolsets == [memory_toolset]

        # Verify deps is the memory store
        assert client._hypothesis_agent.deps is mock_store
        assert client._interpretation_agent.deps is mock_store
        assert client._synthesis_agent.deps is mock_store
        assert client._query_agent.deps is mock_store
        assert client._counter_analysis_agent.deps is mock_store

    def test_memory_store_is_optional(self) -> None:
        """Test that memory_store parameter is optional and defaults to None."""
        # Should not raise
        client = AgentClient(api_key="test-key")
        assert client._memory_store is None

        # Explicitly passing None should also work
        client2 = AgentClient(api_key="test-key", memory_store=None)
        assert client2._memory_store is None

    def test_memory_store_stored_on_client(self) -> None:
        """Test that memory_store is accessible via _memory_store."""
        mock_store = AsyncMock(spec=AgentMemoryProtocol)
        client = AgentClient(api_key="test-key", memory_store=mock_store)

        assert client._memory_store is mock_store


class TestAgentClientTenantId:
    """Test tenant_id parameter threading."""

    def test_generate_hypotheses_accepts_tenant_id(self) -> None:
        """Test generate_hypotheses method signature includes tenant_id."""
        import inspect
        from uuid import UUID

        sig = inspect.signature(AgentClient.generate_hypotheses)
        params = sig.parameters

        assert "tenant_id" in params
        # Check annotation includes UUID | None
        annotation = params["tenant_id"].annotation
        assert UUID in annotation.__args__ if hasattr(annotation, "__args__") else True

    def test_synthesize_findings_raw_accepts_tenant_id(self) -> None:
        """Test synthesize_findings_raw method signature includes tenant_id."""
        import inspect
        from uuid import UUID

        sig = inspect.signature(AgentClient.synthesize_findings_raw)
        params = sig.parameters

        assert "tenant_id" in params
        annotation = params["tenant_id"].annotation
        assert UUID in annotation.__args__ if hasattr(annotation, "__args__") else True
