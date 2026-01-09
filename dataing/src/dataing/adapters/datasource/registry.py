"""Adapter registry for managing data source adapters.

This module provides a singleton registry for registering and creating
data source adapters by type.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    ConfigSchema,
    SourceCategory,
    SourceType,
    SourceTypeDefinition,
)

T = TypeVar("T", bound=BaseAdapter)


class AdapterRegistry:
    """Singleton registry for data source adapters.

    This registry maintains a mapping of source types to adapter classes,
    allowing dynamic creation of adapters based on configuration.
    """

    _instance: AdapterRegistry | None = None
    _adapters: dict[SourceType, type[BaseAdapter]]
    _definitions: dict[SourceType, SourceTypeDefinition]

    def __new__(cls) -> AdapterRegistry:
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters = {}
            cls._instance._definitions = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> AdapterRegistry:
        """Get the singleton instance."""
        return cls()

    def register(
        self,
        source_type: SourceType,
        adapter_class: type[BaseAdapter],
        display_name: str,
        category: SourceCategory,
        icon: str,
        description: str,
        capabilities: AdapterCapabilities,
        config_schema: ConfigSchema,
    ) -> None:
        """Register an adapter class for a source type.

        Args:
            source_type: The source type to register.
            adapter_class: The adapter class to register.
            display_name: Human-readable name for the source type.
            category: Category of the source (database, api, filesystem).
            icon: Icon identifier for the source type.
            description: Description of the source type.
            capabilities: Capabilities of the adapter.
            config_schema: Configuration schema for connection forms.
        """
        self._adapters[source_type] = adapter_class
        self._definitions[source_type] = SourceTypeDefinition(
            type=source_type,
            display_name=display_name,
            category=category,
            icon=icon,
            description=description,
            capabilities=capabilities,
            config_schema=config_schema,
        )

    def unregister(self, source_type: SourceType) -> None:
        """Unregister an adapter for a source type.

        Args:
            source_type: The source type to unregister.
        """
        self._adapters.pop(source_type, None)
        self._definitions.pop(source_type, None)

    def create(
        self,
        source_type: SourceType | str,
        config: dict[str, Any],
    ) -> BaseAdapter:
        """Create an adapter instance for a source type.

        Args:
            source_type: The source type (can be string or enum).
            config: Configuration dictionary for the adapter.

        Returns:
            Instance of the appropriate adapter.

        Raises:
            ValueError: If source type is not registered.
        """
        if isinstance(source_type, str):
            source_type = SourceType(source_type)

        adapter_class = self._adapters.get(source_type)
        if adapter_class is None:
            raise ValueError(f"No adapter registered for source type: {source_type}")

        return adapter_class(config)

    def get_adapter_class(self, source_type: SourceType) -> type[BaseAdapter] | None:
        """Get the adapter class for a source type.

        Args:
            source_type: The source type.

        Returns:
            The adapter class, or None if not registered.
        """
        return self._adapters.get(source_type)

    def get_definition(self, source_type: SourceType) -> SourceTypeDefinition | None:
        """Get the source type definition.

        Args:
            source_type: The source type.

        Returns:
            The source type definition, or None if not registered.
        """
        return self._definitions.get(source_type)

    def list_types(self) -> list[SourceTypeDefinition]:
        """List all registered source type definitions.

        Returns:
            List of all source type definitions.
        """
        return list(self._definitions.values())

    def is_registered(self, source_type: SourceType) -> bool:
        """Check if a source type is registered.

        Args:
            source_type: The source type to check.

        Returns:
            True if registered, False otherwise.
        """
        return source_type in self._adapters

    @property
    def registered_types(self) -> list[SourceType]:
        """Get list of all registered source types."""
        return list(self._adapters.keys())


def register_adapter(
    source_type: SourceType,
    display_name: str,
    category: SourceCategory,
    icon: str,
    description: str,
    capabilities: AdapterCapabilities,
    config_schema: ConfigSchema,
) -> Callable[[type[T]], type[T]]:
    """Decorator to register an adapter class.

    Usage:
        @register_adapter(
            source_type=SourceType.POSTGRESQL,
            display_name="PostgreSQL",
            category=SourceCategory.DATABASE,
            icon="postgresql",
            description="PostgreSQL database",
            capabilities=AdapterCapabilities(...),
            config_schema=ConfigSchema(...),
        )
        class PostgresAdapter(SQLAdapter):
            ...

    Args:
        source_type: The source type to register.
        display_name: Human-readable name.
        category: Source category.
        icon: Icon identifier.
        description: Source description.
        capabilities: Adapter capabilities.
        config_schema: Configuration schema.

    Returns:
        Decorator function.
    """

    def decorator(cls: type[T]) -> type[T]:
        registry = AdapterRegistry.get_instance()
        registry.register(
            source_type=source_type,
            adapter_class=cls,
            display_name=display_name,
            category=category,
            icon=icon,
            description=description,
            capabilities=capabilities,
            config_schema=config_schema,
        )
        return cls

    return decorator


# Global registry instance
_registry = AdapterRegistry.get_instance()


def get_registry() -> AdapterRegistry:
    """Get the global adapter registry instance."""
    return _registry
