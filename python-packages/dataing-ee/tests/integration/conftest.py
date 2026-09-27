"""Shared fixtures for EE integration tests.

The migrated-database fixtures are defined once, in the CE integration conftest.
Both packages have a `tests.integration` package, so that module cannot be
imported by name; it is loaded from its path instead.
"""

import importlib.util
from pathlib import Path

_CE_CONFTEST = Path(__file__).resolve().parents[3] / "dataing/tests/integration/conftest.py"
_spec = importlib.util.spec_from_file_location("dataing_ce_integration_conftest", _CE_CONFTEST)
assert _spec is not None and _spec.loader is not None
_ce_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ce_conftest)

migrated_dsn = _ce_conftest.migrated_dsn
migrated_db = _ce_conftest.migrated_db
