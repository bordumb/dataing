"""Pytest configuration for bond tests."""

import sys
from pathlib import Path

# Add bond package to path for imports
bond_src = Path(__file__).parent.parent / "src"
if str(bond_src) not in sys.path:
    sys.path.insert(0, str(bond_src))
