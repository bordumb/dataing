"""Great Expectations webhook adapter."""

from __future__ import annotations

from typing import Any

from dataing.core.domain_types import MetricSpec
from dataing_ee.adapters.integrations.base import IntegrationAdapter, IssueData, WebhookRequest
from dataing_ee.adapters.integrations.registry import register_adapter

# Great Expectations expectation type mapping to standard anomaly types
GX_TYPE_MAP = {
    # Null checks
    "expect_column_values_to_not_be_null": "null_rate",
    "expect_column_values_to_be_null": "null_rate",
    # Uniqueness checks
    "expect_column_values_to_be_unique": "duplicate_rate",
    "expect_compound_columns_to_be_unique": "duplicate_rate",
    # Distribution checks
    "expect_column_values_to_be_in_set": "distribution",
    "expect_column_distinct_values_to_be_in_set": "distribution",
    "expect_column_distinct_values_to_equal_set": "distribution",
    "expect_column_distinct_values_to_contain_set": "distribution",
    # Row count checks
    "expect_table_row_count_to_be_between": "row_count",
    "expect_table_row_count_to_equal": "row_count",
    # Schema checks
    "expect_table_columns_to_match_ordered_list": "schema_drift",
    "expect_table_columns_to_match_set": "schema_drift",
    "expect_column_to_exist": "schema_drift",
    # Type checks
    "expect_column_values_to_be_of_type": "schema_drift",
    # Freshness (custom)
    "expect_column_max_to_be_between": "freshness",  # Often used for date freshness
}


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

    def _map_anomaly_type(self, issue_data: IssueData) -> str:
        """Map Great Expectations expectation types to standard anomaly types."""
        # Check for expectation types in metadata
        statistics = issue_data.metadata.get("ge_statistics", {})

        # If we have statistics with failed expectations, try to determine type
        # from the most common failed expectation type
        if isinstance(statistics, dict):
            # This would require access to the failed expectations list
            # which might be in a separate field
            pass

        # Check title for expectation type hints
        title = (issue_data.title or "").lower()
        for exp_type, anomaly_type in GX_TYPE_MAP.items():
            if exp_type.replace("_", " ").replace("expect ", "") in title:
                return anomaly_type

        # Fall back to base implementation
        return super()._map_anomaly_type(issue_data)

    def _build_metric_spec(
        self,
        issue_data: IssueData,
        anomaly_type: str,
    ) -> MetricSpec:
        """Build MetricSpec from Great Expectations metadata."""
        suite_name = issue_data.metadata.get("ge_suite", "")
        checkpoint = issue_data.metadata.get("ge_checkpoint", "")
        statistics = issue_data.metadata.get("ge_statistics", {})

        # Build expression from GE context
        if suite_name:
            expression = f"Great Expectations suite: {suite_name}"
        elif checkpoint:
            expression = f"Great Expectations checkpoint: {checkpoint}"
        else:
            expression = issue_data.title or "Great Expectations validation"

        # Get column references if available
        columns: list[str] = []
        # Columns might be embedded in the title or description
        if issue_data.dataset_id:
            columns.append(issue_data.dataset_id)

        # Include statistics in display name
        display_name = issue_data.title or "GX Validation Failed"
        if isinstance(statistics, dict):
            failed = statistics.get("unsuccessful_expectations", 0)
            total = statistics.get("evaluated_expectations", 0)
            if total > 0:
                display_name = f"{display_name} ({failed}/{total} failed)"

        return MetricSpec(
            metric_type="description",
            expression=expression,
            display_name=display_name,
            columns_referenced=columns[:5],
            source_url=issue_data.external_url,
        )
