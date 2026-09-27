"""dbt Cloud webhook adapter."""

from __future__ import annotations

from typing import Any

from dataing.core.domain_types import MetricSpec
from dataing_ee.adapters.integrations.base import (
    IntegrationAdapter,
    IssueData,
    WebhookRequest,
)
from dataing_ee.adapters.integrations.registry import register_adapter

# dbt test type mapping to standard anomaly types
DBT_TYPE_MAP = {
    "not_null": "null_rate",
    "unique": "duplicate_rate",
    "accepted_values": "distribution",
    "relationships": "referential_integrity",
    "freshness": "freshness",
    # Common custom tests
    "recency": "freshness",
    "row_count": "row_count",
    "equal_rowcount": "row_count",
    "expression_is_true": "distribution",
}


@register_adapter
class DbtAdapter(IntegrationAdapter):
    """Adapter for dbt Cloud webhooks.

    dbt Cloud sends webhooks for job events with the following structure:
    - Authorization header with HMAC-SHA256 signature
    - Body with job/run details including status and test results
    """

    provider = "dbt"
    signature_header = "Authorization"

    # Event types we care about
    SUPPORTED_EVENTS = {
        "job.run.completed",
        "job.run.errored",
    }

    def verify_signature(
        self,
        request: WebhookRequest,
        secret: str,
    ) -> bool:
        """Verify dbt Cloud webhook signature.

        dbt Cloud uses HMAC-SHA256 signature in the Authorization header.
        Format varies by dbt Cloud version - support both Bearer token and raw signature.
        """
        auth_header = request.header(self.signature_header)
        if not auth_header:
            return False

        # dbt Cloud may send as "Bearer <signature>" or just the signature
        if auth_header.startswith("Bearer "):
            signature = auth_header[7:]  # Remove "Bearer " prefix
        else:
            signature = auth_header

        # Try both sha256= prefixed and raw
        if signature.startswith("sha256="):
            return self._verify_sha256_prefixed(request.body, signature, secret)
        return self._verify_hmac_sha256(request.body, signature, secret)

    def parse_payload(
        self,
        request: WebhookRequest,
        field_mappings: list[dict[str, Any]] | None = None,
    ) -> IssueData:
        """Parse dbt Cloud webhook payload."""
        payload = request.body_json

        # dbt Cloud sends data in 'data' wrapper
        data = payload.get("data", payload)
        run = data.get("run", data)
        job = data.get("job", {})

        # Check for test failures in run results
        run_results = data.get("run_results", [])
        test_failures = self._extract_test_failures(run_results)

        if test_failures:
            issue_data = self._parse_test_failures(test_failures, run, job, data)
        else:
            # General run failure
            issue_data = self._parse_run_failure(run, job, data)

        # Apply custom field mappings
        self._apply_field_mappings(payload, field_mappings, issue_data)

        return issue_data

    def _extract_test_failures(
        self,
        run_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract failed tests from run results."""
        failures = []
        for result in run_results:
            # Check if this is a test node that failed
            node_type = result.get("unique_id", "").split(".")[0]
            if node_type == "test" and result.get("status") in ("fail", "error"):
                failures.append(result)
        return failures

    def _parse_test_failures(
        self,
        test_failures: list[dict[str, Any]],
        run: dict[str, Any],
        job: dict[str, Any],
        data: dict[str, Any],
    ) -> IssueData:
        """Parse test failures into IssueData."""
        job_name = job.get("name", run.get("job_name", "dbt Job"))
        run_id = run.get("id") or data.get("run_id")
        project_name = data.get("project", {}).get("name", "")

        # Build title
        failure_count = len(test_failures)
        title = f"dbt Test Failed: {failure_count} test(s) in {job_name}"
        if project_name:
            title = f"{title} ({project_name})"

        # Build description with test details
        description_parts = []
        description_parts.append(f"**Run ID:** {run_id}")
        if run.get("started_at"):
            description_parts.append(f"**Started:** {run['started_at']}")

        description_parts.append("\n**Failed Tests:**")
        for test in test_failures[:10]:  # Limit to first 10
            test_name = self._extract_test_name(test)
            message = test.get("message", "")
            description_parts.append(f"- **{test_name}**")
            if message:
                description_parts.append(f"  {message[:200]}")

        if len(test_failures) > 10:
            description_parts.append(f"\n... and {len(test_failures) - 10} more tests")

        # Determine severity based on failure count
        if failure_count >= 5:
            severity = "critical"
        elif failure_count >= 3:
            severity = "high"
        elif failure_count >= 1:
            severity = "medium"
        else:
            severity = "low"

        # Extract first test's model for dataset_id
        first_test = test_failures[0] if test_failures else {}
        model_name = self._extract_model_from_test(first_test)

        # Get run URL if available
        external_url = run.get("href") or data.get("run_url")
        if not external_url and run_id:
            account_id = data.get("account_id") or data.get("account", {}).get("id")
            if account_id:
                external_url = f"https://cloud.getdbt.com/deploy/{account_id}/runs/{run_id}"

        return IssueData(
            title=title,
            description="\n".join(description_parts),
            severity=severity,
            dataset_id=model_name,
            external_url=external_url,
            labels=["dbt", "test-failed"],
            metadata={
                "dbt_run_id": run_id,
                "dbt_job_id": job.get("id"),
                "dbt_job_name": job_name,
                "dbt_project": project_name,
                "dbt_test_count": failure_count,
                "dbt_test_type": self._get_primary_test_type(test_failures),
                "dbt_model": model_name,
                "dbt_test_names": [self._extract_test_name(t) for t in test_failures[:10]],
            },
        )

    def _parse_run_failure(
        self,
        run: dict[str, Any],
        job: dict[str, Any],
        data: dict[str, Any],
    ) -> IssueData:
        """Parse general run failure (not specifically test failures)."""
        job_name = job.get("name", run.get("job_name", "dbt Job"))
        run_id = run.get("id") or data.get("run_id")
        status = run.get("status", data.get("status", "error"))

        title = f"dbt Run Failed: {job_name}"

        description_parts = []
        description_parts.append(f"**Status:** {status}")
        description_parts.append(f"**Run ID:** {run_id}")
        if run.get("started_at"):
            description_parts.append(f"**Started:** {run['started_at']}")
        if run.get("finished_at"):
            description_parts.append(f"**Finished:** {run['finished_at']}")

        # Include error message if available
        error_message = run.get("status_message") or data.get("error")
        if error_message:
            description_parts.append(f"\n**Error:** {error_message}")

        # Get run URL
        external_url = run.get("href") or data.get("run_url")
        if not external_url and run_id:
            account_id = data.get("account_id") or data.get("account", {}).get("id")
            if account_id:
                external_url = f"https://cloud.getdbt.com/deploy/{account_id}/runs/{run_id}"

        return IssueData(
            title=title,
            description="\n".join(description_parts),
            severity="high",
            external_url=external_url,
            labels=["dbt", "run-failed"],
            metadata={
                "dbt_run_id": run_id,
                "dbt_job_id": job.get("id"),
                "dbt_job_name": job_name,
                "dbt_status": status,
                "dbt_error": error_message,
            },
        )

    def _extract_test_name(self, test: dict[str, Any]) -> str:
        """Extract human-readable test name from test result."""
        # Try unique_id first (e.g., "test.project.not_null_orders_id")
        unique_id = str(test.get("unique_id", ""))
        if unique_id:
            parts = unique_id.split(".")
            if len(parts) >= 3:
                return ".".join(parts[2:])  # Skip "test.project_name"
            return unique_id

        # Fallback to name field
        name: str = str(test.get("name", test.get("test_name", "Unknown test")))
        return name

    def _extract_model_from_test(self, test: dict[str, Any]) -> str | None:
        """Extract the model name that a test is associated with."""
        # Check depends_on for model references
        depends_on = test.get("depends_on", {})
        nodes = depends_on.get("nodes", [])
        for node in nodes:
            if isinstance(node, str) and node.startswith("model."):
                # Extract model name from "model.project.model_name"
                parts = node.split(".")
                if len(parts) >= 3:
                    model_name: str = str(parts[-1])
                    return model_name

        # Try to infer from test name (e.g., "not_null_orders_id" -> "orders")
        unique_id = str(test.get("unique_id", ""))
        if unique_id:
            # Pattern: test.project.test_type_model_column
            parts = unique_id.split(".")
            if len(parts) >= 3:
                test_full_name = parts[-1]  # e.g., "not_null_orders_id"
                for test_type in DBT_TYPE_MAP:
                    if test_full_name.startswith(f"{test_type}_"):
                        remainder = test_full_name[len(test_type) + 1 :]
                        # First word is likely the model
                        inferred_model: str = remainder.split("_")[0]
                        if inferred_model:
                            return inferred_model

        return None

    def _get_primary_test_type(self, test_failures: list[dict[str, Any]]) -> str:
        """Get the most common test type from failures."""
        type_counts: dict[str, int] = {}
        for test in test_failures:
            test_type = self._infer_test_type(test)
            type_counts[test_type] = type_counts.get(test_type, 0) + 1

        if type_counts:
            return max(type_counts, key=lambda k: type_counts[k])
        return "unknown"

    def _infer_test_type(self, test: dict[str, Any]) -> str:
        """Infer the test type from a test result."""
        unique_id = test.get("unique_id", "")

        # Check unique_id for test type patterns
        unique_id_lower = unique_id.lower()
        for test_type in DBT_TYPE_MAP:
            if test_type in unique_id_lower:
                return test_type

        # Check test name
        test_name = test.get("name", "").lower()
        for test_type in DBT_TYPE_MAP:
            if test_type in test_name:
                return test_type

        return "unknown"

    def get_fingerprint(
        self,
        request: WebhookRequest,
    ) -> str:
        """Generate fingerprint from dbt run ID."""
        payload = request.body_json
        data = payload.get("data", payload)
        run = data.get("run", data)

        # Use run_id as primary fingerprint
        run_id = run.get("id") or data.get("run_id")
        if run_id:
            return f"dbt_run_{run_id}"

        # Try event ID
        event_id = payload.get("event_id") or payload.get("id")
        if event_id:
            return f"dbt_{event_id}"

        # Check for webhook ID header
        webhook_id = request.header("X-dbt-Cloud-Webhook-Id")
        if webhook_id:
            return f"dbt_{webhook_id}"

        # Fallback to payload hash
        return f"dbt_{self._hash_payload(payload)}"

    def get_event_type(
        self,
        request: WebhookRequest,
    ) -> str:
        """Extract event type from dbt Cloud payload."""
        payload = request.body_json

        # Check for explicit event type
        event_type = payload.get("event_type") or payload.get("eventType")
        if event_type:
            return str(event_type)

        # Check webhook_type
        webhook_type = payload.get("webhook_type")
        if webhook_type:
            return str(webhook_type)

        # Infer from run status
        data = payload.get("data", payload)
        run = data.get("run", data)
        status = run.get("status", "").lower()

        if status in ("error", "failed", "cancelled"):
            return "job.run.errored"
        if status in ("success", "complete"):
            return "job.run.completed"

        return "unknown"

    def should_process(
        self,
        request: WebhookRequest,
    ) -> bool:
        """Only process failed or errored runs."""
        event_type = self.get_event_type(request)

        # Skip successful runs
        if "success" in event_type.lower() or "complete" in event_type.lower():
            # Check if there are test failures even in completed runs
            payload = request.body_json
            data = payload.get("data", payload)
            run_results = data.get("run_results", [])
            test_failures = self._extract_test_failures(run_results)
            return len(test_failures) > 0

        # Process error events
        if "error" in event_type.lower() or "fail" in event_type.lower():
            return True

        # For unknown events, check run status
        payload = request.body_json
        data = payload.get("data", payload)
        run = data.get("run", data)
        status = run.get("status", "").lower()

        return status in ("error", "failed", "cancelled")

    def _map_anomaly_type(self, issue_data: IssueData) -> str:
        """Map dbt test type to standard anomaly type."""
        # Check for test type in metadata
        test_type = issue_data.metadata.get("dbt_test_type")
        if test_type and isinstance(test_type, str):
            mapped = DBT_TYPE_MAP.get(test_type.lower())
            if mapped:
                return mapped

        # Try to infer from test names
        test_names = issue_data.metadata.get("dbt_test_names", [])
        for test_name in test_names:
            if isinstance(test_name, str):
                test_name_lower = test_name.lower()
                for dbt_type, anomaly_type in DBT_TYPE_MAP.items():
                    if dbt_type in test_name_lower:
                        return anomaly_type

        # Fall back to base implementation
        return super()._map_anomaly_type(issue_data)

    def _build_metric_spec(
        self,
        issue_data: IssueData,
        anomaly_type: str,
    ) -> MetricSpec:
        """Build MetricSpec from dbt metadata."""
        job_name = issue_data.metadata.get("dbt_job_name", "")
        model = issue_data.metadata.get("dbt_model", "")
        test_names = issue_data.metadata.get("dbt_test_names", [])

        # Build expression
        if test_names:
            expression = f"dbt tests: {', '.join(test_names[:3])}"
            if len(test_names) > 3:
                expression += f" (+{len(test_names) - 3} more)"
        elif job_name:
            expression = f"dbt job: {job_name}"
        else:
            expression = issue_data.title or "dbt test"

        # Get column references
        columns: list[str] = []
        if model:
            columns.append(str(model))

        return MetricSpec(
            metric_type="description",
            expression=expression,
            display_name=issue_data.title or "dbt Test Failed",
            columns_referenced=columns[:5],
            source_url=issue_data.external_url,
        )
