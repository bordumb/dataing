"""DataingAssistant - Unified AI assistant for Dataing platform.

Provides help with infrastructure debugging, data questions, and investigation support.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bond import BondAgent, StreamHandlers
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.tools import Tool

from dataing.agents.tools.docker import (
    find_unhealthy_docker_containers,
    get_docker_container_health,
    get_docker_container_stats,
    get_docker_container_status,
    list_docker_containers,
)
from dataing.agents.tools.local_files import (
    list_directory,
    read_local_file,
    search_in_files,
)
from dataing.agents.tools.log_providers import (
    LocalFileLogProvider,
    LogProviderConfig,
)
from dataing.agents.tools.log_providers.base import LogSource

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)

# System prompt for the Dataing Assistant
ASSISTANT_SYSTEM_PROMPT = """You are the Dataing Assistant, an AI helper for the Dataing platform.

## Your Capabilities

You can help users with:
1. **Infrastructure debugging** - Check Docker containers, read logs, inspect config files
2. **Data questions** - Query connected datasources, explain schemas
3. **Investigation support** - Provide context on investigations, explain findings
4. **Code understanding** - Read local files, search codebases, check git history

## Dataing Platform Overview

Dataing is an autonomous data quality investigation platform that:
- Detects anomalies in data pipelines
- Generates hypotheses about root causes using LLMs
- Tests hypotheses via SQL queries in parallel
- Synthesizes findings into root cause analysis

Key components:
- **Investigations**: Automated root cause analysis workflows
- **Datasources**: Connected databases and data warehouses
- **Alerts**: Anomaly notifications from monitoring
- **Agents**: LLM-powered analysis (you are one!)

## Your Approach

1. **Be helpful and concise** - Give direct answers with enough context
2. **Explain your reasoning** - When debugging, explain what you're checking and why
3. **Suggest next steps** - After diagnosing an issue, recommend fixes
4. **Ask clarifying questions** - If the request is ambiguous, ask for more details
5. **Stay in scope** - If asked about something outside your capabilities, politely decline

## Tool Usage

You have access to tools for:
- Reading local files (with security restrictions on sensitive files)
- Searching across files (grep-like functionality)
- Checking Docker container status and logs
- Querying connected datasources

When using tools:
- Explain what you're doing: "Let me check the Docker containers..."
- Summarize findings: "I found 3 containers, 1 is unhealthy..."
- Handle errors gracefully: If a tool fails, explain what happened

## Response Format

