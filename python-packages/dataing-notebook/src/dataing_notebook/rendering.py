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
    datasets = lineage.get("datasets", {})
    edges = lineage.get("edges", [])

    html_parts = [
        '<div class="dataing-lineage">',
        '<style>',
        '.dataing-lineage { font-family: monospace; }',
        '.dataing-lineage details { margin-left: 20px; }',
        '.dataing-lineage summary { cursor: pointer; padding: 4px; }',
        '.dataing-lineage summary:hover { background: #f0f0f0; }',
        '.dataing-lineage .edge { color: #666; font-size: 0.9em; }',
        '.dataing-lineage .dataset { color: #2563eb; }',
        '.dataing-lineage .root { font-weight: bold; color: #059669; }',
        '</style>',
        f'<details open>',
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
                f' &rarr; '
                f'<span class="dataset">{html.escape(str(target))}</span>'
                f' <small>({html.escape(str(edge_type))})</small>'
                f'</li>'
            )
        html_parts.append('</ul>')
    else:
        html_parts.append('<p><em>No edges defined</em></p>')

    html_parts.append('</details>')
    html_parts.append('</div>')

    return '\n'.join(html_parts)


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
        '<style>',
        '.dataing-table table { border-collapse: collapse; margin: 10px 0; }',
        '.dataing-table th, .dataing-table td { ',
        '  border: 1px solid #ddd; padding: 8px; text-align: left; ',
        '}',
        '.dataing-table th { background: #f5f5f5; font-weight: bold; }',
        '.dataing-table tr:nth-child(even) { background: #fafafa; }',
        '.dataing-table tr:hover { background: #f0f0f0; }',
        '.dataing-table .null { color: #999; font-style: italic; }',
        '</style>',
        '<table>',
        '<thead><tr>',
    ]

    # Header
    for col in col_names:
        html_parts.append(f'<th>{html.escape(str(col))}</th>')
    html_parts.append('</tr></thead>')

    # Body
    html_parts.append('<tbody>')
    for row in rows[:100]:  # Limit to 100 rows
        html_parts.append('<tr>')
        for col in col_names:
            value = row.get(col)
            if value is None:
                html_parts.append('<td class="null">NULL</td>')
            else:
                html_parts.append(f'<td>{html.escape(str(value))}</td>')
        html_parts.append('</tr>')
    html_parts.append('</tbody>')

    html_parts.append('</table>')

    if len(rows) > 100:
        html_parts.append(f'<p><em>Showing 100 of {len(rows)} rows</em></p>')

    html_parts.append('</div>')

    return '\n'.join(html_parts)


def render_evidence(evidence: RunEvidence) -> str:
    """Render evidence with syntax highlighting.

    Args:
        evidence: RunEvidence object.

    Returns:
        HTML string for the evidence.
    """
    html_parts = [
        '<div class="dataing-evidence">',
        '<style>',
        '.dataing-evidence { ',
        '  font-family: system-ui, sans-serif; ',
        '  border: 1px solid #e5e7eb; border-radius: 8px; ',
        '  padding: 16px; margin: 8px 0; ',
        '}',
        '.dataing-evidence .header { ',
        '  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; ',
        '}',
        '.dataing-evidence .kind { ',
        '  background: #3b82f6; color: white; ',
        '  padding: 2px 8px; border-radius: 4px; font-size: 0.8em; ',
        '}',
        '.dataing-evidence .kind-sql { background: #8b5cf6; }',
        '.dataing-evidence .kind-metric { background: #10b981; }',
        '.dataing-evidence .kind-schema { background: #f59e0b; }',
        '.dataing-evidence .kind-log { background: #6b7280; }',
        '.dataing-evidence .confidence { ',
        '  color: #6b7280; font-size: 0.9em; ',
        '}',
        '.dataing-evidence .summary { ',
        '  background: #f9fafb; padding: 12px; border-radius: 4px; ',
        '  margin-top: 8px; ',
        '}',
        '.dataing-evidence pre { ',
        '  background: #1f2937; color: #e5e7eb; ',
        '  padding: 12px; border-radius: 4px; overflow-x: auto; ',
        '}',
        '.dataing-evidence .conclusion { ',
        '  margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5e7eb; ',
        '}',
        '</style>',
    ]

    # Header
    kind = evidence.kind.value if hasattr(evidence.kind, "value") else str(evidence.kind)
    kind_class = f"kind-{kind.lower()}"
    html_parts.append(f'<div class="header">')
    html_parts.append(f'<span class="kind {kind_class}">{html.escape(kind.upper())}</span>')
    if evidence.confidence is not None:
        confidence_pct = int(evidence.confidence * 100)
        html_parts.append(f'<span class="confidence">{confidence_pct}% confidence</span>')
    html_parts.append('</div>')

    # Summary
    if evidence.result_summary:
        html_parts.append(f'<div class="summary">{html.escape(evidence.result_summary)}</div>')

    # SQL (with syntax highlighting placeholder)
    if evidence.source and "sql" in evidence.source:
        sql_code = evidence.source["sql"]
        html_parts.append(f'<pre><code>{html.escape(sql_code)}</code></pre>')

    # Conclusion
    if evidence.conclusion:
        html_parts.append(f'<div class="conclusion">{html.escape(evidence.conclusion)}</div>')

    html_parts.append('</div>')

    return '\n'.join(html_parts)


