"""Base adapter interface for integration webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import parse_qsl

from dataing.core.domain_types import AnomalyAlert, MetricSpec

FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"


@dataclass
class WebhookRequest:
    """Represents an incoming webhook request.

    Header names are case-insensitive, so they are stored lowercased; read them
    with ``header``, which accepts a name in any case.
    """

    body: bytes
    headers: dict[str, str]
    query_params: dict[str, str]

    def __post_init__(self) -> None:
        """Lowercase header names, the form ASGI servers deliver them in."""
        self.headers = {name.lower(): value for name, value in self.headers.items()}

    def header(self, name: str) -> str | None:
        """Get a header's value by case-insensitive name, or None if it was not sent."""
        return self.headers.get(name.lower())

    @property
    def body_json(self) -> dict[str, Any]:
        """Parse the body as a JSON object.

        Form-encoded bodies are decoded too, in the two shapes Slack sends: a
        JSON document in a ``payload`` field (interactive components), or plain
        fields (slash commands).

        Raises:
            ValueError: If the body is neither a JSON object nor such a form.
        """
        content_type = (self.header("Content-Type") or "").split(";")[0].strip().lower()
        if content_type == FORM_CONTENT_TYPE:
            fields: dict[str, Any] = dict(parse_qsl(self.body.decode(), keep_blank_values=True))
            if "payload" not in fields:
                return fields
            result = json.loads(fields["payload"])
        else:
            result = json.loads(self.body)
        if not isinstance(result, dict):
            raise ValueError("Webhook body is not a JSON object")
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

    def handshake_response(
        self,
        request: WebhookRequest,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        """Answer the provider's endpoint-verification handshake, if this is one.

        Override for providers that check a webhook URL by expecting a specific
        response, such as Slack's url_verification challenge. Only called once
        the request's signature has been verified.

        Args:
            request: The incoming webhook request

        Returns:
            The response body to send back, or None if the request is not a handshake
        """
        _ = request  # Available for subclass overrides
        return None

    def format_response(
        self,
        request: WebhookRequest,  # noqa: ARG002
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Shape the response body once the webhook has been handled.

        Override for providers that show the response to a user, such as the
        reply to a Slack slash command.

        Args:
            request: The incoming webhook request
            result: What handling the webhook produced, such as its status

        Returns:
            The response body to send back
        """
        _ = request  # Available for subclass overrides
        return result

    def deferred_reply_url(
        self,
        request: WebhookRequest,  # noqa: ARG002
    ) -> str | None:
        """Return where to post the outcome, if the provider can't wait for it.

        Override for providers that need an immediate reply, such as Slack,
        which gives a slash command 3 seconds. The webhook is then acknowledged
        at once, handled in the background, and its formatted outcome posted to
        the returned URL.

        Args:
            request: The incoming webhook request

        Returns:
            The URL to post the outcome to, or None to reply once it is handled
        """
        _ = request  # Available for subclass overrides
        return None

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
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:16]

    def to_anomaly_alert(
        self,
        issue_data: IssueData,
        fingerprint: str,
    ) -> AnomalyAlert:
        """Convert IssueData to AnomalyAlert for investigation.

        Args:
            issue_data: Parsed issue data from the webhook
            fingerprint: Unique identifier for this event (used as source_alert_id)

        Returns:
            AnomalyAlert ready for investigation
        """
        # Extract dataset_ids
        dataset_ids = []
        if issue_data.dataset_id:
            dataset_ids.append(issue_data.dataset_id)
        # Also check metadata for additional tables
        if issue_data.metadata.get("tables"):
            tables = issue_data.metadata["tables"]
            if isinstance(tables, list):
                dataset_ids.extend([t for t in tables if t not in dataset_ids])
        if not dataset_ids:
            dataset_ids = ["unknown"]

        # Map anomaly type - subclasses should override for provider-specific mapping
        anomaly_type = self._map_anomaly_type(issue_data)

        # Build metric_spec from available info
        metric_spec = self._build_metric_spec(issue_data, anomaly_type)

        # Extract values from metadata if available
        expected_value = float(issue_data.metadata.get("expected_value", 0.0))
        actual_value = float(issue_data.metadata.get("actual_value", 0.0))
        deviation_pct = float(issue_data.metadata.get("deviation_pct", 0.0))

        # Calculate deviation if we have expected/actual but not deviation
        if expected_value != 0 and actual_value != 0 and deviation_pct == 0:
            deviation_pct = abs((actual_value - expected_value) / expected_value) * 100

        return AnomalyAlert(
            dataset_ids=dataset_ids,
            metric_spec=metric_spec,
            anomaly_type=anomaly_type,
            expected_value=expected_value,
            actual_value=actual_value,
            deviation_pct=deviation_pct,
            anomaly_date=date.today().isoformat(),
            severity=issue_data.severity or "medium",
            source_system=self.provider,
            source_alert_id=fingerprint,
            source_url=issue_data.external_url,
            metadata={
                k: v
                for k, v in issue_data.metadata.items()
                if isinstance(v, str | int | float | bool)
            },
        )

    def _map_anomaly_type(self, issue_data: IssueData) -> str:
        """Map provider-specific type to standard anomaly type.

        Subclasses should override for provider-specific mapping.
        """
        # Check metadata for type hints
        if issue_data.metadata.get("anomaly_type"):
            return str(issue_data.metadata["anomaly_type"])

        # Default based on common patterns in title/description
        title = (issue_data.title or "").lower()
        if "null" in title or "missing" in title:
            return "null_rate"
        if "volume" in title or "row" in title or "count" in title:
            return "row_count"
        if "fresh" in title or "stale" in title or "delay" in title:
            return "freshness"
        if "schema" in title or "column" in title:
            return "schema_drift"
        if "duplicate" in title or "unique" in title:
            return "duplicate_rate"
        return "custom"

    def _build_metric_spec(
        self,
        issue_data: IssueData,
        anomaly_type: str,
    ) -> MetricSpec:
        """Build MetricSpec from issue data.

        Subclasses can override for provider-specific metric extraction.
        """
        # Try to get column from metadata
        column = issue_data.metadata.get("column")
        if column and isinstance(column, str):
            return MetricSpec.from_column(
                column_name=column,
                display_name=issue_data.title or column,
            )

        # Default to description-based metric
        return MetricSpec(
            metric_type="description",
            expression=issue_data.title or "Unknown metric",
            display_name=issue_data.title or "Unknown",
            columns_referenced=[],
            source_url=issue_data.external_url,
        )
