"""Feature registry and plan definitions."""

from enum import Enum


class Feature(str, Enum):
    """Features that can be gated by plan."""

    # Auth features (boolean)
    SSO_OIDC = "sso_oidc"
    SSO_SAML = "sso_saml"
    SCIM = "scim"

    # Limits (numeric, -1 = unlimited)
    MAX_SEATS = "max_seats"
    MAX_DATASOURCES = "max_datasources"
    MAX_INVESTIGATIONS_PER_MONTH = "max_investigations_per_month"

    # Future enterprise features
    AUDIT_LOGS = "audit_logs"
    CUSTOM_BRANDING = "custom_branding"


class Plan(str, Enum):
    """Available subscription plans."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Plan feature definitions - what each plan includes
PLAN_FEATURES: dict[Plan, dict[Feature, int | bool]] = {
    Plan.FREE: {
        Feature.MAX_SEATS: 3,
        Feature.MAX_DATASOURCES: 2,
        Feature.MAX_INVESTIGATIONS_PER_MONTH: 10,
    },
    Plan.PRO: {
        Feature.MAX_SEATS: 10,
        Feature.MAX_DATASOURCES: 10,
        Feature.MAX_INVESTIGATIONS_PER_MONTH: 100,
    },
    Plan.ENTERPRISE: {
        Feature.SSO_OIDC: True,
        Feature.SSO_SAML: True,
        Feature.SCIM: True,
        Feature.AUDIT_LOGS: True,
        Feature.MAX_SEATS: -1,  # unlimited
        Feature.MAX_DATASOURCES: -1,
        Feature.MAX_INVESTIGATIONS_PER_MONTH: -1,
    },
}
