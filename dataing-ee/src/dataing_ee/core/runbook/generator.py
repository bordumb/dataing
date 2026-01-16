"""Runbook generator from resolved issues."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from dataing.adapters.db.app_db import AppDatabase

logger = logging.getLogger(__name__)


@dataclass
class GeneratedRunbook:
    """Generated runbook content from an issue and investigation."""

    title: str
    summary: str
    body: str
    symptoms: list[dict[str, Any]]
    root_cause: str | None
    verification_steps: list[dict[str, Any]]
    fix_steps: list[dict[str, Any]]
    prevention_notes: str | None
    dataset_id: str | None
    labels: list[str]


class RunbookGenerator:
    """Generate runbooks from resolved issues and investigations."""

    async def generate_from_issue(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        issue_id: UUID,
    ) -> GeneratedRunbook | None:
        """Generate a runbook from a resolved issue.

        Args:
            db: Database connection
            tenant_id: Tenant ID
            issue_id: Issue ID to generate from

        Returns:
            GeneratedRunbook or None if issue not suitable
        """
        # Fetch issue with investigation
        issue = await db.fetch_one(
            """
            SELECT
                i.id,
                i.title,
                i.description,
                i.status,
                i.resolution,
                i.dataset_id,
                i.metadata,
                inv.id as investigation_id,
                inv.synthesis,
                inv.metadata as inv_metadata
            FROM issues i
            LEFT JOIN investigations inv ON inv.issue_id = i.id
            WHERE i.id = $1 AND i.tenant_id = $2
            ORDER BY inv.created_at DESC
            LIMIT 1
            """,
            issue_id,
            tenant_id,
        )

        if not issue:
            logger.warning(f"Issue not found: {issue_id}")
            return None

        # Extract data
        title = issue.get("title", "Untitled Issue")
        description = issue.get("description", "")
        resolution = issue.get("resolution", "")
        synthesis = issue.get("synthesis") or {}
        dataset_id = issue.get("dataset_id")
        metadata = issue.get("metadata") or {}

        # Build runbook content
        symptoms = self._extract_symptoms(description, synthesis)
        root_cause = self._extract_root_cause(synthesis)
        verification_steps = self._extract_verification_steps(synthesis)
        fix_steps = self._extract_fix_steps(resolution, synthesis)
        prevention_notes = self._extract_prevention_notes(synthesis)
        labels = self._extract_labels(metadata, synthesis)

        # Generate summary
        summary = self._generate_summary(title, root_cause, symptoms)

        # Generate full body
        body = self._generate_body(
            title=title,
            description=description,
            symptoms=symptoms,
            root_cause=root_cause,
            verification_steps=verification_steps,
            fix_steps=fix_steps,
            prevention_notes=prevention_notes,
            resolution=resolution,
        )

        return GeneratedRunbook(
            title=f"Runbook: {title}",
            summary=summary,
            body=body,
            symptoms=symptoms,
            root_cause=root_cause,
            verification_steps=verification_steps,
            fix_steps=fix_steps,
            prevention_notes=prevention_notes,
            dataset_id=dataset_id,
            labels=labels,
        )

    def _extract_symptoms(
        self,
        description: str,
        synthesis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Extract symptoms from description and synthesis."""
        symptoms: list[dict[str, Any]] = []

        # From synthesis findings
        findings = synthesis.get("findings", [])
        for finding in findings:
            if isinstance(finding, dict):
                symptoms.append({
                    "description": finding.get("description", str(finding)),
                    "severity": finding.get("severity", "unknown"),
                })
            else:
                symptoms.append({"description": str(finding), "severity": "unknown"})

        # If no findings, use description as symptom
        if not symptoms and description:
            symptoms.append({
                "description": description[:500],
                "severity": "unknown",
            })

        return symptoms

    def _extract_root_cause(self, synthesis: dict[str, Any]) -> str | None:
        """Extract root cause from synthesis."""
        # Try various keys
        root_cause = synthesis.get("root_cause")
        if root_cause:
            return str(root_cause)

        root_cause = synthesis.get("rootCause")
        if root_cause:
            return str(root_cause)

        # From conclusion
        conclusion = synthesis.get("conclusion")
        if conclusion:
            return str(conclusion)[:1000]

        return None

    def _extract_verification_steps(
        self,
        synthesis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Extract verification steps from synthesis."""
        steps: list[dict[str, Any]] = []

        # From queries executed
        queries = synthesis.get("queries_executed", [])
        for i, query in enumerate(queries):
            if isinstance(query, dict):
                steps.append({
                    "step": i + 1,
                    "description": query.get("description", "Run verification query"),
                    "query": query.get("sql", query.get("query", "")),
                })
            elif isinstance(query, str):
                steps.append({
                    "step": i + 1,
                    "description": "Run verification query",
                    "query": query,
                })

        # From evidence
        evidence = synthesis.get("evidence", [])
        for _i, item in enumerate(evidence):
            if isinstance(item, dict) and item.get("query"):
                steps.append({
                    "step": len(steps) + 1,
                    "description": item.get("description", "Verify with query"),
                    "query": item.get("query"),
                })

        return steps

    def _extract_fix_steps(
        self,
        resolution: str,
        synthesis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Extract fix steps from resolution and synthesis."""
        steps: list[dict[str, Any]] = []

        # From resolution text
        if resolution:
            steps.append({
                "step": 1,
                "description": resolution[:1000],
                "type": "manual",
            })

        # From synthesis recommendations
        recommendations = synthesis.get("recommendations", [])
        for _i, rec in enumerate(recommendations):
            if isinstance(rec, dict):
                steps.append({
                    "step": len(steps) + 1,
                    "description": rec.get("description", str(rec)),
                    "type": rec.get("type", "recommendation"),
                })
            else:
                steps.append({
                    "step": len(steps) + 1,
                    "description": str(rec),
                    "type": "recommendation",
                })

        return steps

    def _extract_prevention_notes(self, synthesis: dict[str, Any]) -> str | None:
        """Extract prevention notes from synthesis."""
        prevention = synthesis.get("prevention")
        if prevention:
            return str(prevention)

        # From recommendations marked as preventive
        recommendations = synthesis.get("recommendations", [])
        preventive = [
            r for r in recommendations
            if isinstance(r, dict) and r.get("type") == "preventive"
        ]
        if preventive:
            return "; ".join(r.get("description", str(r)) for r in preventive)

        return None

    def _extract_labels(
        self,
        metadata: dict[str, Any],
        synthesis: dict[str, Any],
    ) -> list[str]:
        """Extract labels from metadata and synthesis."""
        labels: list[str] = []

        # From metadata
        if metadata.get("labels"):
            labels.extend(metadata["labels"])

        # From synthesis tags
        if synthesis.get("tags"):
            labels.extend(synthesis["tags"])

        # From category
        if synthesis.get("category"):
            labels.append(synthesis["category"])

        # Deduplicate
        return list(set(labels))

    def _generate_summary(
        self,
        title: str,
        root_cause: str | None,
        symptoms: list[dict[str, Any]],
    ) -> str:
        """Generate a short summary."""
        parts = []

        if root_cause:
            parts.append(f"Root cause: {root_cause[:200]}")
        elif symptoms:
            parts.append(f"Symptoms: {symptoms[0].get('description', '')[:200]}")
        else:
            parts.append(f"Issue: {title}")

        return " ".join(parts)[:500]

    def _generate_body(
        self,
        title: str,
        description: str,
        symptoms: list[dict[str, Any]],
        root_cause: str | None,
        verification_steps: list[dict[str, Any]],
        fix_steps: list[dict[str, Any]],
        prevention_notes: str | None,
        resolution: str,
    ) -> str:
        """Generate full runbook body in markdown."""
        sections = []

        # Overview
        sections.append(f"# {title}\n")
        if description:
            sections.append(f"## Overview\n\n{description}\n")

        # Symptoms
        if symptoms:
            sections.append("## Symptoms\n")
            for symptom in symptoms:
                desc = symptom.get("description", "")
                severity = symptom.get("severity", "unknown")
                sections.append(f"- **{severity}**: {desc}\n")
            sections.append("")

        # Root Cause
        if root_cause:
            sections.append(f"## Root Cause\n\n{root_cause}\n")

        # Verification Steps
        if verification_steps:
            sections.append("## Verification Steps\n")
            for step in verification_steps:
                desc = step.get("description", "")
                query = step.get("query", "")
                sections.append(f"### Step {step.get('step', '?')}: {desc}\n")
                if query:
                    sections.append(f"```sql\n{query}\n```\n")
            sections.append("")

        # Fix Steps
        if fix_steps:
            sections.append("## Resolution Steps\n")
            for step in fix_steps:
                desc = step.get("description", "")
                sections.append(f"{step.get('step', '?')}. {desc}\n")
            sections.append("")

        # Prevention
        if prevention_notes:
            sections.append(f"## Prevention\n\n{prevention_notes}\n")

        # Resolution
        if resolution and not fix_steps:
            sections.append(f"## Resolution\n\n{resolution}\n")

        return "\n".join(sections)
