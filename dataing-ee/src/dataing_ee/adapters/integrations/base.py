"""Base adapter interface for integration webhooks."""

from __future__ import annotations

import hashlib
import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WebhookRequest:
    """Represents an incoming webhook request."""

    body: bytes
    headers: dict[str, str]
    query_params: dict[str, str]

    @property
    def body_json(self) -> dict[str, Any]:
        """Parse body as JSON."""
        import json

        result: dict[str, Any] = json.loads(self.body)
        return result


@dataclass
class IssueData:
    """Data extracted from webhook for issue creation."""

    title: str | None = None
    description: str | None = None
    severity: str | None = None
    priority: str | None = None
    dataset_id: str | None = None
    labels: list[str] = field(default_factory=list)
    external_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class IntegrationAdapter(ABC):
    """Base class for integration webhook adapters.

    Each adapter implements provider-specific logic for:
    - Signature verification
    - Payload parsing to extract issue fields
    - Fingerprint generation for deduplication
    """

    # Provider name (e.g., "jira", "monte_carlo")
    provider: str = ""

    # Signature header name
    signature_header: str = "X-Webhook-Signature"

    @abstractmethod
    def verify_signature(
        self,
        request: WebhookRequest,
        secret: str,
    ) -> bool:
        """Verify the webhook signature.

        Args:
            request: The incoming webhook request
            secret: The shared signing secret

        Returns:
            True if signature is valid
        """
        pass

    @abstractmethod
    def parse_payload(
        self,
        request: WebhookRequest,
        field_mappings: list[dict[str, Any]] | None = None,
    ) -> IssueData:
        """Parse the webhook payload into issue data.

        Args:
            request: The incoming webhook request
            field_mappings: Optional custom field mappings

        Returns:
            Extracted issue data
        """
        pass

    @abstractmethod
    def get_fingerprint(
        self,
        request: WebhookRequest,
    ) -> str:
        """Generate a fingerprint for deduplication.

        Args:
            request: The incoming webhook request

        Returns:
            Unique fingerprint string for this event
        """
        pass

    @abstractmethod
    def get_event_type(
        self,
        request: WebhookRequest,
    ) -> str:
        """Extract event type from the payload.

        Args:
            request: The incoming webhook request

        Returns:
            Event type string (e.g., "issue_created", "alert_triggered")
        """
        pass

    def should_process(
        self,
        request: WebhookRequest,  # noqa: ARG002
    ) -> bool:
        """Check if this webhook should be processed.

        Override to filter out certain event types.

        Args:
            request: The incoming webhook request

        Returns:
            True if webhook should be processed
        """
        _ = request  # Available for subclass overrides
        return True

    # Helper methods for common signature verification patterns

    def _verify_hmac_sha256(
        self,
        body: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify HMAC-SHA256 signature."""
        calculated = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(calculated, signature)

    def _verify_sha256_prefixed(
        self,
        body: bytes,
        signature_header: str | None,
        secret: str,
        prefix: str = "sha256=",
    ) -> bool:
        """Verify signature with prefix (e.g., sha256=...)."""
        if not signature_header:
            return False
        if not signature_header.startswith(prefix):
            return False
        signature = signature_header[len(prefix) :]
        return self._verify_hmac_sha256(body, signature, secret)

    def _get_nested_value(self, obj: dict[str, Any], path: str) -> Any:
        """Get a nested value from a dict using dot notation."""
        keys = path.split(".")
        current = obj
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _apply_field_mappings(
        self,
        payload: dict[str, Any],
        mappings: list[dict[str, Any]] | None,
        issue_data: IssueData,
    ) -> None:
        """Apply custom field mappings to issue data."""
        if not mappings:
            return

        for mapping in mappings:
            value = self._get_nested_value(payload, mapping["source_field"])
            if value is None:
                continue

            # Apply transform if specified
            transform = mapping.get("transform")
            if transform:
                value = self._apply_transform(value, transform)

            # Set target field
            target = mapping["target_field"]
            if target == "title":
                issue_data.title = str(value)
            elif target == "description":
                issue_data.description = str(value)
            elif target == "severity":
                issue_data.severity = str(value)
            elif target == "priority":
                issue_data.priority = str(value)
            elif target == "dataset_id":
                issue_data.dataset_id = str(value)
            elif target == "labels":
                if isinstance(value, list):
                    issue_data.labels = [str(v) for v in value]
                else:
                    issue_data.labels = [str(value)]

    def _apply_transform(self, value: Any, transform: str) -> Any:
        """Apply a transform to a value."""
        if not isinstance(value, str):
            return value

        if transform == "uppercase":
            return value.upper()
        elif transform == "lowercase":
            return value.lower()
        elif transform == "severity_map":
            severity_map = {
                "blocker": "critical",
                "critical": "critical",
                "major": "high",
                "high": "high",
                "medium": "medium",
                "minor": "low",
                "low": "low",
                "trivial": "low",
            }
            return severity_map.get(value.lower(), value.lower())

        return value

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        """Generate hash of payload for fallback fingerprinting."""
        import json

        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:16]
