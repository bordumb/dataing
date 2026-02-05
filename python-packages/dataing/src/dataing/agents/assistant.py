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

## CRITICAL: Investigation Before Advice

You have tools. USE THEM. Never give generic troubleshooting advice.

When a user asks about infrastructure, data, or debugging:
1. FIRST use your tools to investigate the actual system state
2. THEN provide findings based on evidence you gathered
3. NEVER respond with generic advice like "check your config" - that's useless

## Your Capabilities

- **Infrastructure debugging** - Docker containers, logs, config files
- **Data questions** - Connected datasources, schemas
- **Investigation support** - Context on investigations, findings
- **Code understanding** - Local files, search, git history

## Investigation Methodology

For debugging questions, follow this pattern:

1. **Observe** - Use tools to see actual state:
   - `list_docker_containers()` - What's running?
   - `get_docker_container_status("name")` - Container details
   - `find_unhealthy_docker_containers()` - Any problems?

2. **Gather evidence** - Read relevant files:
   - `list_directory("demo/")` - What config files exist?
   - `read_local_file("path")` - Read the actual config
   - `search_in_files("keyword", "directory")` - Find related code

3. **Analyze** - Look for discrepancies between:
   - What the config says should happen
   - What's actually happening (container state, logs)

4. **Report** - Share specific findings with evidence

## Allowed Directories

Use these paths (NOT "." which will be blocked):
- `demo/` - Docker configs, init scripts, fixtures
- `python-packages/` - Backend Python code
- `frontend/` - Frontend React code
- `docs/` - Documentation

## Page Awareness

You receive context about what page the user is currently viewing in the Dataing UI.
Use this to:
- Answer "what am I looking at?" by describing the page and its data
- Diagnose frontend errors from the "Recent Frontend Errors" section
- Provide page-specific help based on the page type
- Reference relevant entities (investigation IDs, dataset names, etc.) without asking

## Response Format

- Use markdown formatting
- Code blocks with language hints
- Show what you found, not generic advice
- Include specific file paths and line numbers when relevant
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
        logger.info(f"DataingAssistant initialized with {len(tools)} tools")
        for tool in tools:
            logger.info(f"  - Tool: {tool.name}")

        # Create the agent
        self._agent: BondAgent[str, None] = BondAgent(
            name="dataing-assistant",
            instructions=ASSISTANT_SYSTEM_PROMPT,
            model=self._model,
            toolsets=[tools],
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
            from bond.tools.githunter import githunter_toolset

            # githunter_toolset is already a list of tools
            tools.extend(githunter_toolset)
            logger.info("Loaded githunter toolset")
        except ImportError:
            logger.debug("githunter tools not available")
        except Exception as e:
            logger.warning(f"Failed to load githunter tools: {e}")

        if self._github_token:
            try:
                from bond.tools.github import github_toolset

                # github_toolset is already a list of tools
                tools.extend(github_toolset)
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

        # Page context (what the user is currently viewing)
        if "page_context" in context:
            pc = context["page_context"]
            lines.append("")
            lines.append("### Current Page")
            if pc.get("page_title"):
                lines.append(f"- Page: {pc['page_title']}")
            lines.append(f"- Route: {pc.get('route', 'unknown')}")
            lines.append(f"- Page type: {pc.get('page_type', 'unknown')}")

            # Include page-specific data
            page_data = pc.get("page_data", {})
            for key, value in page_data.items():
                lines.append(f"- {key}: {value}")

            # Include route params
            route_params = pc.get("route_params", {})
            for key, value in route_params.items():
                lines.append(f"- {key}: {value}")

            # Include recent frontend errors
            page_errors = pc.get("errors", [])
            if page_errors:
                lines.append("")
                lines.append("### Recent Frontend Errors")
                for err in page_errors[-5:]:
                    err_type = err.get("type", "unknown").upper()
                    msg = err.get("message", "Unknown error")
                    status = err.get("status")
                    url = err.get("url")
                    prefix = f"[{err_type}]"
                    detail = msg
                    if status:
                        detail = f"HTTP {status}: {msg}"
                    lines.append(f"- {prefix} {detail}")
                    if url:
                        lines.append(f"  Endpoint: {url}")

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
