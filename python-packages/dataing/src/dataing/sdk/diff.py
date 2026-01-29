"""Snapshot comparison utilities for debugging investigations.

This module provides tools to compare two investigation snapshots,
highlighting changes in evidence, hypotheses, schema, and data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SchemaDiff:
    """Schema changes between snapshots."""

    added_tables: list[str] = field(default_factory=list)
    removed_tables: list[str] = field(default_factory=list)
    added_columns: dict[str, list[str]] = field(default_factory=dict)
    removed_columns: dict[str, list[str]] = field(default_factory=dict)
    type_changes: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        """Check if there are no schema changes."""
        return (
            not self.added_tables
            and not self.removed_tables
            and not self.added_columns
            and not self.removed_columns
            and not self.type_changes
        )

    def summary(self) -> str:
        """Get a brief summary of changes."""
        changes = []
        if self.added_tables:
            changes.append(f"+{len(self.added_tables)} tables")
        if self.removed_tables:
            changes.append(f"-{len(self.removed_tables)} tables")
        total_cols_added = sum(len(cols) for cols in self.added_columns.values())
        total_cols_removed = sum(len(cols) for cols in self.removed_columns.values())
        if total_cols_added:
            changes.append(f"+{total_cols_added} columns")
        if total_cols_removed:
            changes.append(f"-{total_cols_removed} columns")
        if self.type_changes:
            total_type_changes = sum(len(cols) for cols in self.type_changes.values())
            changes.append(f"~{total_type_changes} type changes")
        return ", ".join(changes) if changes else "No changes"


@dataclass
class HypothesisDiff:
    """Hypothesis changes between snapshots."""

    added: list[dict[str, Any]] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)
    status_changed: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Check if there are no hypothesis changes."""
        return not self.added and not self.removed and not self.status_changed

    def summary(self) -> str:
        """Get a brief summary of changes."""
        changes = []
        if self.added:
            changes.append(f"+{len(self.added)} hypotheses")
        if self.removed:
            changes.append(f"-{len(self.removed)} hypotheses")
        if self.status_changed:
            changes.append(f"~{len(self.status_changed)} status changes")
        return ", ".join(changes) if changes else "No changes"


@dataclass
class EvidenceDiff:
    """Evidence changes between snapshots."""

    added: list[dict[str, Any]] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Check if there are no evidence changes."""
        return not self.added and not self.removed

    def summary(self) -> str:
        """Get a brief summary of changes."""
        changes = []
        if self.added:
            changes.append(f"+{len(self.added)} evidence items")
        if self.removed:
            changes.append(f"-{len(self.removed)} evidence items")
        return ", ".join(changes) if changes else "No changes"


@dataclass
class DataFrameDiff:
    """DataFrame changes between snapshots."""

    table_name: str
    rows_added: int = 0
    rows_removed: int = 0
    values_changed: int = 0
    sample_changes: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Check if there are no DataFrame changes."""
        return self.rows_added == 0 and self.rows_removed == 0 and self.values_changed == 0

    def summary(self) -> str:
        """Get a brief summary of changes."""
        changes = []
        if self.rows_added:
            changes.append(f"+{self.rows_added} rows")
        if self.rows_removed:
            changes.append(f"-{self.rows_removed} rows")
        if self.values_changed:
            changes.append(f"~{self.values_changed} value changes")
        return ", ".join(changes) if changes else "No changes"


@dataclass
class SynthesisDiff:
    """Synthesis changes between snapshots."""

    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    root_cause_changed: bool = False
    confidence_change: float | None = None
    recommendations_changed: bool = False

    def is_empty(self) -> bool:
        """Check if there are no synthesis changes."""
        return (
            not self.root_cause_changed
            and self.confidence_change is None
            and not self.recommendations_changed
        )

    def summary(self) -> str:
        """Get a brief summary of changes."""
        changes = []
        if self.root_cause_changed:
            changes.append("root_cause changed")
        if self.confidence_change is not None:
            direction = "+" if self.confidence_change > 0 else ""
            changes.append(f"confidence {direction}{self.confidence_change:.1%}")
        if self.recommendations_changed:
            changes.append("recommendations changed")
        return ", ".join(changes) if changes else "No changes"


