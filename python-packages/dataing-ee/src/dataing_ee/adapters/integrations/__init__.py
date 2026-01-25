"""Integration webhook adapters for external providers."""

from dataing_ee.adapters.integrations.base import (
    IntegrationAdapter,
    IssueData,
    WebhookRequest,
)

# Import adapters to trigger registration
from dataing_ee.adapters.integrations.great_expectations import GreatExpectationsAdapter
from dataing_ee.adapters.integrations.jira import JiraAdapter
from dataing_ee.adapters.integrations.monte_carlo import MonteCarloAdapter
from dataing_ee.adapters.integrations.registry import (
    AdapterRegistry,
    get_adapter,
    register_adapter,
)
from dataing_ee.adapters.integrations.slack import SlackAdapter
from dataing_ee.adapters.integrations.soda import SodaAdapter

__all__ = [
    "IntegrationAdapter",
    "IssueData",
    "WebhookRequest",
    "AdapterRegistry",
    "get_adapter",
    "register_adapter",
    # Adapters
    "JiraAdapter",
    "MonteCarloAdapter",
    "GreatExpectationsAdapter",
    "SlackAdapter",
    "SodaAdapter",
]
