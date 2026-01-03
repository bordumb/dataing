"""PII Scanner and Redactor.

This module provides utilities for detecting and redacting
Personally Identifiable Information (PII) from text and query results.

This helps prevent sensitive data from being logged or sent to LLMs.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class PIIPattern(NamedTuple):
    """Pattern for detecting a type of PII."""

    regex: str
    pii_type: str
    description: str


# Patterns for common PII types
PII_PATTERNS: list[PIIPattern] = [
    PIIPattern(
        regex=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        pii_type="email",
        description="Email address",
    ),
    PIIPattern(
        regex=r"\b\d{3}-\d{2}-\d{4}\b",
        pii_type="ssn",
        description="Social Security Number",
    ),
    PIIPattern(
        regex=r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        pii_type="credit_card",
        description="Credit card number",
    ),
    PIIPattern(
        regex=r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
        pii_type="phone",
        description="Phone number",
    ),
    PIIPattern(
        regex=r"\b\d{5}(-\d{4})?\b",
        pii_type="zip_code",
        description="ZIP code",
    ),
]


def scan_for_pii(text: str) -> list[str]:
    """Scan text for potential PII.

    Args:
        text: The text to scan.

    Returns:
        List of PII types found in the text.

    Examples:
        >>> scan_for_pii("Contact: john@example.com")
        ['email']
        >>> scan_for_pii("SSN: 123-45-6789")
        ['ssn']
        >>> scan_for_pii("Hello world")
        []
    """
    found: list[str] = []
    for pattern in PII_PATTERNS:
        if re.search(pattern.regex, text):
            if pattern.pii_type not in found:
                found.append(pattern.pii_type)
    return found


def redact_pii(text: str) -> str:
    """Redact potential PII from text.

    Replaces detected PII with redaction markers.

    Args:
        text: The text to redact.

    Returns:
        Text with PII redacted.

    Examples:
        >>> redact_pii("Contact: john@example.com")
        'Contact: [REDACTED_EMAIL]'
        >>> redact_pii("SSN: 123-45-6789")
        'SSN: [REDACTED_SSN]'
    """
    result = text
    for pattern in PII_PATTERNS:
        result = re.sub(
            pattern.regex,
            f"[REDACTED_{pattern.pii_type.upper()}]",
            result,
        )
    return result


def contains_pii(text: str) -> bool:
    """Check if text contains any PII.

    Args:
        text: The text to check.

    Returns:
        True if PII is detected, False otherwise.

    Examples:
        >>> contains_pii("Contact: john@example.com")
        True
        >>> contains_pii("Hello world")
        False
    """
    return len(scan_for_pii(text)) > 0


def redact_dict(data: dict[str, str | int | float | bool | None]) -> dict[str, str]:
    """Redact PII from all string values in a dictionary.

    Args:
        data: Dictionary with values that may contain PII.

    Returns:
        Dictionary with PII redacted from string values.
    """
    result: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = redact_pii(value)
        else:
            result[key] = str(value) if value is not None else ""
    return result
