"""Tests for feature registry types."""

from dataing.core.entitlements.features import PLAN_FEATURES, Feature, Plan


class TestFeatureEnum:
    """Test Feature enum."""

    def test_feature_values_are_strings(self) -> None:
        """Feature enum values should be lowercase strings."""
        assert Feature.SSO_OIDC.value == "sso_oidc"
        assert Feature.MAX_SEATS.value == "max_seats"

    def test_all_features_defined(self) -> None:
        """All expected features should be defined."""
        expected = {
            "sso_oidc",
            "sso_saml",
            "scim",
            "max_seats",
            "max_datasources",
            "max_investigations_per_month",
            "audit_logs",
            "custom_branding",
        }
        actual = {f.value for f in Feature}
        assert expected == actual


class TestPlanEnum:
    """Test Plan enum."""

    def test_plan_values(self) -> None:
        """Plan enum values should be lowercase strings."""
        assert Plan.FREE.value == "free"
        assert Plan.PRO.value == "pro"
        assert Plan.ENTERPRISE.value == "enterprise"


class TestPlanFeatures:
    """Test plan feature definitions."""

    def test_free_plan_has_limits(self) -> None:
        """Free plan should have numeric limits."""
        free = PLAN_FEATURES[Plan.FREE]
        assert free[Feature.MAX_SEATS] == 3
        assert free[Feature.MAX_DATASOURCES] == 2
        assert free[Feature.MAX_INVESTIGATIONS_PER_MONTH] == 10

    def test_free_plan_no_enterprise_features(self) -> None:
        """Free plan should not include enterprise features."""
        free = PLAN_FEATURES[Plan.FREE]
        assert Feature.SSO_OIDC not in free
        assert Feature.SCIM not in free

    def test_pro_plan_has_limits(self) -> None:
        """Pro plan should have numeric limits."""
        pro = PLAN_FEATURES[Plan.PRO]
        assert pro[Feature.MAX_SEATS] == 10
        assert pro[Feature.MAX_DATASOURCES] == 10
        assert pro[Feature.MAX_INVESTIGATIONS_PER_MONTH] == 100

    def test_pro_plan_no_enterprise_features(self) -> None:
        """Pro plan should not include enterprise features."""
        pro = PLAN_FEATURES[Plan.PRO]
        assert Feature.SSO_OIDC not in pro
        assert Feature.SSO_SAML not in pro
        assert Feature.SCIM not in pro
        assert Feature.AUDIT_LOGS not in pro

    def test_enterprise_plan_has_all_features(self) -> None:
        """Enterprise plan should include all features."""
        ent = PLAN_FEATURES[Plan.ENTERPRISE]
        assert ent[Feature.SSO_OIDC] is True
        assert ent[Feature.SSO_SAML] is True
        assert ent[Feature.SCIM] is True
        assert ent[Feature.AUDIT_LOGS] is True

    def test_enterprise_plan_unlimited(self) -> None:
        """Enterprise plan should have unlimited (-1) for limits."""
        ent = PLAN_FEATURES[Plan.ENTERPRISE]
        assert ent[Feature.MAX_SEATS] == -1
        assert ent[Feature.MAX_DATASOURCES] == -1
        assert ent[Feature.MAX_INVESTIGATIONS_PER_MONTH] == -1