def render_context(context: Context) -> str:
    """Render Context as rich HTML.

    Args:
        context: Context object.

    Returns:
        HTML string.
    """
    html_parts = [
        '<div class="dataing-context">',
        '<style>',
        '.dataing-context { ',
        '  font-family: system-ui, sans-serif; ',
        '  border: 1px solid #e5e7eb; border-radius: 8px; ',
        '  padding: 16px; ',
        '}',
        '.dataing-context h3 { margin: 0 0 12px 0; color: #1f2937; }',
        '.dataing-context .meta { color: #6b7280; font-size: 0.9em; margin-bottom: 12px; }',
        '.dataing-context .assets { margin-top: 12px; }',
        '.dataing-context .asset { ',
        '  display: inline-block; background: #eff6ff; color: #1d4ed8; ',
        '  padding: 4px 8px; border-radius: 4px; margin: 2px; font-size: 0.9em; ',
        '}',
        '.dataing-context section { margin-top: 16px; padding-top: 16px; border-top: 1px solid #e5e7eb; }',
        '.dataing-context section h4 { margin: 0 0 8px 0; color: #374151; }',
        '</style>',
    ]

    # Header
    html_parts.append('<h3>Context</h3>')
    html_parts.append(
        f'<div class="meta">'
        f'Bundle: <code>{context.bundle_id[:16]}...</code> | '
        f'Hash: <code>{context.bundle_hash}</code>'
        f'</div>'
    )

    # Assets
    html_parts.append('<div class="assets">')
    html_parts.append(f'<strong>{len(context.resolved_assets)} asset(s):</strong><br>')
    for asset in context.resolved_assets:
        html_parts.append(f'<span class="asset">{html.escape(asset.dataset_id)}</span>')
    html_parts.append('</div>')

    # Lineage section
    if context.lineage:
        html_parts.append('<section>')
        html_parts.append('<h4>Lineage</h4>')
        html_parts.append(render_lineage_tree(context.lineage))
        html_parts.append('</section>')

    # Anomalies section
    if context.anomalies:
        html_parts.append('<section>')
        html_parts.append('<h4>Anomalies</h4>')
        html_parts.append(f'<p>{len(context.anomalies)} anomaly(ies) detected</p>')
        html_parts.append('</section>')

    html_parts.append('</div>')

    return '\n'.join(html_parts)


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
        '<style>',
        '.dataing-run { ',
        '  font-family: system-ui, sans-serif; ',
        '  border: 1px solid #e5e7eb; border-radius: 8px; ',
        '  padding: 16px; ',
        '}',
        '.dataing-run .header { display: flex; align-items: center; gap: 12px; }',
        '.dataing-run h3 { margin: 0; color: #1f2937; }',
        '.dataing-run .status { ',
        '  padding: 4px 12px; border-radius: 9999px; ',
        '  font-size: 0.85em; font-weight: 500; ',
        '}',
        '.dataing-run .meta { color: #6b7280; font-size: 0.9em; margin-top: 8px; }',
        '.dataing-run code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }',
        '</style>',
        '<div class="header">',
        '<h3>Run</h3>',
        f'<span class="status" style="background: {status_color}20; color: {status_color};">'
        f'{html.escape(status.upper())}'
        f'</span>',
        '</div>',
        '<div class="meta">',
        f'ID: <code>{html.escape(run.run_id[:16])}...</code> | ',
        f'Bundle: <code>{html.escape(run.bundle_hash)}</code>',
        '</div>',
        '</div>',
    ]

    return '\n'.join(html_parts)


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
            {f'<span style="color: #6b7280; margin-left: 12px;">{details}</span>' if details else ''}
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
