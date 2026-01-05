"""Entitlements module for feature gating and billing."""

from dataing.core.entitlements.features import PLAN_FEATURES, Feature, Plan
from dataing.core.entitlements.interfaces import EntitlementsAdapter

__all__ = ["Feature", "Plan", "PLAN_FEATURES", "EntitlementsAdapter"]
