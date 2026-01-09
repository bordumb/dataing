"""DNS verification service for domain claims."""

import logging
import secrets
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# DNS record prefix for verification
DNS_RECORD_PREFIX = "_dataing"
TOKEN_PREFIX = "dataing-verify="


@dataclass
class VerificationToken:
    """DNS verification token."""

    token: str
    dns_record: str
    dns_value: str

    @classmethod
    def generate(cls, domain: str) -> "VerificationToken":
        """Generate a new verification token for a domain.

        Args:
            domain: Domain to verify.

        Returns:
            New verification token with DNS record instructions.
        """
        # Generate random 32-byte hex token
        token = secrets.token_hex(32)
        dns_record = f"{DNS_RECORD_PREFIX}.{domain}"
        dns_value = f"{TOKEN_PREFIX}{token}"

        return cls(
            token=token,
            dns_record=dns_record,
            dns_value=dns_value,
        )


async def verify_domain_dns(domain: str, expected_token: str) -> bool:
    """Verify domain ownership via DNS TXT record.

    Checks if the domain has a TXT record at _dataing.<domain>
    containing the expected verification token.

    Args:
        domain: Domain to verify.
        expected_token: Expected token value.

    Returns:
        True if verification succeeds, False otherwise.
    """
    try:
        import dns.resolver

        record_name = f"{DNS_RECORD_PREFIX}.{domain}"
        expected_value = f"{TOKEN_PREFIX}{expected_token}"

        logger.info(f"Verifying DNS for {record_name}")

        # Query TXT records
        answers = dns.resolver.resolve(record_name, "TXT")

        for rdata in answers:
            # TXT records may have multiple strings, join them
            txt_value = "".join(s.decode() for s in rdata.strings)
            logger.debug(f"Found TXT record: {txt_value}")

            if txt_value == expected_value:
                logger.info(f"DNS verification successful for {domain}")
                return True

        logger.warning(f"DNS verification failed - token not found for {domain}")
        return False

    except dns.resolver.NXDOMAIN:
        logger.warning(f"DNS verification failed - no DNS record for {domain}")
        return False
    except dns.resolver.NoAnswer:
        logger.warning(f"DNS verification failed - no TXT record for {domain}")
        return False
    except dns.resolver.NoNameservers:
        logger.warning(f"DNS verification failed - no nameservers for {domain}")
        return False
    except Exception as e:
        logger.exception(f"DNS verification error for {domain}: {e}")
        return False


def generate_verification_instructions(domain: str, token: str) -> str:
    """Generate human-readable DNS verification instructions.

    Args:
        domain: Domain to verify.
        token: Verification token.

    Returns:
        Instructions string.
    """
    record_name = f"{DNS_RECORD_PREFIX}.{domain}"
    record_value = f"{TOKEN_PREFIX}{token}"

    return f"""To verify ownership of {domain}, add the following DNS TXT record:

Record Name: {record_name}
Record Type: TXT
Record Value: {record_value}

After adding the record, it may take up to 24 hours to propagate.
Once propagated, click "Verify" to complete the verification process.
"""
