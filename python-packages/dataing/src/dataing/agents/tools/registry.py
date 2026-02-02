"""Unified tool registry for the Dataing Assistant.

This module provides a central registry for all tools available to the
Dataing Assistant agent. Tools are organized by category and can be
enabled/disabled per tenant.

Usage:
    registry = get_default_registry()
    tools = registry.get_enabled_tools(tenant_id)

    # Create agent with tools
    agent = BondAgent(
        name="assistant",
        toolsets=tools,
        ...
    )
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic_ai.tools import Tool

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    """Categories for assistant tools."""

    FILES = "files"
    GIT = "git"
    DOCKER = "docker"
    LOGS = "logs"
    DATASOURCE = "datasource"
    ENVIRONMENT = "environment"


@runtime_checkable
class ToolProtocol(Protocol):
    """Protocol for tool functions."""

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool."""
        ...


@dataclass
class ToolConfig:
    """Configuration for a registered tool.

    Attributes:
        name: Unique tool name.
        category: Tool category for grouping.
        description: Human-readable description.
        tool: The PydanticAI Tool instance.
        enabled_by_default: Whether the tool is enabled by default.
        requires_auth: Whether the tool requires authentication.
        priority: Tool priority within category (lower = higher priority).
    """

    name: str
    category: ToolCategory
    description: str
    tool: Tool[Any]
    enabled_by_default: bool = True
    requires_auth: bool = True
    priority: int = 100


@dataclass
class TenantToolConfig:
    """Per-tenant tool configuration.

    Attributes:
        enabled_tools: Set of explicitly enabled tool names.
        disabled_tools: Set of explicitly disabled tool names.
        tool_limits: Per-tool rate limits or restrictions.
    """

    enabled_tools: set[str] = field(default_factory=set)
    disabled_tools: set[str] = field(default_factory=set)
    tool_limits: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Central registry for all assistant tools.

    The registry manages tool registration, per-tenant configuration,
    and provides tools to the BondAgent based on tenant settings.
    """

    def __init__(self) -> None:
        """Initialize the tool registry."""
        self._tools: dict[str, ToolConfig] = {}
        self._tenant_configs: dict[UUID, TenantToolConfig] = {}
        self._category_tools: dict[ToolCategory, list[str]] = {cat: [] for cat in ToolCategory}

    def register(self, config: ToolConfig) -> None:
        """Register a tool with the registry.

        Args:
            config: Tool configuration.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if config.name in self._tools:
            raise ValueError(f"Tool '{config.name}' is already registered")

        self._tools[config.name] = config
        self._category_tools[config.category].append(config.name)
        self._category_tools[config.category].sort(key=lambda n: self._tools[n].priority)
        logger.debug(f"Registered tool: {config.name} ({config.category})")

    def register_tool(
        self,
        name: str,
        category: ToolCategory,
        description: str,
        func: Callable[..., Any],
        *,
        enabled_by_default: bool = True,
        requires_auth: bool = True,
        priority: int = 100,
    ) -> None:
        """Register a tool function with the registry.

        Args:
            name: Unique tool name.
            category: Tool category.
            description: Human-readable description.
            func: The tool function.
            enabled_by_default: Whether enabled by default.
            requires_auth: Whether requires authentication.
            priority: Tool priority.
        """
        tool = Tool(func)
        config = ToolConfig(
            name=name,
            category=category,
            description=description,
            tool=tool,
            enabled_by_default=enabled_by_default,
            requires_auth=requires_auth,
            priority=priority,
        )
        self.register(config)

    def get_tool(self, name: str) -> ToolConfig | None:
        """Get a tool configuration by name.

        Args:
            name: Tool name.

        Returns:
            Tool configuration or None if not found.
        """
        return self._tools.get(name)

    def get_tools_by_category(self, category: ToolCategory) -> list[ToolConfig]:
        """Get all tools in a category.

        Args:
            category: Tool category.

        Returns:
            List of tool configurations.
        """
        return [self._tools[name] for name in self._category_tools[category]]

    def get_all_tools(self) -> list[ToolConfig]:
        """Get all registered tools.

        Returns:
            List of all tool configurations.
        """
        return list(self._tools.values())

    def set_tenant_config(self, tenant_id: UUID, config: TenantToolConfig) -> None:
        """Set tool configuration for a tenant.

        Args:
            tenant_id: Tenant UUID.
            config: Tenant-specific tool configuration.
        """
        self._tenant_configs[tenant_id] = config

    def get_tenant_config(self, tenant_id: UUID) -> TenantToolConfig:
        """Get tool configuration for a tenant.

        Args:
            tenant_id: Tenant UUID.

        Returns:
            Tenant-specific configuration (or default if not set).
        """
        return self._tenant_configs.get(tenant_id, TenantToolConfig())

    def is_tool_enabled(self, name: str, tenant_id: UUID | None = None) -> bool:
        """Check if a tool is enabled for a tenant.

        Args:
            name: Tool name.
            tenant_id: Optional tenant UUID.

        Returns:
            True if the tool is enabled.
        """
        tool = self._tools.get(name)
        if tool is None:
            return False

        if tenant_id is None:
            return tool.enabled_by_default

        config = self.get_tenant_config(tenant_id)

        # Explicit enable/disable takes precedence
        if name in config.disabled_tools:
            return False
        if name in config.enabled_tools:
            return True

        return tool.enabled_by_default

    def get_enabled_tools(
        self,
        tenant_id: UUID | None = None,
        categories: list[ToolCategory] | None = None,
    ) -> list[Tool[Any]]:
        """Get all enabled tools for a tenant.

        Args:
            tenant_id: Optional tenant UUID.
            categories: Optional list of categories to filter.

        Returns:
            List of PydanticAI Tool instances.
        """
        tools = []
        for name, config in self._tools.items():
            if categories and config.category not in categories:
                continue
            if self.is_tool_enabled(name, tenant_id):
                tools.append(config.tool)
        return tools

    def enable_tool(self, tenant_id: UUID, name: str) -> None:
        """Enable a tool for a tenant.

        Args:
            tenant_id: Tenant UUID.
            name: Tool name.
        """
        config = self._tenant_configs.setdefault(tenant_id, TenantToolConfig())
        config.enabled_tools.add(name)
        config.disabled_tools.discard(name)

    def disable_tool(self, tenant_id: UUID, name: str) -> None:
        """Disable a tool for a tenant.

        Args:
            tenant_id: Tenant UUID.
            name: Tool name.
        """
        config = self._tenant_configs.setdefault(tenant_id, TenantToolConfig())
        config.disabled_tools.add(name)
        config.enabled_tools.discard(name)


# Singleton registry instance
_default_registry: ToolRegistry | None = None


def get_default_registry() -> ToolRegistry:
    """Get the default tool registry singleton.

    Returns:
        The default ToolRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def reset_registry() -> None:
    """Reset the default registry (for testing)."""
    global _default_registry
    _default_registry = None
