"""Enterprise Edition datasource adapters.

Each adapter registers itself with the shared adapter registry when its module
is imported, so importing this package makes Salesforce, HubSpot and Stripe
available to the datasource routes.
"""

from dataing_ee.adapters.datasource.api.hubspot import HubSpotAdapter
from dataing_ee.adapters.datasource.api.salesforce import SalesforceAdapter
from dataing_ee.adapters.datasource.api.stripe import StripeAdapter

__all__ = ["HubSpotAdapter", "SalesforceAdapter", "StripeAdapter"]
