"""Unit tests for runbook generator."""

import pytest

from dataing_ee.core.runbook.generator import RunbookGenerator


class TestRunbookGenerator:
    """Test runbook generation logic."""

    @pytest.fixture
    def generator(self) -> RunbookGenerator:
        """Create generator instance."""
        return RunbookGenerator()

    def test_extract_symptoms_from_findings(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test extracting symptoms from synthesis findings."""
        synthesis = {
            "findings": [
                {"description": "Row count dropped by 50%", "severity": "high"},
                {"description": "Missing data in date column", "severity": "medium"},
            ]
        }
        symptoms = generator._extract_symptoms("", synthesis)
        assert len(symptoms) == 2
        assert symptoms[0]["description"] == "Row count dropped by 50%"
        assert symptoms[0]["severity"] == "high"

    def test_extract_symptoms_from_description(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test extracting symptoms from description when no findings."""
        symptoms = generator._extract_symptoms(
            "Database connection timeout",
            {},
        )
        assert len(symptoms) == 1
        assert "Database connection timeout" in symptoms[0]["description"]

    def test_extract_root_cause(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test extracting root cause from synthesis."""
        synthesis = {"root_cause": "Schema migration caused column type change"}
        root_cause = generator._extract_root_cause(synthesis)
        assert root_cause == "Schema migration caused column type change"

    def test_extract_root_cause_from_conclusion(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test fallback to conclusion for root cause."""
        synthesis = {"conclusion": "The issue was caused by a network timeout"}
        root_cause = generator._extract_root_cause(synthesis)
        assert "network timeout" in root_cause

    def test_extract_verification_steps(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test extracting verification steps from queries."""
        synthesis = {
            "queries_executed": [
                {"description": "Check row count", "sql": "SELECT COUNT(*) FROM t"},
                {"description": "Check nulls", "sql": "SELECT * FROM t WHERE x IS NULL"},
            ]
        }
        steps = generator._extract_verification_steps(synthesis)
        assert len(steps) == 2
        assert steps[0]["query"] == "SELECT COUNT(*) FROM t"

    def test_extract_fix_steps_from_resolution(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test extracting fix steps from resolution."""
        fix_steps = generator._extract_fix_steps(
            "Revert schema migration and re-run ETL",
            {},
        )
        assert len(fix_steps) == 1
        assert "Revert schema migration" in fix_steps[0]["description"]

    def test_extract_fix_steps_from_recommendations(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test extracting fix steps from recommendations."""
        synthesis = {
            "recommendations": [
                {"description": "Add monitoring", "type": "preventive"},
                {"description": "Fix the query", "type": "fix"},
            ]
        }
        fix_steps = generator._extract_fix_steps("", synthesis)
        assert len(fix_steps) == 2

    def test_extract_prevention_notes(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test extracting prevention notes."""
        synthesis = {"prevention": "Set up data quality alerts"}
        notes = generator._extract_prevention_notes(synthesis)
        assert notes == "Set up data quality alerts"

    def test_extract_labels(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test extracting labels from metadata and synthesis."""
        metadata = {"labels": ["database", "production"]}
        synthesis = {"tags": ["etl"], "category": "data-quality"}
        labels = generator._extract_labels(metadata, synthesis)
        assert "database" in labels
        assert "production" in labels
        assert "etl" in labels
        assert "data-quality" in labels

    def test_generate_summary(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test generating summary."""
        summary = generator._generate_summary(
            title="Test Issue",
            root_cause="Missing data",
            symptoms=[],
        )
        assert "Missing data" in summary

    def test_generate_summary_without_root_cause(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test generating summary from symptoms when no root cause."""
        summary = generator._generate_summary(
            title="Test Issue",
            root_cause=None,
            symptoms=[{"description": "Row count dropped"}],
        )
        assert "Row count dropped" in summary

    def test_generate_body(
        self,
        generator: RunbookGenerator,
    ) -> None:
        """Test generating full runbook body."""
        body = generator._generate_body(
            title="Test Issue",
            description="Something went wrong",
            symptoms=[{"description": "Data missing", "severity": "high"}],
            root_cause="Schema change",
            verification_steps=[{"step": 1, "description": "Check data", "query": "SELECT 1"}],
            fix_steps=[{"step": 1, "description": "Fix it"}],
            prevention_notes="Add monitoring",
            resolution="Fixed by reverting",
        )
        assert "# Test Issue" in body
        assert "## Overview" in body
        assert "## Symptoms" in body
        assert "## Root Cause" in body
        assert "## Verification Steps" in body
        assert "## Resolution Steps" in body
        assert "## Prevention" in body
