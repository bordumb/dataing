"""Slack notification adapter."""
import json
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class SlackConfig:
    """Slack configuration."""

    webhook_url: str
    channel: str | None = None  # Override default channel
    username: str = "DataDr"
    icon_emoji: str = ":microscope:"
    timeout_seconds: int = 30


class SlackNotifier:
    """Delivers notifications to Slack via incoming webhooks."""

    def __init__(self, config: SlackConfig):
        self.config = config

    async def send(
        self,
        event_type: str,
        payload: dict,
        color: str | None = None,
    ) -> bool:
        """Send Slack notification.

        Returns True if the message was delivered successfully.
        """
        # Build message based on event type
        message = self._build_message(event_type, payload, color)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.webhook_url,
                    json=message,
                    timeout=self.config.timeout_seconds,
                )

                success = response.status_code == 200

                logger.info(
                    "slack_notification_sent",
                    event_type=event_type,
                    success=success,
                )

                return success

        except httpx.TimeoutException:
            logger.warning("slack_timeout", event_type=event_type)
            return False

        except httpx.RequestError as e:
            logger.error("slack_error", event_type=event_type, error=str(e))
            return False

    def _build_message(
        self,
        event_type: str,
        payload: dict,
        color: str | None = None,
    ) -> dict:
        """Build Slack message payload."""
        # Determine color based on event type
        if color is None:
            color = self._get_color_for_event(event_type)

        # Build the attachment
        attachment = {
            "color": color,
            "fallback": f"DataDr: {event_type}",
            "fields": [],
        }

        # Add fields based on event type
        if event_type == "investigation.completed":
            attachment["pretext"] = ":white_check_mark: Investigation Completed"
            investigation_id = payload.get("investigation_id", "Unknown")
            attachment["fields"].append({
                "title": "Investigation ID",
                "value": investigation_id,
                "short": True,
            })

            finding = payload.get("finding", {})
            if finding:
                attachment["fields"].append({
                    "title": "Root Cause",
                    "value": finding.get("root_cause", "Unknown"),
                    "short": False,
                })

        elif event_type == "investigation.failed":
            attachment["pretext"] = ":x: Investigation Failed"
            attachment["fields"].append({
                "title": "Investigation ID",
                "value": payload.get("investigation_id", "Unknown"),
                "short": True,
            })
            attachment["fields"].append({
                "title": "Error",
                "value": payload.get("error", "Unknown error"),
                "short": False,
            })

        elif event_type == "approval.required":
            attachment["pretext"] = ":eyes: Approval Required"
            attachment["fields"].append({
                "title": "Investigation ID",
                "value": payload.get("investigation_id", "Unknown"),
                "short": True,
            })
            context = payload.get("context", {})
            if context:
                attachment["fields"].append({
                    "title": "Context",
                    "value": json.dumps(context, indent=2)[:500],
                    "short": False,
                })

        else:
            # Generic event
            attachment["pretext"] = f":bell: {event_type}"
            for key, value in payload.items():
                if isinstance(value, (str, int, float, bool)):
                    attachment["fields"].append({
                        "title": key.replace("_", " ").title(),
                        "value": str(value),
                        "short": True,
                    })

        message = {
            "username": self.config.username,
            "icon_emoji": self.config.icon_emoji,
            "attachments": [attachment],
        }

        if self.config.channel:
            message["channel"] = self.config.channel

        return message

    def _get_color_for_event(self, event_type: str) -> str:
        """Get color for event type."""
        colors = {
            "investigation.completed": "#36a64f",  # Green
            "investigation.failed": "#dc3545",  # Red
            "investigation.started": "#007bff",  # Blue
            "approval.required": "#ffc107",  # Yellow
        }
        return colors.get(event_type, "#6c757d")  # Gray default
