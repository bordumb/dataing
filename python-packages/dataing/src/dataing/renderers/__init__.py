"""Test renderers for multiple data quality frameworks.

This package provides renderers to convert abstract DataQualityTest objects
into concrete test definitions for various frameworks:
- Great Expectations (GX): JSON expectation suite
- dbt: schema.yml test definitions
- Soda: SodaCL check YAML
- SQL: Raw assertion queries
"""

from dataing.renderers.base import BaseRenderer, RenderFormat
from dataing.renderers.dbt import DbtRenderer
from dataing.renderers.gx import GXRenderer
from dataing.renderers.soda import SodaRenderer
from dataing.renderers.sql import SQLRenderer

__all__ = [
    "BaseRenderer",
    "RenderFormat",
    "GXRenderer",
    "DbtRenderer",
    "SodaRenderer",
    "SQLRenderer",
    "get_renderer",
]


def get_renderer(format: RenderFormat | str) -> BaseRenderer:
    """Get a renderer instance for the specified format.

    Args:
        format: The output format (gx, dbt, soda, sql).

    Returns:
        A renderer instance.

    Raises:
        ValueError: If the format is not supported.
    """
    if isinstance(format, str):
        try:
            format = RenderFormat(format.lower())
        except ValueError as e:
            raise ValueError(f"Unsupported format: {format}") from e

    renderers: dict[RenderFormat, type[GXRenderer | DbtRenderer | SodaRenderer | SQLRenderer]] = {
        RenderFormat.GX: GXRenderer,
        RenderFormat.DBT: DbtRenderer,
        RenderFormat.SODA: SodaRenderer,
        RenderFormat.SQL: SQLRenderer,
    }

    renderer_class = renderers.get(format)
    if renderer_class is None:
        raise ValueError(f"Unsupported format: {format}")

    return renderer_class()
