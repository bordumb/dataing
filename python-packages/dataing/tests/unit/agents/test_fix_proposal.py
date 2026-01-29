"""Tests for FixProposal model."""

import pytest
from pydantic import ValidationError

from dataing.agents.models import FixProposal


class TestFixProposalBasic:
    """Basic validation tests for FixProposal model."""

    def test_valid_sql_dml_fix(self) -> None:
        """Test valid SQL DML fix proposal."""
        fix = FixProposal(
            fix_type="sql_dml",
            description="Update NULL user_ids to default value",
            code="UPDATE orders SET user_id = 0 WHERE user_id IS NULL",
            confidence=0.85,
            risks=["May affect historical reports", "Default user_id may not exist"],
            rollback="UPDATE orders SET user_id = NULL WHERE user_id = 0",
            estimated_impact="Affects ~485 rows in orders table",
            target_asset="orders",
        )
        assert fix.fix_type == "sql_dml"
        assert fix.confidence == 0.85
        assert len(fix.risks) == 2

    def test_valid_sql_ddl_fix(self) -> None:
        """Test valid SQL DDL fix proposal."""
        fix = FixProposal(
            fix_type="sql_ddl",
            description="Add NOT NULL constraint to user_id column",
            code="ALTER TABLE orders ALTER COLUMN user_id SET NOT NULL",
            confidence=0.9,
            risks=["Existing NULL rows will cause failure"],
            rollback="ALTER TABLE orders ALTER COLUMN user_id DROP NOT NULL",
            estimated_impact="Schema change on orders table",
            target_asset="orders",
        )
        assert fix.fix_type == "sql_ddl"
        # DDL always requires confirmation
        assert fix.requires_confirmation is True

    def test_valid_dbt_patch_yaml(self) -> None:
        """Test valid dbt YAML patch."""
        fix = FixProposal(
            fix_type="dbt_patch",
            description="Add NOT NULL test to user_id column",
            code="""models:
  - name: stg_orders
    columns:
      - name: user_id
        tests:
          - not_null""",
            confidence=0.95,
            risks=[],
            estimated_impact="Adds data quality test to stg_orders model",
            target_asset="stg_orders",
        )
        assert fix.fix_type == "dbt_patch"

    def test_valid_dbt_patch_sql(self) -> None:
        """Test valid dbt SQL model patch."""
        fix = FixProposal(
            fix_type="dbt_patch",
            description="Add COALESCE to handle NULL user_ids",
            code="SELECT COALESCE(user_id, 0) as user_id FROM {{ ref('raw_orders') }}",
            confidence=0.8,
            risks=["Default user_id 0 may need to be created"],
            estimated_impact="Changes user_id handling in stg_orders",
            target_asset="stg_orders",
        )
        assert fix.fix_type == "dbt_patch"

    def test_valid_python_patch(self) -> None:
        """Test valid Python code patch."""
        fix = FixProposal(
            fix_type="python_patch",
            description="Add validation to reject NULL user_ids",
            code="""def validate_user_id(user_id: int | None) -> int:
    if user_id is None:
        raise ValueError("user_id cannot be None")
    return user_id""",
            confidence=0.9,
            risks=["May cause ETL failures if NULLs are expected"],
            estimated_impact="Changes validation in order processing pipeline",
            target_asset="order_processor.py",
        )
        assert fix.fix_type == "python_patch"

    def test_valid_manual_instruction(self) -> None:
        """Test valid manual instruction fix."""
        fix = FixProposal(
            fix_type="manual_instruction",
            description="Contact upstream team to re-run failed ETL job",
            code="1. Contact data-eng team\n2. Request re-run of users_etl job\n3. Verify data",
            confidence=0.7,
            risks=["Depends on upstream team availability"],
            estimated_impact="Requires manual intervention",
            target_asset="users_etl",
        )
        assert fix.fix_type == "manual_instruction"


