"""Rich rendering utilities for Jupyter notebooks.

This module provides HTML rendering for Dataing SDK objects,
with graceful degradation in non-Jupyter environments.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dataing_sdk import Context, Run, RunEvidence
    from dataing_sdk.types import RunEvent


def is_notebook_environment() -> bool:
    """Check if running in a Jupyter notebook environment.

    Returns:
        True if running in Jupyter, False otherwise.
    """
    try:
        from IPython import get_ipython

        shell = get_ipython()
        if shell is None:
            return False
        shell_class = shell.__class__.__name__
        return shell_class in ("ZMQInteractiveShell", "TerminalInteractiveShell")
    except ImportError:
        return False


def render_lineage_tree(lineage: dict[str, Any] | None) -> str:
    """Render lineage as a collapsible HTML tree.

    Args:
        lineage: Lineage dictionary with root, datasets, and edges.

    Returns:
        HTML string for the lineage tree.
    """
    if not lineage:
        return "<p>No lineage information available</p>"

    root = lineage.get("root", "Unknown")
    edges = lineage.get("edges", [])

    html_parts = [
        '<div class="dataing-lineage">',
        "<style>",
        ".dataing-lineage { font-family: monospace; }",
        ".dataing-lineage details { margin-left: 20px; }",
        ".dataing-lineage summary { cursor: pointer; padding: 4px; }",
        ".dataing-lineage summary:hover { background: #f0f0f0; }",
        ".dataing-lineage .edge { color: #666; font-size: 0.9em; }",
        ".dataing-lineage .dataset { color: #2563eb; }",
        ".dataing-lineage .root { font-weight: bold; color: #059669; }",
        "</style>",
        "<details open>",
        f'<summary><span class="root">{html.escape(str(root))}</span></summary>',
    ]

    # Build tree from edges
    if edges:
        html_parts.append('<ul style="list-style: none; padding-left: 15px;">')
        for edge in edges:
            source = edge.get("source", "?")
            target = edge.get("target", "?")
            edge_type = edge.get("edge_type", "transforms")
            html_parts.append(
                f'<li class="edge">'
                f'<span class="dataset">{html.escape(str(source))}</span>'
                f" &rarr; "
                f'<span class="dataset">{html.escape(str(target))}</span>'
                f" <small>({html.escape(str(edge_type))})</small>"
                f"</li>"
            )
        html_parts.append("</ul>")
    else:
        html_parts.append("<p><em>No edges defined</em></p>")

    html_parts.append("</details>")
    html_parts.append("</div>")

    return "\n".join(html_parts)


def render_table(rows: list[dict[str, Any]], columns: list[dict[str, Any]] | None = None) -> str:
    """Render rows as an HTML table with pandas-style formatting.

    Args:
        rows: List of row dictionaries.
        columns: Optional column metadata.

    Returns:
        HTML string for the table.
    """
    if not rows:
        return "<p><em>No data</em></p>"

    # Extract column names from first row or column metadata
    if columns:
        col_names = [c.get("name", f"col{i}") for i, c in enumerate(columns)]
    else:
        col_names = list(rows[0].keys())

    html_parts = [
        '<div class="dataing-table">',
        "<style>",
        ".dataing-table table { border-collapse: collapse; margin: 10px 0; }",
        ".dataing-table th, .dataing-table td { ",
        "  border: 1px solid #ddd; padding: 8px; text-align: left; ",
        "}",
        ".dataing-table th { background: #f5f5f5; font-weight: bold; }",
        ".dataing-table tr:nth-child(even) { background: #fafafa; }",
        ".dataing-table tr:hover { background: #f0f0f0; }",
        ".dataing-table .null { color: #999; font-style: italic; }",
        "</style>",
        "<table>",
        "<thead><tr>",
    ]

    # Header
    for col in col_names:
        html_parts.append(f"<th>{html.escape(str(col))}</th>")
    html_parts.append("</tr></thead>")

    # Body
    html_parts.append("<tbody>")
    for row in rows[:100]:  # Limit to 100 rows
        html_parts.append("<tr>")
        for col in col_names:
            value = row.get(col)
            if value is None:
                html_parts.append('<td class="null">NULL</td>')
            else:
                html_parts.append(f"<td>{html.escape(str(value))}</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody>")

    html_parts.append("</table>")

    if len(rows) > 100:
        html_parts.append(f"<p><em>Showing 100 of {len(rows)} rows</em></p>")

    html_parts.append("</div>")

    return "\n".join(html_parts)


def render_evidence(evidence: RunEvidence) -> str:
    """Render evidence with syntax highlighting.

    Args:
        evidence: RunEvidence object.

    Returns:
        HTML string for the evidence.
    """
    html_parts = [
        '<div class="dataing-evidence">',
        "<style>",
        ".dataing-evidence { ",
        "  font-family: system-ui, sans-serif; ",
        "  border: 1px solid #e5e7eb; border-radius: 8px; ",
        "  padding: 16px; margin: 8px 0; ",
        "}",
        ".dataing-evidence .header { ",
        "  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; ",
        "}",
        ".dataing-evidence .kind { ",
        "  background: #3b82f6; color: white; ",
        "  padding: 2px 8px; border-radius: 4px; font-size: 0.8em; ",
        "}",
        ".dataing-evidence .kind-sql { background: #8b5cf6; }",
        ".dataing-evidence .kind-metric { background: #10b981; }",
        ".dataing-evidence .kind-schema { background: #f59e0b; }",
        ".dataing-evidence .kind-log { background: #6b7280; }",
        ".dataing-evidence .confidence { ",
        "  color: #6b7280; font-size: 0.9em; ",
        "}",
        ".dataing-evidence .summary { ",
        "  background: #f9fafb; padding: 12px; border-radius: 4px; ",
        "  margin-top: 8px; ",
        "}",
        ".dataing-evidence pre { ",
        "  background: #1f2937; color: #e5e7eb; ",
        "  padding: 12px; border-radius: 4px; overflow-x: auto; ",
        "}",
        ".dataing-evidence .conclusion { ",
        "  margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5e7eb; ",
        "}",
        "</style>",
    ]

    # Header
    kind = evidence.kind.value if hasattr(evidence.kind, "value") else str(evidence.kind)
    kind_class = f"kind-{kind.lower()}"
    html_parts.append('<div class="header">')
    html_parts.append(f'<span class="kind {kind_class}">{html.escape(kind.upper())}</span>')
    if evidence.confidence is not None:
        confidence_pct = int(evidence.confidence * 100)
        html_parts.append(f'<span class="confidence">{confidence_pct}% confidence</span>')
    html_parts.append("</div>")

    # Summary
    if evidence.result_summary:
        html_parts.append(f'<div class="summary">{html.escape(evidence.result_summary)}</div>')

    # SQL (with syntax highlighting placeholder)
    if evidence.source and "sql" in evidence.source:
        sql_code = evidence.source["sql"]
        html_parts.append(f"<pre><code>{html.escape(sql_code)}</code></pre>")

    # Conclusion
    if evidence.conclusion:
        html_parts.append(f'<div class="conclusion">{html.escape(evidence.conclusion)}</div>')

    html_parts.append("</div>")

    return "\n".join(html_parts)


def render_context(context: Context) -> str:
    """Render Context as rich HTML.

    Args:
        context: Context object.

    Returns:
        HTML string.
    """
    html_parts = [
        '<div class="dataing-context">',
        "<style>",
        ".dataing-context { ",
        "  font-family: system-ui, sans-serif; ",
        "  border: 1px solid #e5e7eb; border-radius: 8px; ",
        "  padding: 16px; ",
        "}",
        ".dataing-context h3 { margin: 0 0 12px 0; color: #1f2937; }",
        ".dataing-context .meta { color: #6b7280; font-size: 0.9em; margin-bottom: 12px; }",
        ".dataing-context .assets { margin-top: 12px; }",
        ".dataing-context .asset { ",
        "  display: inline-block; background: #eff6ff; color: #1d4ed8; ",
        "  padding: 4px 8px; border-radius: 4px; margin: 2px; font-size: 0.9em; ",
        "}",
        ".dataing-context section { ",
        "  margin-top: 16px; padding-top: 16px; border-top: 1px solid #e5e7eb; ",
        "}",
        ".dataing-context section h4 { margin: 0 0 8px 0; color: #374151; }",
        "</style>",
    ]

    # Header
    html_parts.append("<h3>Context</h3>")
    html_parts.append(
        f'<div class="meta">'
        f"Bundle: <code>{context.bundle_id[:16]}...</code> | "
        f"Hash: <code>{context.bundle_hash}</code>"
        f"</div>"
    )

    # Assets
    html_parts.append('<div class="assets">')
    html_parts.append(f"<strong>{len(context.resolved_assets)} asset(s):</strong><br>")
    for asset in context.resolved_assets:
        html_parts.append(f'<span class="asset">{html.escape(asset.dataset_id)}</span>')
    html_parts.append("</div>")

    # Lineage section
    if context.lineage:
        html_parts.append("<section>")
        html_parts.append("<h4>Lineage</h4>")
        html_parts.append(render_lineage_tree(context.lineage))
        html_parts.append("</section>")

    # Anomalies section
    if context.anomalies:
        html_parts.append("<section>")
        html_parts.append("<h4>Anomalies</h4>")
        html_parts.append(f"<p>{len(context.anomalies)} anomaly(ies) detected</p>")
        html_parts.append("</section>")

    html_parts.append("</div>")

    return "\n".join(html_parts)


def render_run(run: Run) -> str:
    """Render Run as rich HTML.

    Args:
        run: Run object.

    Returns:
        HTML string.
    """
    status = run.status.value if hasattr(run.status, "value") else str(run.status)

    # Status color
    status_colors = {
        "running": "#3b82f6",
        "completed": "#10b981",
        "failed": "#ef4444",
        "cancelled": "#6b7280",
    }
    status_color = status_colors.get(status.lower(), "#6b7280")

    html_parts = [
        '<div class="dataing-run">',
        "<style>",
        ".dataing-run { ",
        "  font-family: system-ui, sans-serif; ",
        "  border: 1px solid #e5e7eb; border-radius: 8px; ",
        "  padding: 16px; ",
        "}",
        ".dataing-run .header { display: flex; align-items: center; gap: 12px; }",
        ".dataing-run h3 { margin: 0; color: #1f2937; }",
        ".dataing-run .status { ",
        "  padding: 4px 12px; border-radius: 9999px; ",
        "  font-size: 0.85em; font-weight: 500; ",
        "}",
        ".dataing-run .meta { color: #6b7280; font-size: 0.9em; margin-top: 8px; }",
        ".dataing-run code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }",
        "</style>",
        '<div class="header">',
        "<h3>Run</h3>",
        f'<span class="status" style="background: {status_color}20; color: {status_color};">'
        f"{html.escape(status.upper())}"
        f"</span>",
        "</div>",
        '<div class="meta">',
        f"ID: <code>{html.escape(run.run_id[:16])}...</code> | ",
        f"Bundle: <code>{html.escape(run.bundle_hash)}</code>",
        "</div>",
        "</div>",
    ]

    return "\n".join(html_parts)


def render_timeline_event(event: RunEvent) -> None:
    """Render an SSE event to the notebook output with styled timeline.

    Args:
        event: RunEvent from the SSE stream.
    """
    # Event type to icon/color mapping
    event_styles = {
        "run_started": ("🚀", "#3b82f6", "Investigation started"),
        "run_progress": ("⏳", "#8b5cf6", "Progress"),
        "run_evidence": ("📋", "#10b981", "Evidence collected"),
        "run_completed": ("✅", "#10b981", "Investigation completed"),
        "run_failed": ("❌", "#ef4444", "Investigation failed"),
        "run_heartbeat": ("💓", "#6b7280", "Heartbeat"),
    }

    icon, color, label = event_styles.get(event.event, ("•", "#6b7280", event.event))

    # Try to use IPython HTML display for rich output
    try:
        from IPython.display import HTML, display

        # Build event details from data
        details = ""
        data = event.data
        if data:
            if "goal" in data:
                details = f"Goal: {html.escape(str(data['goal']))}"
            elif "hypothesis" in data:
                details = f"Hypothesis: {html.escape(str(data['hypothesis']))}"
            elif "sql" in data:
                sql_preview = str(data["sql"])[:100]
                details = f"SQL: <code>{html.escape(sql_preview)}...</code>"
            elif "error" in data:
                details = f"Error: {html.escape(str(data['error']))}"
            elif "message" in data:
                details = html.escape(str(data["message"]))
            elif "query_succeeded" in data:
                details = "Query executed successfully"
            elif "reason" in data:
                details = html.escape(str(data["reason"]))

        html_content = f"""
        <div style="
            font-family: system-ui, sans-serif;
            padding: 8px 12px;
            margin: 4px 0;
            border-left: 3px solid {color};
            background: {color}10;
            border-radius: 0 4px 4px 0;
        ">
            <span style="margin-right: 8px;">{icon}</span>
            <strong style="color: {color};">[{event.seq}] {html.escape(label)}</strong>
            {f'<span style="color: #6b7280; margin-left: 12px;">{details}</span>'
             if details else ''}
        </div>
        """
        display(HTML(html_content))

    except ImportError:
        # Fallback to plain text
        details = ""
        data = event.data
        if data:
            if "goal" in data:
                details = f" - Goal: {data['goal']}"
            elif "hypothesis" in data:
                details = f" - {data['hypothesis']}"
            elif "error" in data:
                details = f" - Error: {data['error']}"

        print(f"{icon} [{event.seq}] {label}{details}")


def render_history_table(
    investigations: list[dict[str, Any]],
    page: int = 1,
    total: int | None = None,
    page_size: int = 20,
) -> str:
    """Render investigation history as a styled HTML table.

    Args:
        investigations: List of investigation dicts with id, dataset, status, created_at.
        page: Current page number.
        total: Total number of results (for pagination display).
        page_size: Number of results per page.

    Returns:
        HTML string with styled table and pagination.
    """
    if not investigations:
        return "<p><em>No investigations found</em></p>"

    # Status badge colors
    status_colors = {
        "completed": "#10b981",
        "running": "#3b82f6",
        "queued": "#8b5cf6",
        "failed": "#ef4444",
        "cancelled": "#6b7280",
    }

    html_parts = [
        '<div class="dataing-history">',
        "<style>",
        ".dataing-history { font-family: system-ui, sans-serif; }",
        ".dataing-history table { ",
        "  border-collapse: collapse; width: 100%; margin: 10px 0; ",
        "}",
        ".dataing-history th, .dataing-history td { ",
        "  border: 1px solid #e5e7eb; padding: 10px 12px; text-align: left; ",
        "}",
        ".dataing-history th { ",
        "  background: #f9fafb; font-weight: 600; color: #374151; ",
        "}",
        ".dataing-history tr:hover { background: #f3f4f6; }",
        ".dataing-history .id-link { ",
        "  color: #2563eb; text-decoration: none; font-family: monospace; ",
        "  font-size: 0.9em; cursor: pointer; ",
        "}",
        ".dataing-history .id-link:hover { text-decoration: underline; }",
        ".dataing-history .status-badge { ",
        "  padding: 3px 8px; border-radius: 9999px; font-size: 0.8em; ",
        "  font-weight: 500; display: inline-block; ",
        "}",
        ".dataing-history .timestamp { color: #6b7280; font-size: 0.9em; }",
        ".dataing-history .dataset { color: #374151; }",
        ".dataing-history .pagination { ",
        "  margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5e7eb; ",
        "  color: #6b7280; font-size: 0.9em; ",
        "}",
        "</style>",
        "<table>",
        "<thead><tr>",
        "<th>Investigation ID</th>",
        "<th>Dataset</th>",
        "<th>Status</th>",
        "<th>Created</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    for inv in investigations:
        inv_id = str(inv.get("investigation_id", ""))
        dataset = inv.get("dataset_id", "N/A")
        status = inv.get("status", "unknown").lower()
        created = inv.get("created_at", "")[:19].replace("T", " ")  # Truncate to datetime

        status_color = status_colors.get(status, "#6b7280")

        html_parts.append("<tr>")
        # Clickable ID (user can copy/paste for %dataing replay)
        html_parts.append(
            f'<td><span class="id-link" title="Copy ID for %dataing replay {inv_id}">'
            f"{html.escape(inv_id[:8])}...</span></td>"
        )
        html_parts.append(f'<td class="dataset">{html.escape(str(dataset))}</td>')
        html_parts.append(
            f'<td><span class="status-badge" style="background: {status_color}20; '
            f'color: {status_color};">{html.escape(status.upper())}</span></td>'
        )
        html_parts.append(f'<td class="timestamp">{html.escape(created)}</td>')
        html_parts.append("</tr>")

    html_parts.append("</tbody>")
    html_parts.append("</table>")

    # Pagination info
    actual_total = total if total is not None else len(investigations)
    start_idx = (page - 1) * page_size + 1
    end_idx = min(page * page_size, actual_total)
    total_pages = (actual_total + page_size - 1) // page_size

    html_parts.append(
        f'<div class="pagination">'
        f"Showing {start_idx}-{end_idx} of {actual_total} investigations"
    )
    if total_pages > 1:
        html_parts.append(f" | Page {page} of {total_pages}")
    html_parts.append("</div>")

    html_parts.append("</div>")

    return "\n".join(html_parts)


def render_replay_detail(investigation: dict[str, Any]) -> str:
    """Render a replayed investigation as rich HTML.

    Args:
        investigation: Investigation state dict with main_branch, evidence, synthesis.

    Returns:
        HTML string with styled investigation details.
    """
    status = investigation.get("status", "unknown").lower()
    inv_id = investigation.get("investigation_id", "")
    root_hash = investigation.get("root_hash", "")
    main_branch = investigation.get("main_branch", {})
    synthesis = main_branch.get("synthesis", {})
    evidence_list = main_branch.get("evidence", [])

    status_colors = {
        "completed": "#10b981",
        "running": "#3b82f6",
        "queued": "#8b5cf6",
        "failed": "#ef4444",
    }
    status_color = status_colors.get(status, "#6b7280")

    html_parts = [
        '<div class="dataing-replay">',
        "<style>",
        ".dataing-replay { font-family: system-ui, sans-serif; }",
        ".dataing-replay .header { ",
        "  border: 1px solid #e5e7eb; border-radius: 8px; ",
        "  padding: 16px; margin-bottom: 16px; background: #f9fafb; ",
        "}",
        ".dataing-replay .header h3 { margin: 0 0 8px 0; color: #1f2937; }",
        ".dataing-replay .status-badge { ",
        "  padding: 4px 12px; border-radius: 9999px; font-size: 0.85em; ",
        "  font-weight: 500; display: inline-block; margin-left: 12px; ",
        "}",
        ".dataing-replay .meta { color: #6b7280; font-size: 0.9em; }",
        ".dataing-replay .meta code { ",
        "  background: #e5e7eb; padding: 2px 6px; border-radius: 4px; ",
        "}",
        ".dataing-replay .synthesis { ",
        "  border: 2px solid #10b981; border-radius: 8px; ",
        "  padding: 16px; margin: 16px 0; background: #ecfdf5; ",
        "}",
        ".dataing-replay .synthesis h4 { margin: 0 0 12px 0; color: #065f46; }",
        ".dataing-replay .synthesis p { margin: 8px 0; color: #065f46; }",
        ".dataing-replay .evidence-section { margin-top: 16px; }",
        ".dataing-replay .evidence-section h4 { ",
        "  color: #374151; border-bottom: 2px solid #e5e7eb; ",
        "  padding-bottom: 8px; margin-bottom: 12px; ",
        "}",
        ".dataing-replay details { ",
        "  border: 1px solid #e5e7eb; border-radius: 6px; ",
        "  margin: 8px 0; ",
        "}",
        ".dataing-replay summary { ",
        "  padding: 10px 12px; cursor: pointer; background: #f9fafb; ",
        "  border-radius: 6px; ",
        "}",
        ".dataing-replay summary:hover { background: #f3f4f6; }",
        ".dataing-replay .evidence-content { padding: 12px; }",
        ".dataing-replay .evidence-kind { ",
        "  background: #3b82f6; color: white; ",
        "  padding: 2px 8px; border-radius: 4px; font-size: 0.8em; ",
        "  margin-right: 8px; ",
        "}",
        ".dataing-replay pre { ",
        "  background: #1f2937; color: #e5e7eb; ",
        "  padding: 12px; border-radius: 4px; overflow-x: auto; ",
        "  font-size: 0.9em; ",
        "}",
        "</style>",
    ]

    # Header
    html_parts.append('<div class="header">')
    html_parts.append(
        f"<h3>Investigation Replay"
        f'<span class="status-badge" style="background: {status_color}20; '
        f'color: {status_color};">{html.escape(status.upper())}</span></h3>'
    )
    html_parts.append(f'<div class="meta">ID: <code>{html.escape(inv_id)}</code>')
    if root_hash:
        html_parts.append(f" | Hash: <code>{html.escape(root_hash[:16])}...</code>")
    html_parts.append("</div></div>")

    # Synthesis (if available)
    if synthesis:
        html_parts.append('<div class="synthesis">')
        html_parts.append("<h4>Root Cause Analysis</h4>")
        if isinstance(synthesis, dict):
            if "root_cause" in synthesis:
                html_parts.append(
                    f'<p><strong>Root Cause:</strong> '
                    f'{html.escape(str(synthesis["root_cause"]))}</p>'
                )
            if "summary" in synthesis:
                html_parts.append(f'<p>{html.escape(str(synthesis["summary"]))}</p>')
            if "recommendations" in synthesis:
                html_parts.append("<p><strong>Recommendations:</strong></p><ul>")
                recs = synthesis["recommendations"]
                if isinstance(recs, list):
                    for rec in recs:
                        html_parts.append(f"<li>{html.escape(str(rec))}</li>")
                else:
                    html_parts.append(f"<li>{html.escape(str(recs))}</li>")
                html_parts.append("</ul>")
        else:
            html_parts.append(f"<p>{html.escape(str(synthesis))}</p>")
        html_parts.append("</div>")

    # Evidence section
    if evidence_list:
        html_parts.append('<div class="evidence-section">')
        html_parts.append(f"<h4>Evidence ({len(evidence_list)} items)</h4>")

        for i, ev in enumerate(evidence_list, 1):
            kind = ev.get("kind", "unknown")
            html_parts.append("<details>")
            html_parts.append(
                f"<summary>"
                f'<span class="evidence-kind">{html.escape(kind.upper())}</span>'
                f"Evidence #{i}"
                f"</summary>"
            )
            html_parts.append('<div class="evidence-content">')

            if kind == "sql_result":
                sql_code = ev.get("sql", "")
                if sql_code:
                    html_parts.append(f"<pre><code>{html.escape(sql_code)}</code></pre>")
                rows = ev.get("row_count", ev.get("rows", "?"))
                html_parts.append(f"<p><strong>Rows:</strong> {rows}</p>")
                conclusion = ev.get("conclusion", "")
                if conclusion:
                    html_parts.append(
                        f"<p><strong>Conclusion:</strong> " f"{html.escape(conclusion)}</p>"
                    )
            elif kind == "metric":
                metric = ev.get("metric", "")
                value = ev.get("value", "")
                html_parts.append(f"<p><strong>{html.escape(metric)}:</strong> {value}</p>")
            elif kind == "hypothesis":
                hyp = ev.get("hypothesis", ev.get("text", ""))
                status_ev = ev.get("status", "")
                html_parts.append(f"<p><strong>Hypothesis:</strong> {html.escape(hyp)}</p>")
                if status_ev:
                    html_parts.append(f"<p><strong>Status:</strong> {html.escape(status_ev)}</p>")
            else:
                # Generic rendering
                for key, value in ev.items():
                    if key not in ("kind", "seq", "prev_hash", "hash"):
                        val_str = str(value)[:200]
                        html_parts.append(
                            f"<p><strong>{html.escape(key)}:</strong> "
                            f"{html.escape(val_str)}</p>"
                        )

            html_parts.append("</div></details>")

        html_parts.append("</div>")
    else:
        html_parts.append("<p><em>No evidence collected yet.</em></p>")

    html_parts.append("</div>")

    return "\n".join(html_parts)


def render_comparison_table(inv1: dict[str, Any], inv2: dict[str, Any]) -> str:
    """Render side-by-side comparison of two investigations as HTML.

    Args:
        inv1: First investigation state dict.
        inv2: Second investigation state dict.

    Returns:
        HTML string with two-column comparison.
    """
    status_colors = {
        "completed": "#10b981",
        "running": "#3b82f6",
        "queued": "#8b5cf6",
        "failed": "#ef4444",
    }

    def get_status_badge(status: str) -> str:
        color = status_colors.get(status.lower(), "#6b7280")
        return (
            f'<span style="background: {color}20; color: {color}; '
            f'padding: 3px 8px; border-radius: 9999px; font-size: 0.8em;">'
            f"{html.escape(status.upper())}</span>"
        )

    def extract_root_cause(synth: dict | None) -> str:
        if not synth:
            return "(no synthesis)"
        if isinstance(synth, dict):
            return str(synth.get("root_cause", synth.get("summary", "(no root cause)")))
        return str(synth)

    html_parts = [
        '<div class="dataing-compare">',
        "<style>",
        ".dataing-compare { font-family: system-ui, sans-serif; }",
        ".dataing-compare .compare-grid { ",
        "  display: grid; grid-template-columns: 1fr 1fr; gap: 16px; ",
        "}",
        ".dataing-compare .column { ",
        "  border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; ",
        "}",
        ".dataing-compare .column.left { border-color: #10b981; }",
        ".dataing-compare .column.right { border-color: #3b82f6; }",
        ".dataing-compare h4 { margin: 0 0 12px 0; color: #374151; }",
        ".dataing-compare .meta { color: #6b7280; font-size: 0.9em; margin-bottom: 12px; }",
        ".dataing-compare .meta code { ",
        "  background: #e5e7eb; padding: 2px 6px; border-radius: 4px; ",
        "}",
        ".dataing-compare .synthesis { ",
        "  background: #f9fafb; padding: 12px; border-radius: 6px; margin: 12px 0; ",
        "}",
        ".dataing-compare .diff-section { margin-top: 16px; }",
        ".dataing-compare .diff-header { ",
        "  font-weight: 600; color: #374151; margin-bottom: 8px; ",
        "}",
        ".dataing-compare .unique-left { color: #059669; }",
        ".dataing-compare .unique-right { color: #2563eb; }",
        ".dataing-compare .shared { color: #6b7280; }",
        ".dataing-compare ul { margin: 0; padding-left: 20px; }",
        ".dataing-compare li { margin: 4px 0; font-size: 0.9em; }",
        "</style>",
    ]

    id1 = inv1.get("investigation_id", "")
    id2 = inv2.get("investigation_id", "")
    status1 = inv1.get("status", "unknown")
    status2 = inv2.get("status", "unknown")
    branch1 = inv1.get("main_branch", {})
    branch2 = inv2.get("main_branch", {})
    synth1 = branch1.get("synthesis")
    synth2 = branch2.get("synthesis")
    evidence1 = branch1.get("evidence", [])
    evidence2 = branch2.get("evidence", [])

    # Header
    html_parts.append("<h3>Investigation Comparison</h3>")

    # Two-column grid
    html_parts.append('<div class="compare-grid">')

    # Left column
    html_parts.append('<div class="column left">')
    html_parts.append(f"<h4>Investigation A {get_status_badge(status1)}</h4>")
    html_parts.append(f'<div class="meta">ID: <code>{html.escape(id1[:12])}...</code></div>')
    html_parts.append('<div class="synthesis">')
    html_parts.append(f"<strong>Root Cause:</strong> {html.escape(extract_root_cause(synth1))}")
    html_parts.append("</div>")
    html_parts.append(f"<p>Evidence items: {len(evidence1)}</p>")
    html_parts.append("</div>")

    # Right column
    html_parts.append('<div class="column right">')
    html_parts.append(f"<h4>Investigation B {get_status_badge(status2)}</h4>")
    html_parts.append(f'<div class="meta">ID: <code>{html.escape(id2[:12])}...</code></div>')
    html_parts.append('<div class="synthesis">')
    html_parts.append(f"<strong>Root Cause:</strong> {html.escape(extract_root_cause(synth2))}")
    html_parts.append("</div>")
    html_parts.append(f"<p>Evidence items: {len(evidence2)}</p>")
    html_parts.append("</div>")

    html_parts.append("</div>")  # End compare-grid

    # Diff section
    def evidence_sig(ev: dict) -> str:
        kind = ev.get("kind", "")
        if kind == "sql_result":
            return f"sql:{ev.get('sql', '')[:80]}"
        elif kind == "hypothesis":
            return f"hyp:{ev.get('hypothesis', ev.get('text', ''))[:80]}"
        return f"{kind}:{str(list(ev.values())[:2])[:60]}"

    sigs1 = {evidence_sig(e): e for e in evidence1}
    sigs2 = {evidence_sig(e): e for e in evidence2}
    shared = set(sigs1.keys()) & set(sigs2.keys())
    only1 = set(sigs1.keys()) - shared
    only2 = set(sigs2.keys()) - shared

    html_parts.append('<div class="diff-section">')
    html_parts.append('<div class="diff-header">Evidence Comparison</div>')

    html_parts.append(f'<p class="shared">Shared evidence: {len(shared)}</p>')

    if only1:
        html_parts.append(f'<p class="unique-left">Unique to A: {len(only1)}</p>')
        html_parts.append("<ul>")
        for sig in list(only1)[:5]:
            html_parts.append(f'<li class="unique-left">{html.escape(sig[:70])}...</li>')
        if len(only1) > 5:
            html_parts.append(f"<li>...and {len(only1) - 5} more</li>")
        html_parts.append("</ul>")

    if only2:
        html_parts.append(f'<p class="unique-right">Unique to B: {len(only2)}</p>')
        html_parts.append("<ul>")
        for sig in list(only2)[:5]:
            html_parts.append(f'<li class="unique-right">{html.escape(sig[:70])}...</li>')
        if len(only2) > 5:
            html_parts.append(f"<li>...and {len(only2) - 5} more</li>")
        html_parts.append("</ul>")

    html_parts.append("</div>")

    # Status difference notice
    if status1 != status2:
        html_parts.append(
            '<p style="margin-top: 12px; padding: 8px; background: #fef3c7; '
            'border-radius: 4px; color: #92400e;">'
            "<strong>Note:</strong> These investigations have different statuses.</p>"
        )

    html_parts.append("</div>")

    return "\n".join(html_parts)
