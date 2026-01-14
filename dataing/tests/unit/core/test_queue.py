"""Tests for the queue module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from dataing.core.queue import get_redis_settings


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
        env = {
            "REDIS_URL": "",
            "REDIS_HOST": "",
            "REDIS_PORT": "",
            "REDIS_PASSWORD": "",
            "REDIS_DB": "",
        }
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
