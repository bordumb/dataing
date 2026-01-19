"""Registry for integration adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dataing_ee.adapters.integrations.base import IntegrationAdapter


class AdapterRegistry:
    """Registry for looking up adapters by provider name."""

    _adapters: dict[str, type[IntegrationAdapter]] = {}

    @classmethod
    def register(cls, adapter_class: type[IntegrationAdapter]) -> None:
        """Register an adapter class."""
        cls._adapters[adapter_class.provider] = adapter_class

    @classmethod
    def get(cls, provider: str) -> IntegrationAdapter | None:
        """Get an adapter instance for a provider."""
        adapter_class = cls._adapters.get(provider)
        if adapter_class:
            return adapter_class()
        return None

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names."""
        return list(cls._adapters.keys())

    @classmethod
    def has(cls, provider: str) -> bool:
        """Check if a provider is registered."""
        return provider in cls._adapters


def register_adapter(adapter_class: type[IntegrationAdapter]) -> type[IntegrationAdapter]:
    """Decorator to register an adapter class."""
    AdapterRegistry.register(adapter_class)
    return adapter_class


def get_adapter(provider: str) -> IntegrationAdapter | None:
    """Get an adapter instance for a provider."""
    return AdapterRegistry.get(provider)
