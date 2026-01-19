# Bond

Generic agent runtime wrapping PydanticAI with full-spectrum streaming.

## Features

- High-fidelity streaming with callbacks for every lifecycle event
- Block start/end notifications for UI rendering
- Real-time streaming of text, thinking, and tool arguments
- Tool execution and result callbacks
- Message history management
- Dynamic instruction override
- Toolset composition

## Installation

```bash
pip install bond
```

## Quick Start

```python
from bond import BondAgent, StreamHandlers, create_print_handlers
from bond.tools.memory import memory_toolset, QdrantMemoryStore

# Create agent with memory tools
agent = BondAgent(
    name="assistant",
    instructions="You are a helpful assistant with memory capabilities.",
    model="anthropic:claude-sonnet-4-20250514",
    toolsets=[memory_toolset],
    deps=QdrantMemoryStore(),  # In-memory for development
)

# Stream with console output
handlers = create_print_handlers(show_thinking=True)
response = await agent.ask("Remember my preference for dark mode", handlers=handlers)
```

## Streaming Handlers

Bond provides factory functions for common streaming scenarios:

- `create_websocket_handlers(send)` - JSON events over WebSocket
- `create_sse_handlers(send)` - Server-Sent Events format
- `create_print_handlers()` - Console output for CLI/debugging
