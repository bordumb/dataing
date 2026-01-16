"""Tests for the queue module."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

from dataing.core.queue import (
    INVESTIGATIONS_QUEUE,
    enqueue_investigation,
    get_redis_settings,
)


class TestGetRedisSettings:
    """Tests for get_redis_settings function."""

    def test_component_based_config(self) -> None:
        """Test Redis settings from individual environment variables."""
        env = {
            "REDIS_URL": "",
            "REDIS_HOST": "redis.example.com",
            "REDIS_PORT": "6380",
            "REDIS_PASSWORD": "secret123",
            "REDIS_DB": "2",
        }
        with patch.dict(os.environ, env, clear=False):
            # Need to reload settings after changing env
            from dataing.entrypoints.api import deps

            original_settings = deps.settings
            try:
                deps.settings = deps.Settings()
                settings = get_redis_settings()

                assert settings.host == "redis.example.com"
                assert settings.port == 6380
                assert settings.password == "secret123"
                assert settings.database == 2
            finally:
                deps.settings = original_settings

    def test_url_based_config(self) -> None:
        """Test Redis settings from REDIS_URL takes precedence."""
        env = {
            "REDIS_URL": "redis://:urlpassword@url-host.com:6381/3",
            "REDIS_HOST": "component-host.com",
            "REDIS_PORT": "6379",
            "REDIS_PASSWORD": "componentpassword",
            "REDIS_DB": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            from dataing.entrypoints.api import deps

            original_settings = deps.settings
            try:
                deps.settings = deps.Settings()
                settings = get_redis_settings()

                # URL should take precedence
                assert settings.host == "url-host.com"
                assert settings.port == 6381
                assert settings.password == "urlpassword"
                assert settings.database == 3
            finally:
                deps.settings = original_settings

    def test_default_values(self) -> None:
        """Test default Redis settings when no env vars set."""
        # Clear Redis-related env vars
        with patch.dict(os.environ, {}, clear=False):
            # Remove any existing Redis env vars
            for key in ["REDIS_URL", "REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD", "REDIS_DB"]:
                os.environ.pop(key, None)

            from dataing.entrypoints.api import deps

            original_settings = deps.settings
            try:
                deps.settings = deps.Settings()
                settings = get_redis_settings()

                assert settings.host == "localhost"
                assert settings.port == 6379
                assert settings.password is None
                assert settings.database == 0
            finally:
                deps.settings = original_settings


class TestEnqueueInvestigation:
    """Tests for enqueue_investigation function."""

    async def test_enqueue_creates_job(self) -> None:
        """Test that enqueue_investigation creates an arq job."""
        mock_job = MagicMock()
        mock_job.job_id = "test-job-123"

        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with patch("dataing.core.queue.create_pool", return_value=mock_pool):
            job_id = await enqueue_investigation(
                investigation_id="inv-123",
                tenant_id="tenant-456",
            )

            assert job_id == "test-job-123"
            mock_pool.enqueue_job.assert_called_once()

            # Check the call arguments
            call_args = mock_pool.enqueue_job.call_args
            assert call_args.args[0] == "run_investigation"
            assert call_args.kwargs["investigation_id"] == "inv-123"
            assert call_args.kwargs["tenant_id"] == "tenant-456"
            assert call_args.kwargs["_queue_name"] == INVESTIGATIONS_QUEUE

    async def test_enqueue_with_datasource_id(self) -> None:
        """Test that enqueue_investigation passes datasource_id."""
        mock_job = MagicMock()
        mock_job.job_id = "test-job-456"

        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with patch("dataing.core.queue.create_pool", return_value=mock_pool):
            job_id = await enqueue_investigation(
                investigation_id="inv-789",
                tenant_id="tenant-111",
                datasource_id="ds-222",
            )

            assert job_id == "test-job-456"
            call_kwargs = mock_pool.enqueue_job.call_args.kwargs
            assert call_kwargs["datasource_id"] == "ds-222"

    async def test_enqueue_with_priority(self) -> None:
        """Test that enqueue_investigation respects priority."""
        mock_job = MagicMock()
        mock_job.job_id = "priority-job"

        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with patch("dataing.core.queue.create_pool", return_value=mock_pool):
            job_id = await enqueue_investigation(
                investigation_id="inv-priority",
                tenant_id="tenant-priority",
                priority=5,
            )

            assert job_id == "priority-job"


class TestQueueConstants:
    """Tests for queue module constants."""

    def test_investigations_queue_name(self) -> None:
        """Test that INVESTIGATIONS_QUEUE has expected value."""
        assert INVESTIGATIONS_QUEUE == "investigations"
