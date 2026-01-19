"""Notification orchestration service."""

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.notifications.webhook import WebhookConfig, WebhookNotifier

logger = structlog.get_logger()


@dataclass
class NotificationEvent:
    """An event to be notified."""

    event_type: str
    payload: dict[str, Any]
    tenant_id: UUID


class NotificationService:
    """Orchestrates sending notifications through multiple channels."""

    def __init__(self, db: AppDatabase):
        """Initialize the notification service.

        Args:
            db: Application database instance.
        """
        self.db = db

    async def notify(self, event: NotificationEvent) -> dict[str, Any]:
        """Send notification through all configured channels.

        Returns a dict with results for each channel.
        """
        results: dict[str, Any] = {}

        # Get webhooks configured for this event
        webhooks = await self.db.get_webhooks_for_event(
            event.tenant_id,
            event.event_type,
        )

        if webhooks:
            webhook_results = await self._send_webhooks(webhooks, event)
            results["webhooks"] = webhook_results

        # Add other channels here (Slack, email, etc.)

        logger.info(
            "notifications_sent",
            event_type=event.event_type,
            tenant_id=str(event.tenant_id),
            channels=list(results.keys()),
        )

        return results

    async def _send_webhooks(
        self,
        webhooks: list[dict[str, Any]],
        event: NotificationEvent,
    ) -> list[dict[str, Any]]:
        """Send notifications to all configured webhooks."""
        results = []

        # Send webhooks in parallel
        tasks = []
        for webhook in webhooks:
            notifier = WebhookNotifier(
                WebhookConfig(
                    url=webhook["url"],
                    secret=webhook.get("secret"),
                )
            )
            tasks.append(self._send_single_webhook(notifier, webhook, event))

        if tasks:
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            results = [r if isinstance(r, dict) else {"error": str(r)} for r in gathered]

        return results

    async def _send_single_webhook(
        self,
        notifier: WebhookNotifier,
        webhook: dict[str, Any],
        event: NotificationEvent,
    ) -> dict[str, Any]:
        """Send a single webhook notification."""
        try:
            success = await notifier.send(event.event_type, event.payload)

            # Update webhook status in database
            await self.db.update_webhook_status(
                webhook["id"],
                200 if success else 500,
            )

            return {
                "webhook_id": str(webhook["id"]),
                "success": success,
            }

        except Exception as e:
            logger.error(
                "webhook_failed",
                webhook_id=str(webhook["id"]),
                error=str(e),
            )

            await self.db.update_webhook_status(webhook["id"], 0)

            return {
                "webhook_id": str(webhook["id"]),
                "success": False,
                "error": str(e),
            }

    async def notify_investigation_completed(
        self,
        tenant_id: UUID,
        investigation_id: UUID,
        finding: dict[str, Any],
    ) -> dict[str, Any]:
        """Convenience method for investigation completion notifications."""
        return await self.notify(
            NotificationEvent(
                event_type="investigation.completed",
                tenant_id=tenant_id,
                payload={
                    "investigation_id": str(investigation_id),
                    "finding": finding,
                },
            )
        )

    async def notify_investigation_failed(
        self,
        tenant_id: UUID,
        investigation_id: UUID,
        error: str,
    ) -> dict[str, Any]:
        """Convenience method for investigation failure notifications."""
        return await self.notify(
            NotificationEvent(
                event_type="investigation.failed",
                tenant_id=tenant_id,
                payload={
                    "investigation_id": str(investigation_id),
                    "error": error,
                },
            )
        )

    async def notify_approval_required(
        self,
        tenant_id: UUID,
        investigation_id: UUID,
        approval_request_id: UUID,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Convenience method for approval request notifications."""
        return await self.notify(
            NotificationEvent(
                event_type="approval.required",
                tenant_id=tenant_id,
                payload={
                    "investigation_id": str(investigation_id),
                    "approval_request_id": str(approval_request_id),
                    "context": context,
                },
            )
        )
