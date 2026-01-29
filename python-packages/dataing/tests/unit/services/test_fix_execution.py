"""Tests for fix execution service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dataing.agents.models import FixProposal
from dataing.services.fix_execution import (
    FixExecutionResult,
    FixExecutionService,
    RollbackResult,
)


@pytest.fixture
def mock_adapter() -> MagicMock:
    """Create a mock SQL adapter."""
    adapter = MagicMock()
    adapter.capabilities = MagicMock()
    adapter.capabilities.supports_write = True
    adapter.execute_query = AsyncMock()
    return adapter


@pytest.fixture
def sample_dml_proposal() -> FixProposal:
    """Create a sample DML fix proposal."""
    return FixProposal(
        fix_type="sql_dml",
        description="Update NULL user_ids to default value",
        code="UPDATE orders SET user_id = 0 WHERE user_id IS NULL",
        confidence=0.85,
        risks=["May affect historical reports"],
        rollback="UPDATE orders SET user_id = NULL WHERE user_id = 0",
        estimated_impact="Updates ~485 rows",
        target_asset="orders",
    )


@pytest.fixture
def sample_ddl_proposal() -> FixProposal:
    """Create a sample DDL fix proposal."""
    return FixProposal(
        fix_type="sql_ddl",
        description="Add NOT NULL constraint",
        code="ALTER TABLE orders ALTER COLUMN user_id SET NOT NULL",
        confidence=0.9,
        risks=["Existing NULLs will cause failure"],
        rollback="ALTER TABLE orders ALTER COLUMN user_id DROP NOT NULL",
        estimated_impact="Schema change",
        target_asset="orders",
    )


@pytest.fixture
def manual_instruction_proposal() -> FixProposal:
    """Create a manual instruction proposal."""
    return FixProposal(
        fix_type="manual_instruction",
        description="Contact team to re-run ETL",
        code="1. Contact data-eng team\n2. Request re-run",
        confidence=0.7,
        risks=[],
        estimated_impact="Manual intervention",
        target_asset="etl_job",
    )


class TestFixExecutionService:
    """Tests for FixExecutionService."""

    async def test_execute_dml_fix_success(
        self, mock_adapter: MagicMock, sample_dml_proposal: FixProposal
    ) -> None:
        """Test successful DML fix execution."""
        # Setup
        mock_adapter.execute_query.return_value = MagicMock(row_count=485)

        service = FixExecutionService()
        investigation_id = uuid4()
        tenant_id = uuid4()
        user_id = uuid4()

        # Execute
        result = await service.execute_fix(
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            proposal=sample_dml_proposal,
            adapter=mock_adapter,
            allowed_tables={"orders"},
        )

        # Assert
        assert result.success
        assert result.rows_affected == 485
        assert result.error is None
        assert result.rollback_available_until is not None
        mock_adapter.execute_query.assert_called_once()

    async def test_execute_fix_validation_failure(self, mock_adapter: MagicMock) -> None:
        """Test fix execution fails validation."""
        # Create a DML proposal without WHERE clause
        bad_proposal = FixProposal(
            fix_type="sql_dml",
            description="Delete all orders",
            code="DELETE FROM orders",
            confidence=0.8,
            risks=[],
            estimated_impact="Deletes all orders",
            target_asset="orders",
        )

        service = FixExecutionService()

        result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=bad_proposal,
            adapter=mock_adapter,
        )

        # Assert validation failed
        assert not result.success
        assert "Validation failed" in (result.error or "")
        assert "WHERE" in (result.error or "")
        mock_adapter.execute_query.assert_not_called()

    async def test_execute_fix_skip_validation(self, mock_adapter: MagicMock) -> None:
        """Test fix execution can skip validation."""
        # Create a DML proposal without WHERE clause
        bad_proposal = FixProposal(
            fix_type="sql_dml",
            description="Delete all orders",
            code="DELETE FROM orders",
            confidence=0.8,
            risks=[],
            estimated_impact="Deletes all orders",
            target_asset="orders",
        )
        mock_adapter.execute_query.return_value = MagicMock(row_count=1000)

        service = FixExecutionService()

        result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=bad_proposal,
            adapter=mock_adapter,
            skip_validation=True,
        )

        # Should execute despite validation would fail
        assert result.success
        mock_adapter.execute_query.assert_called_once()

    async def test_execute_manual_instruction_no_execution(
        self, mock_adapter: MagicMock, manual_instruction_proposal: FixProposal
    ) -> None:
        """Test manual instruction doesn't execute SQL."""
        service = FixExecutionService()

        result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=manual_instruction_proposal,
            adapter=mock_adapter,
        )

        assert result.success
        assert result.rows_affected == 0
        mock_adapter.execute_query.assert_not_called()

    async def test_execute_fix_execution_error(
        self, mock_adapter: MagicMock, sample_dml_proposal: FixProposal
    ) -> None:
        """Test fix execution handles adapter errors."""
        mock_adapter.execute_query.side_effect = Exception("Connection lost")

        service = FixExecutionService()

        result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=sample_dml_proposal,
            adapter=mock_adapter,
            allowed_tables={"orders"},
        )

        assert not result.success
        assert "Connection lost" in (result.error or "")

    async def test_rollback_success(
        self, mock_adapter: MagicMock, sample_dml_proposal: FixProposal
    ) -> None:
        """Test successful rollback."""
        # First execute
        mock_adapter.execute_query.return_value = MagicMock(row_count=485)
        service = FixExecutionService()

        exec_result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=sample_dml_proposal,
            adapter=mock_adapter,
            allowed_tables={"orders"},
        )

        assert exec_result.success

        # Then rollback
        mock_adapter.execute_query.return_value = MagicMock(row_count=485)
        rollback_result = await service.rollback_fix(
            fix_execution_id=exec_result.fix_execution_id,
            user_id=uuid4(),
            adapter=mock_adapter,
        )

        assert rollback_result.success
        assert rollback_result.rows_affected == 485

    async def test_rollback_not_found(self, mock_adapter: MagicMock) -> None:
        """Test rollback with unknown execution ID."""
        service = FixExecutionService()

        result = await service.rollback_fix(
            fix_execution_id=uuid4(),
            user_id=uuid4(),
            adapter=mock_adapter,
        )

        assert not result.success
        assert "not found" in (result.error or "")

    async def test_rollback_already_rolled_back(
        self, mock_adapter: MagicMock, sample_dml_proposal: FixProposal
    ) -> None:
        """Test rollback fails if already rolled back."""
        mock_adapter.execute_query.return_value = MagicMock(row_count=485)
        service = FixExecutionService()

        exec_result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=sample_dml_proposal,
            adapter=mock_adapter,
            allowed_tables={"orders"},
        )

        # First rollback
        await service.rollback_fix(
            fix_execution_id=exec_result.fix_execution_id,
            user_id=uuid4(),
            adapter=mock_adapter,
        )

        # Second rollback should fail
        result = await service.rollback_fix(
            fix_execution_id=exec_result.fix_execution_id,
            user_id=uuid4(),
            adapter=mock_adapter,
        )

        assert not result.success
        assert "already been rolled back" in (result.error or "")

    async def test_rollback_no_statement(self, mock_adapter: MagicMock) -> None:
        """Test rollback fails if no rollback statement."""
        proposal_no_rollback = FixProposal(
            fix_type="sql_dml",
            description="Update orders",
            code="UPDATE orders SET status = 'x' WHERE id = 1",
            confidence=0.8,
            risks=[],
            rollback=None,  # No rollback
            estimated_impact="Updates 1 row",
            target_asset="orders",
        )
        mock_adapter.execute_query.return_value = MagicMock(row_count=1)
        service = FixExecutionService()

        exec_result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=proposal_no_rollback,
            adapter=mock_adapter,
            allowed_tables={"orders"},
        )

        result = await service.rollback_fix(
            fix_execution_id=exec_result.fix_execution_id,
            user_id=uuid4(),
            adapter=mock_adapter,
        )

        assert not result.success
        assert "No rollback statement" in (result.error or "")

    async def test_is_rollback_available(
        self, mock_adapter: MagicMock, sample_dml_proposal: FixProposal
    ) -> None:
        """Test is_rollback_available method."""
        mock_adapter.execute_query.return_value = MagicMock(row_count=1)
        service = FixExecutionService()

        exec_result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=sample_dml_proposal,
            adapter=mock_adapter,
            allowed_tables={"orders"},
        )

        # Immediately after execution, rollback should be available
        assert service.is_rollback_available(exec_result.fix_execution_id)

        # After rollback, should not be available
        await service.rollback_fix(
            fix_execution_id=exec_result.fix_execution_id,
            user_id=uuid4(),
            adapter=mock_adapter,
        )
        assert not service.is_rollback_available(exec_result.fix_execution_id)

    async def test_get_execution_record(
        self, mock_adapter: MagicMock, sample_dml_proposal: FixProposal
    ) -> None:
        """Test get_execution_record method."""
        mock_adapter.execute_query.return_value = MagicMock(row_count=1)
        service = FixExecutionService()

        exec_result = await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=sample_dml_proposal,
            adapter=mock_adapter,
            allowed_tables={"orders"},
        )

        record = service.get_execution_record(exec_result.fix_execution_id)
        assert record is not None
        assert record.fix_execution_id == exec_result.fix_execution_id
        assert record.proposal == sample_dml_proposal

    async def test_execution_with_timeout(
        self, mock_adapter: MagicMock, sample_dml_proposal: FixProposal
    ) -> None:
        """Test execution passes timeout to adapter."""
        mock_adapter.execute_query.return_value = MagicMock(row_count=1)
        service = FixExecutionService()

        await service.execute_fix(
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            proposal=sample_dml_proposal,
            adapter=mock_adapter,
            allowed_tables={"orders"},
            timeout_seconds=60,
        )

        # Check timeout was passed
        mock_adapter.execute_query.assert_called_once()
        call_args = mock_adapter.execute_query.call_args
        assert call_args.kwargs.get("timeout_seconds") == 60


class TestFixExecutionResult:
    """Tests for FixExecutionResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful result."""
        result = FixExecutionResult(
            success=True,
            fix_execution_id=uuid4(),
            rows_affected=100,
            execution_time_ms=50,
        )
        assert result.success
        assert result.rows_affected == 100
        assert result.error is None

    def test_failed_result(self) -> None:
        """Test creating a failed result."""
        result = FixExecutionResult(
            success=False,
            fix_execution_id=uuid4(),
            error="Connection refused",
        )
        assert not result.success
        assert result.error == "Connection refused"


class TestRollbackResult:
    """Tests for RollbackResult dataclass."""

    def test_successful_rollback(self) -> None:
        """Test creating a successful rollback result."""
        result = RollbackResult(success=True, rows_affected=50)
        assert result.success
        assert result.rows_affected == 50

    def test_failed_rollback(self) -> None:
        """Test creating a failed rollback result."""
        result = RollbackResult(success=False, error="Timeout")
        assert not result.success
        assert result.error == "Timeout"
