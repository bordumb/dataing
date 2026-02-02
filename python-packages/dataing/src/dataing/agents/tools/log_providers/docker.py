"""Docker container log provider.

Reads logs from Docker containers via the Docker API.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

from dataing.agents.tools.log_providers.base import (
    BaseLogProvider,
    LogEntry,
    LogProviderConfig,
    LogResult,
    LogSource,
)

logger = logging.getLogger(__name__)


class DockerLogProvider(BaseLogProvider):
    """Log provider for Docker containers.

    Reads logs from Docker containers using the Docker SDK.
    Supports:
    - Unix socket connection (default)
    - TCP connection with optional TLS
    - Environment-based auto-detection
    """

    def __init__(
        self,
        config: LogProviderConfig,
        docker_host: str | None = None,
    ) -> None:
        """Initialize the Docker log provider.

        Args:
            config: Provider configuration.
            docker_host: Docker host URL (default: from environment).
        """
        super().__init__(config)
        self._docker_host = docker_host
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create Docker client.

        Returns:
            Docker client instance.

        Raises:
            ImportError: If docker package not installed.
            RuntimeError: If Docker connection fails.
        """
        if self._client is not None:
            return self._client

        try:
            import docker
        except ImportError as err:
            raise ImportError(
                "docker package is required for Docker log provider. "
                "Install with: pip install docker"
            ) from err

        try:
            if self._docker_host:
                self._client = docker.DockerClient(base_url=self._docker_host)
            else:
                # Use default from environment
                self._client = docker.from_env()

            # Test connection
            self._client.ping()
            return self._client

        except Exception as e:
            raise RuntimeError(f"Failed to connect to Docker: {e}") from e

    @property
    def source_type(self) -> LogSource:
        """Get the source type."""
        return LogSource.DOCKER

    async def list_sources(self) -> list[str]:
        """List available containers.

        Returns:
            List of container names/IDs.
        """
        try:
            client = self._get_client()

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            containers = await loop.run_in_executor(None, lambda: client.containers.list(all=True))

            return [c.name for c in containers]

        except Exception:
            logger.exception("Failed to list containers")
            return []

    async def get_logs(
        self,
        source_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_entries: int = 100,
        filter_pattern: str | None = None,
        next_token: str | None = None,
    ) -> LogResult:
        """Get logs from a container.

        Args:
            source_id: Container name or ID.
            start_time: Start of time range.
            end_time: End of time range.
            max_entries: Maximum entries to return.
            filter_pattern: Pattern to filter logs.
            next_token: Timestamp to start from.

        Returns:
            LogResult with entries.
        """
        try:
            client = self._get_client()

            # Get container
            loop = asyncio.get_event_loop()
            container = await loop.run_in_executor(None, lambda: client.containers.get(source_id))

            # Build log arguments
            kwargs: dict[str, Any] = {
                "timestamps": True,
                "tail": max_entries * 2,  # Get extra for filtering
            }

            if start_time:
                kwargs["since"] = start_time
            if end_time:
                kwargs["until"] = end_time

            # Get logs
            logs = await loop.run_in_executor(
                None, lambda: container.logs(**kwargs).decode("utf-8", errors="replace")
            )

            # Parse log lines
            entries: list[LogEntry] = []
            for line in logs.splitlines():
                if not line.strip():
                    continue

                entry = self._parse_docker_log_line(line, source_id)

                # Apply pattern filter
                if filter_pattern:
                    if filter_pattern.lower() not in entry.message.lower():
                        continue

                entries.append(entry)

                if len(entries) >= max_entries:
                    break

            return LogResult(
                entries=entries,
                source=source_id,
                truncated=len(entries) >= max_entries,
            )

        except Exception as e:
            logger.exception(f"Failed to get logs for container: {source_id}")
            return LogResult(
                entries=[],
                source=source_id,
                error=f"Failed to get container logs: {e}",
            )

    async def get_container_status(self, container_id: str) -> dict[str, Any]:
        """Get container status information.

        Args:
            container_id: Container name or ID.

        Returns:
            Container status dict.
        """
        try:
            client = self._get_client()

            loop = asyncio.get_event_loop()
            container = await loop.run_in_executor(
                None, lambda: client.containers.get(container_id)
            )

            return {
                "id": container.short_id,
                "name": container.name,
                "status": container.status,
                "image": container.image.tags[0] if container.image.tags else "unknown",
                "created": container.attrs.get("Created"),
                "started": container.attrs.get("State", {}).get("StartedAt"),
                "ports": container.attrs.get("NetworkSettings", {}).get("Ports", {}),
                "health": container.attrs.get("State", {}).get("Health", {}),
            }

        except Exception as e:
            logger.exception(f"Failed to get container status: {container_id}")
            return {
                "error": str(e),
                "container": container_id,
            }

    async def list_containers_with_status(self) -> list[dict[str, Any]]:
        """List all containers with their status.

        Returns:
            List of container status dicts.
        """
        try:
            client = self._get_client()

            loop = asyncio.get_event_loop()
            containers = await loop.run_in_executor(None, lambda: client.containers.list(all=True))

            return [
                {
                    "id": c.short_id,
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                }
                for c in containers
            ]

        except Exception as e:
            logger.exception("Failed to list containers with status")
            return [{"error": str(e)}]

    def _parse_docker_log_line(self, line: str, source: str) -> LogEntry:
        """Parse a Docker log line.

        Docker logs with timestamps look like:
        2024-01-15T10:30:45.123456789Z message

        Args:
            line: Raw log line.
            source: Container name.

        Returns:
            LogEntry.
        """
        timestamp = None
        message = line
        level = None

        # Try to extract timestamp
        timestamp_pattern = r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+"
        match = re.match(timestamp_pattern, line)
        if match:
            timestamp_str = match.group(1)
            message = line[match.end() :]

            try:
                # Handle nanosecond precision
                if "." in timestamp_str:
                    # Truncate to microseconds
                    parts = timestamp_str.split(".")
                    microseconds = parts[1].rstrip("Z")[:6]
                    timestamp_str = f"{parts[0]}.{microseconds}"
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Try to detect log level
        level_patterns = [
            (r"\b(DEBUG)\b", "debug"),
            (r"\b(INFO)\b", "info"),
            (r"\b(WARN(?:ING)?)\b", "warning"),
            (r"\b(ERROR)\b", "error"),
            (r"\b(FATAL|CRITICAL)\b", "critical"),
        ]

        for pattern, level_name in level_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                level = level_name
                break

        return LogEntry(
            timestamp=timestamp,
            message=message.strip(),
            level=level,
            source=source,
        )


def create_docker_provider(
    name: str = "Docker",
    docker_host: str | None = None,
) -> DockerLogProvider:
    """Create a Docker log provider.

    Args:
        name: Provider name.
        docker_host: Docker host URL.

    Returns:
        Configured DockerLogProvider.
    """
    config = LogProviderConfig(
        source=LogSource.DOCKER,
        name=name,
        settings={"docker_host": docker_host},
    )

    return DockerLogProvider(config=config, docker_host=docker_host)
