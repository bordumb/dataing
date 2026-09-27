"""API routes for integration webhooks (CE).

This module provides a generic webhook endpoint for external integrations
to create issues. Signature verification is used to authenticate requests.
Policy evaluation determines the action taken: auto investigation, review, or issue-only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.team_policy_repository import PolicyAction, TeamPolicyRepository
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope
from dataing.services.notification import NotificationEvent, NotificationService
from dataing.services.policy import IssueContext, PolicyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Annotated types for dependency injection
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]
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
    labels: list[str] | None = Field(default=None)
    source_provider: str | None = Field(default=None, max_length=100)
    source_external_id: str | None = Field(default=None, max_length=500)
    source_external_url: str | None = Field(default=None, max_length=2000)


class WebhookIssueResponse(BaseModel):
    """Response from webhook issue creation."""

    id: UUID
    number: int
    status: str
    created: bool  # True if newly created, False if deduplicated
    policy_action: str | None = None  # auto, review, issue_only
    investigation_id: UUID | None = None  # Set if auto investigation started


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
# JSON Schema Validation
# ============================================================================


@lru_cache(maxsize=16)
def _parse_json_schema(schema_json: str) -> dict[str, Any]:
    """Parse and validate a JSON schema string. Cached for performance."""
    try:
        schema: dict[str, Any] = json.loads(schema_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in schema: {e}",
        ) from e

    # Validate the schema itself
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON Schema: {e.message}",
        ) from e

    return schema


def get_configured_schema() -> dict[str, Any] | None:
    """Get the JSON schema from environment configuration.

    Returns:
        Parsed JSON schema dict, or None if not configured.
    """
    schema_json = os.getenv("WEBHOOK_JSON_SCHEMA")
    if not schema_json:
        return None

    return _parse_json_schema(schema_json)


def decode_header_schema(header_value: str) -> dict[str, Any]:
    """Decode a base64-encoded JSON schema from header.

    Args:
        header_value: Base64-encoded JSON schema string

    Returns:
        Parsed JSON schema dict
    """
    try:
        schema_json = base64.b64decode(header_value).decode("utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid base64 encoding in X-JSON-Schema header: {e}",
        ) from e

    return _parse_json_schema(schema_json)


def validate_payload_against_schema(
    payload: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    """Validate payload against JSON schema.

    Args:
        payload: The JSON payload to validate
        schema: The JSON schema to validate against

    Raises:
        HTTPException: If validation fails
    """
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(payload))

    if errors:
        # Format error messages
        error_messages = []
        for error in errors[:5]:  # Limit to first 5 errors
            path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
            error_messages.append(f"{path}: {error.message}")

        if len(errors) > 5:
            error_messages.append(f"... and {len(errors) - 5} more errors")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schema validation failed: {'; '.join(error_messages)}",
        )


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
    auth: WriteScopeDep,
    db: AppDbDep,
    x_webhook_signature: str | None = Header(default=None),
    x_json_schema: str | None = Header(default=None, description="Base64-encoded JSON Schema"),
) -> WebhookIssueResponse:
    """Receive a generic webhook to create an issue.

    This endpoint allows external systems to create issues via HTTP webhook.
    Requests must be signed with HMAC-SHA256 using the shared secret.

    Optional JSON Schema validation can be configured via:
    - WEBHOOK_JSON_SCHEMA environment variable (inline JSON schema)
    - X-JSON-Schema header (base64-encoded JSON schema, overrides env config)

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
        logger.warning(f"Webhook signature invalid for tenant={auth.tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # Parse raw JSON first
    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {e}",
        ) from e

    # JSON Schema validation (optional)
    schema: dict[str, Any] | None = None
    if x_json_schema:
        # Header takes precedence
        schema = decode_header_schema(x_json_schema)
    else:
        # Fall back to environment configuration
        schema = get_configured_schema()

    if schema:
        validate_payload_against_schema(payload_dict, schema)
        logger.debug(f"Schema validation passed for tenant={auth.tenant_id}")

    # Parse with Pydantic model
    try:
        payload = GenericWebhookPayload(**payload_dict)
    except Exception as e:
        logger.warning(f"Webhook payload invalid: {e}")
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
                f"Webhook deduplicated: issue={existing['id']}, "
                f"provider={payload.source_provider}, external_id={payload.source_external_id}"
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
        to_json_string(
            {
                "source": "webhook",
                "provider": payload.source_provider,
            }
        ),
    )

    logger.info(
        f"Webhook issue created: id={issue_id}, number={issue_number}, "
        f"provider={payload.source_provider}, tenant={auth.tenant_id}"
    )

    # Evaluate policy for the created issue
    policy_action, investigation_id = await _evaluate_and_apply_policy(
        request=request,
        db=db,
        auth=auth,
        issue_id=issue_id,
        payload=payload,
    )

    return WebhookIssueResponse(
        id=issue_id,
        number=row["number"],
        status=row["status"],
        created=True,
        policy_action=policy_action,
        investigation_id=investigation_id,
    )


