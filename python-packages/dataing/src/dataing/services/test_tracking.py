"""Test tracking service for measuring codify effectiveness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()


class TestEventType(str, Enum):
    """Types of test tracking events."""

    TEST_GENERATED = "test_generated"
    TEST_ADOPTED = "test_adopted"
    TEST_RUN = "test_run"
    TEST_CAUGHT_ISSUE = "test_caught_issue"


class TestFormat(str, Enum):
    """Test output formats."""

    GX = "gx"
    DBT = "dbt"
    SODA = "soda"
    SQL = "sql"


@dataclass
class GeneratedTest:
    """A generated test record."""

    test_id: UUID
    investigation_id: UUID
    tenant_id: UUID
    format: str
    test_type: str
    table: str
    column: str | None
    description: str
    created_at: datetime
    adopted_at: datetime | None = None
    last_run_at: datetime | None = None
    run_count: int = 0
    failure_count: int = 0


@dataclass
class TestTrackingStats:
    """Test tracking statistics."""

    tests_generated: int
    tests_adopted: int
    tests_run: int
    issues_caught: int
    adoption_rate: float
    effectiveness_rate: float


@dataclass
class TestRunResult:
    """Result of a test run."""

    test_id: UUID
    passed: bool
    run_at: datetime
    failure_message: str | None = None


class TestTrackingService:
    """Service for tracking generated test adoption and effectiveness."""

    def __init__(self, db: AppDatabase):
        """Initialize the test tracking service.

        Args:
            db: Application database instance.
        """
        self.db = db

    async def record_test_generated(
        self,
        tenant_id: UUID,
        investigation_id: UUID,
        test_id: str | UUID,
        format_: str,
        test_type: str,
        table: str,
        column: str | None,
        description: str,
    ) -> UUID:
        """Record a generated test.

        Args:
            tenant_id: Tenant ID.
            investigation_id: Source investigation ID.
            test_id: Unique test ID (string or UUID).
            format_: Output format (gx, dbt, soda, sql).
            test_type: Type of test (not_null, unique, etc).
            table: Target table name.
            column: Target column name (if applicable).
            description: Test description.

        Returns:
            The test ID.
        """
        # Convert string to UUID if needed
        test_uuid = UUID(test_id) if isinstance(test_id, str) else test_id

        await self.db.execute(
            """
            INSERT INTO generated_tests (
                id, tenant_id, investigation_id, format, test_type,
                table_name, column_name, description, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO NOTHING
            """,
            test_uuid,
            tenant_id,
            investigation_id,
            format_,
            test_type,
            table,
            column,
            description,
            datetime.now(UTC),
        )

        logger.info(
            "test_generated",
            test_id=str(test_uuid),
            tenant_id=str(tenant_id),
            investigation_id=str(investigation_id),
            format=format_,
            test_type=test_type,
            table=table,
        )

        return test_uuid

    async def record_test_adopted(
        self,
        tenant_id: UUID,
        test_id: UUID,
        adopted_by: str | None = None,
    ) -> bool:
        """Record that a test has been adopted.

        Args:
            tenant_id: Tenant ID.
            test_id: The test ID.
            adopted_by: Optional user/system that confirmed adoption.

        Returns:
            True if updated, False if test not found.
        """
        result = await self.db.execute(
            """
            UPDATE generated_tests
            SET adopted_at = $1, adopted_by = $2
            WHERE id = $3 AND tenant_id = $4 AND adopted_at IS NULL
            """,
            datetime.now(UTC),
            adopted_by,
            test_id,
            tenant_id,
        )

        if result:
            logger.info(
                "test_adopted",
                test_id=str(test_id),
                tenant_id=str(tenant_id),
                adopted_by=adopted_by,
            )
            return True

        return False

    async def record_test_run(
        self,
        tenant_id: UUID,
        test_id: UUID,
        passed: bool,
        failure_message: str | None = None,
    ) -> None:
        """Record a test run result.

        Args:
            tenant_id: Tenant ID.
            test_id: The test ID.
            passed: Whether the test passed.
            failure_message: Error message if test failed.
        """
        now = datetime.now(UTC)

        # Update test run stats
        await self.db.execute(
            """
            UPDATE generated_tests
            SET last_run_at = $1,
                run_count = run_count + 1,
                failure_count = failure_count + CASE WHEN $2 THEN 0 ELSE 1 END
            WHERE id = $3 AND tenant_id = $4
            """,
            now,
            passed,
            test_id,
            tenant_id,
        )

        # Record individual run
        await self.db.execute(
            """
            INSERT INTO test_runs (test_id, tenant_id, passed, failure_message, run_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            test_id,
            tenant_id,
            passed,
            failure_message,
            now,
        )

        if not passed:
            logger.info(
                "test_caught_issue",
                test_id=str(test_id),
                tenant_id=str(tenant_id),
                failure_message=failure_message,
            )
        else:
            logger.debug(
                "test_run_passed",
                test_id=str(test_id),
                tenant_id=str(tenant_id),
            )

    async def get_test(self, tenant_id: UUID, test_id: UUID) -> GeneratedTest | None:
        """Get a generated test by ID.

        Args:
            tenant_id: Tenant ID.
            test_id: The test ID.

        Returns:
            GeneratedTest or None if not found.
        """
        row = await self.db.fetch_one(
            """
            SELECT id, investigation_id, tenant_id, format, test_type,
                   table_name, column_name, description, created_at,
                   adopted_at, last_run_at, run_count, failure_count
            FROM generated_tests
            WHERE id = $1 AND tenant_id = $2
            """,
            test_id,
            tenant_id,
        )

        if not row:
            return None

        return GeneratedTest(
            test_id=row["id"],
            investigation_id=row["investigation_id"],
            tenant_id=row["tenant_id"],
            format=row["format"],
            test_type=row["test_type"],
            table=row["table_name"],
            column=row["column_name"],
            description=row["description"],
            created_at=row["created_at"],
            adopted_at=row["adopted_at"],
            last_run_at=row["last_run_at"],
            run_count=row["run_count"] or 0,
            failure_count=row["failure_count"] or 0,
        )

    async def get_tests_by_investigation(
        self,
        tenant_id: UUID,
        investigation_id: UUID,
    ) -> list[GeneratedTest]:
        """Get all tests generated for an investigation.

        Args:
            tenant_id: Tenant ID.
            investigation_id: The investigation ID.

        Returns:
            List of generated tests.
        """
        rows = await self.db.fetch_all(
            """
            SELECT id, investigation_id, tenant_id, format, test_type,
                   table_name, column_name, description, created_at,
                   adopted_at, last_run_at, run_count, failure_count
            FROM generated_tests
            WHERE investigation_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            """,
            investigation_id,
            tenant_id,
        )

        return [
            GeneratedTest(
                test_id=row["id"],
                investigation_id=row["investigation_id"],
                tenant_id=row["tenant_id"],
                format=row["format"],
                test_type=row["test_type"],
                table=row["table_name"],
                column=row["column_name"],
                description=row["description"],
                created_at=row["created_at"],
                adopted_at=row["adopted_at"],
                last_run_at=row["last_run_at"],
                run_count=row["run_count"] or 0,
                failure_count=row["failure_count"] or 0,
            )
            for row in rows
        ]

    async def get_stats(
        self,
        tenant_id: UUID,
        days: int = 30,
    ) -> TestTrackingStats:
        """Get test tracking statistics.

        Args:
            tenant_id: Tenant ID.
            days: Number of days to look back.

        Returns:
            Test tracking statistics.
        """
        since = datetime.now(UTC) - timedelta(days=days)

        row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as tests_generated,
                COUNT(adopted_at) as tests_adopted,
                SUM(run_count) as total_runs,
                SUM(failure_count) as total_failures
            FROM generated_tests
            WHERE tenant_id = $1 AND created_at >= $2
            """,
            tenant_id,
            since,
        )

        if not row:
            return TestTrackingStats(
                tests_generated=0,
                tests_adopted=0,
                tests_run=0,
                issues_caught=0,
                adoption_rate=0.0,
                effectiveness_rate=0.0,
            )

        tests_generated = row["tests_generated"] or 0
        tests_adopted = row["tests_adopted"] or 0
        total_runs = row["total_runs"] or 0
        total_failures = row["total_failures"] or 0

        adoption_rate = tests_adopted / tests_generated if tests_generated > 0 else 0.0
        effectiveness_rate = total_failures / tests_generated if tests_generated > 0 else 0.0

        return TestTrackingStats(
            tests_generated=tests_generated,
            tests_adopted=tests_adopted,
            tests_run=total_runs,
            issues_caught=total_failures,
            adoption_rate=adoption_rate,
            effectiveness_rate=effectiveness_rate,
        )

    async def get_recent_catches(
        self,
        tenant_id: UUID,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent tests that caught issues.

        Args:
            tenant_id: Tenant ID.
            limit: Maximum number of results.

        Returns:
            List of recent catches with test and failure info.
        """
        rows = await self.db.fetch_all(
            """
            SELECT
                tr.test_id,
                tr.run_at,
                tr.failure_message,
                gt.test_type,
                gt.table_name,
                gt.column_name,
                gt.investigation_id
            FROM test_runs tr
            JOIN generated_tests gt ON tr.test_id = gt.id
            WHERE tr.tenant_id = $1 AND tr.passed = FALSE
            ORDER BY tr.run_at DESC
            LIMIT $2
            """,
            tenant_id,
            limit,
        )

        return [
            {
                "test_id": str(row["test_id"]),
                "run_at": row["run_at"].isoformat(),
                "failure_message": row["failure_message"],
                "test_type": row["test_type"],
                "table": row["table_name"],
                "column": row["column_name"],
                "investigation_id": str(row["investigation_id"]),
            }
            for row in rows
        ]
