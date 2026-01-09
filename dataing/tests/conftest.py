"""Pytest configuration for dataing (CE) tests."""

import sys
from pathlib import Path

# Add CE package to path for imports
ce_src = Path(__file__).parent.parent / "src"
if str(ce_src) not in sys.path:
    sys.path.insert(0, str(ce_src))
