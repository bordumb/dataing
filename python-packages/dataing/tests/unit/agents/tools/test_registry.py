"""Tests for the unified tool registry."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai.tools import Tool

from dataing.agents.tools.registry import (
    TenantToolConfig,
    ToolCategory,
    ToolConfig,
    ToolRegistry,
    get_default_registry,
    reset_registry,
)


@pytest.fixture
def registry() -> ToolRegistry:
    """Create a fresh registry for each test."""
    return ToolRegistry()


@pytest.fixture
def sample_tool() -> Tool:
    """Create a sample tool for testing."""

    async def sample_func(arg: str) -> str:
        """Sample tool function."""
        return f"Result: {arg}"

    return Tool(sample_func)


@pytest.fixture
def sample_config(sample_tool: Tool) -> ToolConfig:
    """Create a sample tool config."""
    return ToolConfig(
        name="sample_tool",
        category=ToolCategory.FILES,
        description="A sample tool for testing",
        tool=sample_tool,
    )


class TestToolCategory:
    """Tests for ToolCategory enum."""

    def test_categories_exist(self) -> None:
        """Verify all expected categories exist."""
        assert ToolCategory.FILES == "files"
        assert ToolCategory.GIT == "git"
        assert ToolCategory.DOCKER == "docker"
        assert ToolCategory.LOGS == "logs"
        assert ToolCategory.DATASOURCE == "datasource"
        assert ToolCategory.ENVIRONMENT == "environment"

    def test_category_is_string(self) -> None:
        """Verify categories are string-based for serialization."""
        assert isinstance(ToolCategory.FILES.value, str)


class TestToolConfig:
    """Tests for ToolConfig dataclass."""

    def test_default_values(self, sample_tool: Tool) -> None:
        """Verify default values are set correctly."""
        config = ToolConfig(
            name="test",
            category=ToolCategory.FILES,
            description="Test tool",
            tool=sample_tool,
        )
        assert config.enabled_by_default is True
        assert config.requires_auth is True
        assert config.priority == 100

    def test_custom_values(self, sample_tool: Tool) -> None:
        """Verify custom values override defaults."""
        config = ToolConfig(
            name="test",
            category=ToolCategory.DOCKER,
            description="Test tool",
            tool=sample_tool,
            enabled_by_default=False,
            requires_auth=False,
            priority=50,
        )
        assert config.enabled_by_default is False
        assert config.requires_auth is False
        assert config.priority == 50


class TestTenantToolConfig:
    """Tests for TenantToolConfig dataclass."""

    def test_default_empty_sets(self) -> None:
        """Verify defaults are empty."""
        config = TenantToolConfig()
        assert config.enabled_tools == set()
        assert config.disabled_tools == set()
        assert config.tool_limits == {}

    def test_custom_values(self) -> None:
        """Verify custom values work."""
        config = TenantToolConfig(
            enabled_tools={"tool1", "tool2"},
            disabled_tools={"tool3"},
            tool_limits={"tool1": {"rate": 100}},
        )
        assert "tool1" in config.enabled_tools
        assert "tool3" in config.disabled_tools
        assert config.tool_limits["tool1"]["rate"] == 100


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_register_tool(self, registry: ToolRegistry, sample_config: ToolConfig) -> None:
        """Test basic tool registration."""
        registry.register(sample_config)
        assert registry.get_tool("sample_tool") == sample_config

    def test_register_duplicate_raises(
        self, registry: ToolRegistry, sample_config: ToolConfig
    ) -> None:
        """Test that registering duplicate tool raises ValueError."""
        registry.register(sample_config)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(sample_config)

    def test_register_tool_function(self, registry: ToolRegistry) -> None:
        """Test register_tool convenience method."""

        async def my_tool(x: int) -> int:
            """Double the input."""
            return x * 2

        registry.register_tool(
            name="doubler",
            category=ToolCategory.ENVIRONMENT,
            description="Doubles a number",
            func=my_tool,
            enabled_by_default=False,
            priority=10,
        )

        config = registry.get_tool("doubler")
        assert config is not None
        assert config.name == "doubler"
        assert config.category == ToolCategory.ENVIRONMENT
        assert config.enabled_by_default is False
        assert config.priority == 10

    def test_get_tool_not_found(self, registry: ToolRegistry) -> None:
        """Test get_tool returns None for unknown tool."""
        assert registry.get_tool("nonexistent") is None

    def test_get_tools_by_category(self, registry: ToolRegistry, sample_tool: Tool) -> None:
        """Test filtering tools by category."""
        # Register tools in different categories
        registry.register(
            ToolConfig(
                name="file1",
                category=ToolCategory.FILES,
                description="File tool 1",
                tool=sample_tool,
            )
        )
        registry.register(
            ToolConfig(
                name="file2",
                category=ToolCategory.FILES,
                description="File tool 2",
                tool=sample_tool,
            )
        )
        registry.register(
            ToolConfig(
                name="docker1",
                category=ToolCategory.DOCKER,
                description="Docker tool",
                tool=sample_tool,
            )
        )

        file_tools = registry.get_tools_by_category(ToolCategory.FILES)
        assert len(file_tools) == 2
        assert all(t.category == ToolCategory.FILES for t in file_tools)

        docker_tools = registry.get_tools_by_category(ToolCategory.DOCKER)
        assert len(docker_tools) == 1

    def test_get_all_tools(self, registry: ToolRegistry, sample_tool: Tool) -> None:
        """Test getting all registered tools."""
        registry.register(
            ToolConfig(
                name="tool1",
                category=ToolCategory.FILES,
                description="Tool 1",
                tool=sample_tool,
            )
        )
        registry.register(
            ToolConfig(
                name="tool2",
                category=ToolCategory.GIT,
                description="Tool 2",
                tool=sample_tool,
            )
        )

        all_tools = registry.get_all_tools()
        assert len(all_tools) == 2

    def test_priority_ordering(self, registry: ToolRegistry, sample_tool: Tool) -> None:
        """Test tools are ordered by priority within category."""
        registry.register(
            ToolConfig(
                name="low_priority",
                category=ToolCategory.FILES,
                description="Low priority",
                tool=sample_tool,
                priority=200,
            )
        )
        registry.register(
            ToolConfig(
                name="high_priority",
                category=ToolCategory.FILES,
                description="High priority",
                tool=sample_tool,
                priority=10,
            )
        )

        file_tools = registry.get_tools_by_category(ToolCategory.FILES)
        assert file_tools[0].name == "high_priority"
        assert file_tools[1].name == "low_priority"


class TestTenantConfiguration:
    """Tests for per-tenant tool configuration."""

    def test_set_and_get_tenant_config(self, registry: ToolRegistry) -> None:
        """Test setting and retrieving tenant config."""
        tenant_id = uuid4()
        config = TenantToolConfig(
            enabled_tools={"tool1"},
            disabled_tools={"tool2"},
        )

        registry.set_tenant_config(tenant_id, config)
        retrieved = registry.get_tenant_config(tenant_id)

        assert retrieved == config

    def test_get_tenant_config_default(self, registry: ToolRegistry) -> None:
        """Test default config for unknown tenant."""
        unknown_tenant = uuid4()
        config = registry.get_tenant_config(unknown_tenant)

        assert config.enabled_tools == set()
        assert config.disabled_tools == set()

    def test_is_tool_enabled_default(
        self, registry: ToolRegistry, sample_config: ToolConfig
    ) -> None:
        """Test is_tool_enabled with default settings."""
        registry.register(sample_config)

        # No tenant - uses default
        assert registry.is_tool_enabled("sample_tool") is True

        # Unknown tenant - uses default
        assert registry.is_tool_enabled("sample_tool", uuid4()) is True

    def test_is_tool_enabled_disabled_by_default(
        self, registry: ToolRegistry, sample_tool: Tool
    ) -> None:
        """Test tool disabled by default."""
        registry.register(
            ToolConfig(
                name="disabled_tool",
                category=ToolCategory.FILES,
                description="Disabled by default",
                tool=sample_tool,
                enabled_by_default=False,
            )
        )

        assert registry.is_tool_enabled("disabled_tool") is False

    def test_is_tool_enabled_tenant_override(
        self, registry: ToolRegistry, sample_config: ToolConfig
    ) -> None:
        """Test tenant can override default enabled state."""
        registry.register(sample_config)
        tenant_id = uuid4()

        # Disable for this tenant
        registry.set_tenant_config(
            tenant_id,
            TenantToolConfig(disabled_tools={"sample_tool"}),
        )

        assert registry.is_tool_enabled("sample_tool", tenant_id) is False
        # Other tenants still have it enabled
        assert registry.is_tool_enabled("sample_tool", uuid4()) is True

    def test_enable_tool_for_tenant(self, registry: ToolRegistry, sample_tool: Tool) -> None:
        """Test enabling a disabled-by-default tool for tenant."""
        registry.register(
            ToolConfig(
                name="premium_tool",
                category=ToolCategory.LOGS,
                description="Premium feature",
                tool=sample_tool,
                enabled_by_default=False,
            )
        )
        tenant_id = uuid4()

        # Initially disabled
        assert registry.is_tool_enabled("premium_tool", tenant_id) is False

        # Enable for tenant
        registry.enable_tool(tenant_id, "premium_tool")
        assert registry.is_tool_enabled("premium_tool", tenant_id) is True

    def test_disable_tool_for_tenant(
        self, registry: ToolRegistry, sample_config: ToolConfig
    ) -> None:
        """Test disabling an enabled tool for tenant."""
        registry.register(sample_config)
        tenant_id = uuid4()

        # Initially enabled
        assert registry.is_tool_enabled("sample_tool", tenant_id) is True

        # Disable for tenant
        registry.disable_tool(tenant_id, "sample_tool")
        assert registry.is_tool_enabled("sample_tool", tenant_id) is False

    def test_enable_removes_from_disabled(
        self, registry: ToolRegistry, sample_config: ToolConfig
    ) -> None:
        """Test that enabling removes from disabled set."""
        registry.register(sample_config)
        tenant_id = uuid4()

        registry.disable_tool(tenant_id, "sample_tool")
        config = registry.get_tenant_config(tenant_id)
        assert "sample_tool" in config.disabled_tools

        registry.enable_tool(tenant_id, "sample_tool")
        config = registry.get_tenant_config(tenant_id)
        assert "sample_tool" not in config.disabled_tools
        assert "sample_tool" in config.enabled_tools


class TestGetEnabledTools:
    """Tests for get_enabled_tools method."""

    def test_returns_pydantic_tools(
        self, registry: ToolRegistry, sample_config: ToolConfig
    ) -> None:
        """Test that get_enabled_tools returns Tool instances."""
        registry.register(sample_config)
        tools = registry.get_enabled_tools()

        assert len(tools) == 1
        assert isinstance(tools[0], Tool)

    def test_filters_disabled_tools(self, registry: ToolRegistry, sample_tool: Tool) -> None:
        """Test that disabled tools are filtered out."""
        registry.register(
            ToolConfig(
                name="enabled",
                category=ToolCategory.FILES,
                description="Enabled",
                tool=sample_tool,
            )
        )
        registry.register(
            ToolConfig(
                name="disabled",
                category=ToolCategory.FILES,
                description="Disabled",
                tool=sample_tool,
                enabled_by_default=False,
            )
        )

        tools = registry.get_enabled_tools()
        assert len(tools) == 1

    def test_filters_by_category(self, registry: ToolRegistry, sample_tool: Tool) -> None:
        """Test filtering by categories."""
        registry.register(
            ToolConfig(
                name="file_tool",
                category=ToolCategory.FILES,
                description="File",
                tool=sample_tool,
            )
        )
        registry.register(
            ToolConfig(
                name="docker_tool",
                category=ToolCategory.DOCKER,
                description="Docker",
                tool=sample_tool,
            )
        )

        file_tools = registry.get_enabled_tools(categories=[ToolCategory.FILES])
        assert len(file_tools) == 1

        both = registry.get_enabled_tools(categories=[ToolCategory.FILES, ToolCategory.DOCKER])
        assert len(both) == 2

    def test_respects_tenant_config(self, registry: ToolRegistry, sample_tool: Tool) -> None:
        """Test tenant config affects enabled tools."""
        registry.register(
            ToolConfig(
                name="tool1",
                category=ToolCategory.FILES,
                description="Tool 1",
                tool=sample_tool,
            )
        )
        registry.register(
            ToolConfig(
                name="tool2",
                category=ToolCategory.FILES,
                description="Tool 2",
                tool=sample_tool,
            )
        )

        tenant_id = uuid4()
        registry.disable_tool(tenant_id, "tool1")

        # Without tenant - both enabled
        assert len(registry.get_enabled_tools()) == 2

        # With tenant - only tool2 enabled
        assert len(registry.get_enabled_tools(tenant_id)) == 1


class TestSingleton:
    """Tests for the singleton registry."""

    def test_get_default_registry_returns_same_instance(self) -> None:
        """Test singleton returns same instance."""
        reset_registry()
        reg1 = get_default_registry()
        reg2 = get_default_registry()
        assert reg1 is reg2

    def test_reset_registry_clears_instance(self) -> None:
        """Test reset creates new instance."""
        reg1 = get_default_registry()
        reset_registry()
        reg2 = get_default_registry()
        assert reg1 is not reg2
