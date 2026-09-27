"""Tests for the EE API datasource adapters: Salesforce, HubSpot and Stripe."""

import os
import subprocess
import sys
import textwrap

import pytest

# Import the EE datasource adapters to register them
from dataing_ee.adapters import datasource as _datasource  # noqa: F401

from dataing.adapters.datasource import SourceType, get_registry
from dataing.adapters.datasource.types import ConfigSchema

EE_SOURCE_TYPES = [SourceType.SALESFORCE, SourceType.HUBSPOT, SourceType.STRIPE]


@pytest.fixture(params=EE_SOURCE_TYPES, ids=lambda source_type: source_type.value)
def config_schema(request: pytest.FixtureRequest) -> ConfigSchema:
    """The registered config schema of each EE adapter."""
    definition = get_registry().get_definition(request.param)
    assert definition is not None, f"{request.param.value} is not registered"
    return definition.config_schema


class TestRegistration:
    """The EE adapters are registered wherever the EE edition runs."""

    @pytest.mark.parametrize("source_type", EE_SOURCE_TYPES, ids=lambda t: t.value)
    def test_importing_the_package_registers_the_adapter(self, source_type: SourceType) -> None:
        """Importing dataing_ee.adapters.datasource registers each EE adapter."""
        assert get_registry().is_registered(source_type)

    def test_building_the_ee_app_registers_the_adapters(self) -> None:
        """A fresh process that builds the EE app can serve all three EE types."""
        script = textwrap.dedent(
            """
            import dataing_ee.entrypoints.api.app  # builds the EE app
            from dataing.adapters.datasource import get_registry

            print(*sorted(t.value for t in get_registry().registered_types))
            """
        )
        # A fresh interpreter, so no earlier import in this test run can register them.
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
            timeout=120,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        registered = set(result.stdout.split())
        assert {source_type.value for source_type in EE_SOURCE_TYPES} <= registered


class TestConfigSchemaContracts:
    """The EE config schemas meet the contracts CE checks for its own adapters."""

    def test_show_if_names_a_field_in_the_same_schema(self, config_schema: ConfigSchema) -> None:
        """A field can only depend on another field of its own schema."""
        names = {field.name for field in config_schema.fields}
        for field in config_schema.fields:
            if field.show_if is not None:
                assert field.show_if.field in names, field.name

    def test_enum_defaults_are_options(self, config_schema: ConfigSchema) -> None:
        """An enum field's default must be one of its options."""
        for field in config_schema.fields:
            if field.type == "enum" and field.default_value is not None:
                values = {option.value for option in field.options or []}
                assert field.default_value in values, field.name

    def test_integer_defaults_are_within_bounds(self, config_schema: ConfigSchema) -> None:
        """An integer field's default must lie within its min and max values."""
        for field in config_schema.fields:
            default = field.default_value
            if field.type != "integer" or default is None:
                continue
            assert isinstance(default, int) and not isinstance(default, bool), field.name
            if field.min_value is not None:
                assert default >= field.min_value, field.name
            if field.max_value is not None:
                assert default <= field.max_value, field.name

    def test_required_fields_without_defaults_are_not_collapsed(
        self, config_schema: ConfigSchema
    ) -> None:
        """A field the user must fill in cannot start hidden in a collapsed group."""
        collapsed = {group.id for group in config_schema.field_groups if group.collapsed_by_default}
        for field in config_schema.fields:
            if field.required and field.default_value is None:
                assert field.group not in collapsed, field.name
