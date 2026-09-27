"""Every OpenAPI schema component of the EE app must come from a uniquely named model.

When two models share a class name, FastAPI gives one the plain component name and
the other a module-qualified one (``dataing_ee__entrypoints__api__routes__audit__Foo``).
Which model gets the plain name depends on set iteration order, so the exported spec
and the frontend client generated from it change from run to run.
"""

from typing import Any

import pytest
from dataing_ee.entrypoints.api.app import create_ee_app
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """Build the EE app (CE routes plus EE routes) once for this module."""
    return create_ee_app()


def _module_qualified_names(spec: dict[str, Any]) -> list[str]:
    """Return schema component names that were qualified with a module path."""
    return sorted(name for name in spec["components"]["schemas"] if "__" in name)


@pytest.mark.parametrize(
    "separate_input_output_schemas",
    [True, False],
    ids=["exported", "single-mode"],
)
def test_no_two_models_share_a_schema_name(
    app: FastAPI, separate_input_output_schemas: bool
) -> None:
    """Rename one of the models behind any module-qualified name.

    The single-mode pass also catches a request-only and a response-only model that
    share a name, which the exported spec disguises as ``Foo-Input`` / ``Foo-Output``.
    """
    spec = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        separate_input_output_schemas=separate_input_output_schemas,
    )

    assert _module_qualified_names(spec) == []
