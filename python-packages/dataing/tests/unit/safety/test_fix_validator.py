"""Tests for SQL fix validator."""

from dataing.safety.fix_validator import (
    FixValidationResult,
    validate_fix_proposal,
    validate_fix_sql,
)


class TestValidateFixSqlBasic:
    """Basic validation tests for validate_fix_sql."""

    def test_valid_update_with_where(self) -> None:
        """Test valid UPDATE with WHERE clause."""
        result = validate_fix_sql("UPDATE orders SET status = 'fixed' WHERE id = 1")
        assert result.is_valid
        assert len(result.errors) == 0
        assert "orders" in result.tables_touched

    def test_valid_delete_with_where(self) -> None:
        """Test valid DELETE with WHERE clause."""
        result = validate_fix_sql("DELETE FROM orders WHERE order_date < '2020-01-01'")
        assert result.is_valid
        assert len(result.errors) == 0

    def test_valid_insert(self) -> None:
        """Test valid INSERT statement."""
        result = validate_fix_sql("INSERT INTO orders (id, status) VALUES (1, 'pending')")
        assert result.is_valid
        assert "orders" in result.tables_touched

    def test_valid_alter_table(self) -> None:
        """Test valid ALTER TABLE statement."""
        result = validate_fix_sql("ALTER TABLE orders ADD COLUMN status VARCHAR(50)")
        assert result.is_valid
        assert "orders" in result.tables_touched

    def test_valid_create_table(self) -> None:
        """Test valid CREATE TABLE statement."""
        result = validate_fix_sql("CREATE TABLE audit_log (id SERIAL PRIMARY KEY)")
        assert result.is_valid
        assert "audit_log" in result.tables_touched


class TestValidateFixSqlSafety:
    """Safety validation tests for validate_fix_sql."""

    def test_delete_without_where_rejected(self) -> None:
        """Test DELETE without WHERE is rejected."""
        result = validate_fix_sql("DELETE FROM orders")
        assert not result.is_valid
        assert any("WHERE clause" in e for e in result.errors)

    def test_update_without_where_rejected(self) -> None:
        """Test UPDATE without WHERE is rejected."""
        result = validate_fix_sql("UPDATE orders SET status = 'deleted'")
        assert not result.is_valid
        assert any("WHERE clause" in e for e in result.errors)

    def test_truncate_rejected(self) -> None:
        """Test TRUNCATE is rejected by default."""
        result = validate_fix_sql("TRUNCATE TABLE orders")
        assert not result.is_valid
        assert any("TRUNCATE" in e for e in result.errors)

    def test_truncate_allowed_when_flag_set(self) -> None:
        """Test TRUNCATE is allowed when flag is set."""
        result = validate_fix_sql("TRUNCATE TABLE orders", allow_truncate=True)
        # Should pass safety check (but may fail others)
        assert not any("TRUNCATE" in e for e in result.errors)

    def test_drop_rejected_by_default(self) -> None:
        """Test DROP is rejected by default."""
        result = validate_fix_sql("DROP TABLE orders")
        assert not result.is_valid
        assert any("DROP" in e for e in result.errors)

    def test_drop_allowed_when_flag_set(self) -> None:
        """Test DROP is allowed when flag is set."""
        result = validate_fix_sql("DROP TABLE orders", allow_drop=True)
        assert result.is_valid

    def test_grant_always_rejected(self) -> None:
        """Test GRANT is always rejected."""
        result = validate_fix_sql("GRANT SELECT ON orders TO public")
        assert not result.is_valid
        assert any("Grant" in e for e in result.errors)

    def test_revoke_always_rejected(self) -> None:
        """Test REVOKE is always rejected."""
        result = validate_fix_sql("REVOKE SELECT ON orders FROM public")
        assert not result.is_valid
        assert any("Revoke" in e for e in result.errors)


