"""Unit tests for NotificationService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from dataing.services.notification import NotificationEvent, NotificationService


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database."""
        mock = AsyncMock()
        mock.get_webhooks_for_event.return_value = []
        mock.update_webhook_status.return_value = None
        return mock

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> NotificationService:
        """Return a notification service."""
        return NotificationService(db=mock_db)

    @pytest.fixture
    def tenant_id(self) -> uuid.UUID:
        """Return a sample tenant ID."""
        return uuid.uuid4()

    async def test_notify_no_webhooks(
        self,
        service: NotificationService,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test notify with no configured webhooks."""
        event = NotificationEvent(
            event_type="investigation.completed",
            payload={"investigation_id": "123"},
            tenant_id=tenant_id,
        )

        result = await service.notify(event)

        assert result == {}

    async def test_notify_with_webhooks(
        self,
        service: NotificationService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test notify with configured webhooks."""
        webhook_id = uuid.uuid4()
        mock_db.get_webhooks_for_event.return_value = [
            {
                "id": webhook_id,
                "url": "https://example.com/webhook",
                "secret": "test_secret",
            }
        ]

        event = NotificationEvent(
            event_type="investigation.completed",
            payload={"investigation_id": "123"},
            tenant_id=tenant_id,
        )

        with patch("dataing.services.notification.WebhookNotifier") as mock_notifier_class:
            mock_notifier = AsyncMock()
            mock_notifier.send.return_value = True
            mock_notifier_class.return_value = mock_notifier

            result = await service.notify(event)

            assert "webhooks" in result
            assert len(result["webhooks"]) == 1
            assert result["webhooks"][0]["success"] is True

    async def test_notify_webhook_failure(
        self,
        service: NotificationService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test notify handles webhook failure."""
        webhook_id = uuid.uuid4()
        mock_db.get_webhooks_for_event.return_value = [
            {
                "id": webhook_id,
                "url": "https://example.com/webhook",
            }
        ]

        event = NotificationEvent(
            event_type="investigation.completed",
            payload={},
            tenant_id=tenant_id,
        )

        with patch("dataing.services.notification.WebhookNotifier") as mock_notifier_class:
            mock_notifier = AsyncMock()
            mock_notifier.send.return_value = False
            mock_notifier_class.return_value = mock_notifier

            result = await service.notify(event)

            assert result["webhooks"][0]["success"] is False

    async def test_notify_investigation_completed(
        self,
        service: NotificationService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test convenience method for investigation completed."""
        inv_id = uuid.uuid4()
        finding = {"root_cause": "Test cause"}

        await service.notify_investigation_completed(
            tenant_id=tenant_id,
            investigation_id=inv_id,
            finding=finding,
        )

        mock_db.get_webhooks_for_event.assert_called_once()
        call_args = mock_db.get_webhooks_for_event.call_args
        assert call_args[0][1] == "investigation.completed"

    async def test_notify_investigation_failed(
        self,
        service: NotificationService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test convenience method for investigation failed."""
        inv_id = uuid.uuid4()

        await service.notify_investigation_failed(
            tenant_id=tenant_id,
            investigation_id=inv_id,
            error="Something went wrong",
        )

        call_args = mock_db.get_webhooks_for_event.call_args
        assert call_args[0][1] == "investigation.failed"

    async def test_notify_approval_required(
        self,
        service: NotificationService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test convenience method for approval required."""
        inv_id = uuid.uuid4()
        approval_id = uuid.uuid4()

        await service.notify_approval_required(
            tenant_id=tenant_id,
            investigation_id=inv_id,
            approval_request_id=approval_id,
            context={"query": "SELECT 1"},
        )

        call_args = mock_db.get_webhooks_for_event.call_args
        assert call_args[0][1] == "approval.required"


class TestNotificationEvent:
    """Tests for NotificationEvent."""

    def test_create_event(self) -> None:
        """Test creating a notification event."""
        tenant_id = uuid.uuid4()
        event = NotificationEvent(
            event_type="test.event",
            payload={"key": "value"},
            tenant_id=tenant_id,
        )

        assert event.event_type == "test.event"
        assert event.payload["key"] == "value"
        assert event.tenant_id == tenant_id
