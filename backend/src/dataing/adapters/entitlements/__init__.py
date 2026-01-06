"""Entitlements adapters."""

from dataing.adapters.entitlements.database import DatabaseEntitlementsAdapter
from dataing.adapters.entitlements.opencore import OpenCoreAdapter

__all__ = ["DatabaseEntitlementsAdapter", "OpenCoreAdapter"]
