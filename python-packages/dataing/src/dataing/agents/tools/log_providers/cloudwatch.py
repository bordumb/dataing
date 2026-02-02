"""CloudWatch Logs provider.

Reads logs from AWS CloudWatch Logs using IAM role authentication.
"""

from __future__ import annotations

import asyncio
import logging
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


class CloudWatchLogProvider(BaseLogProvider):
    """Log provider for AWS CloudWatch Logs.

    Reads logs from CloudWatch using boto3 with IAM role authentication.
    """

    def __init__(
        self,
        config: LogProviderConfig,
        region_name: str | None = None,
        log_group_prefix: str | None = None,
    ) -> None:
        """Initialize the CloudWatch log provider.

        Args:
            config: Provider configuration.
            region_name: AWS region (default: from environment).
            log_group_prefix: Prefix to filter log groups.
        """
        super().__init__(config)
        self._region = region_name
        self._log_group_prefix = log_group_prefix
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create CloudWatch Logs client.

        Returns:
            boto3 logs client.

        Raises:
            ImportError: If boto3 not installed.
            RuntimeError: If AWS connection fails.
        """
        if self._client is not None:
            return self._client

        try:
            import boto3
        except ImportError as err:
            raise ImportError(
                "boto3 is required for CloudWatch log provider. " "Install with: pip install boto3"
            ) from err

        try:
            kwargs: dict[str, Any] = {}
            if self._region:
                kwargs["region_name"] = self._region

            self._client = boto3.client("logs", **kwargs)
            return self._client

        except Exception as e:
            raise RuntimeError(f"Failed to create CloudWatch client: {e}") from e

    @property
    def source_type(self) -> LogSource:
        """Get the source type."""
        return LogSource.CLOUDWATCH

    async def list_sources(self) -> list[str]:
        """List available log groups.

        Returns:
            List of log group names.
        """
        try:
            client = self._get_client()

            loop = asyncio.get_event_loop()

            kwargs: dict[str, Any] = {}
            if self._log_group_prefix:
                kwargs["logGroupNamePrefix"] = self._log_group_prefix

            response = await loop.run_in_executor(
                None, lambda: client.describe_log_groups(**kwargs)
            )

            return [lg["logGroupName"] for lg in response.get("logGroups", [])]

        except Exception:
            logger.exception("Failed to list CloudWatch log groups")
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
        """Get logs from a CloudWatch log group.

        Args:
            source_id: Log group name.
            start_time: Start of time range.
            end_time: End of time range.
            max_entries: Maximum entries to return.
            filter_pattern: CloudWatch Insights filter pattern.
            next_token: Token for pagination.

        Returns:
            LogResult with entries.
        """
        try:
            client = self._get_client()
            loop = asyncio.get_event_loop()

            # Build request parameters
            kwargs: dict[str, Any] = {
                "logGroupName": source_id,
                "limit": min(max_entries, 10000),  # CloudWatch max
            }

            if start_time:
                kwargs["startTime"] = int(start_time.timestamp() * 1000)
            if end_time:
                kwargs["endTime"] = int(end_time.timestamp() * 1000)
            if filter_pattern:
                kwargs["filterPattern"] = filter_pattern
            if next_token:
                kwargs["nextToken"] = next_token

            # Fetch events
            response = await loop.run_in_executor(None, lambda: client.filter_log_events(**kwargs))

            entries: list[LogEntry] = []
            for event in response.get("events", []):
                timestamp = None
                if "timestamp" in event:
                    timestamp = datetime.fromtimestamp(event["timestamp"] / 1000)

                entries.append(
                    LogEntry(
                        timestamp=timestamp,
                        message=event.get("message", ""),
                        source=source_id,
                        metadata={
                            "log_stream": event.get("logStreamName"),
                            "event_id": event.get("eventId"),
                        },
                    )
                )

            return LogResult(
                entries=entries,
                source=source_id,
                truncated="nextToken" in response,
                next_token=response.get("nextToken"),
            )

        except Exception as e:
            logger.exception(f"Failed to get CloudWatch logs: {source_id}")
            return LogResult(
                entries=[],
                source=source_id,
                error=f"Failed to get CloudWatch logs: {e}",
            )

    async def list_log_streams(
        self,
        log_group: str,
        prefix: str | None = None,
        max_streams: int = 50,
    ) -> list[dict[str, Any]]:
        """List log streams in a log group.

        Args:
            log_group: Log group name.
            prefix: Stream name prefix to filter.
            max_streams: Maximum streams to return.

        Returns:
            List of log stream info dicts.
        """
        try:
            client = self._get_client()
            loop = asyncio.get_event_loop()

            kwargs: dict[str, Any] = {
                "logGroupName": log_group,
                "limit": max_streams,
                "orderBy": "LastEventTime",
                "descending": True,
            }

            if prefix:
                kwargs["logStreamNamePrefix"] = prefix

            response = await loop.run_in_executor(
                None, lambda: client.describe_log_streams(**kwargs)
            )

            return [
                {
                    "name": stream["logStreamName"],
                    "last_event": datetime.fromtimestamp(
                        stream.get("lastEventTimestamp", 0) / 1000
                    ).isoformat()
                    if stream.get("lastEventTimestamp")
                    else None,
                    "stored_bytes": stream.get("storedBytes", 0),
                }
                for stream in response.get("logStreams", [])
            ]

        except Exception as e:
            logger.exception(f"Failed to list log streams: {log_group}")
            return [{"error": str(e)}]


def create_cloudwatch_provider(
    name: str = "CloudWatch",
    region_name: str | None = None,
    log_group_prefix: str | None = None,
) -> CloudWatchLogProvider:
    """Create a CloudWatch log provider.

    Args:
        name: Provider name.
        region_name: AWS region.
        log_group_prefix: Prefix to filter log groups.

    Returns:
        Configured CloudWatchLogProvider.
    """
    config = LogProviderConfig(
        source=LogSource.CLOUDWATCH,
        name=name,
        settings={
            "region": region_name,
            "log_group_prefix": log_group_prefix,
        },
    )

    return CloudWatchLogProvider(
        config=config,
        region_name=region_name,
        log_group_prefix=log_group_prefix,
    )
