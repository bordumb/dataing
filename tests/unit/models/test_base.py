"""Unit tests for base model."""

from __future__ import annotations

from dataing.models.base import BaseModel


class TestBaseModel:
    """Tests for BaseModel."""

    def test_base_model_has_id(self) -> None:
        """Test that base model has id column."""
        assert hasattr(BaseModel, "id")

    def test_base_model_has_created_at(self) -> None:
        """Test that base model has created_at column."""
        assert hasattr(BaseModel, "created_at")

    def test_base_model_has_updated_at(self) -> None:
        """Test that base model has updated_at column."""
        assert hasattr(BaseModel, "updated_at")
