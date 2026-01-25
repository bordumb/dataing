"""API routes for integration management (EE).

This module provides CRUD endpoints for managing integrations
and provider-specific webhook endpoints.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.team_policy_repository import PolicyAction, TeamPolicyRepository
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db, resolve_datasource_id
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.services.policy import IssueContext, PolicyService
from dataing_ee.adapters.integrations.base import IssueData, WebhookRequest
from dataing_ee.adapters.integrations.registry import get_adapter
from dataing_ee.models.integration import IntegrationEventStatus, IntegrationProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations-ee"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]


# ============================================================================
# Request/Response Schemas
# ============================================================================


VALID_PROVIDERS = (
    "^(jira|linear|pagerduty|opsgenie|monte_carlo|great_expectations|soda|dbt|slack|custom)$"
)


class IntegrationCreate(BaseModel):
    """Request to create an integration."""

    name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., pattern=VALID_PROVIDERS)
    config: dict[str, Any] | None = Field(default=None)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000)


class IntegrationUpdate(BaseModel):
    """Request to update an integration."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=1000)


class IntegrationResponse(BaseModel):
    """Integration response."""

    id: UUID
    tenant_id: UUID
    name: str
    provider: str
    enabled: bool
    config: dict[str, Any]
    rate_limit_per_minute: int
    webhook_url: str
    last_webhook_at: datetime | None
    webhook_count: int
    error_count: int
    created_at: datetime
    updated_at: datetime


class IntegrationListResponse(BaseModel):
    """List of integrations response."""

    items: list[IntegrationResponse]
    total: int


class IntegrationSecretResponse(BaseModel):
    """Response with signing secret (shown once on create/regenerate)."""

    id: UUID
    signing_secret: str


class FieldMappingCreate(BaseModel):
    """Request to create a field mapping."""

    source_field: str = Field(..., min_length=1, max_length=200)
    target_field: str = Field(
        ..., pattern="^(title|description|severity|priority|dataset_id|labels)$"
    )
    transform: str | None = Field(default=None, max_length=50)


class FieldMappingResponse(BaseModel):
    """Field mapping response."""

    id: UUID
    source_field: str
    target_field: str
    transform: str | None


class ProviderWebhookPayload(BaseModel):
    """Generic provider webhook payload."""

    # Fields extracted based on provider type and field mappings
    title: str | None = None
    description: str | None = None
    severity: str | None = None
    priority: str | None = None
    dataset_id: str | None = None
    labels: list[str] | None = None


# ============================================================================
# Helper Functions
# ============================================================================


def _generate_signing_secret() -> str:
    """Generate a secure signing secret."""
    return secrets.token_hex(32)


def _build_webhook_url(request: Request, integration_id: UUID, provider: str) -> str:
    """Build the webhook URL for an integration."""
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/v1/integrations/{provider}/webhook?integration_id={integration_id}"


def _row_to_response(row: dict[str, Any], request: Request) -> IntegrationResponse:
    """Convert database row to response model."""
    return IntegrationResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        provider=row["provider"],
        enabled=row["enabled"],
        config=row["config"] or {},
        rate_limit_per_minute=row["rate_limit_per_minute"],
        webhook_url=_build_webhook_url(request, row["id"], row["provider"]),
        last_webhook_at=row["last_webhook_at"],
        webhook_count=row["webhook_count"],
        error_count=row["error_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _verify_provider_signature(
    body: bytes,
    signature_header: str | None,
    secret: str,
    provider: str,
) -> bool:
    """Verify provider-specific webhook signature.

    Different providers use different signature schemes:
    - jira: X-Hub-Signature (sha256)
    - linear: Linear-Signature (hmac-sha256)
    - pagerduty: X-PagerDuty-Signature (v1=sha256)
    - opsgenie: No built-in signature, use custom header
    - custom: X-Webhook-Signature (sha256=...)
    """
    if not signature_header:
        return False

    if provider == IntegrationProvider.JIRA:
        # Jira uses sha256=<signature>
        if not signature_header.startswith("sha256="):
            return False
        expected = signature_header[7:]
    elif provider == IntegrationProvider.LINEAR:
        # Linear sends raw HMAC
        expected = signature_header
    elif provider == IntegrationProvider.PAGERDUTY:
        # PagerDuty uses v1=<signature>
        if not signature_header.startswith("v1="):
            return False
        expected = signature_header[3:]
    else:
        # Custom/Opsgenie use sha256=<signature>
        if not signature_header.startswith("sha256="):
            return False
        expected = signature_header[7:]

    calculated = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(calculated, expected)