class TestFixProposalValidation:
    """Validation rule tests for FixProposal model."""

    def test_sql_ddl_requires_ddl_statement(self) -> None:
        """Test sql_ddl fix must be ALTER/CREATE/DROP."""
        with pytest.raises(ValidationError) as exc_info:
            FixProposal(
                fix_type="sql_ddl",
                description="Invalid DDL fix with SELECT",
                code="SELECT * FROM orders",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="orders",
            )
        assert "ALTER, CREATE, or DROP" in str(exc_info.value)

    def test_sql_ddl_rejects_dml(self) -> None:
        """Test sql_ddl fix rejects DML statements."""
        with pytest.raises(ValidationError) as exc_info:
            FixProposal(
                fix_type="sql_ddl",
                description="Invalid DDL fix with UPDATE",
                code="UPDATE orders SET user_id = 0",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="orders",
            )
        assert "ALTER, CREATE, or DROP" in str(exc_info.value)

    def test_sql_dml_requires_dml_statement(self) -> None:
        """Test sql_dml fix must be INSERT/UPDATE/DELETE/MERGE."""
        with pytest.raises(ValidationError) as exc_info:
            FixProposal(
                fix_type="sql_dml",
                description="Invalid DML fix with SELECT",
                code="SELECT * FROM orders",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="orders",
            )
        assert "INSERT, UPDATE, DELETE, or MERGE" in str(exc_info.value)

    def test_sql_dml_rejects_ddl(self) -> None:
        """Test sql_dml fix rejects DDL statements."""
        with pytest.raises(ValidationError) as exc_info:
            FixProposal(
                fix_type="sql_dml",
                description="Invalid DML fix with ALTER",
                code="ALTER TABLE orders ADD COLUMN foo INT",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="orders",
            )
        assert "INSERT, UPDATE, DELETE, or MERGE" in str(exc_info.value)

    def test_ddl_always_requires_confirmation(self) -> None:
        """Test DDL fixes always require confirmation even if set to False."""
        fix = FixProposal(
            fix_type="sql_ddl",
            description="Create new table",
            code="CREATE TABLE test_table (id INT)",
            confidence=0.9,
            risks=[],
            requires_confirmation=False,  # Try to set to False
            estimated_impact="Creates new table",
            target_asset="test_table",
        )
        # Should be overridden to True
        assert fix.requires_confirmation is True

    def test_python_patch_validates_syntax(self) -> None:
        """Test Python patch validates syntax."""
        with pytest.raises(ValidationError) as exc_info:
            FixProposal(
                fix_type="python_patch",
                description="Invalid Python syntax",
                code="def broken(\n  # missing everything",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="test.py",
            )
        assert "Invalid Python syntax" in str(exc_info.value)

    def test_invalid_sql_syntax_rejected(self) -> None:
        """Test invalid SQL syntax is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FixProposal(
                fix_type="sql_dml",
                description="Invalid SQL",
                code="UPDAET orders SET foo = bar",  # typo
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="orders",
            )
        assert "Invalid SQL" in str(exc_info.value)

    def test_empty_code_rejected(self) -> None:
        """Test empty code is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FixProposal(
                fix_type="manual_instruction",
                description="Empty instruction",
                code="",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="test",
            )
        assert "code" in str(exc_info.value).lower()

    def test_whitespace_only_code_rejected(self) -> None:
        """Test whitespace-only code is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FixProposal(
                fix_type="manual_instruction",
                description="Whitespace instruction",
                code="   \n\t  ",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="test",
            )
        assert "empty" in str(exc_info.value).lower() or "whitespace" in str(exc_info.value).lower()

    def test_confidence_must_be_between_0_and_1(self) -> None:
        """Test confidence must be in [0, 1] range."""
        with pytest.raises(ValidationError):
            FixProposal(
                fix_type="manual_instruction",
                description="Bad confidence",
                code="Do something",
                confidence=1.5,
                risks=[],
                estimated_impact="No impact",
                target_asset="test",
            )

    def test_description_min_length(self) -> None:
        """Test description has minimum length."""
        with pytest.raises(ValidationError):
            FixProposal(
                fix_type="manual_instruction",
                description="Short",  # Too short
                code="Do something",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="test",
            )


class TestFixProposalFixTypes:
    """Test all supported fix types."""

    @pytest.mark.parametrize(
        "fix_type",
        ["sql_ddl", "sql_dml", "dbt_patch", "python_patch", "manual_instruction"],
    )
    def test_all_fix_types_accepted(self, fix_type: str) -> None:
        """Test all documented fix types are accepted."""
        code_map = {
            "sql_ddl": "ALTER TABLE orders ADD COLUMN test INT",
            "sql_dml": "UPDATE orders SET test = 1 WHERE id = 1",
            "dbt_patch": "SELECT * FROM {{ ref('orders') }}",
            "python_patch": "x = 1",
            "manual_instruction": "Do something manually",
        }
        fix = FixProposal(
            fix_type=fix_type,
            description="Test fix for all types",
            code=code_map[fix_type],
            confidence=0.8,
            risks=[],
            estimated_impact="Test impact",
            target_asset="test",
        )
        assert fix.fix_type == fix_type

    def test_invalid_fix_type_rejected(self) -> None:
        """Test invalid fix type is rejected."""
        with pytest.raises(ValidationError):
            FixProposal(
                fix_type="invalid_type",  # type: ignore[arg-type]
                description="Invalid type test",
                code="some code",
                confidence=0.8,
                risks=[],
                estimated_impact="No impact",
                target_asset="test",
            )


class TestFixProposalDDLStatements:
    """Test DDL statement validation."""

    def test_alter_table_accepted(self) -> None:
        """Test ALTER TABLE is accepted as DDL."""
        fix = FixProposal(
            fix_type="sql_ddl",
            description="Alter table to add column",
            code="ALTER TABLE orders ADD COLUMN status VARCHAR(50)",
            confidence=0.9,
            risks=[],
            estimated_impact="Adds column to orders",
            target_asset="orders",
        )
        assert fix.fix_type == "sql_ddl"

    def test_create_table_accepted(self) -> None:
        """Test CREATE TABLE is accepted as DDL."""
        fix = FixProposal(
            fix_type="sql_ddl",
            description="Create new audit table",
            code="CREATE TABLE audit_log (id SERIAL PRIMARY KEY, action TEXT)",
            confidence=0.9,
            risks=[],
            estimated_impact="Creates new table",
            target_asset="audit_log",
        )
        assert fix.fix_type == "sql_ddl"

    def test_drop_table_accepted(self) -> None:
        """Test DROP TABLE is accepted as DDL."""
        fix = FixProposal(
            fix_type="sql_ddl",
            description="Drop temporary table",
            code="DROP TABLE IF EXISTS temp_orders",
            confidence=0.9,
            risks=["Data loss if table is not temporary"],
            estimated_impact="Removes temp_orders table",
            target_asset="temp_orders",
        )
        assert fix.fix_type == "sql_ddl"


class TestFixProposalDMLStatements:
    """Test DML statement validation."""

    def test_insert_accepted(self) -> None:
        """Test INSERT is accepted as DML."""
        fix = FixProposal(
            fix_type="sql_dml",
            description="Insert missing records",
            code="INSERT INTO orders (id, user_id) VALUES (1, 100)",
            confidence=0.9,
            risks=[],
            estimated_impact="Adds 1 row to orders",
            target_asset="orders",
        )
        assert fix.fix_type == "sql_dml"

    def test_update_accepted(self) -> None:
        """Test UPDATE is accepted as DML."""
        fix = FixProposal(
            fix_type="sql_dml",
            description="Update invalid records",
            code="UPDATE orders SET status = 'fixed' WHERE status IS NULL",
            confidence=0.85,
            risks=[],
            estimated_impact="Updates ~100 rows in orders",
            target_asset="orders",
        )
        assert fix.fix_type == "sql_dml"

    def test_delete_accepted(self) -> None:
        """Test DELETE is accepted as DML."""
        fix = FixProposal(
            fix_type="sql_dml",
            description="Delete duplicate records",
            code="DELETE FROM orders WHERE id IN (SELECT id FROM duplicates)",
            confidence=0.8,
            risks=["May delete valid records if duplicates list is wrong"],
            estimated_impact="Deletes ~50 duplicate rows",
            target_asset="orders",
        )
        assert fix.fix_type == "sql_dml"


class TestFixProposalOptionalFields:
    """Test optional fields behavior."""

    def test_rollback_is_optional(self) -> None:
        """Test rollback field is optional."""
        fix = FixProposal(
            fix_type="manual_instruction",
            description="Manual fix without rollback",
            code="Contact support team",
            confidence=0.7,
            risks=[],
            estimated_impact="Manual intervention required",
            target_asset="external_system",
        )
        assert fix.rollback is None

    def test_rollback_can_be_provided(self) -> None:
        """Test rollback can be provided."""
        fix = FixProposal(
            fix_type="sql_dml",
            description="Update with rollback",
            code="UPDATE orders SET status = 'new' WHERE status = 'old'",
            confidence=0.9,
            risks=[],
            rollback="UPDATE orders SET status = 'old' WHERE status = 'new'",
            estimated_impact="Updates status values",
            target_asset="orders",
        )
        assert fix.rollback is not None

    def test_risks_can_be_empty(self) -> None:
        """Test risks list can be empty."""
        fix = FixProposal(
            fix_type="manual_instruction",
            description="Safe manual instruction",
            code="Review and verify data",
            confidence=0.95,
            risks=[],
            estimated_impact="No direct changes",
            target_asset="data_review",
        )
        assert fix.risks == []

    def test_requires_confirmation_defaults_true(self) -> None:
        """Test requires_confirmation defaults to True."""
        fix = FixProposal(
            fix_type="sql_dml",
            description="DML fix with default confirmation",
            code="UPDATE orders SET status = 'test'",
            confidence=0.8,
            risks=[],
            estimated_impact="Updates orders",
            target_asset="orders",
        )
        assert fix.requires_confirmation is True
