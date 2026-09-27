"""Unit tests for integration webhook adapters."""

import hashlib
import hmac
import json
import time

import pytest
from dataing_ee.adapters.integrations import (
    AdapterRegistry,
    DbtAdapter,
    GreatExpectationsAdapter,
    IntegrationAdapter,
    IssueData,
    JiraAdapter,
    MonteCarloAdapter,
    SlackAdapter,
    SodaAdapter,
    WebhookRequest,
    get_adapter,
)


def make_request(
    body: dict | bytes,
    headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
) -> WebhookRequest:
    """Create a WebhookRequest for testing."""
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    return WebhookRequest(
        body=body,
        headers=headers or {},
        query_params=query_params or {},
    )


def sign_hmac_sha256(body: bytes, secret: str) -> str:
    """Sign body with HMAC-SHA256."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestAdapterRegistry:
    """Test adapter registry."""

    def test_get_jira_adapter(self) -> None:
        """Test getting Jira adapter."""
        adapter = get_adapter("jira")
        assert adapter is not None
        assert isinstance(adapter, JiraAdapter)

    def test_get_monte_carlo_adapter(self) -> None:
        """Test getting Monte Carlo adapter."""
        adapter = get_adapter("monte_carlo")
        assert adapter is not None
        assert isinstance(adapter, MonteCarloAdapter)

    def test_get_great_expectations_adapter(self) -> None:
        """Test getting Great Expectations adapter."""
        adapter = get_adapter("great_expectations")
        assert adapter is not None
        assert isinstance(adapter, GreatExpectationsAdapter)

    def test_get_slack_adapter(self) -> None:
        """Test getting Slack adapter."""
        adapter = get_adapter("slack")
        assert adapter is not None
        assert isinstance(adapter, SlackAdapter)

    def test_get_soda_adapter(self) -> None:
        """Test getting Soda adapter."""
        adapter = get_adapter("soda")
        assert adapter is not None
        assert isinstance(adapter, SodaAdapter)

    def test_get_dbt_adapter(self) -> None:
        """Test getting dbt adapter."""
        adapter = get_adapter("dbt")
        assert adapter is not None
        assert isinstance(adapter, DbtAdapter)

    def test_get_unknown_adapter(self) -> None:
        """Test getting unknown adapter returns None."""
        adapter = get_adapter("unknown_provider")
        assert adapter is None

    def test_list_providers(self) -> None:
        """Test listing all providers."""
        providers = AdapterRegistry.list_providers()
        assert "jira" in providers
        assert "monte_carlo" in providers
        assert "great_expectations" in providers
        assert "slack" in providers
        assert "soda" in providers
        assert "dbt" in providers

    def test_has_provider(self) -> None:
        """Test checking provider exists."""
        assert AdapterRegistry.has("jira")
        assert AdapterRegistry.has("soda")
        assert AdapterRegistry.has("dbt")
        assert not AdapterRegistry.has("unknown")


class TestJiraAdapter:
    """Test Jira adapter."""

    @pytest.fixture
    def adapter(self) -> JiraAdapter:
        """Get Jira adapter."""
        return JiraAdapter()

    def test_verify_signature_valid(self, adapter: JiraAdapter) -> None:
        """Test valid signature verification."""
        body = b'{"issue": {"id": "123"}}'
        secret = "test_secret"
        signature = f"sha256={sign_hmac_sha256(body, secret)}"

        request = make_request(body, {"X-Hub-Signature": signature})
        assert adapter.verify_signature(request, secret) is True

    def test_verify_signature_invalid(self, adapter: JiraAdapter) -> None:
        """Test invalid signature."""
        body = b'{"issue": {"id": "123"}}'
        request = make_request(body, {"X-Hub-Signature": "sha256=invalid"})
        assert adapter.verify_signature(request, "secret") is False

    def test_verify_signature_missing(self, adapter: JiraAdapter) -> None:
        """Test missing signature."""
        request = make_request(b"{}", {})
        assert adapter.verify_signature(request, "secret") is False

    def test_parse_payload(self, adapter: JiraAdapter) -> None:
        """Test parsing Jira webhook payload."""
        payload = {
            "webhookEvent": "jira:issue_created",
            "issue": {
                "id": "12345",
                "key": "PROJ-123",
                "self": "https://company.atlassian.net/rest/api/2/issue/12345",
                "fields": {
                    "summary": "Test Issue Title",
                    "description": "This is a test description",
                    "priority": {"name": "High"},
                    "labels": ["bug", "urgent"],
                    "project": {"key": "PROJ"},
                    "issuetype": {"name": "Bug"},
                },
            },
        }
        request = make_request(payload)
        issue_data = adapter.parse_payload(request)

        assert issue_data.title == "Test Issue Title"
        assert issue_data.description == "This is a test description"
        assert issue_data.priority == "P1"
        assert issue_data.labels == ["bug", "urgent"]
        assert "jira_key" in issue_data.metadata
        assert issue_data.metadata["jira_key"] == "PROJ-123"
        assert issue_data.external_url == "https://company.atlassian.net/browse/PROJ-123"

    def test_get_fingerprint_with_webhook_id(self, adapter: JiraAdapter) -> None:
        """Test fingerprint with webhook ID header."""
        request = make_request(
            {"issue": {"id": "123"}},
            {"X-Atlassian-Webhook-Id": "webhook-abc-123"},
        )
        fingerprint = adapter.get_fingerprint(request)
        assert fingerprint == "jira_webhook_webhook-abc-123"

    def test_get_fingerprint_from_payload(self, adapter: JiraAdapter) -> None:
        """Test fingerprint from payload."""
        request = make_request(
            {
                "webhookEvent": "issue_created",
                "issue": {"id": "12345"},
            }
        )
        fingerprint = adapter.get_fingerprint(request)
        assert fingerprint == "jira_12345_issue_created"

    def test_get_event_type(self, adapter: JiraAdapter) -> None:
        """Test event type extraction."""
        request = make_request({"webhookEvent": "jira:issue_updated"})
        assert adapter.get_event_type(request) == "jira:issue_updated"

    def test_should_process_supported_event(self, adapter: JiraAdapter) -> None:
        """Test should_process for supported event."""
        request = make_request({"webhookEvent": "jira:issue_created"})
        assert adapter.should_process(request) is True

    def test_should_process_unsupported_event(self, adapter: JiraAdapter) -> None:
        """Test should_process for unsupported event."""
        request = make_request({"webhookEvent": "sprint_started"})
        assert adapter.should_process(request) is False


class TestMonteCarloAdapter:
    """Test Monte Carlo adapter."""

    @pytest.fixture
    def adapter(self) -> MonteCarloAdapter:
        """Get Monte Carlo adapter."""
        return MonteCarloAdapter()

    def test_verify_signature_valid(self, adapter: MonteCarloAdapter) -> None:
        """Test valid signature verification."""
        body = b'{"incident": {"id": "123"}}'
        secret = "test_secret"
        signature = sign_hmac_sha256(body, secret)

        request = make_request(body, {"X-MC-Signature": signature})
        assert adapter.verify_signature(request, secret) is True

    def test_verify_signature_invalid(self, adapter: MonteCarloAdapter) -> None:
        """Test invalid signature."""
        body = b'{"incident": {"id": "123"}}'
        request = make_request(body, {"X-MC-Signature": "invalid"})
        assert adapter.verify_signature(request, "secret") is False

    def test_parse_incident_payload(self, adapter: MonteCarloAdapter) -> None:
        """Test parsing incident payload."""
        payload = {
            "event_type": "incident_created",
            "incident": {
                "id": "inc-123",
                "title": "Data Freshness Issue",
                "description": "Table has not been updated in 24 hours",
                "severity": "high",
                "impact": "Production dashboards affected",
                "url": "https://getmontecarlo.com/incidents/inc-123",
                "type": "Freshness",
                "tables": [
                    {"full_table_id": "warehouse.schema.table1"},
                    {"full_table_id": "warehouse.schema.table2"},
                ],
            },
        }
        request = make_request(payload)
        issue_data = adapter.parse_payload(request)

        assert issue_data.title == "Data Freshness Issue"
        assert "24 hours" in issue_data.description
        assert issue_data.severity == "high"
        assert "monte-carlo" in issue_data.labels
        assert "incident" in issue_data.labels
        assert issue_data.metadata["mc_incident_id"] == "inc-123"

    def test_parse_alert_payload(self, adapter: MonteCarloAdapter) -> None:
        """Test parsing alert payload."""
        payload = {
            "event_type": "alert_triggered",
            "alert": {
                "id": "alert-456",
                "name": "Null Rate Spike",
                "description": "Column null rate exceeded threshold",
                "severity": "medium",
                "monitor_type": "field_quality",
                "table": "warehouse.analytics.users",
                "url": "https://getmontecarlo.com/alerts/alert-456",
            },
        }
        request = make_request(payload)
        issue_data = adapter.parse_payload(request)

        assert issue_data.title == "Null Rate Spike"
        assert issue_data.severity == "medium"
        assert issue_data.dataset_id == "warehouse.analytics.users"
        assert "alert" in issue_data.labels

    def test_get_fingerprint_incident(self, adapter: MonteCarloAdapter) -> None:
        """Test fingerprint from incident."""
        request = make_request({"incident": {"id": "inc-123"}})
        assert adapter.get_fingerprint(request) == "mc_incident_inc-123"

    def test_get_fingerprint_alert(self, adapter: MonteCarloAdapter) -> None:
        """Test fingerprint from alert."""
        request = make_request({"alert": {"id": "alert-456"}})
        assert adapter.get_fingerprint(request) == "mc_alert_alert-456"

    def test_should_process_incident(self, adapter: MonteCarloAdapter) -> None:
        """Test should_process for incident."""
        request = make_request({"event_type": "incident_created"})
        assert adapter.should_process(request) is True

    def test_should_not_process_resolved(self, adapter: MonteCarloAdapter) -> None:
        """Test should_process skips resolved events."""
        request = make_request({"event_type": "incident_resolved"})
        assert adapter.should_process(request) is False


class TestGreatExpectationsAdapter:
    """Test Great Expectations adapter."""

    @pytest.fixture
    def adapter(self) -> GreatExpectationsAdapter:
        """Get Great Expectations adapter."""
        return GreatExpectationsAdapter()

    def test_verify_signature_valid(self, adapter: GreatExpectationsAdapter) -> None:
        """Test valid signature verification."""
        body = b'{"result": {"success": false}}'
        secret = "test_secret"
        signature = f"sha256={sign_hmac_sha256(body, secret)}"

        request = make_request(body, {"X-GE-Signature": signature})
        assert adapter.verify_signature(request, secret) is True

    def test_parse_failed_validation(self, adapter: GreatExpectationsAdapter) -> None:
        """Test parsing failed validation result."""
        payload = {
            "checkpoint_name": "daily_validation",
            "data_asset_name": "warehouse.analytics.orders",
            "run_id": "run-123",
            "result": {
                "success": False,
                "expectation_suite_name": "orders_suite",
                "statistics": {
                    "evaluated_expectations": 10,
                    "successful_expectations": 7,
                    "unsuccessful_expectations": 3,
                    "success_percent": 70.0,
                },
                "results": [
                    {
                        "success": False,
                        "expectation_config": {
                            "expectation_type": "expect_column_values_to_not_be_null",
                            "kwargs": {"column": "order_id"},
                        },
                    },
                    {
                        "success": False,
                        "expectation_config": {
                            "expectation_type": "expect_column_values_to_be_unique",
                            "kwargs": {"column": "order_id"},
                        },
                    },
                ],
            },
        }
        request = make_request(payload)
        issue_data = adapter.parse_payload(request)

        assert "Data Quality Check Failed" in issue_data.title
        assert "orders_suite" in issue_data.title
        assert "3/10 failed" in issue_data.description
        assert issue_data.severity == "high"  # 70% success = high severity
        assert issue_data.dataset_id == "warehouse.analytics.orders"
        assert "great-expectations" in issue_data.labels

    def test_should_not_process_success(self, adapter: GreatExpectationsAdapter) -> None:
        """Test should_process skips successful validations."""
        request = make_request({"result": {"success": True}})
        assert adapter.should_process(request) is False

    def test_should_process_failure(self, adapter: GreatExpectationsAdapter) -> None:
        """Test should_process includes failed validations."""
        request = make_request({"result": {"success": False}})
        assert adapter.should_process(request) is True

    def test_get_fingerprint(self, adapter: GreatExpectationsAdapter) -> None:
        """Test fingerprint generation."""
        request = make_request(
            {
                "run_id": "run-123",
                "result": {"expectation_suite_name": "my_suite"},
            }
        )
        assert adapter.get_fingerprint(request) == "ge_run-123_my_suite"

    def test_severity_critical(self, adapter: GreatExpectationsAdapter) -> None:
        """Test critical severity for low success rate."""
        payload = {
            "result": {
                "success": False,
                "statistics": {"success_percent": 40.0},
            },
        }
        request = make_request(payload)
        issue_data = adapter.parse_payload(request)
        assert issue_data.severity == "critical"

    def test_severity_low(self, adapter: GreatExpectationsAdapter) -> None:
        """Test low severity for high success rate."""
        payload = {
            "result": {
                "success": False,
                "statistics": {"success_percent": 95.0},
            },
        }
        request = make_request(payload)
        issue_data = adapter.parse_payload(request)
        assert issue_data.severity == "low"


class TestSlackAdapter:
    """Test Slack adapter."""

    @pytest.fixture
    def adapter(self) -> SlackAdapter:
        """Get Slack adapter."""
        return SlackAdapter()

    def test_verify_signature_valid(self, adapter: SlackAdapter) -> None:
        """Test valid Slack signature verification."""
        secret = "test_secret"
        body = b'{"type": "event_callback"}'
        timestamp = str(int(time.time()))

        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        signature = hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()

        request = make_request(
            body,
            {
                "X-Slack-Signature": f"v0={signature}",
                "X-Slack-Request-Timestamp": timestamp,
            },
        )
        assert adapter.verify_signature(request, secret) is True

    def test_verify_signature_old_timestamp(self, adapter: SlackAdapter) -> None:
        """Test signature rejection for old timestamp."""
        secret = "test_secret"
        body = b'{"type": "event_callback"}'
        timestamp = str(int(time.time()) - 600)  # 10 minutes old

        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        signature = hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()

        request = make_request(
            body,
            {
                "X-Slack-Signature": f"v0={signature}",
                "X-Slack-Request-Timestamp": timestamp,
            },
        )
        assert adapter.verify_signature(request, secret) is False

    def test_parse_message_event(self, adapter: SlackAdapter) -> None:
        """Test parsing message event."""
        payload = {
            "type": "event_callback",
            "team_id": "T12345",
            "event": {
                "type": "message",
                "channel": "C12345",
                "user": "U12345",
                "text": "This is a bug report: something is broken",
                "ts": "1234567890.123456",
            },
        }
        request = make_request(payload)
        issue_data = adapter.parse_payload(request)

        assert issue_data.title == "This is a bug report: something is broken"
        assert "slack" in issue_data.labels
        assert issue_data.metadata["slack_channel"] == "C12345"

    def test_parse_reaction_event(self, adapter: SlackAdapter) -> None:
        """Test parsing reaction event."""
        payload = {
            "type": "event_callback",
            "team_id": "T12345",
            "event": {
                "type": "reaction_added",
                "user": "U12345",
                "reaction": "bug",
                "item": {
                    "type": "message",
                    "channel": "C12345",
                    "ts": "1234567890.123456",
                },
            },
        }
        request = make_request(payload)
        issue_data = adapter.parse_payload(request)

        assert ":bug:" in issue_data.title
        assert "reaction-bug" in issue_data.labels

    def test_should_not_process_url_verification(self, adapter: SlackAdapter) -> None:
        """Test URL verification is skipped."""
        request = make_request(
            {
                "type": "url_verification",
                "challenge": "test-challenge",
            }
        )
        assert adapter.should_process(request) is False

    def test_should_not_process_bot_message(self, adapter: SlackAdapter) -> None:
        """Test bot messages are skipped."""
        request = make_request(
            {
                "type": "event_callback",
                "event": {
                    "type": "message",
                    "bot_id": "B12345",
                },
            }
        )
        assert adapter.should_process(request) is False

    def test_should_process_trigger_reaction(self, adapter: SlackAdapter) -> None:
        """Test trigger reactions are processed."""
        request = make_request(
            {
                "type": "event_callback",
                "event": {
                    "type": "reaction_added",
                    "reaction": "bug",
                },
            }
        )
        assert adapter.should_process(request) is True

    def test_should_not_process_non_trigger_reaction(self, adapter: SlackAdapter) -> None:
        """Test non-trigger reactions are skipped."""
        request = make_request(
            {
                "type": "event_callback",
                "event": {
                    "type": "reaction_added",
                    "reaction": "thumbsup",
                },
            }
        )
        assert adapter.should_process(request) is False

    def test_get_fingerprint_event_id(self, adapter: SlackAdapter) -> None:
        """Test fingerprint from event ID."""
        request = make_request(
            {
                "event_id": "Ev12345",
                "type": "event_callback",
            }
        )
        assert adapter.get_fingerprint(request) == "slack_Ev12345"

    def test_get_event_type(self, adapter: SlackAdapter) -> None:
        """Test event type extraction."""
        request = make_request(
            {
                "type": "event_callback",
                "event": {"type": "message"},
            }
        )
        assert adapter.get_event_type(request) == "message"


class TestSodaAdapter:
    """Test Soda Cloud adapter."""

    @pytest.fixture
    def adapter(self) -> SodaAdapter:
        """Create adapter instance."""
        return SodaAdapter()

    def test_verify_signature_valid(self, adapter: SodaAdapter) -> None:
        """Test valid signature verification."""
        secret = "test_secret"
        body = b'{"check": {"id": "123"}}'
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        request = WebhookRequest(
            body=body,
            headers={"X-Soda-Signature": signature},
            query_params={},
        )
        assert adapter.verify_signature(request, secret) is True

    def test_verify_signature_invalid(self, adapter: SodaAdapter) -> None:
        """Test invalid signature is rejected."""
        request = WebhookRequest(
            body=b'{"check": {"id": "123"}}',
            headers={"X-Soda-Signature": "sha256=invalid"},
            query_params={},
        )
        assert adapter.verify_signature(request, "test_secret") is False

    def test_parse_check_payload(self, adapter: SodaAdapter) -> None:
        """Test parsing check failure payload."""
        request = make_request(
            {
                "check": {
                    "id": "chk-123",
                    "name": "row_count > 0",
                    "dataset": "orders",
                    "type": "row_count",
                    "outcome": "fail",
                    "value": 0,
                    "fail_threshold": 1,
                    "definition": "row_count > 0",
                },
            }
        )
        issue_data = adapter.parse_payload(request)

        assert "row_count > 0" in issue_data.title
        assert "orders" in issue_data.title
        assert issue_data.severity == "high"
        assert issue_data.dataset_id == "orders"
        assert issue_data.metadata["soda_check_id"] == "chk-123"
        assert issue_data.metadata["soda_check_type"] == "row_count"

    def test_parse_scan_payload(self, adapter: SodaAdapter) -> None:
        """Test parsing scan failure payload."""
        request = make_request(
            {
                "scan": {
                    "id": "scan-456",
                    "name": "daily_quality_check",
                    "failed_checks": [
                        {"name": "check1"},
                        {"name": "check2"},
                    ],
                    "warn_checks": [{"name": "check3"}],
                },
            }
        )
        issue_data = adapter.parse_payload(request)

        assert "daily_quality_check" in issue_data.title
        assert "2 failed" in issue_data.title
        assert "1 warnings" in issue_data.title
        assert issue_data.severity == "high"  # 2 failures = high severity
        assert issue_data.metadata["soda_failed_count"] == 2

    def test_get_fingerprint_check(self, adapter: SodaAdapter) -> None:
        """Test fingerprint from check ID."""
        request = make_request({"check": {"id": "chk-789"}})
        assert adapter.get_fingerprint(request) == "soda_check_chk-789"

    def test_get_fingerprint_scan(self, adapter: SodaAdapter) -> None:
        """Test fingerprint from scan ID."""
        request = make_request({"scan": {"id": "scan-789"}})
        assert adapter.get_fingerprint(request) == "soda_scan_scan-789"

    def test_get_event_type_check_failed(self, adapter: SodaAdapter) -> None:
        """Test event type for failed check."""
        request = make_request({"check": {"outcome": "fail"}})
        assert adapter.get_event_type(request) == "check.failed"

    def test_get_event_type_check_warning(self, adapter: SodaAdapter) -> None:
        """Test event type for warning check."""
        request = make_request({"check": {"outcome": "warn"}})
        assert adapter.get_event_type(request) == "check.warning"

    def test_should_process_failure(self, adapter: SodaAdapter) -> None:
        """Test should process failed check."""
        request = make_request({"check": {"outcome": "fail"}})
        assert adapter.should_process(request) is True

    def test_should_not_process_pass(self, adapter: SodaAdapter) -> None:
        """Test should not process passed check."""
        request = make_request({"event_type": "check.passed"})
        assert adapter.should_process(request) is False

    def test_to_anomaly_alert(self, adapter: SodaAdapter) -> None:
        """Test Soda adapter creates valid AnomalyAlert."""
        issue_data = IssueData(
            title="Soda Check Failed: row_count > 0 on orders",
            severity="high",
            dataset_id="orders",
            metadata={
                "soda_check_id": "chk-123",
                "soda_check_type": "row_count",
                "soda_dataset": "orders",
                "expected_value": 1,
                "actual_value": 0,
            },
        )

        alert = adapter.to_anomaly_alert(issue_data, fingerprint="soda_check_chk-123")

        assert alert.source_system == "soda"
        assert alert.source_alert_id == "soda_check_chk-123"
        assert alert.anomaly_type == "row_count"
        assert "orders" in alert.dataset_ids


class TestDbtAdapter:
    """Test dbt Cloud adapter."""

    @pytest.fixture
    def adapter(self) -> DbtAdapter:
        """Create adapter instance."""
        return DbtAdapter()

    def test_verify_signature_bearer_valid(self, adapter: DbtAdapter) -> None:
        """Test valid signature with Bearer prefix."""
        secret = "test_secret"
        body = b'{"data": {"run": {"id": 123}}}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        request = WebhookRequest(
            body=body,
            headers={"Authorization": f"Bearer {signature}"},
            query_params={},
        )
        assert adapter.verify_signature(request, secret) is True

    def test_verify_signature_sha256_prefix_valid(self, adapter: DbtAdapter) -> None:
        """Test valid signature with sha256= prefix."""
        secret = "test_secret"
        body = b'{"data": {"run": {"id": 123}}}'
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        request = WebhookRequest(
            body=body,
            headers={"Authorization": signature},
            query_params={},
        )
        assert adapter.verify_signature(request, secret) is True

    def test_verify_signature_invalid(self, adapter: DbtAdapter) -> None:
        """Test invalid signature is rejected."""
        request = WebhookRequest(
            body=b'{"data": {"run": {"id": 123}}}',
            headers={"Authorization": "Bearer invalid"},
            query_params={},
        )
        assert adapter.verify_signature(request, "test_secret") is False

    def test_verify_signature_missing(self, adapter: DbtAdapter) -> None:
        """Test missing signature is rejected."""
        request = WebhookRequest(
            body=b'{"data": {"run": {"id": 123}}}',
            headers={},
            query_params={},
        )
        assert adapter.verify_signature(request, "test_secret") is False

    def test_parse_test_failures(self, adapter: DbtAdapter) -> None:
        """Test parsing test failure payload."""
        request = make_request(
            {
                "data": {
                    "run": {
                        "id": "run-123",
                        "status": "error",
                        "started_at": "2024-01-15T10:00:00Z",
                    },
                    "job": {
                        "id": "job-456",
                        "name": "Daily Transform",
                    },
                    "project": {"name": "analytics"},
                    "account_id": "acc-789",
                    "run_results": [
                        {
                            "unique_id": "test.project.not_null_orders_id",
                            "status": "fail",
                            "message": "Failed: null values found",
                            "depends_on": {"nodes": ["model.project.orders"]},
                        },
                        {
                            "unique_id": "test.project.unique_orders_id",
                            "status": "fail",
                            "message": "Failed: duplicate values found",
                            "depends_on": {"nodes": ["model.project.orders"]},
                        },
                    ],
                },
            }
        )
        issue_data = adapter.parse_payload(request)

        assert "2 test(s)" in issue_data.title
        assert "Daily Transform" in issue_data.title
        assert issue_data.severity == "medium"  # 2 failures = medium
        assert issue_data.metadata["dbt_run_id"] == "run-123"
        assert issue_data.metadata["dbt_test_count"] == 2
        assert "dbt" in issue_data.labels
        assert "test-failed" in issue_data.labels

    def test_parse_run_failure(self, adapter: DbtAdapter) -> None:
        """Test parsing general run failure (no test results)."""
        request = make_request(
            {
                "data": {
                    "run": {
                        "id": "run-999",
                        "status": "error",
                        "status_message": "Compilation error in model",
                    },
                    "job": {"name": "Daily Transform"},
                },
            }
        )
        issue_data = adapter.parse_payload(request)

        assert "dbt Run Failed" in issue_data.title
        assert "Daily Transform" in issue_data.title
        assert issue_data.severity == "high"
        assert "Compilation error" in issue_data.description
        assert "run-failed" in issue_data.labels

    def test_parse_severity_critical(self, adapter: DbtAdapter) -> None:
        """Test critical severity for 5+ failures."""
        request = make_request(
            {
                "data": {
                    "job": {"name": "Job"},
                    "run_results": [
                        {"unique_id": f"test.project.test_{i}", "status": "fail"} for i in range(5)
                    ],
                },
            }
        )
        issue_data = adapter.parse_payload(request)
        assert issue_data.severity == "critical"

    def test_parse_severity_high(self, adapter: DbtAdapter) -> None:
        """Test high severity for 3-4 failures."""
        request = make_request(
            {
                "data": {
                    "job": {"name": "Job"},
                    "run_results": [
                        {"unique_id": f"test.project.test_{i}", "status": "fail"} for i in range(3)
                    ],
                },
            }
        )
        issue_data = adapter.parse_payload(request)
        assert issue_data.severity == "high"

    def test_get_fingerprint_run_id(self, adapter: DbtAdapter) -> None:
        """Test fingerprint from run ID."""
        request = make_request({"data": {"run": {"id": "run-abc"}}})
        assert adapter.get_fingerprint(request) == "dbt_run_run-abc"

    def test_get_fingerprint_event_id(self, adapter: DbtAdapter) -> None:
        """Test fingerprint from event ID."""
        request = make_request({"event_id": "evt-123"})
        assert adapter.get_fingerprint(request) == "dbt_evt-123"

    def test_get_fingerprint_fallback(self, adapter: DbtAdapter) -> None:
        """Test fingerprint fallback to hash."""
        request = make_request({"some": "data"})
        fingerprint = adapter.get_fingerprint(request)
        assert fingerprint.startswith("dbt_")

    def test_get_event_type_explicit(self, adapter: DbtAdapter) -> None:
        """Test event type from explicit field."""
        request = make_request({"event_type": "job.run.errored"})
        assert adapter.get_event_type(request) == "job.run.errored"

    def test_get_event_type_from_status(self, adapter: DbtAdapter) -> None:
        """Test event type inferred from run status."""
        request = make_request({"data": {"run": {"status": "error"}}})
        assert adapter.get_event_type(request) == "job.run.errored"

    def test_should_process_error(self, adapter: DbtAdapter) -> None:
        """Test should process errored runs."""
        request = make_request({"event_type": "job.run.errored"})
        assert adapter.should_process(request) is True

    def test_should_not_process_success(self, adapter: DbtAdapter) -> None:
        """Test should not process successful runs without test failures."""
        request = make_request({"event_type": "job.run.completed", "data": {}})
        assert adapter.should_process(request) is False

    def test_should_process_completed_with_test_failures(self, adapter: DbtAdapter) -> None:
        """Test should process completed runs that have test failures."""
        request = make_request(
            {
                "event_type": "job.run.completed",
                "data": {
                    "run_results": [
                        {"unique_id": "test.project.test_1", "status": "fail"},
                    ],
                },
            }
        )
        assert adapter.should_process(request) is True

    def test_to_anomaly_alert(self, adapter: DbtAdapter) -> None:
        """Test dbt adapter creates valid AnomalyAlert."""
        issue_data = IssueData(
            title="dbt Test Failed: 2 test(s) in Daily Transform",
            severity="medium",
            dataset_id="orders",
            metadata={
                "dbt_run_id": "run-123",
                "dbt_job_name": "Daily Transform",
                "dbt_test_type": "not_null",
                "dbt_model": "orders",
                "dbt_test_names": ["not_null_orders_id", "unique_orders_id"],
            },
        )

        alert = adapter.to_anomaly_alert(issue_data, fingerprint="dbt_run_run-123")

        assert alert.source_system == "dbt"
        assert alert.source_alert_id == "dbt_run_run-123"
        assert alert.anomaly_type == "null_rate"  # mapped from not_null
        assert "orders" in alert.dataset_ids

    def test_anomaly_type_mapping(self, adapter: DbtAdapter) -> None:
        """Test dbt test type to anomaly type mapping."""
        test_cases = [
            ("not_null", "null_rate"),
            ("unique", "duplicate_rate"),
            ("accepted_values", "distribution"),
            ("relationships", "referential_integrity"),
            ("freshness", "freshness"),
        ]

        for dbt_type, expected_type in test_cases:
            issue_data = IssueData(
                title=f"{dbt_type} test failure",
                metadata={"dbt_test_type": dbt_type},
            )
            alert = adapter.to_anomaly_alert(issue_data, fingerprint=f"test-{dbt_type}")
            assert alert.anomaly_type == expected_type, f"Failed for {dbt_type}"

    def test_extract_model_from_depends_on(self, adapter: DbtAdapter) -> None:
        """Test model extraction from test depends_on."""
        request = make_request(
            {
                "data": {
                    "job": {"name": "Job"},
                    "run_results": [
                        {
                            "unique_id": "test.project.not_null_orders_id",
                            "status": "fail",
                            "depends_on": {"nodes": ["model.project.orders"]},
                        },
                    ],
                },
            }
        )
        issue_data = adapter.parse_payload(request)
        assert issue_data.dataset_id == "orders"


class TestIssueData:
    """Test IssueData dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        data = IssueData()
        assert data.title is None
        assert data.description is None
        assert data.labels == []
        assert data.metadata == {}

    def test_with_values(self) -> None:
        """Test setting values."""
        data = IssueData(
            title="Test Title",
            description="Test Description",
            severity="high",
            priority="P1",
            labels=["bug"],
            metadata={"key": "value"},
        )
        assert data.title == "Test Title"
        assert data.severity == "high"
        assert data.labels == ["bug"]