def _get_signature_header_name(provider: str) -> str:
    """Get the signature header name for a provider."""
    header_map = {
        IntegrationProvider.JIRA: "X-Hub-Signature",
        IntegrationProvider.LINEAR: "Linear-Signature",
        IntegrationProvider.PAGERDUTY: "X-PagerDuty-Signature",
        IntegrationProvider.OPSGENIE: "X-Webhook-Signature",
        IntegrationProvider.MONTE_CARLO: "X-MC-Signature",
        IntegrationProvider.GREAT_EXPECTATIONS: "X-GE-Signature",
        IntegrationProvider.SLACK: "X-Slack-Signature",
        IntegrationProvider.CUSTOM: "X-Webhook-Signature",
    }
    return header_map.get(provider, "X-Webhook-Signature")


# ============================================================================
# Integration CRUD Routes
# ============================================================================


@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    request: Request,
    auth: AuthDep,
    db: AppDbDep,
) -> IntegrationListResponse:
    """List all integrations for the tenant."""
    rows = await db.fetch_all(
        """
        SELECT id, tenant_id, name, provider, enabled, config,
               rate_limit_per_minute, last_webhook_at, webhook_count,
               error_count, created_at, updated_at
        FROM integrations
        WHERE tenant_id = $1
        ORDER BY name ASC
        """,
        auth.tenant_id,
    )
    items = [_row_to_response(row, request) for row in rows]
    return IntegrationListResponse(items=items, total=len(items))


