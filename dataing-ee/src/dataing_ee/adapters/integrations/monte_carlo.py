"""Monte Carlo webhook adapter."""

from __future__ import annotations

from typing import Any

from dataing_ee.adapters.integrations.base import IntegrationAdapter, IssueData, WebhookRequest
from dataing_ee.adapters.integrations.registry import register_adapter


@register_adapter
class MonteCarloAdapter(IntegrationAdapter):
    """Adapter for Monte Carlo webhooks.

    Monte Carlo sends webhooks for incidents and alerts with the following structure:
    - X-MC-Signature header with HMAC-SHA256
    - Body with incident/alert details including tables, type, status
    """

    provider = "monte_carlo"
    signature_header = "X-MC-Signature"

    # Event types we care about
    SUPPORTED_EVENTS = {
        "incident_created",
        "incident_updated",
        "alert_triggered",
        "alert_created",
    }

    def verify_signature(
        self,
        request: WebhookRequest,
        secret: str,
    ) -> bool:
        """Verify Monte Carlo webhook signature (HMAC-SHA256)."""
        signature = request.headers.get(self.signature_header)
        if not signature:
            return False
        return self._verify_hmac_sha256(request.body, signature, secret)

    def parse_payload(
        self,
        request: WebhookRequest,
        field_mappings: list[dict[str, Any]] | None = None,
    ) -> IssueData:
        """Parse Monte Carlo webhook payload."""
        payload = request.body_json

        # Monte Carlo can send incidents or alerts
        incident = payload.get("incident", {})
        alert = payload.get("alert", {})

        if incident:
            issue_data = self._parse_incident(incident)
        elif alert:
            issue_data = self._parse_alert(alert)
        else:
            # Generic format
            issue_data = IssueData(
                title=payload.get("title", payload.get("name")),
                description=payload.get("description"),
            )

        # Apply custom field mappings
        self._apply_field_mappings(payload, field_mappings, issue_data)

        return issue_data

    def _parse_incident(
        self,
        incident: dict[str, Any],
    ) -> IssueData:
        """Parse incident-type payload."""
        tables = incident.get("tables", [])
        table_names = [t.get("full_table_id", t.get("name", "")) for t in tables]

        title = incident.get("title")
        if not title:
            # Build title from incident type and tables
            inc_type = incident.get("type", "Data Incident")
            if table_names:
                title = f"{inc_type}: {', '.join(table_names[:3])}"
                if len(table_names) > 3:
                    title += f" (+{len(table_names) - 3} more)"
            else:
                title = inc_type

        description_parts = []
        if incident.get("description"):
            description_parts.append(incident["description"])
        if incident.get("impact"):
            description_parts.append(f"**Impact:** {incident['impact']}")
        if table_names:
            description_parts.append(f"**Affected Tables:** {', '.join(table_names)}")

        return IssueData(
            title=title,
            description="\n\n".join(description_parts) if description_parts else None,
            severity=self._map_severity(incident.get("severity")),
            external_url=incident.get("url"),
            labels=["monte-carlo", "incident"],
            metadata={
                "mc_incident_id": incident.get("id"),
                "mc_type": incident.get("type"),
                "mc_tables": table_names,
            },
        )

    def _parse_alert(
        self,
        alert: dict[str, Any],
    ) -> IssueData:
        """Parse alert-type payload."""
        title = alert.get("name", alert.get("title", "Monte Carlo Alert"))

        description_parts = []
        if alert.get("description"):
            description_parts.append(alert["description"])
        if alert.get("monitor_type"):
            description_parts.append(f"**Monitor Type:** {alert['monitor_type']}")
        if alert.get("table"):
            description_parts.append(f"**Table:** {alert['table']}")

        dataset_id = None
        table = alert.get("table", "")
        if table:
            # Use table as dataset_id for correlation
            dataset_id = table

        return IssueData(
            title=title,
            description="\n\n".join(description_parts) if description_parts else None,
            severity=self._map_severity(alert.get("severity")),
            dataset_id=dataset_id,
            external_url=alert.get("url"),
            labels=["monte-carlo", "alert"],
            metadata={
                "mc_alert_id": alert.get("id"),
                "mc_monitor_type": alert.get("monitor_type"),
                "mc_rule_id": alert.get("rule_id"),
            },
        )

    def get_fingerprint(
        self,
        request: WebhookRequest,
    ) -> str:
        """Generate fingerprint from Monte Carlo incident/alert ID."""
        payload = request.body_json

        # Check for incident ID
        incident = payload.get("incident", {})
        if incident.get("id"):
            return f"mc_incident_{incident['id']}"

        # Check for alert ID
        alert = payload.get("alert", {})
        if alert.get("id"):
            return f"mc_alert_{alert['id']}"

        # Check headers
        request_id = request.headers.get("X-Request-Id")
        if request_id:
            return f"mc_{request_id}"

        # Fallback to payload hash
        return f"mc_{self._hash_payload(payload)}"

    def get_event_type(
        self,
        request: WebhookRequest,
    ) -> str:
        """Extract event type from Monte Carlo payload."""
        payload = request.body_json
        event_type = payload.get("event_type") or payload.get("type")
        if event_type:
            return str(event_type)

        # Infer from payload structure
        if payload.get("incident"):
            return "incident_created"
        if payload.get("alert"):
            return "alert_triggered"

        return "unknown"

    def should_process(
        self,
        request: WebhookRequest,
    ) -> bool:
        """Process most Monte Carlo events."""
        event_type = self.get_event_type(request)
        # Skip resolution events
        if "resolved" in event_type.lower() or "closed" in event_type.lower():
            return False
        return True

    def _map_severity(self, mc_severity: str | None) -> str | None:
        """Map Monte Carlo severity to standard severity."""
        if not mc_severity:
            return None
        severity_map = {
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
            "warning": "medium",
            "info": "low",
        }
        return severity_map.get(mc_severity.lower(), "medium")
