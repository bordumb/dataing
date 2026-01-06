"""SSO core domain types and interfaces."""

from dataing.core.sso.dns_verification import (
    VerificationToken,
    generate_verification_instructions,
    verify_domain_dns,
)
from dataing.core.sso.types import (
    DomainClaim,
    SSOConfig,
    SSODiscoveryResult,
    SSOIdentity,
    SSOProviderType,
)

__all__ = [
    "DomainClaim",
    "SSOConfig",
    "SSODiscoveryResult",
    "SSOIdentity",
    "SSOProviderType",
    "VerificationToken",
    "generate_verification_instructions",
    "verify_domain_dns",
]