async def _evaluate_and_apply_policy(
    request: Request,
    db: AppDatabase,
    auth: ApiKeyContext,
    issue_id: UUID,
    payload: GenericWebhookPayload,
) -> tuple[str | None, UUID | None]:
    """Evaluate policy for an issue and apply the resulting action.

    Returns:
        Tuple of (policy_action, investigation_id).
        investigation_id is set only for AUTO actions.
    """
    # Get the default team for this tenant
    policy_repo = TeamPolicyRepository(db)
    team_id = await policy_repo.get_default_team_for_tenant(auth.tenant_id)

    if not team_id:
        # No teams configured, default to issue-only
        logger.debug(f"No team found for tenant={auth.tenant_id}, using issue_only")
        return (PolicyAction.ISSUE_ONLY.value, None)

    # Build issue context for policy evaluation
    context = IssueContext(
        team_id=team_id,
        dataset_id=payload.dataset_id,
        severity=payload.severity,
        source=payload.source_provider,
    )

    # Evaluate policy
    policy_service = PolicyService(db)
    policy_result = await policy_service.evaluate(context)

    logger.info(
        f"Policy evaluated: issue={issue_id}, action={policy_result.action.value}, "
        f"source={policy_result.source}"
    )

    # Record policy evaluation event
    await db.execute(
        """
        INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
        VALUES ($1, 'policy_evaluated', NULL, $2)
        """,
        issue_id,
        to_json_string(
            {
                "action": policy_result.action.value,
                "source": policy_result.source,
                "policy_id": (str(policy_result.policy_id) if policy_result.policy_id else None),
                "override_id": (
                    str(policy_result.override_id) if policy_result.override_id else None
                ),
            }
        ),
    )

    investigation_id: UUID | None = None

    if policy_result.action == PolicyAction.AUTO:
        # Start auto investigation
        investigation_id = await _start_auto_investigation(
            request=request,
            db=db,
            auth=auth,
            issue_id=issue_id,
            payload=payload,
        )

    elif policy_result.action == PolicyAction.REVIEW:
        # Send notification that review is required
        await _send_review_notification(
            db=db,
            auth=auth,
            issue_id=issue_id,
            payload=payload,
        )

    # ISSUE_ONLY requires no additional action

    return (policy_result.action.value, investigation_id)


async def _start_auto_investigation(
    request: Request,
    db: AppDatabase,
    auth: ApiKeyContext,
    issue_id: UUID,
    payload: GenericWebhookPayload,
) -> UUID | None:
    """Start an automatic investigation for an issue.

    Returns:
        Investigation ID if started successfully, None otherwise.
    """
    from dataing.entrypoints.api.deps import resolve_datasource_id
    from dataing.temporal.client import TemporalInvestigationClient

    # Get Temporal client
    temporal_client: TemporalInvestigationClient | None = getattr(
        request.app.state, "temporal_client", None
    )

    if temporal_client is None:
        logger.warning(
            f"Temporal not configured, cannot start auto investigation for issue={issue_id}"
        )
        return None

    investigation_id = uuid4()
    now = datetime.now(UTC)

    # Resolve datasource
    try:
        datasource_id = await resolve_datasource_id(request, auth.tenant_id, explicit_id=None)
    except ValueError:
        # No default datasource, use placeholder
        datasource_id = UUID("00000000-0000-0000-0000-000000000003")

    # Build alert data
    alert_data: dict[str, Any] = {
        "dataset_ids": [payload.dataset_id] if payload.dataset_id else [],
        "metric_spec": {
            "metric_type": "description",
            "expression": payload.title,
            "display_name": "Integration Alert",
            "columns_referenced": [],
        },
        "anomaly_type": "integration_alert",
        "expected_value": 0.0,
        "actual_value": 0.0,
        "deviation_pct": 0.0,
        "anomaly_date": now.date().isoformat(),
        "severity": payload.severity or "medium",
        "datasource_id": str(datasource_id),
        "issue_id": str(issue_id),
    }

    try:
        # Create investigation record (issue_id is stored in alert JSONB)
        await db.execute(
            """
            INSERT INTO investigations (id, tenant_id, alert)
            VALUES ($1, $2, $3)
            """,
            investigation_id,
            auth.tenant_id,
            json.dumps(alert_data),
        )

        # Start Temporal workflow
        alert_summary = f"Auto investigation: {payload.title}"
        await temporal_client.start_investigation(
            investigation_id=str(investigation_id),
            tenant_id=str(auth.tenant_id),
            datasource_id=str(datasource_id),
            alert_data=alert_data,
            alert_summary=alert_summary,
        )

        # Record event on issue
        await db.execute(
            """
            INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
            VALUES ($1, 'investigation_started', NULL, $2)
            """,
            issue_id,
            to_json_string(
                {
                    "investigation_id": str(investigation_id),
                    "trigger": "auto_policy",
                }
            ),
        )

        logger.info(
            f"Auto investigation started: investigation={investigation_id}, issue={issue_id}"
        )

        return investigation_id

    except Exception as e:
        logger.error(f"Failed to start auto investigation for issue={issue_id}: {e}")
        return None


async def _send_review_notification(
    db: AppDatabase,
    auth: ApiKeyContext,
    issue_id: UUID,
    payload: GenericWebhookPayload,
) -> None:
    """Send notification that an issue requires review before investigation."""
    notification_service = NotificationService(db)

    await notification_service.notify(
        NotificationEvent(
            event_type="issue.review_required",
            tenant_id=auth.tenant_id,
            payload={
                "issue_id": str(issue_id),
                "title": payload.title,
                "severity": payload.severity,
                "dataset_id": payload.dataset_id,
                "source_provider": payload.source_provider,
            },
        )
    )

    # Record event on issue
    await db.execute(
        """
        INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
        VALUES ($1, 'review_requested', NULL, $2)
        """,
        issue_id,
        to_json_string(
            {
                "trigger": "review_policy",
            }
        ),
    )
