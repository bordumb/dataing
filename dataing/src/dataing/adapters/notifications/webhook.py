"""Webhook notification adapter."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class WebhookConfig:
    """Webhook configuration."""

    url: str
    secret: str | None = None
    timeout_seconds: int = 30


class WebhookNotifier:
    """Delivers notifications via HTTP webhooks."""

    def __init__(self, config: WebhookConfig):
        """Initialize the webhook notifier.

        Args:
            config: Webhook configuration settings.
        """
        self.config = config

    async def send(self, event_type: str, payload: dict[str, Any]) -> bool:
        """Send webhook notification.

        Returns True if the webhook was delivered successfully (2xx response).
        """
        body = json.dumps(
            {
                "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": payload,
            },
            default=str,
        )

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DataDr-Webhook/1.0",
        }

        # Add HMAC signature if secret configured
        if self.config.secret:
            signature = hmac.new(
                self.config.secret.encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
            headers["X-Webhook-Timestamp"] = datetime.now(UTC).isoformat()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.url,
                    content=body,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )

                success = response.is_success

                logger.info(
                    "webhook_sent",
                    url=self.config.url,
                    event_type=event_type,
                    status_code=response.status_code,
                    success=success,
                )

                return success

        except httpx.TimeoutException:
            logger.warning(
                "webhook_timeout",
                url=self.config.url,
                event_type=event_type,
            )
            return False

        except httpx.RequestError as e:
            logger.error(
                "webhook_error",
                url=self.config.url,
                event_type=event_type,
                error=str(e),
            )
            return False

    @staticmethod
    def verify_signature(
        body: bytes,
        signature_header: str,
        secret: str,
    ) -> bool:
        """Verify a webhook signature.

        This is useful for receiving webhooks and verifying their authenticity.
        """
        if not signature_header.startswith("sha256="):
            return False

        expected_signature = signature_header[7:]  # Remove "sha256=" prefix

        calculated = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(calculated, expected_signature)
