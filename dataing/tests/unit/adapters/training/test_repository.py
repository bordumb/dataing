"""Tests for TrainingSignalRepository."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.training.repository import TrainingSignalRepository


class TestTrainingSignalRepository:
    """Tests for TrainingSignalRepository."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database."""
        db = MagicMock()
        db.execute = AsyncMock()
        db.fetch_one = AsyncMock()
        return db

    @pytest.fixture
    def repository(self, mock_db: MagicMock) -> TrainingSignalRepository:
        """Create repository with mock database."""
        return TrainingSignalRepository(db=mock_db)

    @pytest.mark.asyncio
    async def test_record_signal(
        self, repository: TrainingSignalRepository, mock_db: MagicMock
    ) -> None:
        """Test recording a training signal."""
        tenant_id = uuid4()
        investigation_id = uuid4()

        signal_id = await repository.record_signal(
            signal_type="interpretation",
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            input_context={"hypothesis": "test", "query": "SELECT 1"},
            output_response={"interpretation": "test result"},
            automated_score=0.75,
            automated_dimensions={
                "causal_depth": 0.8,
                "specificity": 0.7,
                "actionability": 0.6,
            },
        )

        assert signal_id is not None
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_human_feedback(
        self, repository: TrainingSignalRepository, mock_db: MagicMock
    ) -> None:
        """Test updating human feedback score."""
        investigation_id = uuid4()

        await repository.update_human_feedback(
            investigation_id=investigation_id,
            signal_type="synthesis",
            score=1.0,
        )

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "human_feedback_score" in call_args[0][0]