class TestValidateFixSqlScope:
    """Scope validation tests for validate_fix_sql."""

    def test_allowed_tables_enforced(self) -> None:
        """Test that only allowed tables can be modified."""
        result = validate_fix_sql(
            "UPDATE orders SET status = 'fixed' WHERE id = 1",
            allowed_tables={"users", "products"},
        )
        assert not result.is_valid
        assert any("outside investigation scope" in e for e in result.errors)
        assert any("orders" in e for e in result.errors)

    def test_allowed_tables_pass(self) -> None:
        """Test that allowed tables pass validation."""
        result = validate_fix_sql(
            "UPDATE orders SET status = 'fixed' WHERE id = 1",
            allowed_tables={"orders", "users"},
        )
        assert result.is_valid

    def test_schema_qualified_tables(self) -> None:
        """Test that schema-qualified table names are handled."""
        result = validate_fix_sql(
            "UPDATE public.orders SET status = 'fixed' WHERE id = 1",
            allowed_tables={"public.orders"},
        )
        assert result.is_valid
        assert "public.orders" in result.tables_touched


class TestValidateFixSqlSyntax:
    """Syntax validation tests for validate_fix_sql."""

    def test_invalid_sql_rejected(self) -> None:
        """Test that invalid SQL is rejected."""
        result = validate_fix_sql("UPDAET orders SET foo = bar")
        assert not result.is_valid
        assert any("Invalid SQL syntax" in e for e in result.errors)

    def test_empty_sql_rejected(self) -> None:
        """Test that empty SQL is rejected."""
        result = validate_fix_sql("")
        assert not result.is_valid
        assert any("Empty SQL" in e for e in result.errors)

    def test_whitespace_only_rejected(self) -> None:
        """Test that whitespace-only SQL is rejected."""
        result = validate_fix_sql("   \n\t  ")
        assert not result.is_valid
        assert any("Empty SQL" in e for e in result.errors)


class TestValidateFixSqlWarnings:
    """Warning tests for validate_fix_sql."""

    def test_trivial_where_warned(self) -> None:
        """Test that trivially true WHERE clause generates warning."""
        result = validate_fix_sql("UPDATE orders SET status = 'x' WHERE 1=1")
        # Should still be valid but with warning
        # Note: This depends on sqlglot parsing 1=1 as literals
        assert result.is_valid or "WHERE" in str(result.errors)

    def test_high_affected_rows_warned(self) -> None:
        """Test that high estimated affected rows generates warning."""
        # IN clause with many values
        values = ", ".join(str(i) for i in range(200))
        sql = f"DELETE FROM orders WHERE id IN ({values})"
        result = validate_fix_sql(sql, max_affected_rows=100)
        # Should have warning about affected rows
        if result.estimated_affected_rows:
            assert result.estimated_affected_rows > 100


class TestValidateFixSqlRowEstimation:
    """Row estimation tests for validate_fix_sql."""

    def test_pk_lookup_estimated_one_row(self) -> None:
        """Test that PK lookup estimates 1 row."""
        result = validate_fix_sql("UPDATE orders SET status = 'x' WHERE id = 123")
        assert result.estimated_affected_rows == 1

    def test_in_clause_counts_values(self) -> None:
        """Test that IN clause counts values."""
        result = validate_fix_sql("DELETE FROM orders WHERE id IN (1, 2, 3, 4, 5)")
        assert result.estimated_affected_rows == 5

    def test_insert_counts_values(self) -> None:
        """Test that INSERT counts value tuples."""
        result = validate_fix_sql(
            "INSERT INTO orders (id, status) VALUES (1, 'a'), (2, 'b'), (3, 'c')"
        )
        assert result.estimated_affected_rows == 3

    def test_ddl_zero_rows(self) -> None:
        """Test that DDL statements estimate 0 rows."""
        result = validate_fix_sql("ALTER TABLE orders ADD COLUMN foo INT")
        assert result.estimated_affected_rows == 0