@dataclass
class SnapshotDiff:
    """Complete diff between two snapshots."""

    before_checkpoint: str
    after_checkpoint: str
    before_investigation_id: str
    after_investigation_id: str
    schema: SchemaDiff = field(default_factory=SchemaDiff)
    hypotheses: HypothesisDiff = field(default_factory=HypothesisDiff)
    evidence: EvidenceDiff = field(default_factory=EvidenceDiff)
    synthesis: SynthesisDiff = field(default_factory=SynthesisDiff)
    dataframes: list[DataFrameDiff] = field(default_factory=list)

    def summary(self) -> str:
        """Get an overall summary of all changes."""
        lines = [
            f"Diff: {self.before_checkpoint} -> {self.after_checkpoint}",
            f"Investigation: {self.before_investigation_id}",
            "",
        ]

        if not self.schema.is_empty():
            lines.append(f"Schema: {self.schema.summary()}")
        if not self.hypotheses.is_empty():
            lines.append(f"Hypotheses: {self.hypotheses.summary()}")
        if not self.evidence.is_empty():
            lines.append(f"Evidence: {self.evidence.summary()}")
        if not self.synthesis.is_empty():
            lines.append(f"Synthesis: {self.synthesis.summary()}")

        for df_diff in self.dataframes:
            if not df_diff.is_empty():
                lines.append(f"DataFrame {df_diff.table_name}: {df_diff.summary()}")

        if len(lines) == 3:  # Only header lines
            lines.append("No changes detected")

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Export diff as markdown."""
        lines = [
            "# Snapshot Diff",
            "",
            f"**Before:** {self.before_checkpoint}",
            f"**After:** {self.after_checkpoint}",
            f"**Investigation:** {self.before_investigation_id}",
            "",
        ]

        # Schema changes
        if not self.schema.is_empty():
            lines.append("## Schema Changes")
            lines.append("")
            if self.schema.added_tables:
                lines.append(f"**Added tables:** {', '.join(self.schema.added_tables)}")
            if self.schema.removed_tables:
                lines.append(f"**Removed tables:** {', '.join(self.schema.removed_tables)}")
            for table, cols in self.schema.added_columns.items():
                lines.append(f"**{table}:** +columns {', '.join(cols)}")
            for table, cols in self.schema.removed_columns.items():
                lines.append(f"**{table}:** -columns {', '.join(cols)}")
            for table, changes in self.schema.type_changes.items():
                for col, (old_type, new_type) in changes.items():
                    lines.append(f"**{table}.{col}:** {old_type} -> {new_type}")
            lines.append("")

        # Hypotheses changes
        if not self.hypotheses.is_empty():
            lines.append("## Hypothesis Changes")
            lines.append("")
            if self.hypotheses.added:
                lines.append(f"**Added:** {len(self.hypotheses.added)} hypotheses")
                for h in self.hypotheses.added[:5]:  # Limit to 5
                    title = h.get("title", h.get("id", "unknown"))
                    lines.append(f"  - {title}")
            if self.hypotheses.removed:
                lines.append(f"**Removed:** {len(self.hypotheses.removed)} hypotheses")
            if self.hypotheses.status_changed:
                lines.append("**Status changes:**")
                for change in self.hypotheses.status_changed[:5]:
                    lines.append(
                        f"  - {change['id']}: {change['old_status']} -> {change['new_status']}"
                    )
            lines.append("")

        # Evidence changes
        if not self.evidence.is_empty():
            lines.append("## Evidence Changes")
            lines.append("")
            if self.evidence.added:
                lines.append(f"**Added:** {len(self.evidence.added)} evidence items")
                for e in self.evidence.added[:5]:
                    hyp_id = e.get("hypothesis_id", "N/A")
                    supports = "supports" if e.get("supports") else "refutes"
                    lines.append(f"  - {hyp_id}: {supports}")
            if self.evidence.removed:
                lines.append(f"**Removed:** {len(self.evidence.removed)} evidence items")
            lines.append("")

        # Synthesis changes
        if not self.synthesis.is_empty():
            lines.append("## Synthesis Changes")
            lines.append("")
            if self.synthesis.root_cause_changed:
                before_rc = (
                    self.synthesis.before.get("root_cause", "N/A")
                    if self.synthesis.before
                    else "N/A"
                )
                after_rc = (
                    self.synthesis.after.get("root_cause", "N/A") if self.synthesis.after else "N/A"
                )
                lines.append(f"**Root cause:** {before_rc} -> {after_rc}")
            if self.synthesis.confidence_change is not None:
                direction = "+" if self.synthesis.confidence_change > 0 else ""
                lines.append(f"**Confidence:** {direction}{self.synthesis.confidence_change:.1%}")
            if self.synthesis.recommendations_changed:
                lines.append("**Recommendations:** changed")
            lines.append("")

        # DataFrame changes
        df_changes = [d for d in self.dataframes if not d.is_empty()]
        if df_changes:
            lines.append("## DataFrame Changes")
            lines.append("")
            for df_diff in df_changes:
                lines.append(f"### {df_diff.table_name}")
                lines.append(f"- Rows added: {df_diff.rows_added}")
                lines.append(f"- Rows removed: {df_diff.rows_removed}")
                lines.append(f"- Values changed: {df_diff.values_changed}")
                if df_diff.sample_changes:
                    lines.append("- Sample changes:")
                    for change in df_diff.sample_changes[:10]:
                        lines.append(f"  - {json.dumps(change)}")
                lines.append("")

        return "\n".join(lines)

    def to_html(self) -> str:
        """Export diff as HTML for rich notebook display."""
        css = (
            ".dataing-diff { font-family: system-ui, sans-serif; }"
            ".dataing-diff h2 { color: #1f2937; border-bottom: 1px solid #e5e7eb; "
            "padding-bottom: 0.5rem; }"
            ".dataing-diff h3 { color: #374151; }"
            ".dataing-diff .meta { color: #6b7280; margin-bottom: 1rem; }"
            ".dataing-diff .added { color: #059669; }"
            ".dataing-diff .removed { color: #dc2626; }"
            ".dataing-diff .changed { color: #d97706; }"
            ".dataing-diff table { border-collapse: collapse; margin: 0.5rem 0; }"
            ".dataing-diff th, .dataing-diff td { border: 1px solid #e5e7eb; "
            "padding: 0.5rem; text-align: left; }"
            ".dataing-diff th { background: #f9fafb; }"
        )
        html_parts = [
            "<div class='dataing-diff'>",
            f"<style>{css}</style>",
            "<h2>Snapshot Diff</h2>",
            "<div class='meta'>",
            f"<strong>Before:</strong> {self.before_checkpoint} | ",
            f"<strong>After:</strong> {self.after_checkpoint} | ",
            f"<strong>Investigation:</strong> {self.before_investigation_id[:8]}...",
            "</div>",
        ]

        # Schema section
        if not self.schema.is_empty():
            html_parts.append("<h3>Schema Changes</h3>")
            html_parts.append("<table><tr><th>Change</th><th>Details</th></tr>")
            if self.schema.added_tables:
                tables = ", ".join(self.schema.added_tables)
                html_parts.append(f"<tr><td class='added'>+Tables</td><td>{tables}</td></tr>")
            if self.schema.removed_tables:
                tables = ", ".join(self.schema.removed_tables)
                html_parts.append(f"<tr><td class='removed'>-Tables</td><td>{tables}</td></tr>")
            for table, cols in self.schema.added_columns.items():
                html_parts.append(
                    f"<tr><td class='added'>+Columns ({table})</td><td>{', '.join(cols)}</td></tr>"
                )
            for table, cols in self.schema.removed_columns.items():
                col_list = ", ".join(cols)
                html_parts.append(
                    f"<tr><td class='removed'>-Columns ({table})</td><td>{col_list}</td></tr>"
                )
            for table, changes in self.schema.type_changes.items():
                for col, (old_type, new_type) in changes.items():
                    cell = f"~Type ({table}.{col})"
                    html_parts.append(
                        f"<tr><td class='changed'>{cell}</td><td>{old_type} → {new_type}</td></tr>"
                    )
            html_parts.append("</table>")

        # Hypotheses section
        if not self.hypotheses.is_empty():
            html_parts.append("<h3>Hypothesis Changes</h3>")
            html_parts.append("<table><tr><th>Change</th><th>Count</th><th>Details</th></tr>")
            if self.hypotheses.added:
                titles = ", ".join(
                    h.get("title", h.get("id", "?"))[:30] for h in self.hypotheses.added[:3]
                )
                count = len(self.hypotheses.added)
                html_parts.append(
                    f"<tr><td class='added'>+Added</td><td>{count}</td><td>{titles}...</td></tr>"
                )
            if self.hypotheses.removed:
                count = len(self.hypotheses.removed)
                html_parts.append(
                    f"<tr><td class='removed'>-Removed</td><td>{count}</td><td></td></tr>"
                )
            if self.hypotheses.status_changed:
                changes_str = ", ".join(
                    f"{c['id'][:8]}" for c in self.hypotheses.status_changed[:3]
                )
                count = len(self.hypotheses.status_changed)
                row = f"<tr><td class='changed'>~Status</td><td>{count}</td>"
                html_parts.append(f"{row}<td>{changes_str}</td></tr>")
            html_parts.append("</table>")

        # Evidence section
        if not self.evidence.is_empty():
            html_parts.append("<h3>Evidence Changes</h3>")
            html_parts.append("<table><tr><th>Change</th><th>Count</th></tr>")
            if self.evidence.added:
                html_parts.append(
                    f"<tr><td class='added'>+Added</td><td>{len(self.evidence.added)}</td></tr>"
                )
            if self.evidence.removed:
                count = len(self.evidence.removed)
                html_parts.append(f"<tr><td class='removed'>-Removed</td><td>{count}</td></tr>")
            html_parts.append("</table>")

        # Synthesis section
        if not self.synthesis.is_empty():
            html_parts.append("<h3>Synthesis Changes</h3>")
            html_parts.append("<table><tr><th>Field</th><th>Before</th><th>After</th></tr>")
            if self.synthesis.root_cause_changed:
                before_rc = (
                    self.synthesis.before.get("root_cause", "N/A")[:50]
                    if self.synthesis.before
                    else "N/A"
                )
                after_rc = (
                    self.synthesis.after.get("root_cause", "N/A")[:50]
                    if self.synthesis.after
                    else "N/A"
                )
                html_parts.append(
                    f"<tr><td>Root Cause</td><td>{before_rc}</td><td>{after_rc}</td></tr>"
                )
            if self.synthesis.confidence_change is not None:
                before_conf = (
                    self.synthesis.before.get("confidence", 0) if self.synthesis.before else 0
                )
                after_conf = (
                    self.synthesis.after.get("confidence", 0) if self.synthesis.after else 0
                )
                html_parts.append(
                    f"<tr><td>Confidence</td><td>{before_conf:.1%}</td><td>{after_conf:.1%}</td></tr>"
                )
            html_parts.append("</table>")

        # DataFrame section
        df_changes = [d for d in self.dataframes if not d.is_empty()]
        if df_changes:
            html_parts.append("<h3>DataFrame Changes</h3>")
            html_parts.append(
                "<table><tr><th>Table</th><th>+Rows</th><th>-Rows</th><th>~Values</th></tr>"
            )
            for df_diff in df_changes:
                name = df_diff.table_name
                added = df_diff.rows_added
                removed = df_diff.rows_removed
                changed = df_diff.values_changed
                row = (
                    f"<tr><td>{name}</td><td class='added'>{added}</td>"
                    f"<td class='removed'>{removed}</td><td class='changed'>{changed}</td></tr>"
                )
                html_parts.append(row)
            html_parts.append("</table>")

        html_parts.append("</div>")
        return "".join(html_parts)

    def _repr_html_(self) -> str:
        """Jupyter notebook rich display."""
        return self.to_html()


def compare_snapshots(before: Any, after: Any, max_changes: int = 100) -> SnapshotDiff:
    """Compare two HydratedState snapshots and return differences.

    Args:
        before: First HydratedState (earlier checkpoint).
        after: Second HydratedState (later checkpoint).
        max_changes: Maximum number of detailed changes to include.

    Returns:
        SnapshotDiff with all detected changes.
    """
    diff = SnapshotDiff(
        before_checkpoint=before.checkpoint,
        after_checkpoint=after.checkpoint,
        before_investigation_id=before.investigation_id,
        after_investigation_id=after.investigation_id,
    )

    # Compare schema
    diff.schema = _compare_schema(before.schema, after.schema)

    # Compare hypotheses
    diff.hypotheses = _compare_hypotheses(before.hypotheses, after.hypotheses)

    # Compare evidence
    diff.evidence = _compare_evidence(before.evidence, after.evidence, max_changes)

    # Compare synthesis
    diff.synthesis = _compare_synthesis(before.synthesis, after.synthesis)

    # Compare DataFrames
    diff.dataframes = _compare_dataframes(before.dataframes, after.dataframes, max_changes)

    return diff


def _compare_schema(before: Any, after: Any) -> SchemaDiff:
    """Compare schema between snapshots."""
    diff = SchemaDiff()

    before_tables = set(before.tables.keys()) if before else set()
    after_tables = set(after.tables.keys()) if after else set()

    diff.added_tables = list(after_tables - before_tables)
    diff.removed_tables = list(before_tables - after_tables)

    # Compare columns in common tables
    for table_name in before_tables & after_tables:
        before_table = before.tables[table_name]
        after_table = after.tables[table_name]

        before_cols = {col.name: col for col in before_table.columns}
        after_cols = {col.name: col for col in after_table.columns}

        added = set(after_cols.keys()) - set(before_cols.keys())
        removed = set(before_cols.keys()) - set(after_cols.keys())

        if added:
            diff.added_columns[table_name] = list(added)
        if removed:
            diff.removed_columns[table_name] = list(removed)

        # Check type changes in common columns
        for col_name in set(before_cols.keys()) & set(after_cols.keys()):
            before_type = before_cols[col_name].data_type
            after_type = after_cols[col_name].data_type
            if before_type != after_type:
                if table_name not in diff.type_changes:
                    diff.type_changes[table_name] = {}
                diff.type_changes[table_name][col_name] = (before_type, after_type)

    return diff


def _compare_hypotheses(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> HypothesisDiff:
    """Compare hypotheses between snapshots."""
    diff = HypothesisDiff()

    before_by_id = {h.get("id", str(i)): h for i, h in enumerate(before)}
    after_by_id = {h.get("id", str(i)): h for i, h in enumerate(after)}

    before_ids = set(before_by_id.keys())
    after_ids = set(after_by_id.keys())

    # Added hypotheses
    for hyp_id in after_ids - before_ids:
        diff.added.append(after_by_id[hyp_id])

    # Removed hypotheses
    for hyp_id in before_ids - after_ids:
        diff.removed.append(before_by_id[hyp_id])

    # Status changes in existing hypotheses
    for hyp_id in before_ids & after_ids:
        before_status = before_by_id[hyp_id].get("status", "unknown")
        after_status = after_by_id[hyp_id].get("status", "unknown")
        if before_status != after_status:
            diff.status_changed.append(
                {"id": hyp_id, "old_status": before_status, "new_status": after_status}
            )

    return diff


def _compare_evidence(
    before: list[dict[str, Any]], after: list[dict[str, Any]], max_changes: int
) -> EvidenceDiff:
    """Compare evidence between snapshots."""
    diff = EvidenceDiff()

    before_by_id = {e.get("id", str(i)): e for i, e in enumerate(before)}
    after_by_id = {e.get("id", str(i)): e for i, e in enumerate(after)}

    before_ids = set(before_by_id.keys())
    after_ids = set(after_by_id.keys())

    # Added evidence (limit to max_changes)
    added_ids = list(after_ids - before_ids)[:max_changes]
    for ev_id in added_ids:
        diff.added.append(after_by_id[ev_id])

    # Removed evidence
    removed_ids = list(before_ids - after_ids)[:max_changes]
    for ev_id in removed_ids:
        diff.removed.append(before_by_id[ev_id])

    return diff


def _compare_synthesis(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> SynthesisDiff:
    """Compare synthesis between snapshots."""
    diff = SynthesisDiff(before=before, after=after)

    if before is None and after is None:
        return diff

    before_rc = before.get("root_cause") if before else None
    after_rc = after.get("root_cause") if after else None
    diff.root_cause_changed = before_rc != after_rc

    before_conf = before.get("confidence", 0) if before else 0
    after_conf = after.get("confidence", 0) if after else 0
    if before_conf != after_conf:
        diff.confidence_change = after_conf - before_conf

    before_recs = before.get("recommendations", []) if before else []
    after_recs = after.get("recommendations", []) if after else []
    diff.recommendations_changed = before_recs != after_recs

    return diff


def _compare_dataframes(
    before: dict[str, Any], after: dict[str, Any], max_changes: int
) -> list[DataFrameDiff]:
    """Compare DataFrames between snapshots."""
    diffs = []

    # Get all table names
    before_tables = set(before.keys()) if before else set()
    after_tables = set(after.keys()) if after else set()
    all_tables = before_tables | after_tables

    for table_name in all_tables:
        df_diff = DataFrameDiff(table_name=table_name)

        before_df = before.get(table_name) if before else None
        after_df = after.get(table_name) if after else None

        # Try to compare if both exist and are DataFrames
        if before_df is not None and after_df is not None:
            try:
                # Check if they're pandas DataFrames
                before_len = len(before_df)
                after_len = len(after_df)

                if after_len > before_len:
                    df_diff.rows_added = after_len - before_len
                elif before_len > after_len:
                    df_diff.rows_removed = before_len - after_len

                # Try to compare values if same shape
                if hasattr(before_df, "compare") and before_len == after_len:
                    try:
                        comparison = before_df.compare(after_df)
                        df_diff.values_changed = len(comparison)

                        # Sample some changes
                        for idx in comparison.index[:max_changes]:
                            change_row: dict[str, Any] = {"index": str(idx)}
                            for col in comparison.columns.get_level_values(0).unique():
                                try:
                                    before_val = comparison.loc[idx, (col, "self")]
                                    after_val = comparison.loc[idx, (col, "other")]
                                    change_row[col] = {
                                        "before": str(before_val),
                                        "after": str(after_val),
                                    }
                                except (KeyError, TypeError):
                                    pass
                            df_diff.sample_changes.append(change_row)
                    except (ValueError, TypeError):
                        # Columns don't match, can't compare values
                        pass
            except (TypeError, AttributeError):
                # Not a DataFrame-like object
                pass
        elif before_df is None and after_df is not None:
            try:
                df_diff.rows_added = len(after_df)
            except TypeError:
                pass
        elif before_df is not None and after_df is None:
            try:
                df_diff.rows_removed = len(before_df)
            except TypeError:
                pass

        diffs.append(df_diff)

    return diffs
