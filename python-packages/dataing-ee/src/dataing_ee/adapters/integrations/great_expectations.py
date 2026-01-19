"""Great Expectations webhook adapter."""

from __future__ import annotations

from typing import Any

from dataing_ee.adapters.integrations.base import IntegrationAdapter, IssueData, WebhookRequest
from dataing_ee.adapters.integrations.registry import register_adapter


@register_adapter
class GreatExpectationsAdapter(IntegrationAdapter):
    """Adapter for Great Expectations webhooks.

    Great Expectations sends checkpoint validation results with the following structure:
    - X-GE-Signature header with sha256=<signature>
    - Body with checkpoint results including suite name, statistics, failed expectations
    """

    provider = "great_expectations"
    signature_header = "X-GE-Signature"

    def verify_signature(
        self,
        request: WebhookRequest,
        secret: str,
    ) -> bool:
        """Verify Great Expectations webhook signature (sha256=...)."""
        signature = request.headers.get(self.signature_header)
        return self._verify_sha256_prefixed(request.body, signature, secret)

    def parse_payload(
        self,
        request: WebhookRequest,
        field_mappings: list[dict[str, Any]] | None = None,
    ) -> IssueData:
        """Parse Great Expectations checkpoint result payload."""
        payload = request.body_json

        # GE sends validation results with different structures
        # Handle both direct results and nested structures
        result = payload.get("result", payload.get("validation_result", payload))

        success = result.get("success", True)
        if success:
            # Don't create issues for successful validations
            return IssueData()

        statistics = result.get("statistics", {})
        results = result.get("results", [])

        # Build title
        suite_name = self._get_suite_name(result, payload)
        checkpoint_name = payload.get("checkpoint_name", "")
        data_asset = payload.get("data_asset_name", payload.get("batch_id", ""))

        title_parts = ["Data Quality Check Failed"]
        if suite_name:
            title_parts.append(f"- {suite_name}")
        if data_asset:
            title_parts.append(f"on {data_asset}")

        title = " ".join(title_parts)

        # Build description with failed expectations
        description_parts = []

        if checkpoint_name:
            description_parts.append(f"**Checkpoint:** {checkpoint_name}")
        if data_asset:
            description_parts.append(f"**Data Asset:** {data_asset}")

        # Add statistics
        if statistics:
            total = statistics.get("evaluated_expectations", 0)
            failed = statistics.get("unsuccessful_expectations", 0)
            success_pct = statistics.get("success_percent", 0)
            failure_rate = 100 - success_pct
            msg = f"**Results:** {failed}/{total} failed ({failure_rate:.1f}% failure rate)"
            description_parts.append(msg)

        # Add failed expectations detail
        failed_expectations = [r for r in results if not r.get("success", True)]
        if failed_expectations:
            description_parts.append("\n**Failed Expectations:**")
            for exp in failed_expectations[:10]:  # Limit to first 10
                exp_type = exp.get("expectation_config", {}).get("expectation_type", "")
                column = exp.get("expectation_config", {}).get("kwargs", {}).get("column", "")
                if column:
                    description_parts.append(f"- `{column}`: {exp_type}")
                else:
                    description_parts.append(f"- {exp_type}")

            if len(failed_expectations) > 10:
                description_parts.append(f"- ... and {len(failed_expectations) - 10} more")

        # Determine severity based on failure rate
        severity = self._determine_severity(statistics)

        issue_data = IssueData(
            title=title,
            description="\n".join(description_parts) if description_parts else None,
            severity=severity,
            dataset_id=data_asset if data_asset else None,
            labels=["great-expectations", "data-quality"],
            external_url=payload.get("docs_url"),
            metadata={
                "ge_checkpoint": checkpoint_name,
                "ge_suite": suite_name,
                "ge_run_id": payload.get("run_id"),
                "ge_statistics": statistics,
            },
        )

        # Apply custom field mappings
        self._apply_field_mappings(payload, field_mappings, issue_data)

        return issue_data

    def get_fingerprint(
        self,
        request: WebhookRequest,
    ) -> str:
        """Generate fingerprint from GE run ID and suite name."""
        payload = request.body_json

        run_id = payload.get("run_id")
        suite = self._get_suite_name(
            payload.get("result", payload.get("validation_result", payload)),
            payload,
        )

        if run_id:
            return f"ge_{run_id}_{suite or 'default'}"

        # Use checkpoint + batch + timestamp
        checkpoint = payload.get("checkpoint_name", "")
        batch = payload.get("batch_id", "")
        if checkpoint or batch:
            return f"ge_{checkpoint}_{batch}"

        # Fallback to payload hash
        return f"ge_{self._hash_payload(payload)}"

    def get_event_type(
        self,
        request: WebhookRequest,
    ) -> str:
        """Extract event type from GE payload."""
        payload = request.body_json

        event_type = payload.get("event_type", "validation_result")

        # Check success to determine specific type
        result = payload.get("result", payload.get("validation_result", payload))
        success = result.get("success", True)

        if not success:
            return f"{event_type}_failed"
        return f"{event_type}_passed"

    def should_process(
        self,
        request: WebhookRequest,
    ) -> bool:
        """Only process failed validations."""
        payload = request.body_json
        result = payload.get("result", payload.get("validation_result", payload))
        success = result.get("success", True)
        return not success

    def _get_suite_name(
        self,
        result: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        """Extract expectation suite name."""
        # Try various locations
        suite = result.get("expectation_suite_name")
        if suite:
            return str(suite)

        meta = result.get("meta", {})
        suite = meta.get("expectation_suite_name")
        if suite:
            return str(suite)

        suite_name: str = payload.get("suite_name", "")
        return suite_name

    def _determine_severity(self, statistics: dict[str, Any]) -> str:
        """Determine severity based on failure statistics."""
        if not statistics:
            return "medium"

        success_pct = statistics.get("success_percent", 100)

        if success_pct < 50:
            return "critical"
        elif success_pct < 75:
            return "high"
        elif success_pct < 90:
            return "medium"
        return "low"
