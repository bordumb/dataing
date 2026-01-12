# fn-2.2 Backend: SSE endpoint for real-time notifications

## Description

Add SSE endpoint for real-time notification push with heartbeat and reconnect support.

### SSE Endpoint Contract

```
GET /api/v1/notifications/stream?token=<jwt>
Accept: text/event-stream

# New notification event
event: notification
id: <notification_id>
data: {"id": "...", "type": "investigation_completed", ...}

# Heartbeat every 30s
event: heartbeat
data: {"ts": "2024-01-15T10:30:00Z"}
```

### Implementation

Add to `dataing/src/dataing/entrypoints/api/routes/notifications.py`:

```python
@router.get("/stream")
async def notification_stream(
    token: str = Query(...),  # Browser EventSource can't send headers
    db: DatabaseDep,
) -> StreamingResponse:
    # Validate token (same as auth middleware)
    auth = await verify_token(token)

    async def generate():
        last_id = None
        last_heartbeat = time.time()
        while True:
            # Heartbeat every 30s
            if time.time() - last_heartbeat > 30:
                yield f"event: heartbeat
data: {json.dumps({'ts': datetime.utcnow().isoformat()})}

"
                last_heartbeat = time.time()

            # Poll for new notifications
            notifications = await db.get_new_notifications(
                tenant_id=auth.tenant_id,
                since_id=last_id,
            )
            for n in notifications:
                yield f"event: notification
id: {n.id}
data: {n.model_dump_json()}

"
                last_id = n.id

            await asyncio.sleep(0.5)

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Notification Creation Path

Modify `dataing/src/dataing/services/notification.py`:

```python
async def create_in_app(
    self,
    tenant_id: UUID,
    type: str,
    title: str,
    body: str | None = None,
    resource_kind: str | None = None,
    resource_id: UUID | None = None,
    severity: str = "info",
) -> UUID:
    """Create in-app notification record."""
    return await self._db.create_notification(
        tenant_id=tenant_id,
        type=type,
        title=title,
        body=body,
        resource_kind=resource_kind,
        resource_id=resource_id,
        severity=severity,
    )
```

Wire into `dataing/src/dataing/core/investigation/service.py`:

```python
# After investigation completes/fails:
if self._notification_service:
    await self._notification_service.create_in_app(
        tenant_id=tenant_id,
        type="investigation_completed",  # or "investigation_failed"
        title=f"Investigation completed: {alert_summary[:50]}",
        resource_kind="investigation",
        resource_id=investigation.id,
    )
```

### Files to Modify

- Modify: `dataing/src/dataing/entrypoints/api/routes/notifications.py` (add `/stream`)
- Modify: `dataing/src/dataing/services/notification.py` (add `create_in_app`)
- Modify: `dataing/src/dataing/core/investigation/service.py` (call on complete/fail)
- Modify: `dataing/src/dataing/adapters/db/app_db.py` (add `get_new_notifications`, `create_notification`)

### Reuse Points

- SSE pattern: `dataing/src/dataing/entrypoints/api/routes/investigations.py:401-506`
- Token auth: `dataing/src/dataing/entrypoints/api/middleware/auth.py` (supports `?token=`)

## Acceptance

- [ ] `GET /notifications/stream?token=xxx` returns `text/event-stream`
- [ ] SSE sends heartbeat every 30s
- [ ] SSE includes event IDs for client resume
- [ ] Investigation completion triggers notification event in < 2s
- [ ] Investigation failure triggers notification event
- [ ] SSE handles client disconnect gracefully
- [ ] Token query param auth works for browser EventSource

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