@router.post("", response_model=IntegrationSecretResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    auth: AdminScopeDep,
    db: AppDbDep,
    body: IntegrationCreate,
) -> IntegrationSecretResponse:
    """Create a new integration.

    Requires admin scope. Returns the signing secret (shown only once).
    """
    signing_secret = _generate_signing_secret()

    row = await db.fetch_one(
        """
        INSERT INTO integrations
            (tenant_id, name, provider, config, signing_secret, rate_limit_per_minute)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        auth.tenant_id,
        body.name,
        body.provider,
        to_json_string(body.config or {}),
        signing_secret,
        body.rate_limit_per_minute,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create integration",
        )

    logger.info(
        f"Integration created: id={row['id']}, provider={body.provider}, tenant={auth.tenant_id}"
    )

    return IntegrationSecretResponse(
        id=row["id"],
        signing_secret=signing_secret,
    )


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    integration_id: UUID,
    request: Request,
    auth: AuthDep,
    db: AppDbDep,
) -> IntegrationResponse:
    """Get an integration by ID."""
    row = await db.fetch_one(
        """
        SELECT id, tenant_id, name, provider, enabled, config,
               rate_limit_per_minute, last_webhook_at, webhook_count,
               error_count, created_at, updated_at
        FROM integrations
        WHERE id = $1 AND tenant_id = $2
        """,
        integration_id,
        auth.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")
    return _row_to_response(row, request)


@router.patch("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: UUID,
    request: Request,
    auth: AdminScopeDep,
    db: AppDbDep,
    body: IntegrationUpdate,
) -> IntegrationResponse:
    """Update an integration.

    Requires admin scope.
    """
    # Check exists
    existing = await db.fetch_one(
        "SELECT id FROM integrations WHERE id = $1 AND tenant_id = $2",
        integration_id,
        auth.tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Build update query
    updates = []
    params: list[Any] = []
    param_idx = 1

    if body.name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(body.name)
        param_idx += 1

    if body.enabled is not None:
        updates.append(f"enabled = ${param_idx}")
        params.append(body.enabled)
        param_idx += 1

    if body.config is not None:
        updates.append(f"config = ${param_idx}")
        params.append(to_json_string(body.config))
        param_idx += 1

    if body.rate_limit_per_minute is not None:
        updates.append(f"rate_limit_per_minute = ${param_idx}")
        params.append(body.rate_limit_per_minute)
        param_idx += 1

    updates.append("updated_at = NOW()")

    if not updates:
        return await get_integration(integration_id, request, auth, db)

    params.extend([integration_id, auth.tenant_id])
    query = f"""
        UPDATE integrations
        SET {", ".join(updates)}
        WHERE id = ${param_idx} AND tenant_id = ${param_idx + 1}
        RETURNING id, tenant_id, name, provider, enabled, config,
                  rate_limit_per_minute, last_webhook_at, webhook_count,
                  error_count, created_at, updated_at
    """

    row = await db.fetch_one(query, *params)
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")

    return _row_to_response(row, request)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: UUID,
    auth: AdminScopeDep,
    db: AppDbDep,
) -> Response:
    """Delete an integration.

    Requires admin scope.
    """
    existing = await db.fetch_one(
        "SELECT id FROM integrations WHERE id = $1 AND tenant_id = $2",
        integration_id,
        auth.tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")

    await db.execute("DELETE FROM integrations WHERE id = $1", integration_id)

    logger.info(f"Integration deleted: id={integration_id}, tenant={auth.tenant_id}")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{integration_id}/regenerate-secret", response_model=IntegrationSecretResponse)
async def regenerate_signing_secret(
    integration_id: UUID,
    auth: AdminScopeDep,
    db: AppDbDep,
) -> IntegrationSecretResponse:
    """Regenerate the signing secret for an integration.

    Requires admin scope. Returns the new secret (shown only once).
    """
    existing = await db.fetch_one(
        "SELECT id FROM integrations WHERE id = $1 AND tenant_id = $2",
        integration_id,
        auth.tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")

    new_secret = _generate_signing_secret()

    await db.execute(
        "UPDATE integrations SET signing_secret = $1, updated_at = NOW() WHERE id = $2",
        new_secret,
        integration_id,
    )

    logger.info(f"Integration secret regenerated: id={integration_id}, tenant={auth.tenant_id}")

    return IntegrationSecretResponse(
        id=integration_id,
        signing_secret=new_secret,
    )


# ============================================================================
# Provider Webhook Route
# ============================================================================


@router.post("/{provider}/webhook", status_code=status.HTTP_200_OK)
async def receive_provider_webhook(
    provider: str,
    request: Request,
    db: AppDbDep,
    integration_id: UUID | None = None,
) -> dict[str, Any]:
    """Receive a webhook from an integration provider.

    The webhook is verified using the provider-specific signature scheme.
    Uses adapter classes for MC/GX when available, falls back to inline logic otherwise.
    Idempotency is enforced via the integration_events table.
    """
    if provider not in IntegrationProvider.all():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider}",
        )

    if not integration_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="integration_id query parameter required",
        )

    # Get integration
    integration = await db.fetch_one(
        """
        SELECT id, tenant_id, provider, enabled, signing_secret, rate_limit_per_minute
        FROM integrations
        WHERE id = $1 AND provider = $2
        """,
        integration_id,
        provider,
    )

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    if not integration["enabled"]:
        return {"status": "skipped", "reason": "integration_disabled"}

    # Read body
    body = await request.body()

    # Try to get adapter for this provider
    adapter = get_adapter(provider)

    # Build WebhookRequest for adapter if available
    webhook_request: WebhookRequest | None = None
    if adapter:
        webhook_request = WebhookRequest(
            body=body,
            headers=dict(request.headers),
            query_params=dict(request.query_params),
        )

        # Check if adapter wants to process this event
        if not adapter.should_process(webhook_request):
            logger.info(
                f"Webhook skipped by adapter: integration={integration_id}, provider={provider}"
            )
            return {"status": "skipped", "reason": "filtered_by_adapter"}

    # Verify signature
    if integration["signing_secret"]:
        if adapter and webhook_request:
            # Use adapter for signature verification
            if not adapter.verify_signature(webhook_request, integration["signing_secret"]):
                logger.warning(
                    f"Webhook signature invalid: integration={integration_id}, provider={provider}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )
        else:
            # Fallback to inline verification
            sig_header_name = _get_signature_header_name(provider)
            signature = request.headers.get(sig_header_name)
            if not _verify_provider_signature(
                body, signature, integration["signing_secret"], provider
            ):
                logger.warning(
                    f"Webhook signature invalid: integration={integration_id}, provider={provider}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )

    # Parse payload and compute idempotency key
    import json

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {e}",
        ) from e

    # Extract idempotency key and event type (provider-specific)
    if adapter and webhook_request:
        # Use adapter for fingerprinting and event type
        idempotency_key = adapter.get_fingerprint(webhook_request)
        event_type = adapter.get_event_type(webhook_request)
    else:
        # Fallback to inline extraction
        idempotency_key = _extract_idempotency_key(payload, provider, request)
        event_type = _extract_event_type(payload, provider)
    payload_hash = hashlib.sha256(body).hexdigest()

    # Check for existing event (idempotency)
    existing_event = await db.fetch_one(
        """
        SELECT id, status, issue_id
        FROM integration_events
        WHERE integration_id = $1 AND idempotency_key = $2
        """,
        integration_id,
        idempotency_key,
    )

    if existing_event:
        logger.info(f"Webhook deduplicated: integration={integration_id}, key={idempotency_key}")
        return {
            "status": "deduplicated",
            "event_id": str(existing_event["id"]),
            "issue_id": str(existing_event["issue_id"]) if existing_event["issue_id"] else None,
        }

    # Create event record
    event_row = await db.fetch_one(
        """
        INSERT INTO integration_events
            (integration_id, idempotency_key, event_type, payload_hash, status, received_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        RETURNING id
        """,
        integration_id,
        idempotency_key,
        event_type,
        payload_hash,
        IntegrationEventStatus.PENDING,
    )

    if not event_row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create integration event",
        )
    event_id = event_row["id"]

    # Get field mappings
    mappings = await db.fetch_all(
        """
        SELECT source_field, target_field, transform
        FROM integration_field_mappings
        WHERE integration_id = $1
        """,
        integration_id,
    )
    mappings_list = [dict(m) for m in mappings]

    # Map payload to issue fields using adapter or fallback
    if adapter and webhook_request:
        # Use adapter for payload parsing - returns IssueData dataclass
        issue_data_obj = adapter.parse_payload(webhook_request, mappings_list)
        # Convert IssueData to dict for consistent access
        issue_data: dict[str, Any] = {
            "title": issue_data_obj.title,
            "description": issue_data_obj.description,
            "severity": issue_data_obj.severity,
            "priority": issue_data_obj.priority,
            "dataset_id": issue_data_obj.dataset_id,
            "labels": issue_data_obj.labels,
            "external_url": issue_data_obj.external_url,
            "metadata": issue_data_obj.metadata,
        }
    else:
        # Fallback to inline parsing
        issue_data = _map_payload_to_issue(payload, mappings_list, provider)

    if not issue_data.get("title"):
        # Mark as skipped - no title means we can't create an issue
        await db.execute(
            """
            UPDATE integration_events
            SET status = $1, error_message = $2, processed_at = NOW()
            WHERE id = $3
            """,
            IntegrationEventStatus.SKIPPED,
            "No title could be extracted from payload",
            event_id,
        )
        return {"status": "skipped", "reason": "no_title"}

    # Create issue
    tenant_id = integration["tenant_id"]

    # Get next issue number
    number_row = await db.fetch_one(
        "SELECT next_issue_number($1) as num",
        tenant_id,
    )
    issue_number = number_row["num"] if number_row else 1

    issue_row = await db.fetch_one(
        """
        INSERT INTO issues (
            tenant_id, number, title, description, status,
            priority, severity, dataset_id,
            author_type, source_provider, source_external_id
        )
        VALUES ($1, $2, $3, $4, 'open', $5, $6, $7, 'integration', $8, $9)
        RETURNING id, number
        """,
        tenant_id,
        issue_number,
        issue_data.get("title"),
        issue_data.get("description"),
        issue_data.get("priority"),
        issue_data.get("severity"),
        issue_data.get("dataset_id"),
        provider,
        idempotency_key,
    )

    if not issue_row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create issue from webhook",
        )
    issue_id = issue_row["id"]

    # Add labels if present
    labels = issue_data.get("labels", [])
    for label in labels:
        await db.execute(
            "INSERT INTO issue_labels (issue_id, label) VALUES ($1, $2)",
            issue_id,
            label,
        )

    # Record creation event
    event_payload = {
        "source": "webhook",
        "provider": provider,
        "integration_id": str(integration_id),
    }
    await db.execute(
        """
        INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
        VALUES ($1, 'created', NULL, $2)
        """,
        issue_id,
        to_json_string(event_payload),
    )

    # Evaluate policy and start auto-investigation if applicable
    investigation_id = await _evaluate_and_start_investigation(
        request=request,
        db=db,
        tenant_id=tenant_id,
        issue_id=issue_id,
        issue_data=issue_data,
        adapter=adapter,
        webhook_request=webhook_request,
        idempotency_key=idempotency_key,
        provider=provider,
    )

    # Update integration event as processed
    await db.execute(
        """
        UPDATE integration_events
        SET status = $1, issue_id = $2, processed_at = NOW()
        WHERE id = $3
        """,
        IntegrationEventStatus.PROCESSED,
        issue_id,
        event_id,
    )

    # Update integration statistics
    await db.execute(
        """
        UPDATE integrations
        SET webhook_count = webhook_count + 1, last_webhook_at = NOW()
        WHERE id = $1
        """,
        integration_id,
    )

    logger.info(
        f"Webhook processed: integration={integration_id}, event={event_id}, "
        f"issue={issue_id}, number={issue_number}, provider={provider}, "
        f"investigation={investigation_id}"
    )

    result: dict[str, Any] = {
        "status": "processed",
        "event_id": str(event_id),
        "issue_id": str(issue_id),
        "issue_number": issue_number,
    }
    if investigation_id:
        result["investigation_id"] = str(investigation_id)
    return result


async def _evaluate_and_start_investigation(
    request: Request,
    db: AppDatabase,
    tenant_id: UUID,
    issue_id: UUID,
    issue_data: dict[str, Any],
    adapter: Any,
    webhook_request: WebhookRequest | None,
    idempotency_key: str,
    provider: str,
) -> UUID | None:
    """Evaluate policy and start auto-investigation if applicable.

    Returns:
        Investigation ID if started, None otherwise.
    """
    from dataing.temporal.client import TemporalInvestigationClient

    # Get the default team for this tenant
    policy_repo = TeamPolicyRepository(db)
    team_id = await policy_repo.get_default_team_for_tenant(tenant_id)

    if not team_id:
        logger.debug(f"No team found for tenant={tenant_id}, skipping policy evaluation")
        return None

    # Build issue context for policy evaluation
    context = IssueContext(
        team_id=team_id,
        dataset_id=issue_data.get("dataset_id"),
        severity=issue_data.get("severity"),
        source=provider,
    )

    # Evaluate policy
    policy_service = PolicyService(db)
    policy_result = await policy_service.evaluate(context)

    logger.info(
        f"Policy evaluated: issue={issue_id}, action={policy_result.action.value}, "
        f"source={policy_result.source}, provider={provider}"
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
                "policy_id": str(policy_result.policy_id) if policy_result.policy_id else None,
                "override_id": str(policy_result.override_id)
                if policy_result.override_id
                else None,
            }
        ),
    )

    if policy_result.action != PolicyAction.AUTO:
        return None

    # Get Temporal client
    temporal_client: TemporalInvestigationClient | None = getattr(
        request.app.state, "temporal_client", None
    )

    if temporal_client is None:
        logger.warning(
            f"Temporal not configured, cannot start auto investigation for issue={issue_id}"
        )
        return None

    # Build AnomalyAlert from issue data
    if adapter and webhook_request:
        # Use adapter to create proper IssueData then convert to AnomalyAlert
        issue_data_obj = IssueData(
            title=issue_data.get("title"),
            description=issue_data.get("description"),
            severity=issue_data.get("severity"),
            priority=issue_data.get("priority"),
            dataset_id=issue_data.get("dataset_id"),
            labels=issue_data.get("labels", []),
            external_url=issue_data.get("external_url"),
            metadata=issue_data.get("metadata", {}),
        )
        anomaly_alert = adapter.to_anomaly_alert(issue_data_obj, idempotency_key)
        alert_data = anomaly_alert.model_dump()
    else:
        # Fallback for providers without adapters
        now = datetime.now(UTC)
        alert_data = {
            "dataset_ids": [issue_data.get("dataset_id")] if issue_data.get("dataset_id") else [],
            "metric_spec": {
                "metric_type": "description",
                "expression": issue_data.get("title", ""),
                "display_name": issue_data.get("title", "Integration Alert"),
                "columns_referenced": [],
            },
            "anomaly_type": "integration_alert",
            "expected_value": 0.0,
            "actual_value": 0.0,
            "deviation_pct": 0.0,
            "anomaly_date": now.date().isoformat(),
            "severity": issue_data.get("severity") or "medium",
            "source_system": provider,
            "source_alert_id": idempotency_key,
        }

    investigation_id = uuid4()

    # Resolve datasource
    try:
        datasource_id = await resolve_datasource_id(request, tenant_id, explicit_id=None)
    except ValueError:
        # No default datasource, use placeholder
        datasource_id = UUID("00000000-0000-0000-0000-000000000003")

    # Add issue_id to alert data for back-linking
    alert_data["issue_id"] = str(issue_id)
    alert_data["datasource_id"] = str(datasource_id)

    try:
        # Create investigation record
        await db.execute(
            """
            INSERT INTO investigations (id, tenant_id, alert)
            VALUES ($1, $2, $3)
            """,
            investigation_id,
            tenant_id,
            json.dumps(alert_data),
        )

        # Start Temporal workflow
        alert_summary = f"Auto investigation: {issue_data.get('title', 'Webhook alert')}"
        await temporal_client.start_investigation(
            investigation_id=str(investigation_id),
            tenant_id=str(tenant_id),
            datasource_id=str(datasource_id),
            alert_data=alert_data,
            alert_summary=alert_summary,
        )

        # Record investigation started event on issue
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
                    "source_system": provider,
                }
            ),
        )

        logger.info(
            f"Auto investigation started: investigation={investigation_id}, "
            f"issue={issue_id}, provider={provider}"
        )

        return investigation_id

    except Exception as e:
        logger.error(f"Failed to start auto investigation for issue={issue_id}: {e}")
        return None


def _extract_idempotency_key(payload: dict[str, Any], provider: str, request: Request) -> str:
    """Extract idempotency key from provider payload."""
    # Try provider-specific fields first
    if provider == IntegrationProvider.JIRA:
        # Jira webhook has webhookEvent and issue.id
        if "issue" in payload and "id" in payload["issue"]:
            return f"jira_{payload['issue']['id']}_{payload.get('webhookEvent', 'unknown')}"
    elif provider == IntegrationProvider.LINEAR:
        # Linear has action and data.id
        if "data" in payload and "id" in payload["data"]:
            return f"linear_{payload['data']['id']}_{payload.get('action', 'unknown')}"
    elif provider == IntegrationProvider.PAGERDUTY:
        # PagerDuty has messages[].incident.id
        messages = payload.get("messages", [])
        if messages and "incident" in messages[0]:
            return f"pagerduty_{messages[0]['incident'].get('id', 'unknown')}"

    # Fall back to request headers
    request_id = request.headers.get("X-Request-Id") or request.headers.get("X-Correlation-Id")
    if request_id:
        return f"{provider}_{request_id}"

    # Last resort: hash the payload
    import json

    payload_str = json.dumps(payload, sort_keys=True)
    return f"{provider}_{hashlib.sha256(payload_str.encode()).hexdigest()[:16]}"


def _extract_event_type(payload: dict[str, Any], provider: str) -> str:
    """Extract event type from provider payload."""
    if provider == IntegrationProvider.JIRA:
        event_type: str = payload.get("webhookEvent", "unknown")
        return event_type
    elif provider == IntegrationProvider.LINEAR:
        action: str = payload.get("action", "unknown")
        return action
    elif provider == IntegrationProvider.PAGERDUTY:
        messages = payload.get("messages", [])
        if messages:
            event: str = messages[0].get("event", "unknown")
            return event
    fallback: str = payload.get("type", payload.get("event_type", "unknown"))
    return fallback


def _map_payload_to_issue(
    payload: dict[str, Any],
    mappings: list[dict[str, Any]],
    provider: str,
) -> dict[str, Any]:
    """Map provider payload to issue fields using field mappings."""
    result: dict[str, Any] = {}

    # Apply custom mappings first
    for mapping in mappings:
        value = _get_nested_value(payload, mapping["source_field"])
        if value is not None:
            if mapping["transform"]:
                value = _apply_transform(value, mapping["transform"])
            result[mapping["target_field"]] = value

    # Apply default mappings if not already set
    if "title" not in result:
        result["title"] = _get_default_title(payload, provider)

    if "description" not in result:
        result["description"] = _get_default_description(payload, provider)

    return result


def _get_nested_value(obj: dict[str, Any], path: str) -> Any:
    """Get a nested value from a dict using dot notation."""
    keys = path.split(".")
    current = obj
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _apply_transform(value: Any, transform: str) -> Any:
    """Apply a transform to a value."""
    if transform == "uppercase" and isinstance(value, str):
        return value.upper()
    elif transform == "lowercase" and isinstance(value, str):
        return value.lower()
    elif transform == "severity_map" and isinstance(value, str):
        # Map common severity names
        severity_map = {
            "blocker": "critical",
            "critical": "critical",
            "major": "high",
            "high": "high",
            "medium": "medium",
            "minor": "low",
            "low": "low",
            "trivial": "low",
        }
        return severity_map.get(value.lower(), value.lower())
    return value


def _get_default_title(payload: dict[str, Any], provider: str) -> str | None:
    """Get default title from provider payload."""
    result: str | None = None
    if provider == IntegrationProvider.JIRA:
        issue = payload.get("issue", {})
        fields = issue.get("fields", {})
        result = fields.get("summary")
    elif provider == IntegrationProvider.LINEAR:
        data = payload.get("data", {})
        result = data.get("title")
    elif provider == IntegrationProvider.PAGERDUTY:
        messages = payload.get("messages", [])
        if messages:
            incident = messages[0].get("incident", {})
            result = incident.get("title")
    else:
        result = payload.get("title", payload.get("summary", payload.get("name")))
    return result


def _get_default_description(payload: dict[str, Any], provider: str) -> str | None:
    """Get default description from provider payload."""
    result: str | None = None
    if provider == IntegrationProvider.JIRA:
        issue = payload.get("issue", {})
        fields = issue.get("fields", {})
        result = fields.get("description")
    elif provider == IntegrationProvider.LINEAR:
        data = payload.get("data", {})
        result = data.get("description")
    elif provider == IntegrationProvider.PAGERDUTY:
        messages = payload.get("messages", [])
        if messages:
            incident = messages[0].get("incident", {})
            result = incident.get("description")
    else:
        result = payload.get("description", payload.get("body"))
    return result
