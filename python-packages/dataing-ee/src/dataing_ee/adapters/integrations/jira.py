"""Jira webhook adapter."""

from __future__ import annotations

from typing import Any

from dataing_ee.adapters.integrations.base import IntegrationAdapter, IssueData, WebhookRequest
from dataing_ee.adapters.integrations.registry import register_adapter


@register_adapter
class JiraAdapter(IntegrationAdapter):
    """Adapter for Jira webhooks.

    Jira sends webhooks for issue events with the following structure:
    - X-Atlassian-Webhook-Id header (optional, for dedup)
    - X-Hub-Signature header with sha256=<signature>
    - Body with webhookEvent, issue.id, issue.key, issue.fields
    """

    provider = "jira"
    signature_header = "X-Hub-Signature"

    # Event types we care about
    SUPPORTED_EVENTS = {
        "jira:issue_created",
        "jira:issue_updated",
        "issue_created",
        "issue_updated",
    }

    def verify_signature(
        self,
        request: WebhookRequest,
        secret: str,
    ) -> bool:
        """Verify Jira webhook signature (sha256=...)."""
        signature = request.headers.get(self.signature_header)
        return self._verify_sha256_prefixed(request.body, signature, secret)

    def parse_payload(
        self,
        request: WebhookRequest,
        field_mappings: list[dict[str, Any]] | None = None,
    ) -> IssueData:
        """Parse Jira webhook payload."""
        payload = request.body_json
        issue = payload.get("issue", {})
        fields = issue.get("fields", {})

        issue_data = IssueData(
            title=fields.get("summary"),
            description=fields.get("description"),
            external_url=self._build_issue_url(issue),
            metadata={
                "jira_key": issue.get("key"),
                "jira_id": issue.get("id"),
                "project_key": fields.get("project", {}).get("key"),
                "issue_type": fields.get("issuetype", {}).get("name"),
            },
        )

        # Map priority
        priority = fields.get("priority", {})
        if priority:
            issue_data.priority = self._map_priority(priority.get("name", ""))

        # Map labels
        labels = fields.get("labels", [])
        if labels:
            issue_data.labels = labels

        # Apply custom field mappings
        self._apply_field_mappings(payload, field_mappings, issue_data)

        return issue_data

    def get_fingerprint(
        self,
        request: WebhookRequest,
    ) -> str:
        """Generate fingerprint from Jira issue ID and event type."""
        # Check for webhook ID header first
        webhook_id = request.headers.get("X-Atlassian-Webhook-Id")
        if webhook_id:
            return f"jira_webhook_{webhook_id}"

        payload = request.body_json
        issue = payload.get("issue", {})
        issue_id = issue.get("id", "")
        event = payload.get("webhookEvent", "unknown")

        if issue_id:
            return f"jira_{issue_id}_{event}"

        # Fallback to payload hash
        return f"jira_{self._hash_payload(payload)}"

    def get_event_type(
        self,
        request: WebhookRequest,
    ) -> str:
        """Extract event type from Jira payload."""
        payload = request.body_json
        event_type: str = payload.get("webhookEvent", "unknown")
        return event_type

    def should_process(
        self,
        request: WebhookRequest,
    ) -> bool:
        """Only process issue created/updated events."""
        event_type = self.get_event_type(request)
        return event_type in self.SUPPORTED_EVENTS

    def _build_issue_url(self, issue: dict[str, Any]) -> str | None:
        """Build Jira issue URL from self link."""
        self_link = issue.get("self", "")
        if not self_link:
            return None
        # self is like https://company.atlassian.net/rest/api/2/issue/12345
        # We want https://company.atlassian.net/browse/PROJ-123
        key = issue.get("key")
        if not key:
            return None
        base_url = self_link.split("/rest/")[0]
        return f"{base_url}/browse/{key}"

    def _map_priority(self, priority_name: str) -> str | None:
        """Map Jira priority to standard priority."""
        priority_map = {
            "highest": "P0",
            "high": "P1",
            "medium": "P2",
            "low": "P3",
            "lowest": "P3",
        }
        return priority_map.get(priority_name.lower())
