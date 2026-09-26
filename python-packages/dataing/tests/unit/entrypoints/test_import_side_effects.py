"""Tests that importing entrypoint modules does not build the API app.

Importing dataing.entrypoints.api.app calls create_app(), which configures logging and
telemetry for the whole process. Only the API server should pay for that.
"""

import json
import os
import subprocess
import sys


def _modules_loaded_by_import(module: str) -> set[str]:
    """Import a module in a fresh interpreter and return the names of all loaded modules.

    This test process has usually imported the API app already, so sys.modules here
    can't tell what the import itself pulls in.
    """
    code = f"import json, sys, {module}; print(json.dumps(sorted(sys.modules.copy())))"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        # Resolve imports exactly as this test process does.
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded: list[str] = json.loads(result.stdout.splitlines()[-1])
    return set(loaded)


def test_temporal_worker_does_not_import_api_package() -> None:
    """The worker loads no API module, so importing it never calls create_app()."""
    loaded = _modules_loaded_by_import("dataing.entrypoints.temporal_worker")

    api_modules = sorted(
        name
        for name in loaded
        if name == "dataing.entrypoints.api" or name.startswith("dataing.entrypoints.api.")
    )
    assert api_modules == []


def test_api_deps_does_not_import_app_module() -> None:
    """Importing the API's deps module does not load app.py, so it never calls create_app()."""
    loaded = _modules_loaded_by_import("dataing.entrypoints.api.deps")

    assert "dataing.entrypoints.api.app" not in loaded
