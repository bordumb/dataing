"""Lineage adapter registry for managing lineage providers.

This module provides a singleton registry for registering and creating
lineage adapters by type.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from dataing.adapters.lineage.base import BaseLineageAdapter
from dataing.adapters.lineage.exceptions import LineageProviderNotFoundError
from dataing.adapters.lineage.types import (
    LineageCapabilities,
    LineageProviderType,
)

T = TypeVar("T", bound=BaseLineageAdapter)


class LineageConfigField(BaseModel):
    """Configuration field for lineage provider forms.

    Attributes:
        name: Field name (key in config dict).
        label: Human-readable label.
        field_type: Type of field (string, integer, boolean, enum, secret).
        required: Whether the field is required.
        group: Group for organizing fields.
        default_value: Default value.
        placeholder: Placeholder text.
        description: Field description.
        options: Options for enum fields.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    field_type: str = Field(alias="type")
    required: bool
    group: str = "connection"
    default_value: Any | None = Field(default=None, alias="default")
    placeholder: str | None = None
    description: str | None = None
    options: list[dict[str, str]] | None = None


class LineageConfigSchema(BaseModel):
    """Configuration schema for a lineage provider.

    Attributes:
        fields: List of configuration fields.
    """

    model_config = ConfigDict(frozen=True)

    fields: list[LineageConfigField]


class LineageProviderDefinition(BaseModel):
    """Complete definition of a lineage provider.

    Attributes:
        provider_type: The provider type.
        display_name: Human-readable name.
        description: Description of the provider.
        capabilities: Provider capabilities.
        config_schema: Configuration schema.
    """

    model_config = ConfigDict(frozen=True)

    provider_type: LineageProviderType
    display_name: str
    description: str
    capabilities: LineageCapabilities
    config_schema: LineageConfigSchema


class LineageRegistry:
    """Singleton registry for lineage adapters.

    This registry maintains a mapping of provider types to adapter classes,
    allowing dynamic creation of adapters based on configuration.
    """

    _instance: LineageRegistry | None = None
    _adapters: dict[LineageProviderType, type[BaseLineageAdapter]]
    _definitions: dict[LineageProviderType, LineageProviderDefinition]

    def __new__(cls) -> LineageRegistry:
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters = {}
            cls._instance._definitions = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> LineageRegistry:
        """Get the singleton instance.

        Returns:
            The singleton LineageRegistry instance.
        """
        return cls()

    def register(
        self,
        provider_type: LineageProviderType,
        adapter_class: type[BaseLineageAdapter],
        display_name: str,
        description: str,
        capabilities: LineageCapabilities,
        config_schema: LineageConfigSchema,
    ) -> None:
        """Register a lineage adapter class.

        Args:
            provider_type: The provider type to register.
            adapter_class: The adapter class to register.
            display_name: Human-readable name.
            description: Provider description.
            capabilities: Provider capabilities.
            config_schema: Configuration schema.
        """
        self._adapters[provider_type] = adapter_class
        self._definitions[provider_type] = LineageProviderDefinition(
            provider_type=provider_type,
            display_name=display_name,
            description=description,
            capabilities=capabilities,
            config_schema=config_schema,
        )

    def unregister(self, provider_type: LineageProviderType) -> None:
        """Unregister a lineage adapter.

        Args:
            provider_type: The provider type to unregister.
        """
        self._adapters.pop(provider_type, None)
        self._definitions.pop(provider_type, None)

    def create(
        self,
        provider_type: LineageProviderType | str,
        config: dict[str, Any],
    ) -> BaseLineageAdapter:
        """Create a lineage adapter instance.

        Args:
            provider_type: The provider type (can be string or enum).
            config: Configuration dictionary for the adapter.

        Returns:
            Instance of the appropriate adapter.

        Raises:
            LineageProviderNotFoundError: If provider type is not registered.
        """
        if isinstance(provider_type, str):
            try:
                provider_type = LineageProviderType(provider_type)
            except ValueError as e:
                raise LineageProviderNotFoundError(provider_type) from e

        adapter_class = self._adapters.get(provider_type)
        if adapter_class is None:
            raise LineageProviderNotFoundError(provider_type.value)

        return adapter_class(config)

    def create_composite(
        self,
        configs: list[dict[str, Any]],
    ) -> BaseLineageAdapter:
        """Create composite adapter from multiple configs.

        Each config should have 'provider', 'priority', and provider-specific
        fields.

        Args:
            configs: List of provider configurations.

        Returns:
            CompositeLineageAdapter instance.
        """
        from dataing.adapters.lineage.adapters.composite import CompositeLineageAdapter

        adapters: list[tuple[BaseLineageAdapter, int]] = []
        for config in configs:
            provider = config.pop("provider")
            priority = config.pop("priority", 0)
            adapter = self.create(provider, config)
            adapters.append((adapter, priority))

        return CompositeLineageAdapter({"adapters": adapters})

    def get_adapter_class(
        self, provider_type: LineageProviderType
    ) -> type[BaseLineageAdapter] | None:
        """Get the adapter class for a provider type.

        Args:
            provider_type: The provider type.

        Returns:
            The adapter class, or None if not registered.
        """
        return self._adapters.get(provider_type)

    def get_definition(
        self, provider_type: LineageProviderType
    ) -> LineageProviderDefinition | None:
        """Get the provider definition.

        Args:
            provider_type: The provider type.

        Returns:
            The provider definition, or None if not registered.
        """
        return self._definitions.get(provider_type)

    def list_providers(self) -> list[LineageProviderDefinition]:
        """List all registered provider definitions.

        Returns:
            List of all provider definitions.
        """
        return list(self._definitions.values())

    def is_registered(self, provider_type: LineageProviderType) -> bool:
        """Check if a provider type is registered.

        Args:
            provider_type: The provider type to check.

        Returns:
            True if registered, False otherwise.
        """
        return provider_type in self._adapters

    @property
    def registered_types(self) -> list[LineageProviderType]:
        """Get list of all registered provider types.

        Returns:
            List of registered provider types.
        """
        return list(self._adapters.keys())


def register_lineage_adapter(
    provider_type: LineageProviderType,
    display_name: str,
    description: str,
    capabilities: LineageCapabilities,
    config_schema: LineageConfigSchema,
) -> Callable[[type[T]], type[T]]:
    """Decorator to register a lineage adapter class.

    Usage:
        @register_lineage_adapter(
            provider_type=LineageProviderType.DBT,
            display_name="dbt",
            description="Lineage from dbt manifest.json or dbt Cloud",
            capabilities=LineageCapabilities(...),
            config_schema=LineageConfigSchema(...),
        )
        class DbtAdapter(BaseLineageAdapter):
            ...

    Args:
        provider_type: The provider type to register.
        display_name: Human-readable name.
        description: Provider description.
        capabilities: Provider capabilities.
        config_schema: Configuration schema.

    Returns:
        Decorator function.
    """

    def decorator(cls: type[T]) -> type[T]:
        registry = LineageRegistry.get_instance()
        registry.register(
            provider_type=provider_type,
            adapter_class=cls,
            display_name=display_name,
            description=description,
            capabilities=capabilities,
            config_schema=config_schema,
        )
        return cls

    return decorator


# Global registry instance
_registry = LineageRegistry.get_instance()


def get_lineage_registry() -> LineageRegistry:
    """Get the global lineage registry instance.

    Returns:
        The global LineageRegistry instance.
    """
    return _registry
