"""API routes for integration webhooks (CE).

This module provides a generic webhook endpoint for external integrations
to create issues. Signature verification is used to authenticate requests.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


# ============================================================================
# Request/Response Schemas
# ============================================================================


class GenericWebhookPayload(BaseModel):
    """Payload for generic webhook issue creation."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    severity: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    priority: str | None = Field(default=None, pattern="^P[0-3]$")
    dataset_id: str | None = Field(default=None, max_length=200)
    labels: list[str] | None = Field(default=None, max_items=20)
    source_provider: str | None = Field(default=None, max_length=100)
    source_external_id: str | None = Field(default=None, max_length=500)
    source_external_url: str | None = Field(default=None, max_length=2000)


class WebhookIssueResponse(BaseModel):
    """Response from webhook issue creation."""

    id: UUID
    number: int
    status: str
    created: bool  # True if newly created, False if deduplicated


# ============================================================================
# Signature Verification
# ============================================================================


def verify_webhook_signature(
    body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify webhook HMAC signature.

    Args:
        body: Raw request body
        signature_header: Value of X-Webhook-Signature header (sha256=...)
        secret: Shared secret for verification

    Returns:
        True if signature is valid
    """
    if not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header[7:]  # Remove "sha256=" prefix

    calculated = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(calculated, expected_signature)


def get_webhook_secret() -> str | None:
    """Get the shared webhook secret from environment."""
    return os.getenv("WEBHOOK_SHARED_SECRET")


# ============================================================================
# API Routes
# ============================================================================


@router.post(
    "/webhook-generic",
    response_model=WebhookIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def receive_generic_webhook(
    request: Request,
    auth: AuthDep,
    db: AppDbDep,
    x_webhook_signature: str | None = Header(default=None),
) -> WebhookIssueResponse:
    """Receive a generic webhook to create an issue.

    This endpoint allows external systems to create issues via HTTP webhook.
    Requests must be signed with HMAC-SHA256 using the shared secret.

    Idempotency: If source_provider and source_external_id are provided,
    duplicate webhooks will return the existing issue instead of creating
    a new one.
    """
    # Get shared secret
    secret = get_webhook_secret()
    if not secret:
        logger.error("webhook_secret_not_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook integration not configured",
        )

    # Read and verify body
    body = await request.body()

    if not verify_webhook_signature(body, x_webhook_signature, secret):
        logger.warning(
            "webhook_signature_invalid",
            tenant_id=str(auth.tenant_id),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # Parse payload
    try:
        import json

        payload_dict = json.loads(body)
        payload = GenericWebhookPayload(**payload_dict)
    except Exception as e:
        logger.warning(
            "webhook_payload_invalid",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {e}",
        ) from e

    # Check for existing issue (idempotency via primary dedup index)
    if payload.source_provider and payload.source_external_id:
        existing = await db.fetch_one(
            """
            SELECT id, number, status
            FROM issues
            WHERE tenant_id = $1
              AND source_provider = $2
              AND source_external_id = $3
            """,
            auth.tenant_id,
            payload.source_provider,
            payload.source_external_id,
        )
        if existing:
            logger.info(
                "webhook_deduplicated",
                issue_id=str(existing["id"]),
                source_provider=payload.source_provider,
                source_external_id=payload.source_external_id,
            )
            return WebhookIssueResponse(
                id=existing["id"],
                number=existing["number"],
                status=existing["status"],
                created=False,
            )

    # Get next issue number
    number_row = await db.fetch_one(
        "SELECT next_issue_number($1) as num",
        auth.tenant_id,
    )
    issue_number = number_row["num"] if number_row else 1

    # Create the issue
    row = await db.fetch_one(
        """
        INSERT INTO issues (
            tenant_id, number, title, description, status,
            priority, severity, dataset_id,
            author_type, source_provider, source_external_id, source_external_url
        )
        VALUES ($1, $2, $3, $4, 'open', $5, $6, $7, 'integration', $8, $9, $10)
        RETURNING id, number, status
        """,
        auth.tenant_id,
        issue_number,
        payload.title,
        payload.description,
        payload.priority,
        payload.severity,
        payload.dataset_id,
        payload.source_provider,
        payload.source_external_id,
        payload.source_external_url,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create issue",
        )

    issue_id = row["id"]

    # Add labels if provided
    if payload.labels:
        for label in payload.labels:
            await db.execute(
                "INSERT INTO issue_labels (issue_id, label) VALUES ($1, $2)",
                issue_id,
                label,
            )

    # Record creation event
    await db.execute(
        """
        INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
        VALUES ($1, 'created', NULL, $2)
        """,
        issue_id,
        to_json_string({
            "source": "webhook",
            "provider": payload.source_provider,
        }),
    )

    logger.info(
        "webhook_issue_created",
        issue_id=str(issue_id),
        issue_number=issue_number,
        source_provider=payload.source_provider,
        tenant_id=str(auth.tenant_id),
    )

    return WebhookIssueResponse(
        id=issue_id,
        number=row["number"],
        status=row["status"],
        created=True,
    )
