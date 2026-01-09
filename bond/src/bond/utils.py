"""Utility functions for Bond agents.

Includes helpers for WebSocket/SSE streaming integration.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from bond.agent import StreamHandlers


class WebSocketProtocol(Protocol):
    """Protocol for WebSocket-like objects."""

    async def send_json(self, data: dict[str, Any]) -> None:
        """Send JSON data over the WebSocket."""
        ...


def create_websocket_handlers(
    send: Callable[[dict[str, Any]], Awaitable[None]],
) -> StreamHandlers:
    """Create StreamHandlers that send events over WebSocket/SSE.

    This creates handlers that serialize all streaming events to JSON
    and send them via the provided async send function.

    Args:
        send: Async function to send JSON data (e.g., ws.send_json).

    Returns:
        StreamHandlers configured for WebSocket streaming.

    Example:
        async def websocket_handler(ws: WebSocket):
            handlers = create_websocket_handlers(ws.send_json)
            await agent.ask("Check the database", handlers=handlers)

    Message Types:
        - {"t": "block_start", "kind": str, "idx": int}
        - {"t": "block_end", "kind": str, "idx": int}
        - {"t": "text", "c": str}
        - {"t": "thinking", "c": str}
        - {"t": "tool_delta", "n": str, "a": str}
        - {"t": "tool_exec", "id": str, "name": str, "args": dict}
        - {"t": "tool_result", "id": str, "name": str, "result": str}
        - {"t": "complete", "data": Any}
    """
    # We need to handle the sync callbacks by scheduling async sends
    import asyncio

    def _send_sync(data: dict[str, Any]) -> None:
        """Schedule async send from sync callback."""
        try:
            loop = asyncio.get_running_loop()
            coro = send(data)
            loop.create_task(coro)  # type: ignore[arg-type]
        except RuntimeError:
            # No running loop - this shouldn't happen in normal usage
            pass

    return StreamHandlers(
        on_block_start=lambda kind, idx: _send_sync({
            "t": "block_start",
            "kind": kind,
            "idx": idx,
        }),
        on_block_end=lambda kind, idx: _send_sync({
            "t": "block_end",
            "kind": kind,
            "idx": idx,
        }),
        on_text_delta=lambda txt: _send_sync({
            "t": "text",
            "c": txt,
        }),
        on_thinking_delta=lambda txt: _send_sync({
            "t": "thinking",
            "c": txt,
        }),
        on_tool_call_delta=lambda name, args: _send_sync({
            "t": "tool_delta",
            "n": name,
            "a": args,
        }),
        on_tool_execute=lambda tool_id, name, args: _send_sync({
            "t": "tool_exec",
            "id": tool_id,
            "name": name,
            "args": args,
        }),
        on_tool_result=lambda tool_id, name, result: _send_sync({
            "t": "tool_result",
            "id": tool_id,
            "name": name,
            "result": result,
        }),
        on_complete=lambda data: _send_sync({
            "t": "complete",
            "data": data,
        }),
    )


def create_sse_handlers(
    send: Callable[[str, dict[str, Any]], Awaitable[None]],
) -> StreamHandlers:
    r"""Create StreamHandlers for Server-Sent Events (SSE).

    Similar to WebSocket handlers but uses SSE event format.

    Args:
        send: Async function to send SSE event (event_type, data).

    Returns:
        StreamHandlers configured for SSE streaming.

    Example:
        async def sse_handler(request):
            async def send_sse(event: str, data: dict):
                await response.write(f"event: {event}\ndata: {json.dumps(data)}\n\n")

            handlers = create_sse_handlers(send_sse)
            await agent.ask("Query", handlers=handlers)
    """
    import asyncio

    def _send_sync(event: str, data: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
            coro = send(event, data)
            loop.create_task(coro)  # type: ignore[arg-type]
        except RuntimeError:
            pass

    return StreamHandlers(
        on_block_start=lambda kind, idx: _send_sync("block_start", {"kind": kind, "idx": idx}),
        on_block_end=lambda kind, idx: _send_sync("block_end", {"kind": kind, "idx": idx}),
        on_text_delta=lambda txt: _send_sync("text", {"content": txt}),
        on_thinking_delta=lambda txt: _send_sync("thinking", {"content": txt}),
        on_tool_call_delta=lambda n, a: _send_sync("tool_delta", {"name": n, "args": a}),
        on_tool_execute=lambda i, n, a: _send_sync("tool_exec", {"id": i, "name": n, "args": a}),
        on_tool_result=lambda i, n, r: _send_sync("tool_result", {"id": i, "name": n, "result": r}),
        on_complete=lambda data: _send_sync("complete", {"data": data}),
    )


def create_print_handlers(
    *,
    show_thinking: bool = False,
    show_tool_args: bool = False,
) -> StreamHandlers:
    """Create StreamHandlers that print to console.

    Useful for CLI applications and debugging.

    Args:
        show_thinking: Whether to print thinking/reasoning content.
        show_tool_args: Whether to print tool argument deltas.

    Returns:
        StreamHandlers configured for console output.

    Example:
        handlers = create_print_handlers(show_thinking=True)
        await agent.ask("Hello", handlers=handlers)
    """
    return StreamHandlers(
        on_block_start=lambda kind, idx: print(f"\n[{kind} block #{idx}]", end=""),
        on_text_delta=lambda txt: print(txt, end="", flush=True),
        on_thinking_delta=(
            (lambda txt: print(f"[think: {txt}]", end="", flush=True))
            if show_thinking
            else None
        ),
        on_tool_call_delta=(
            (lambda n, a: print(f"[tool: {n}{a}]", end="", flush=True))
            if show_tool_args
            else None
        ),
        on_tool_execute=lambda i, name, args: print(f"\n[Running {name}...]", flush=True),
        on_tool_result=lambda i, name, res: print(
            f"[{name} returned: {res[:100]}{'...' if len(res) > 100 else ''}]",
            flush=True,
        ),
        on_complete=lambda data: print("\n[Complete]", flush=True),
    )
