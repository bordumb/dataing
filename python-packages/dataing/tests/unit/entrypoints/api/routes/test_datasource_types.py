"""Tests for the datasource source-type catalogue route."""

from dataing.adapters.datasource import SourceType, get_registry
from dataing.entrypoints.api.routes.datasources import (
    SourceTypeResponse,
    list_source_types,
)


class TestListSourceTypes:
    """Tests for the source type catalogue that drives the connection form."""

    async def test_returns_each_adapters_config_schema(self) -> None:
        """Every listed type carries its adapter's own config schema."""
        response = await list_source_types()

        registry = get_registry()
        assert response.types
        for source_type in response.types:
            definition = registry.get_definition(SourceType(source_type.type))
            assert definition is not None
            assert source_type.config_schema == definition.config_schema

    def test_config_schema_is_typed_in_openapi(self) -> None:
        """Clients generate their connection forms from a typed schema, not a dict."""
        json_schema = SourceTypeResponse.model_json_schema()

        assert json_schema["properties"]["config_schema"] == {"$ref": "#/$defs/ConfigSchema"}