- Use markdown for formatting
- Use code blocks with language hints for code/configs
- Use bullet points for lists
- Keep responses focused and actionable
"""


class DataingAssistant:
    """Unified AI assistant for Dataing platform.

    Provides help with:
    - Infrastructure debugging (Docker, logs, config files)
    - Data questions via connected datasources
    - Investigation context and findings
    - Git history and code understanding
    """

    def __init__(
        self,
        api_key: str,
        tenant_id: UUID | str,
        *,
        model: str = "claude-sonnet-4-20250514",
        repo_path: str | Path = ".",
        github_token: str | None = None,
        log_directories: list[str] | None = None,
        max_retries: int = 2,
    ) -> None:
        """Initialize the Dataing Assistant.

        Args:
            api_key: Anthropic API key.
            tenant_id: Tenant ID for multi-tenancy isolation.
            model: LLM model to use (default: Claude Sonnet for speed).
            repo_path: Path to local git repository.
            github_token: Optional GitHub token for git tools.
            log_directories: Directories to scan for log files.
            max_retries: Max retries on LLM errors.
        """
        self._tenant_id = str(tenant_id)
        self._repo_path = Path(repo_path)
        self._github_token = github_token

        # Setup LLM provider
        provider = AnthropicProvider(api_key=api_key)
        self._model = AnthropicModel(model, provider=provider)

        # Setup log provider for local files
        self._log_provider = self._create_log_provider(log_directories or [])

        # Build tool list
        tools = self._build_tools()

        # Create the agent
        self._agent: BondAgent[str, None] = BondAgent(
            name="dataing-assistant",
            instructions=ASSISTANT_SYSTEM_PROMPT,
            model=self._model,
            tools=tools,
            max_retries=max_retries,
        )

    def _create_log_provider(self, log_directories: list[str]) -> LocalFileLogProvider:
        """Create a local file log provider.

        Args:
            log_directories: Directories to scan for logs.

        Returns:
            Configured LocalFileLogProvider.
        """
        config = LogProviderConfig(
            source=LogSource.LOCAL_FILE,
            name="Local Logs",
            settings={"directories": log_directories},
        )
        return LocalFileLogProvider(
            config=config,
            log_directories=[Path(d) for d in log_directories],
        )

    def _build_tools(self) -> list[Tool[Any]]:
        """Build the list of tools for the assistant.

        Returns:
            List of PydanticAI Tool instances.
        """
        tools: list[Tool[Any]] = []

        # Local file tools
        tools.append(Tool(read_local_file))
        tools.append(Tool(search_in_files))
        tools.append(Tool(list_directory))

        # Docker tools
        tools.append(Tool(list_docker_containers))
        tools.append(Tool(get_docker_container_status))
        tools.append(Tool(get_docker_container_health))
        tools.append(Tool(get_docker_container_stats))
        tools.append(Tool(find_unhealthy_docker_containers))

        # Log tools
        tools.append(Tool(self._get_logs))
        tools.append(Tool(self._search_logs))
        tools.append(Tool(self._get_recent_errors))

        # Git tools (from bond-agent) - loaded lazily if available
        git_tools = self._load_git_tools()
        tools.extend(git_tools)

        return tools

    def _load_git_tools(self) -> list[Tool[Any]]:
        """Load git tools from bond-agent if available.

        Returns:
            List of git-related tools.
        """
        tools: list[Tool[Any]] = []

        try:
            from bond.tools.githunter import GitHunterAdapter, githunter_toolset

            # Create adapter for local repo
            adapter = GitHunterAdapter(repo_path=str(self._repo_path))
            toolset = githunter_toolset(adapter)
            tools.extend(toolset)
            logger.info("Loaded githunter toolset")
        except ImportError:
            logger.debug("githunter tools not available")
        except Exception as e:
            logger.warning(f"Failed to load githunter tools: {e}")

        if self._github_token:
            try:
                from bond.tools.github import GitHubAdapter, github_toolset

                adapter = GitHubAdapter(token=self._github_token)
                toolset = github_toolset(adapter)
                tools.extend(toolset)
                logger.info("Loaded github toolset")
            except ImportError:
                logger.debug("github tools not available")
            except Exception as e:
                logger.warning(f"Failed to load github tools: {e}")

        return tools

    async def _get_logs(
        self,
        source: str,
        max_entries: int = 50,
        filter_pattern: str | None = None,
    ) -> str:
        """Get logs from a source file.

        Args:
            source: Path to the log file.
            max_entries: Maximum entries to return.
            filter_pattern: Optional pattern to filter logs.

        Returns:
            Formatted log entries or error message.
        """
        result = await self._log_provider.get_logs(
            source_id=source,
            max_entries=max_entries,
            filter_pattern=filter_pattern,
        )

        if not result.success:
            return f"Error reading logs: {result.error}"

        if not result.entries:
            return f"No log entries found in {source}"

        lines = [f"Logs from {source} ({len(result.entries)} entries):"]
        for entry in result.entries:
            ts = entry.timestamp.isoformat() if entry.timestamp else "?"
            level = f"[{entry.level}]" if entry.level else ""
            lines.append(f"  {ts} {level} {entry.message[:200]}")

        if result.truncated:
            lines.append(f"  ... (truncated, {result.next_token} more available)")

        return "\n".join(lines)

    async def _search_logs(
        self,
        pattern: str,
        source: str | None = None,
        max_entries: int = 20,
    ) -> str:
        """Search logs for a pattern.

        Args:
            pattern: Search pattern.
            source: Optional specific log file to search.
            max_entries: Maximum entries to return.

        Returns:
            Formatted search results.
        """
        result = await self._log_provider.search_logs(
            pattern=pattern,
            source_id=source,
            max_entries=max_entries,
        )

        if not result.success:
            return f"Error searching logs: {result.error}"

        if not result.entries:
            return f"No log entries matching '{pattern}'"

        lines = [f"Found {len(result.entries)} entries matching '{pattern}':"]
        for entry in result.entries:
            ts = entry.timestamp.isoformat() if entry.timestamp else "?"
            src = entry.source or "?"
            lines.append(f"  [{src}] {ts}: {entry.message[:150]}")

        return "\n".join(lines)

    async def _get_recent_errors(
        self,
        source: str,
        max_entries: int = 10,
    ) -> str:
        """Get recent errors from a log file.

        Args:
            source: Path to the log file.
            max_entries: Maximum errors to return.

        Returns:
            Formatted error entries.
        """
        result = await self._log_provider.get_recent_errors(
            source_id=source,
            max_entries=max_entries,
        )

        if not result.success:
            return f"Error reading log errors: {result.error}"

        if not result.entries:
            return f"No errors found in {source}"

        lines = [f"Recent errors from {source} ({len(result.entries)} found):"]
        for entry in result.entries:
            ts = entry.timestamp.isoformat() if entry.timestamp else "?"
            lines.append(f"  {ts}: {entry.message[:200]}")
            # Include context if available
            ctx_before = entry.metadata.get("context_before", [])
            ctx_after = entry.metadata.get("context_after", [])
            if ctx_before:
                lines.append(f"    Context before: {ctx_before[-1][:100]}")
            if ctx_after:
                lines.append(f"    Context after: {ctx_after[0][:100]}")

        return "\n".join(lines)

    async def ask(
        self,
        question: str,
        *,
        session_id: str | None = None,
        handlers: StreamHandlers | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Ask the assistant a question.

        Args:
            question: The user's question or request.
            session_id: Optional session ID for conversation continuity.
            handlers: Optional streaming handlers for real-time output.
            context: Optional additional context (e.g., current investigation).

        Returns:
            The assistant's response.

        Raises:
            Exception: If the LLM call fails.
        """
        # Build user prompt with optional context
        prompt = question
        if context:
            context_str = self._format_context(context)
            prompt = f"{context_str}\n\nUser question: {question}"

        # Add session context for conversation continuity
        dynamic_instructions = None
        if session_id:
            dynamic_instructions = f"Session ID: {session_id}\nTenant ID: {self._tenant_id}"

        result = await self._agent.ask(
            prompt,
            dynamic_instructions=dynamic_instructions,
            handlers=handlers,
        )

        return str(result)

    def _format_context(self, context: dict[str, Any]) -> str:
        """Format additional context for the prompt.

        Args:
            context: Context dictionary.

        Returns:
            Formatted context string.
        """
        lines = ["## Current Context"]

        if "investigation" in context:
            inv = context["investigation"]
            lines.append(f"- Investigation: {inv.get('id', 'unknown')}")
            lines.append(f"- Status: {inv.get('status', 'unknown')}")
            if inv.get("finding"):
                lines.append(f"- Finding: {inv['finding'].get('root_cause', 'pending')}")

        if "datasource" in context:
            ds = context["datasource"]
            lines.append(f"- Connected to: {ds.get('name', 'unknown')} ({ds.get('type', '')})")

        if "recent_alerts" in context:
            alerts = context["recent_alerts"]
            lines.append(f"- Recent alerts: {len(alerts)}")

        return "\n".join(lines)


def create_assistant(
    api_key: str,
    tenant_id: UUID | str,
    **kwargs: Any,
) -> DataingAssistant:
    """Create a DataingAssistant instance.

    Args:
        api_key: Anthropic API key.
        tenant_id: Tenant ID for isolation.
        **kwargs: Additional arguments passed to DataingAssistant.

    Returns:
        Configured DataingAssistant instance.
    """
    return DataingAssistant(api_key=api_key, tenant_id=tenant_id, **kwargs)