class TestToAnomalyAlert:
    """Test to_anomaly_alert conversion method."""

    def test_monte_carlo_to_anomaly_alert(self) -> None:
        """Test Monte Carlo adapter creates valid AnomalyAlert."""
        adapter = MonteCarloAdapter()
        issue_data = IssueData(
            title="Freshness issue on orders table",
            description="Data is stale",
            severity="high",
            dataset_id="db.schema.orders",
            external_url="https://getmontecarlo.com/incident/123",
            metadata={
                "mc_incident_id": "inc-123",
                "mc_type": "freshness",
                "mc_tables": ["db.schema.orders", "db.schema.order_items"],
            },
        )

        alert = adapter.to_anomaly_alert(issue_data, fingerprint="mc_incident_inc-123")

        assert alert.source_system == "monte_carlo"
        assert alert.source_alert_id == "mc_incident_inc-123"
        assert alert.severity == "high"
        assert alert.anomaly_type == "freshness"
        assert "db.schema.orders" in alert.dataset_ids
        assert alert.source_url == "https://getmontecarlo.com/incident/123"
        assert alert.metric_spec.metric_type == "description"
        assert "freshness" in alert.metric_spec.expression.lower()

    def test_great_expectations_to_anomaly_alert(self) -> None:
        """Test Great Expectations adapter creates valid AnomalyAlert."""
        adapter = GreatExpectationsAdapter()
        issue_data = IssueData(
            title="Data Quality Check Failed - orders_suite",
            description="3 expectations failed",
            severity="critical",
            dataset_id="orders",
            external_url="https://ge-docs.example.com/results/123",
            metadata={
                "ge_suite": "orders_suite",
                "ge_checkpoint": "daily_check",
                "ge_run_id": "run-456",
                "ge_statistics": {
                    "evaluated_expectations": 10,
                    "unsuccessful_expectations": 3,
                    "success_percent": 70.0,
                },
            },
        )

        alert = adapter.to_anomaly_alert(issue_data, fingerprint="ge_run-456_orders_suite")

        assert alert.source_system == "great_expectations"
        assert alert.source_alert_id == "ge_run-456_orders_suite"
        assert alert.severity == "critical"
        assert "orders" in alert.dataset_ids
        assert alert.source_url == "https://ge-docs.example.com/results/123"
        assert "orders_suite" in alert.metric_spec.expression
        assert "(3/10 failed)" in alert.metric_spec.display_name

    def test_to_anomaly_alert_with_values(self) -> None:
        """Test to_anomaly_alert uses expected/actual values from metadata."""
        adapter = MonteCarloAdapter()
        issue_data = IssueData(
            title="Volume anomaly",
            severity="medium",
            metadata={
                "expected_value": 1000.0,
                "actual_value": 500.0,
                "deviation_pct": 50.0,
            },
        )

        alert = adapter.to_anomaly_alert(issue_data, fingerprint="test-123")

        assert alert.expected_value == 1000.0
        assert alert.actual_value == 500.0
        assert alert.deviation_pct == 50.0

    def test_to_anomaly_alert_calculates_deviation(self) -> None:
        """Test deviation is calculated if not provided."""
        adapter = MonteCarloAdapter()
        issue_data = IssueData(
            title="Row count anomaly",
            severity="low",
            metadata={
                "expected_value": 100.0,
                "actual_value": 80.0,
            },
        )

        alert = adapter.to_anomaly_alert(issue_data, fingerprint="test-456")

        assert alert.deviation_pct == 20.0  # (100-80)/100 * 100

    def test_anomaly_type_mapping_monte_carlo(self) -> None:
        """Test Monte Carlo type mapping."""
        adapter = MonteCarloAdapter()

        test_cases = [
            ("volume", "row_count"),
            ("field_health", "null_rate"),
            ("freshness", "freshness"),
            ("dimension_tracking", "distribution"),
        ]

        for mc_type, expected_type in test_cases:
            issue_data = IssueData(
                title=f"{mc_type} issue",
                metadata={"mc_type": mc_type},
            )
            alert = adapter.to_anomaly_alert(issue_data, fingerprint=f"test-{mc_type}")
            assert alert.anomaly_type == expected_type, f"Failed for {mc_type}"