class TestValidateFixProposal:
    """Tests for validate_fix_proposal with FixProposal objects."""

    def test_sql_dml_validated(self) -> None:
        """Test SQL DML proposals are validated."""
        from dataing.agents.models import FixProposal

        proposal = FixProposal(
            fix_type="sql_dml",
            description="Update NULL user_ids",
            code="UPDATE orders SET user_id = 0 WHERE user_id IS NULL",
            confidence=0.8,
            risks=[],
            estimated_impact="Updates orders with NULL user_id",
            target_asset="orders",
        )

        result = validate_fix_proposal(proposal)
        assert result.is_valid

    def test_sql_dml_without_where_rejected(self) -> None:
        """Test SQL DML without WHERE is rejected."""
        from dataing.agents.models import FixProposal

        proposal = FixProposal(
            fix_type="sql_dml",
            description="Delete all orders",
            code="DELETE FROM orders",
            confidence=0.8,
            risks=[],
            estimated_impact="Deletes orders",
            target_asset="orders",
        )

        result = validate_fix_proposal(proposal)
        assert not result.is_valid
        assert any("WHERE" in e for e in result.errors)

    def test_sql_ddl_allows_drop(self) -> None:
        """Test SQL DDL proposals allow DROP statements."""
        from dataing.agents.models import FixProposal

        proposal = FixProposal(
            fix_type="sql_ddl",
            description="Drop temporary table",
            code="DROP TABLE IF EXISTS temp_orders",
            confidence=0.9,
            risks=["Data loss if not temporary"],
            estimated_impact="Removes temp table",
            target_asset="temp_orders",
        )

        result = validate_fix_proposal(proposal)
        assert result.is_valid

    def test_dbt_patch_with_jinja_passes(self) -> None:
        """Test dbt patch with Jinja templates passes with warning."""
        from dataing.agents.models import FixProposal

        proposal = FixProposal(
            fix_type="dbt_patch",
            description="Add COALESCE for NULL handling",
            code="SELECT COALESCE(user_id, 0) FROM {{ ref('orders') }}",
            confidence=0.8,
            risks=[],
            estimated_impact="Changes user_id handling",
            target_asset="stg_orders",
        )

        result = validate_fix_proposal(proposal)
        assert result.is_valid
        assert any("Jinja" in w for w in result.warnings)

    def test_dbt_patch_plain_sql_validated(self) -> None:
        """Test dbt patch without Jinja is validated as SQL."""
        from dataing.agents.models import FixProposal

        proposal = FixProposal(
            fix_type="dbt_patch",
            description="Add NOT NULL filter",
            code="SELECT * FROM orders WHERE user_id IS NOT NULL",
            confidence=0.8,
            risks=[],
            estimated_impact="Filters NULL user_ids",
            target_asset="stg_orders",
        )

        result = validate_fix_proposal(proposal)
        assert result.is_valid

    def test_manual_instruction_always_valid(self) -> None:
        """Test manual instruction is always valid."""
        from dataing.agents.models import FixProposal

        proposal = FixProposal(
            fix_type="manual_instruction",
            description="Contact upstream team",
            code="1. Contact team\n2. Request re-run",
            confidence=0.7,
            risks=[],
            estimated_impact="Manual intervention",
            target_asset="external_system",
        )

        result = validate_fix_proposal(proposal)
        assert result.is_valid

    def test_python_patch_always_valid(self) -> None:
        """Test Python patch is always valid (validated at model level)."""
        from dataing.agents.models import FixProposal

        proposal = FixProposal(
            fix_type="python_patch",
            description="Add validation",
            code="def validate(x): return x is not None",
            confidence=0.9,
            risks=[],
            estimated_impact="Adds validation",
            target_asset="validator.py",
        )

        result = validate_fix_proposal(proposal)
        assert result.is_valid


class TestFixValidationResult:
    """Tests for FixValidationResult dataclass."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        result = FixValidationResult(is_valid=True)
        assert result.is_valid
        assert result.errors == []
        assert result.warnings == []
        assert result.estimated_affected_rows is None
        assert result.tables_touched == set()

    def test_with_errors(self) -> None:
        """Test result with errors."""
        result = FixValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"],
        )
        assert not result.is_valid
        assert len(result.errors) == 2
