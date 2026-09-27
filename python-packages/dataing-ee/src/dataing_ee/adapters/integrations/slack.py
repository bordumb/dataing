"""Slack webhook adapter."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from dataing_ee.adapters.integrations.base import IntegrationAdapter, IssueData, WebhookRequest
from dataing_ee.adapters.integrations.registry import register_adapter


@register_adapter
class SlackAdapter(IntegrationAdapter):
    """Adapter for Slack webhooks.

    Slack uses a unique signature verification scheme:
    - X-Slack-Signature header with v0=<signature>
    - X-Slack-Request-Timestamp header
    - Signature is HMAC-SHA256 of "v0:{timestamp}:{body}"

    Event types include:
    - Event subscriptions (message events, reaction events)
    - Slash commands
    - Interactive components (button clicks, modals)
    """

    provider = "slack"
    signature_header = "X-Slack-Signature"

    # Event types we care about for issue creation
    SUPPORTED_EVENTS = {
        "message",
        "app_mention",
        "reaction_added",
        "shortcut",
        "message_action",
    }

    # Reaction emojis that can trigger issue creation
    TRIGGER_REACTIONS = {
        "bug",
        "warning",
        "fire",
        "alert",
        "sos",
        "rotating_light",
        "exclamation",
        "x",
    }

    def verify_signature(
        self,
        request: WebhookRequest,
        secret: str,
    ) -> bool:
        """Verify Slack webhook signature.

        Slack signature is HMAC-SHA256 of "v0:{timestamp}:{body}"
        with header format "v0={signature}".
        """
        signature = request.header(self.signature_header)
        if not signature:
            return False

        timestamp = request.header("X-Slack-Request-Timestamp")
        if not timestamp:
            return False

        # Reject old timestamps (>5 minutes) to prevent replay attacks
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 300:
                return False
        except ValueError:
            return False

        # Build signature base string
        sig_basestring = f"v0:{timestamp}:{request.body.decode()}"

        # Calculate expected signature
        calculated = hmac.new(
            secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()

        expected_signature = f"v0={calculated}"
        return hmac.compare_digest(signature, expected_signature)

    def handshake_response(
        self,
        request: WebhookRequest,
    ) -> dict[str, Any] | None:
        """Echo the challenge of a url_verification request.

        Slack checks an Events API request URL by sending a challenge that the
        endpoint must send back.
        """
        payload = request.body_json
        challenge = payload.get("challenge")
        if payload.get("type") == "url_verification" and isinstance(challenge, str):
            return {"challenge": challenge}
        return None

    def parse_payload(
        self,
        request: WebhookRequest,
        field_mappings: list[dict[str, Any]] | None = None,
    ) -> IssueData:
        """Parse Slack webhook payload."""
        payload = request.body_json

        # Handle different Slack payload types
        payload_type = payload.get("type")

        if payload_type == "url_verification":
            # Challenge request - should not create issue
            return IssueData()

        if payload_type == "event_callback":
            event = payload.get("event", {})
            issue_data = self._parse_event(event, payload)
        elif payload_type in ("shortcut", "message_action"):
            issue_data = self._parse_shortcut(payload)
        elif payload_type in ("block_actions", "interactive_message"):
            issue_data = self._parse_interactive(payload)
        else:
            # Generic/unknown payload
            issue_data = IssueData(
                title=payload.get("text", "Slack Notification"),
                description=str(payload),
            )

        # Apply custom field mappings
        self._apply_field_mappings(payload, field_mappings, issue_data)

        return issue_data

    def _parse_event(
        self,
        event: dict[str, Any],
        payload: dict[str, Any],
    ) -> IssueData:
        """Parse event callback payload."""
        event_type = event.get("type")

        if event_type == "reaction_added":
            return self._parse_reaction_event(event)
        elif event_type in ("message", "app_mention"):
            return self._parse_message_event(event, payload)

        return IssueData()

    def _parse_reaction_event(
        self,
        event: dict[str, Any],
    ) -> IssueData:
        """Parse reaction_added event."""
        reaction = event.get("reaction", "")

        # Only process trigger reactions
        if reaction not in self.TRIGGER_REACTIONS:
            return IssueData()

        item = event.get("item", {})
        user = event.get("user", "")

        title = f"Issue flagged via :{reaction}: reaction"

        description_parts = [
            f"A message was flagged with :{reaction}: by <@{user}>",
            "",
            f"**Channel:** <#{item.get('channel', '')}>",
            f"**Message Timestamp:** {item.get('ts', '')}",
        ]

        return IssueData(
            title=title,
            description="\n".join(description_parts),
            labels=["slack", f"reaction-{reaction}"],
            metadata={
                "slack_channel": item.get("channel"),
                "slack_ts": item.get("ts"),
                "slack_user": user,
                "slack_reaction": reaction,
            },
        )

    def _parse_message_event(
        self,
        event: dict[str, Any],
        payload: dict[str, Any],
    ) -> IssueData:
        """Parse message or app_mention event."""
        text = event.get("text", "")
        user = event.get("user", "")
        channel = event.get("channel", "")

        # Extract title from first line of message
        lines = text.split("\n")
        title = lines[0][:100] if lines else "Slack Message"

        # Clean up bot mentions from title
        if title.startswith("<@"):
            title = title.split(">", 1)[-1].strip()
        if not title:
            title = "Slack Message"

        description = text if len(text) > 100 else None

        return IssueData(
            title=title,
            description=description,
            labels=["slack"],
            external_url=self._build_message_url(channel, event.get("ts", ""), payload),
            metadata={
                "slack_channel": channel,
                "slack_ts": event.get("ts"),
                "slack_user": user,
                "slack_team": payload.get("team_id"),
            },
        )

    def _parse_shortcut(
        self,
        payload: dict[str, Any],
    ) -> IssueData:
        """Parse shortcut or message_action payload."""
        callback_id = payload.get("callback_id", "")

        # For message shortcuts, get the message content
        message = payload.get("message", {})
        text = message.get("text", "")

        title = text[:100] if text else f"Slack Shortcut: {callback_id}"

        user = payload.get("user", {})
        channel = payload.get("channel", {})

        return IssueData(
            title=title,
            description=text if len(text) > 100 else None,
            labels=["slack", "shortcut"],
            external_url=self._build_message_url(
                channel.get("id", ""),
                message.get("ts", ""),
                payload,
            ),
            metadata={
                "slack_channel": channel.get("id"),
                "slack_channel_name": channel.get("name"),
                "slack_user": user.get("id"),
                "slack_username": user.get("username"),
                "slack_callback_id": callback_id,
            },
        )

    def _parse_interactive(
        self,
        payload: dict[str, Any],
    ) -> IssueData:
        """Parse interactive component payload."""
        # Get action details
        actions = payload.get("actions", [])
        action = actions[0] if actions else {}

        action_id = action.get("action_id", action.get("name", ""))
        action_value = action.get("value", action.get("selected_option", {}).get("value", ""))

        title = f"Slack Action: {action_id}"
        if action_value:
            title = f"{title} = {action_value}"

        return IssueData(
            title=title[:100],
            labels=["slack", "interactive"],
            metadata={
                "slack_action_id": action_id,
                "slack_action_value": action_value,
                "slack_trigger_id": payload.get("trigger_id"),
            },
        )

    def _build_message_url(
        self,
        channel: str,
        ts: str,
        payload: dict[str, Any],
    ) -> str | None:
        """Build Slack message URL."""
        if not channel or not ts:
            return None

        team_id = payload.get("team_id", payload.get("team", {}).get("id", ""))
        if not team_id:
            return None

        # Convert ts to message format (remove decimal)
        msg_ts = ts.replace(".", "")
        return f"https://slack.com/archives/{channel}/p{msg_ts}"

    def get_fingerprint(
        self,
        request: WebhookRequest,
    ) -> str:
        """Generate fingerprint from Slack event."""
        payload = request.body_json

        # For event callbacks, use event_id
        event_id = payload.get("event_id")
        if event_id:
            return f"slack_{event_id}"

        # For interactive payloads, use trigger_id
        trigger_id = payload.get("trigger_id")
        if trigger_id:
            return f"slack_trigger_{trigger_id}"

        # For events with messages, use channel + ts
        event = payload.get("event", {})
        channel = event.get("channel", payload.get("channel", {}).get("id", ""))
        ts = event.get("ts", payload.get("message", {}).get("ts", ""))
        if channel and ts:
            return f"slack_{channel}_{ts}"

        # Fallback to payload hash
        return f"slack_{self._hash_payload(payload)}"

    def get_event_type(
        self,
        request: WebhookRequest,
    ) -> str:
        """Extract event type from Slack payload."""
        payload = request.body_json

        payload_type = payload.get("type", "")

        if payload_type == "event_callback":
            event = payload.get("event", {})
            event_type: str = event.get("type", "unknown")
            return event_type

        return str(payload_type) if payload_type else "unknown"

    def should_process(
        self,
        request: WebhookRequest,
    ) -> bool:
        """Determine if Slack event should be processed."""
        payload = request.body_json
        payload_type = payload.get("type")

        # Always skip url_verification challenges
        if payload_type == "url_verification":
            return False

        # For event callbacks, check event type
        if payload_type == "event_callback":
            event = payload.get("event", {})
            event_type = event.get("type", "")

            # Skip bot messages to avoid loops
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                return False

            # For reactions, only process trigger reactions
            if event_type == "reaction_added":
                reaction = event.get("reaction", "")
                return reaction in self.TRIGGER_REACTIONS

            return event_type in self.SUPPORTED_EVENTS

        # Process shortcuts and interactive components
        return payload_type in ("shortcut", "message_action", "block_actions")