class TestWebhookRequest:
    """Test WebhookRequest dataclass."""

    def test_body_json(self) -> None:
        """Test body_json property."""
        request = make_request({"key": "value"})
        assert request.body_json == {"key": "value"}

    def test_body_json_invalid(self) -> None:
        """Test body_json with invalid JSON."""
        request = WebhookRequest(
            body=b"not json",
            headers={},
            query_params={},
        )
        with pytest.raises(json.JSONDecodeError):
            _ = request.body_json

    def test_header_found_in_any_case(self) -> None:
        """Test a header is found whatever case it was sent or asked for in."""
        request = make_request({}, {"x-hub-signature": "sha256=abc", "X-Request-Id": "req-1"})

        assert request.header("X-Hub-Signature") == "sha256=abc"
        assert request.header("x-request-id") == "req-1"

    def test_header_missing(self) -> None:
        """Test a header that was not sent is None."""
        assert make_request({}).header("X-Hub-Signature") is None


class TestLowercaseHeaders:
    """ASGI servers deliver header names in lowercase; adapters must still find them."""

    @pytest.mark.parametrize(
        ("adapter", "headers", "fingerprint"),
        [
            (JiraAdapter(), {"x-atlassian-webhook-id": "wh-1"}, "jira_webhook_wh-1"),
            (MonteCarloAdapter(), {"x-request-id": "req-1"}, "mc_req-1"),
            (SodaAdapter(), {"x-request-id": "req-1"}, "soda_req-1"),
            (DbtAdapter(), {"x-dbt-cloud-webhook-id": "wh-1"}, "dbt_wh-1"),
        ],
        ids=["jira", "monte_carlo", "soda", "dbt"],
    )
    def test_fingerprint_header(
        self, adapter: IntegrationAdapter, headers: dict[str, str], fingerprint: str
    ) -> None:
        """Test fingerprint headers are read from their lowercase names."""
        assert adapter.get_fingerprint(make_request({}, headers)) == fingerprint
