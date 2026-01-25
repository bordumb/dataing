"""Soda Cloud webhook adapter."""

from __future__ import annotations

from typing import Any

from dataing.core.domain_types import MetricSpec
from dataing_ee.adapters.integrations.base import IntegrationAdapter, IssueData, WebhookRequest
from dataing_ee.adapters.integrations.registry import register_adapter

# Soda check type mapping to standard anomaly types
SODA_TYPE_MAP = {
    "freshness": "freshness",
    "row_count": "row_count",
    "missing_count": "null_rate",
    "missing_percent": "null_rate",
    "duplicate_count": "duplicate_rate",
    "duplicate_percent": "duplicate_rate",
    "schema": "schema_drift",
    "invalid_count": "distribution",
    "invalid_percent": "distribution",
    "values_not_in_set": "distribution",
    "reference": "referential_integrity",
}


@register_adapter
class SodaAdapter(IntegrationAdapter):
    """Adapter for Soda Cloud webhooks.

    Soda Cloud sends webhooks for check failures with the following structure:
    - X-Soda-Signature header with HMAC-SHA256
    - Body with check result details including check name, dataset, status
    """

    provider = "soda"
    signature_header = "X-Soda-Signature"

    # Event types we care about
    SUPPORTED_EVENTS = {
        "check.failed",
        "check.warning",
        "scan.failed",
    }

    def verify_signature(
        self,
        request: WebhookRequest,
        secret: str,
    ) -> bool:
        """Verify Soda Cloud webhook signature (HMAC-SHA256 with sha256= prefix)."""
        signature = request.headers.get(self.signature_header)
        return self._verify_sha256_prefixed(request.body, signature, secret)

    def parse_payload(
        self,
        request: WebhookRequest,
        field_mappings: list[dict[str, Any]] | None = None,
    ) -> IssueData:
        """Parse Soda Cloud webhook payload."""
        payload = request.body_json

        # Soda Cloud sends check results in various formats
        # Handle both single check and scan results
        check = payload.get("check", {})
        scan = payload.get("scan", {})

        if check:
            issue_data = self._parse_check_result(check, payload)
        elif scan:
            issue_data = self._parse_scan_result(scan, payload)
        else:
            # Generic format
            issue_data = IssueData(
                title=payload.get("title", payload.get("name", "Soda Alert")),
                description=payload.get("description"),
            )

        # Apply custom field mappings
        self._apply_field_mappings(payload, field_mappings, issue_data)

        return issue_data

    def _parse_check_result(
        self,
        check: dict[str, Any],
        payload: dict[str, Any],
    ) -> IssueData:
        """Parse check-type payload."""
        check_name = check.get("name", "Unnamed check")
        dataset = check.get("dataset") or check.get("table") or payload.get("dataset")
        check_type = check.get("type", "")

        # Build title
        title_parts = [f"Soda Check Failed: {check_name}"]
        if dataset:
            title_parts.append(f"on {dataset}")
        title = " ".join(title_parts)

        # Build description
        description_parts = []
        if check.get("definition"):
            description_parts.append(f"**Check Definition:** `{check['definition']}`")
        if check.get("outcome"):
            description_parts.append(f"**Outcome:** {check['outcome']}")
        if check.get("value") is not None:
            description_parts.append(f"**Value:** {check['value']}")
        if check.get("fail_threshold") is not None:
            description_parts.append(f"**Threshold:** {check['fail_threshold']}")

        # Map severity based on outcome
        outcome = check.get("outcome", "").lower()
        if outcome == "fail":
            severity = "high"
        elif outcome == "warn":
            severity = "medium"
        else:
            severity = "low"

        return IssueData(
            title=title,
            description="\n\n".join(description_parts) if description_parts else None,
            severity=severity,
            dataset_id=dataset,
            external_url=check.get("url") or payload.get("url"),
            labels=["soda", "check-failed"],
            metadata={
                "soda_check_id": check.get("id"),
                "soda_check_name": check_name,
                "soda_check_type": check_type,
                "soda_dataset": dataset,
                "soda_value": check.get("value"),
                "soda_threshold": check.get("fail_threshold"),
                "expected_value": check.get("fail_threshold"),
                "actual_value": check.get("value"),
            },
        )

    def _parse_scan_result(
        self,
        scan: dict[str, Any],
        payload: dict[str, Any],
    ) -> IssueData:
        """Parse scan-type payload (multiple check failures)."""
        scan_name = scan.get("name", "Soda Scan")
        failed_checks = scan.get("failed_checks", [])
        warn_checks = scan.get("warn_checks", [])

        total_failed = len(failed_checks)
        total_warn = len(warn_checks)

        title = f"Soda Scan Failed: {scan_name} ({total_failed} failed, {total_warn} warnings)"

        description_parts = []
        if failed_checks:
            description_parts.append("**Failed Checks:**")
            for check in failed_checks[:10]:  # Limit to first 10
                check_name = check.get("name", "Unknown")
                description_parts.append(f"- {check_name}")
            if len(failed_checks) > 10:
                description_parts.append(f"- ... and {len(failed_checks) - 10} more")

        # Determine severity based on failure count
        if total_failed >= 5:
            severity = "critical"
        elif total_failed >= 2:
            severity = "high"
        elif total_failed >= 1:
            severity = "medium"
        else:
            severity = "low"

        return IssueData(
            title=title,
            description="\n".join(description_parts) if description_parts else None,
            severity=severity,
            external_url=scan.get("url") or payload.get("url"),
            labels=["soda", "scan-failed"],
            metadata={
                "soda_scan_id": scan.get("id"),
                "soda_scan_name": scan_name,
                "soda_failed_count": total_failed,
                "soda_warn_count": total_warn,
            },
        )

    def get_fingerprint(
        self,
        request: WebhookRequest,
    ) -> str:
        """Generate fingerprint from Soda check/scan ID."""
        payload = request.body_json

        # Check for check ID
        check = payload.get("check", {})
        if check.get("id"):
            return f"soda_check_{check['id']}"

        # Check for scan ID
        scan = payload.get("scan", {})
        if scan.get("id"):
            return f"soda_scan_{scan['id']}"

        # Check for event ID
        event_id = payload.get("event_id") or payload.get("id")
        if event_id:
            return f"soda_{event_id}"

        # Check headers
        request_id = request.headers.get("X-Request-Id")
        if request_id:
            return f"soda_{request_id}"

        # Fallback to payload hash
        return f"soda_{self._hash_payload(payload)}"

    def get_event_type(
        self,
        request: WebhookRequest,
    ) -> str:
        """Extract event type from Soda payload."""
        payload = request.body_json

        event_type = payload.get("event_type") or payload.get("type")
        if event_type:
            return str(event_type)

        # Infer from payload structure
        if payload.get("check"):
            outcome = payload["check"].get("outcome", "").lower()
            if outcome == "fail":
                return "check.failed"
            elif outcome == "warn":
                return "check.warning"
            return "check.unknown"

        if payload.get("scan"):
            return "scan.failed"

        return "unknown"

    def should_process(
        self,
        request: WebhookRequest,
    ) -> bool:
        """Process failure and warning events."""
        event_type = self.get_event_type(request)

        # Skip passed checks
        if "pass" in event_type.lower():
            return False

        return True

    def _map_anomaly_type(self, issue_data: IssueData) -> str:
        """Map Soda check type to standard anomaly type."""
        # Check for check type in metadata
        check_type = issue_data.metadata.get("soda_check_type")
        if check_type and isinstance(check_type, str):
            # Try direct mapping
            mapped = SODA_TYPE_MAP.get(check_type.lower())
            if mapped:
                return mapped

            # Try partial matching
            check_type_lower = check_type.lower()
            for soda_type, anomaly_type in SODA_TYPE_MAP.items():
                if soda_type in check_type_lower:
                    return anomaly_type

        # Fall back to base implementation
        return super()._map_anomaly_type(issue_data)

    def _build_metric_spec(
        self,
        issue_data: IssueData,
        anomaly_type: str,
    ) -> MetricSpec:
        """Build MetricSpec from Soda metadata."""
        check_name = issue_data.metadata.get("soda_check_name", "")
        dataset = issue_data.metadata.get("soda_dataset", "")

        # Build expression from check name
        if check_name:
            expression = f"Soda check: {check_name}"
        else:
            expression = issue_data.title or "Soda check"

        # Get column references
        columns: list[str] = []
        if dataset:
            columns.append(str(dataset))

        return MetricSpec(
            metric_type="description",
            expression=expression,
            display_name=issue_data.title or "Soda Check Failed",
            columns_referenced=columns[:5],
            source_url=issue_data.external_url,
        )
