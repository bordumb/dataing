"""SSO core domain types and interfaces."""

from dataing_ee.core.sso.dns_verification import (
    VerificationToken,
    generate_verification_instructions,
    verify_domain_dns,
)
from dataing_ee.core.sso.encryption import (
    EncryptionError,
    MissingEncryptionKeyError,
    clear_key_cache,
    decrypt_secret,
    encrypt_secret,
    generate_key,
)
from dataing_ee.core.sso.types import (
    DomainClaim,
    SSOConfig,
    SSODiscoveryResult,
    SSOIdentity,
    SSOProviderType,
    SSOState,
)

__all__ = [
    "DomainClaim",
    "EncryptionError",
    "MissingEncryptionKeyError",
    "SSOConfig",
    "SSODiscoveryResult",
    "SSOIdentity",
    "SSOProviderType",
    "SSOState",
    "VerificationToken",
    "clear_key_cache",
    "decrypt_secret",
    "encrypt_secret",
    "generate_key",
    "generate_verification_instructions",
    "verify_domain_dns",
]
