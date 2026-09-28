"""Interactive REPL for investigation conversations."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory, ThreadedHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel

from dataing_cli.config import get_history_path
from dataing_cli.display import (
    format_evidence_item,
    format_hypothesis,
    format_synthesis,
    format_timestamp,
)

if TYPE_CHECKING:
    from dataing_sdk import DataingClient
    from dataing_sdk.types import InvestigationState


class DataingREPL:
    """Interactive REPL for investigation conversations.

    Provides an interactive interface for asking questions about
    investigations, viewing evidence, hypotheses, and more.

    Example:
        ```python
        from dataing_cli.repl import DataingREPL

        repl = DataingREPL(client, investigation_id)
        repl.run()
        ```
    """

    def __init__(self, client: DataingClient, investigation_id: str) -> None:
        """Initialize the REPL.

        Args:
            client: The DataingClient instance.
            investigation_id: The investigation ID to attach to.
        """
        self.client = client
        self.investigation_id = investigation_id
        self.console = Console()
        self.investigation: InvestigationState | None = None

        history_path = get_history_path()

        self.session = PromptSession(
            history=ThreadedHistory(FileHistory(str(history_path))),
            completer=self._build_completer(),
        )

    def _build_completer(self) -> NestedCompleter:
        """Build tab completer for slash commands.

        Returns:
            NestedCompleter with slash commands.
        """
        return NestedCompleter.from_nested_dict(
            {
                "/lineage": None,
                "/hypotheses": None,
                "/evidence": None,
                "/export": {"json": None, "markdown": None},
                "/help": None,
                "/quit": None,
            }
        )

    def _get_prompt(self) -> HTML:
        """Build prompt with context indicator.

        Returns:
            HTML formatted prompt string.
        """
        short_id = self.investigation_id[:8]

        # Get counts from investigation state
        evidence_count = 0
        hypothesis_count = 0

        if self.investigation:
            evidence = self.investigation.evidence or []
            evidence_count = len(evidence)
            # Count hypothesis evidence items
            hypothesis_count = sum(1 for e in evidence if e.get("kind") == "hypothesis")

        return HTML(
            f"<style fg='cyan'>[{short_id}]</style> "
            f"<style fg='#888888'>hyp:{hypothesis_count} ev:{evidence_count}</style> > "
        )

    def run(self) -> None:
        """Run the REPL loop synchronously."""
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """Async REPL loop."""
        # Initial state refresh
        await self._refresh_investigation()

        self.console.print(
            f"\n[bold cyan]Attached to investigation {self.investigation_id[:8]}...[/bold cyan]"
        )
        self.console.print("[dim]Type /help for commands, Ctrl+C to cancel, Ctrl+D to exit[/dim]\n")

        with patch_stdout():
            while True:
                try:
                    text = await self.session.prompt_async(self._get_prompt)
                    await self._handle_input(text.strip())
                except KeyboardInterrupt:
                    self.console.print("\n[dim]Interrupted. Type /quit to exit.[/dim]")
                    continue
                except EOFError:
                    break

        self.console.print("[dim]Goodbye![/dim]")

    async def _handle_input(self, text: str) -> None:
        """Route input to handler.

        Args:
            text: The user input text.
        """
        if not text:
            return

        if text.startswith("/"):
            await self._handle_command(text)
        else:
            await self._handle_message(text)

    async def _handle_command(self, text: str) -> None:
        """Handle slash command.

        Args:
            text: The command string (e.g., "/help").
        """
        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:]

        handlers = {
            "/lineage": self._cmd_lineage,
            "/hypotheses": self._cmd_hypotheses,
            "/evidence": self._cmd_evidence,
            "/export": self._cmd_export,
            "/help": self._cmd_help,
            "/quit": self._cmd_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(args)
        else:
            self.console.print(f"[red]Unknown command: {cmd}[/red]")
            self.console.print("[dim]Type /help to see available commands.[/dim]")

    async def _handle_message(self, message: str) -> None:
        """Give the running investigation this context and stream what it does next.

        Args:
            message: The context to add.
        """
        steer = self.client.steer(self.investigation_id, message)
        if steer.status == "rejected":
            self.console.print(f"[yellow]Not applied:[/yellow] {steer.outcome}")
            return

        # Stream response with Rich Live display
        panels: list[Any] = []
        start_time = time.time()
        hypothesis_idx = 0

        # Header showing the question
        panels.append(
            Panel(
                f"[bold]You:[/bold] {message}",
                border_style="dim",
            )
        )

        with Live(
            Group(*panels),
            refresh_per_second=4,
            transient=False,
            console=self.console,
        ) as live:
            try:
                for event in self.client.stream_run(self.investigation_id):
                    event_type = event.event
                    elapsed = format_timestamp(start_time)

                    if event_type == "hypothesis_testing":
                        hypothesis_idx += 1
                        panels.append(format_hypothesis(event, hypothesis_idx, elapsed))
                        live.update(Group(*panels))

                    elif event_type in ("run_evidence", "hypothesis_result"):
                        panels.append(format_evidence_item(event, elapsed))
                        live.update(Group(*panels))

                    elif event_type == "run_completed":
                        panels.append(format_synthesis(event, elapsed))
                        live.update(Group(*panels))
                        break

                    elif event_type == "run_failed":
                        error = event.data.get("error", "Unknown error")
                        panels.append(
                            Panel(
                                f"[red]-[/red] {error}",
                                title=f"{elapsed} Failed",
                                border_style="red",
                            )
                        )
                        live.update(Group(*panels))
                        break

                    elif event_type == "run_heartbeat":
                        live.refresh()

                    elif event_type == "awaiting_user":
                        # Investigation is waiting for more input
                        panels.append(
                            Panel(
                                "[dim]Investigation processed your message.[/dim]",
                                title=f"{elapsed} Ready",
                                border_style="green",
                            )
                        )
                        live.update(Group(*panels))
                        break

                    if event.is_terminal:
                        break

            except KeyboardInterrupt:
                elapsed = format_timestamp(start_time)
                panels.append(
                    Panel(
                        "[yellow]Stream interrupted[/yellow]",
                        title=f"{elapsed} Cancelled",
                        border_style="yellow",
                    )
                )
                live.update(Group(*panels))

        # Refresh state after response
        await self._refresh_investigation()

    async def _refresh_investigation(self) -> None:
        """Refresh cached investigation state."""
        try:
            self.investigation = self.client.get_investigation(self.investigation_id)
        except Exception as e:
            self.console.print(f"[yellow]Could not refresh state: {e}[/yellow]")

    # Slash command implementations
    async def _cmd_lineage(self, args: list[str]) -> None:
        """Show lineage graph for investigation datasource."""
        await self._refresh_investigation()

        # Lineage requires investigation context which may not be available
        self.console.print("[dim]Lineage display is not yet available.[/dim]")
        self.console.print("[dim]Use the Dataing web UI to view lineage graphs.[/dim]")

    async def _cmd_hypotheses(self, args: list[str]) -> None:
        """Show hypotheses and their status."""
        await self._refresh_investigation()

        if not self.investigation:
            self.console.print("[red]Could not load investigation state.[/red]")
            return

        evidence = self.investigation.evidence or []

        # Filter for hypothesis evidence items
        hypotheses = [e for e in evidence if e.get("kind") == "hypothesis"]

        if not hypotheses:
            self.console.print("[dim]No hypotheses yet.[/dim]")
            return

        self.console.print(f"\n[bold]Hypotheses ({len(hypotheses)})[/bold]\n")

        for i, hyp in enumerate(hypotheses, 1):
            # Format hypothesis display
            text = hyp.get("hypothesis_text", hyp.get("hypothesis", "Unknown"))
            verdict = hyp.get("verdict", "pending")
            confidence = hyp.get("confidence", 0)

            # Color based on verdict
            if verdict == "confirmed" or verdict == "supported":
                color = "green"
                icon = "+"
            elif verdict == "rejected" or verdict == "refuted":
                color = "red"
                icon = "-"
            else:
                color = "yellow"
                icon = "?"

            conf_pct = confidence * 100 if confidence <= 1 else confidence

            self.console.print(
                Panel(
                    f"[{color}]{icon}[/{color}] {text}\n"
                    f"[dim]Verdict: {verdict} | Confidence: {conf_pct:.0f}%[/dim]",
                    title=f"Hypothesis {i}",
                    border_style=color,
                )
            )

    async def _cmd_evidence(self, args: list[str]) -> None:
        """Show collected evidence items."""
        await self._refresh_investigation()

        if not self.investigation:
            self.console.print("[red]Could not load investigation state.[/red]")
            return

        evidence = self.investigation.evidence or []

        if not evidence:
            self.console.print("[dim]No evidence collected yet.[/dim]")
            return

        self.console.print(f"\n[bold]Evidence ({len(evidence)})[/bold]\n")

        for i, ev in enumerate(evidence, 1):
            kind = ev.get("kind", "unknown")
            supports = ev.get("supports_hypothesis", ev.get("supports"))
            interpretation = ev.get("interpretation", ev.get("finding", ""))
            confidence = ev.get("confidence", 0)

            # Color based on support verdict
            if supports is True:
                color = "green"
                verdict = "Supports"
            elif supports is False:
                color = "red"
                verdict = "Refutes"
            else:
                color = "yellow"
                verdict = "Inconclusive"

            # Build content
            content_parts = []
            if interpretation:
                content_parts.append(str(interpretation))

            if confidence:
                conf_pct = confidence * 100 if confidence <= 1 else confidence
                content_parts.append(f"[dim]Confidence: {conf_pct:.0f}%[/dim]")

            # Add SQL if present (truncated)
            sql = ev.get("query", ev.get("sql", ""))
            if sql:
                sql_preview = str(sql)[:200]
                if len(str(sql)) > 200:
                    sql_preview += "..."
                content_parts.append(f"[dim]SQL: {sql_preview}[/dim]")

            content = "\n".join(content_parts) if content_parts else "[dim]Evidence collected[/dim]"

            self.console.print(
                Panel(
                    content,
                    title=f"#{i} {kind.replace('_', ' ').title()} ({verdict})",
                    border_style=color,
                )
            )

    async def _cmd_export(self, args: list[str]) -> None:
        """Export investigation without leaving REPL."""
        format_type = args[0].lower() if args else "markdown"

        if format_type not in ("json", "markdown"):
            self.console.print("[red]Usage: /export [json|markdown][/red]")
            return

        await self._refresh_investigation()

        if not self.investigation:
            self.console.print("[red]Could not load investigation state.[/red]")
            return

        from dataing_cli.export import render_json, render_markdown

        # Convert InvestigationState to dict for rendering
        inv_dict = {
            "investigation_id": self.investigation.investigation_id,
            "status": self.investigation.status,
            "main_branch": {
                "status": self.investigation.main_branch.status,
                "current_step": self.investigation.main_branch.current_step,
                "synthesis": self.investigation.main_branch.synthesis,
                "evidence": self.investigation.main_branch.evidence,
            },
        }

        if format_type == "json":
            output = render_json(inv_dict)
            self.console.print(output)
        else:
            output = render_markdown(inv_dict)
            self.console.print(output)

    async def _cmd_help(self, args: list[str]) -> None:
        """Show help."""
        help_text = """
[bold]Available Commands[/bold]

  /lineage      Show lineage graph for investigation datasource
  /hypotheses   Show hypotheses and their status
  /evidence     Show collected evidence items
  /export       Export investigation (json or markdown)
  /help         Show this help
  /quit         Exit interactive mode

[dim]Type any text to send a message to the investigation.[/dim]
"""
        self.console.print(help_text)

    async def _cmd_quit(self, args: list[str]) -> None:
        """Exit REPL."""
        raise EOFError()
