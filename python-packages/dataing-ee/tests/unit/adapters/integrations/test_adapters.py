"""Unit tests for integration webhook adapters."""

import hashlib
import hmac
import json
import time

import pytest
from dataing_ee.adapters.integrations import (
    AdapterRegistry,
    GreatExpectationsAdapter,
    IssueData,
    JiraAdapter,
    MonteCarloAdapter,
    SlackAdapter,
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

    def test_has_provider(self) -> None:
        """Test checking provider exists."""
        assert AdapterRegistry.has("jira")
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
