"""Bond - Generic agent runtime.

A skilled agent that gets things done, and "bonding" = connecting.
"""

from bond.agent import BondAgent, StreamHandlers
from bond.utils import (
    create_print_handlers,
    create_sse_handlers,
    create_websocket_handlers,
)

__version__ = "0.1.0"

__all__ = [
    # Core
    "BondAgent",
    "StreamHandlers",
    # Utilities
    "create_websocket_handlers",
    "create_sse_handlers",
    "create_print_handlers",
]
