#!/usr/bin/env python3
"""Analyze Temporal workflow performance for investigation benchmarks.

Staff engineer perspective: understand where time is spent across the entire
investigation workflow to identify optimization opportunities.

Usage:
    python tests/performance/analyze_temporal.py
    python tests/performance/analyze_temporal.py --last 20
    python tests/performance/analyze_temporal.py --output analysis.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from temporalio.client import Client


@dataclass
class ActivityExecution:
    """Single activity execution with timing."""
    name: str
    scheduled_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    queue_time_ms: float  # Time waiting to be picked up
    execution_time_ms: float  # Time actually running
    total_time_ms: float
    success: bool
    error: str | None = None


@dataclass
class WorkflowExecution:
    """Single workflow execution with all activities."""
    workflow_id: str
    workflow_type: str
    started_at: datetime
    completed_at: datetime | None
    total_duration_ms: float
    status: str
    activities: list[ActivityExecution] = field(default_factory=list)

    @property
    def activity_time_ms(self) -> float:
        """Total time spent in activities."""
        return sum(a.total_time_ms for a in self.activities)

    @property
    def overhead_time_ms(self) -> float:
        """Time not spent in activities (workflow orchestration overhead)."""
        return self.total_duration_ms - self.activity_time_ms


@dataclass
class PhaseBreakdown:
    """Time spent in each investigation phase."""
    context_gathering_ms: float = 0
    hypothesis_generation_ms: float = 0
    hypothesis_evaluation_ms: float = 0
    synthesis_ms: float = 0
    other_ms: float = 0

    @property
    def total_ms(self) -> float:
        return (self.context_gathering_ms + self.hypothesis_generation_ms +
                self.hypothesis_evaluation_ms + self.synthesis_ms + self.other_ms)


def classify_activity_phase(activity_name: str) -> str:
    """Map activity name to investigation phase."""
    name_lower = activity_name.lower()

    if any(x in name_lower for x in ['schema', 'context', 'gather', 'lineage', 'metadata', 'pattern']):
        return 'context_gathering'
    elif 'generate_hypothes' in name_lower:  # generate_hypotheses specifically
        return 'hypothesis_generation'
    elif any(x in name_lower for x in ['evaluate', 'eval', 'query', 'sql', 'execute', 'interpret', 'evidence']):
        return 'hypothesis_evaluation'
    elif any(x in name_lower for x in ['synthesize', 'synthesis', 'conclude', 'summary', 'counter']):
        return 'synthesis'
    else:
        return 'other'


def get_event_time(event: Any) -> datetime | None:
    """Extract datetime from Temporal event, handling SDK differences."""
    if not hasattr(event, 'event_time'):
        return None
    event_time = event.event_time
    if hasattr(event_time, 'ToDatetime'):
        return event_time.ToDatetime()
    return event_time


def get_event_type_name(event: Any) -> str:
    """Get event type name, handling SDK differences."""
    if hasattr(event.event_type, 'name'):
        return event.event_type.name
    return str(event.event_type)


# Temporal event type integer values (from proto definition)
# https://github.com/temporalio/api/blob/master/temporal/api/enums/v1/event_type.proto
# Note: 5-9 are WORKFLOW_TASK events, 10+ are ACTIVITY_TASK events
EVENT_TYPE_ACTIVITY_TASK_SCHEDULED = 10
EVENT_TYPE_ACTIVITY_TASK_STARTED = 11
EVENT_TYPE_ACTIVITY_TASK_COMPLETED = 12
EVENT_TYPE_ACTIVITY_TASK_FAILED = 13
EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT = 14


def is_activity_scheduled(event_type: str) -> bool:
    """Check if event type is ACTIVITY_TASK_SCHEDULED."""
    return ("ACTIVITY_TASK_SCHEDULED" in event_type or
            event_type == str(EVENT_TYPE_ACTIVITY_TASK_SCHEDULED))


def is_activity_started(event_type: str) -> bool:
    """Check if event type is ACTIVITY_TASK_STARTED."""
    return ("ACTIVITY_TASK_STARTED" in event_type or
            event_type == str(EVENT_TYPE_ACTIVITY_TASK_STARTED))


def is_activity_completed(event_type: str) -> bool:
    """Check if event type is ACTIVITY_TASK_COMPLETED."""
    return ("ACTIVITY_TASK_COMPLETED" in event_type or
            event_type == str(EVENT_TYPE_ACTIVITY_TASK_COMPLETED))


def is_activity_failed(event_type: str) -> bool:
    """Check if event type is ACTIVITY_TASK_FAILED."""
    return ("ACTIVITY_TASK_FAILED" in event_type or
            event_type == str(EVENT_TYPE_ACTIVITY_TASK_FAILED))


async def fetch_workflow_execution(
    client: Client,
    workflow_id: str,
    run_id: str | None,
    debug: bool = False,
) -> WorkflowExecution | None:
    """Fetch detailed execution data for a single workflow."""
    try:
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        desc = await handle.describe()

        # Basic workflow info
        started_at = desc.start_time
        completed_at = desc.close_time

        if not started_at:
            return None

        duration_ms = 0.0
        if completed_at:
            duration_ms = (completed_at - started_at).total_seconds() * 1000

        status = str(desc.status.name) if hasattr(desc.status, 'name') else str(desc.status)

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            workflow_type=desc.workflow_type or "unknown",
            started_at=started_at,
            completed_at=completed_at,
            total_duration_ms=duration_ms,
            status=status,
        )

        # Parse activity timings from history
        scheduled_activities: dict[int, tuple[str, datetime]] = {}  # event_id -> (name, scheduled_time)
        started_activities: dict[int, datetime] = {}  # scheduled_event_id -> started_time

        event_types_seen: set[str] = set()

        async for event in handle.fetch_history_events():
            event_type = get_event_type_name(event)
            event_time = get_event_time(event)
            event_types_seen.add(event_type)

            if not event_time:
                continue

            if is_activity_scheduled(event_type):
                attrs = event.activity_task_scheduled_event_attributes
                if attrs and attrs.activity_type and attrs.activity_type.name:
                    scheduled_activities[event.event_id] = (attrs.activity_type.name, event_time)

            elif is_activity_started(event_type):
                attrs = event.activity_task_started_event_attributes
                if attrs:
                    started_activities[attrs.scheduled_event_id] = event_time

            elif is_activity_completed(event_type):
                attrs = event.activity_task_completed_event_attributes
                if attrs and attrs.scheduled_event_id in scheduled_activities:
                    activity_name, scheduled_at = scheduled_activities[attrs.scheduled_event_id]
                    started_at = started_activities.get(attrs.scheduled_event_id)
                    completed_at = event_time

                    queue_time = 0.0
                    exec_time = 0.0

                    if started_at:
                        queue_time = (started_at - scheduled_at).total_seconds() * 1000
                        exec_time = (completed_at - started_at).total_seconds() * 1000

                    total_time = (completed_at - scheduled_at).total_seconds() * 1000

                    execution.activities.append(ActivityExecution(
                        name=activity_name,
                        scheduled_at=scheduled_at,
                        started_at=started_at,
                        completed_at=completed_at,
                        queue_time_ms=queue_time,
                        execution_time_ms=exec_time,
                        total_time_ms=total_time,
                        success=True,
                    ))

            elif is_activity_failed(event_type):
                attrs = event.activity_task_failed_event_attributes
                if attrs and attrs.scheduled_event_id in scheduled_activities:
                    activity_name, scheduled_at = scheduled_activities[attrs.scheduled_event_id]
                    started_at = started_activities.get(attrs.scheduled_event_id)

                    execution.activities.append(ActivityExecution(
                        name=activity_name,
                        scheduled_at=scheduled_at,
                        started_at=started_at,
                        completed_at=event_time,
                        queue_time_ms=0,
                        execution_time_ms=0,
                        total_time_ms=(event_time - scheduled_at).total_seconds() * 1000,
                        success=False,
                        error=str(attrs.failure) if hasattr(attrs, 'failure') else "Unknown",
                    ))

        if debug:
            print(f"    {workflow_id[:20]}...: {len(execution.activities)} activities, {format_duration(duration_ms)}")

        return execution

    except Exception as e:
        print(f"  Warning: Failed to fetch {workflow_id}: {e}")
        return None


async def fetch_all_workflows(
    client: Client,
    limit: int = 50,
    workflow_type: str | None = None,
    debug: bool = False,
) -> list[WorkflowExecution]:
    """Fetch all completed workflow executions."""
    executions: list[WorkflowExecution] = []

    query = "ExecutionStatus = 'Completed' OR ExecutionStatus = 'Failed'"
    if workflow_type:
        query = f"WorkflowType = '{workflow_type}' AND ({query})"

    print(f"Fetching up to {limit} workflows...")

    count = 0
    # Track first workflow for debug output
    first_debug = debug

    async for workflow in client.list_workflows(query=query):
        if count >= limit:
            break

        execution = await fetch_workflow_execution(
            client, workflow.id, workflow.run_id, debug=first_debug
        )
        if execution:
            executions.append(execution)
            count += 1
            if count % 10 == 0:
                print(f"  Fetched {count} workflows...")
            # Only show debug for first few workflows
            if count >= 3:
                first_debug = False

    # Sort by start time
    executions.sort(key=lambda x: x.started_at)

    return executions


def compute_phase_breakdown(execution: WorkflowExecution) -> PhaseBreakdown:
    """Compute time spent in each investigation phase."""
    breakdown = PhaseBreakdown()

    for activity in execution.activities:
        phase = classify_activity_phase(activity.name)
        time_ms = activity.total_time_ms

        if phase == 'context_gathering':
            breakdown.context_gathering_ms += time_ms
        elif phase == 'hypothesis_generation':
            breakdown.hypothesis_generation_ms += time_ms
        elif phase == 'hypothesis_evaluation':
            breakdown.hypothesis_evaluation_ms += time_ms
        elif phase == 'synthesis':
            breakdown.synthesis_ms += time_ms
        else:
            breakdown.other_ms += time_ms

    return breakdown


def format_duration(ms: float) -> str:
    """Format milliseconds as human-readable duration."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        minutes = int(ms // 60000)
        seconds = (ms % 60000) / 1000
        return f"{minutes}m {seconds:.0f}s"


def format_percent(part: float, total: float) -> str:
    """Format as percentage."""
    if total == 0:
        return "0%"
    return f"{(part/total)*100:.1f}%"


def print_analysis(executions: list[WorkflowExecution]) -> None:
    """Print comprehensive performance analysis."""
    if not executions:
        print("\nNo workflow executions found!")
        print("\nPossible causes:")
        print("  1. No investigations have been run")
        print("  2. Investigations failed before completing")
        print("  3. Wrong Temporal namespace")
        print("\nTry running: python tests/performance/bench.py --keep-infra --runs 3")
        return

    print("\n" + "=" * 80)
    print("INVESTIGATION WORKFLOW PERFORMANCE ANALYSIS")
    print("=" * 80)

    # Filter to only InvestigationWorkflow (not child hypothesis workflows)
    main_workflows = [e for e in executions if 'hypothesis' not in e.workflow_type.lower()]
    child_workflows = [e for e in executions if 'hypothesis' in e.workflow_type.lower()]

    print(f"\nAnalyzed: {len(main_workflows)} investigation workflows, {len(child_workflows)} child workflows")

    # Aggregate activities from ALL workflows (parent + child) for activity analysis
    all_workflows_for_activities = executions

    if not main_workflows:
        print("\nNo main investigation workflows found. Only child workflows:")
        for wf in child_workflows[:5]:
            print(f"  - {wf.workflow_type}: {format_duration(wf.total_duration_ms)}")
        return

    # =========================================================================
    # 1. OVERALL WORKFLOW TIMING
    # =========================================================================
    print("\n" + "-" * 80)
    print("1. OVERALL WORKFLOW TIMING")
    print("-" * 80)

    durations = [e.total_duration_ms for e in main_workflows]

    print(f"\n  Total Workflows: {len(durations)}")
    print(f"  Mean Duration:   {format_duration(statistics.mean(durations))}")
    print(f"  Median Duration: {format_duration(statistics.median(durations))}")
    if len(durations) > 1:
        print(f"  Std Dev:         {format_duration(statistics.stdev(durations))}")
    print(f"  Min:             {format_duration(min(durations))}")
    print(f"  Max:             {format_duration(max(durations))}")

    # P95/P99
    sorted_durations = sorted(durations)
    p95_idx = int(len(sorted_durations) * 0.95)
    p99_idx = int(len(sorted_durations) * 0.99)
    print(f"  P95:             {format_duration(sorted_durations[min(p95_idx, len(sorted_durations)-1)])}")
    if len(sorted_durations) > 10:
        print(f"  P99:             {format_duration(sorted_durations[min(p99_idx, len(sorted_durations)-1)])}")

    # Child workflow timing
    if child_workflows:
        print(f"\n  Child Workflows ({len(child_workflows)} total):")
        child_durations = [e.total_duration_ms for e in child_workflows]
        print(f"    Mean Duration: {format_duration(statistics.mean(child_durations))}")
        print(f"    Min/Max:       {format_duration(min(child_durations))} - {format_duration(max(child_durations))}")

        # Group by workflow type
        child_by_type: dict[str, list[float]] = defaultdict(list)
        for wf in child_workflows:
            child_by_type[wf.workflow_type].append(wf.total_duration_ms)

        if len(child_by_type) > 1:
            print(f"\n  Child Workflow Types:")
            for wf_type, times in sorted(child_by_type.items(), key=lambda x: -sum(x[1])):
                print(f"    {wf_type}: {len(times)}x, mean {format_duration(statistics.mean(times))}")

    # =========================================================================
    # 2. PHASE BREAKDOWN (WHERE TIME IS SPENT)
    # =========================================================================
    print("\n" + "-" * 80)
    print("2. PHASE BREAKDOWN (WHERE TIME IS SPENT)")
    print("-" * 80)

    # Use ALL workflows (parent + child) for phase breakdown since activities run in children
    total_phase = PhaseBreakdown()
    for execution in all_workflows_for_activities:
        breakdown = compute_phase_breakdown(execution)
        total_phase.context_gathering_ms += breakdown.context_gathering_ms
        total_phase.hypothesis_generation_ms += breakdown.hypothesis_generation_ms
        total_phase.hypothesis_evaluation_ms += breakdown.hypothesis_evaluation_ms
        total_phase.synthesis_ms += breakdown.synthesis_ms
        total_phase.other_ms += breakdown.other_ms

    total = total_phase.total_ms
    if total > 0:
        phases = [
            ("Context Gathering", total_phase.context_gathering_ms),
            ("Hypothesis Generation", total_phase.hypothesis_generation_ms),
            ("Hypothesis Evaluation", total_phase.hypothesis_evaluation_ms),
            ("Synthesis", total_phase.synthesis_ms),
            ("Other/Orchestration", total_phase.other_ms),
        ]

        # Sort by time spent (descending)
        phases.sort(key=lambda x: -x[1])

        print(f"\n  {'Phase':<25} {'Time':>12} {'% of Total':>12}  Bar")
        print("  " + "-" * 70)

        max_bar = 40
        for name, time_ms in phases:
            pct = (time_ms / total) * 100
            bar_len = int((time_ms / total) * max_bar)
            bar = "█" * bar_len
            print(f"  {name:<25} {format_duration(time_ms):>12} {pct:>10.1f}%  {bar}")
    else:
        print("\n  No activity timing data found!")
        print("  Workflows may be completing without running activities.")

    # =========================================================================
    # 3. ACTIVITY-LEVEL BREAKDOWN
    # =========================================================================
    print("\n" + "-" * 80)
    print("3. ACTIVITY-LEVEL BREAKDOWN (TOP 10 BY TIME)")
    print("-" * 80)

    # Use ALL workflows (parent + child) for activity breakdown
    activity_times: dict[str, list[float]] = defaultdict(list)
    activity_queue_times: dict[str, list[float]] = defaultdict(list)

    for execution in all_workflows_for_activities:
        for activity in execution.activities:
            activity_times[activity.name].append(activity.execution_time_ms)
            activity_queue_times[activity.name].append(activity.queue_time_ms)

    if activity_times:
        # Calculate totals and sort
        activity_totals = [(name, sum(times), len(times), statistics.mean(times))
                          for name, times in activity_times.items()]
        activity_totals.sort(key=lambda x: -x[1])  # Sort by total time

        print(f"\n  {'Activity':<35} {'Count':>6} {'Total':>10} {'Mean':>10} {'% Time':>8}")
        print("  " + "-" * 75)

        grand_total = sum(t[1] for t in activity_totals)

        for name, total_time, count, mean_time in activity_totals[:10]:
            pct = (total_time / grand_total) * 100 if grand_total > 0 else 0
            # Truncate long names
            display_name = name[:33] + ".." if len(name) > 35 else name
            print(f"  {display_name:<35} {count:>6} {format_duration(total_time):>10} {format_duration(mean_time):>10} {pct:>7.1f}%")
    else:
        print("\n  No activity data found!")

    # =========================================================================
    # 4. QUEUE TIME ANALYSIS (WORKER CAPACITY)
    # =========================================================================
    print("\n" + "-" * 80)
    print("4. QUEUE TIME ANALYSIS (WORKER CAPACITY)")
    print("-" * 80)

    all_queue_times = []
    for times in activity_queue_times.values():
        all_queue_times.extend(times)

    if all_queue_times:
        mean_queue = statistics.mean(all_queue_times)
        max_queue = max(all_queue_times)

        print(f"\n  Mean Queue Time: {format_duration(mean_queue)}")
        print(f"  Max Queue Time:  {format_duration(max_queue)}")

        if mean_queue > 1000:  # More than 1 second average queue time
            print(f"\n  ⚠️  HIGH QUEUE TIME - Consider adding more workers")
        elif mean_queue > 100:
            print(f"\n  ℹ️  Moderate queue time - workers are keeping up")
        else:
            print(f"\n  ✓  Low queue time - workers have capacity")
    else:
        print("\n  No queue time data available")

    # =========================================================================
    # 5. RUN-OVER-RUN PROGRESSION (DEGRADATION DETECTION)
    # =========================================================================
    print("\n" + "-" * 80)
    print("5. RUN-OVER-RUN PROGRESSION")
    print("-" * 80)

    print(f"\n  {'Run':>4}  {'Duration':>10}  {'Activities':>10}  Workflow ID")
    print("  " + "-" * 65)

    for i, execution in enumerate(main_workflows, 1):
        print(f"  {i:>4}  {format_duration(execution.total_duration_ms):>10}  {len(execution.activities):>10}  {execution.workflow_id[:36]}")

    # Degradation check
    if len(main_workflows) >= 3:
        third = len(main_workflows) // 3
        first_third = statistics.mean([e.total_duration_ms for e in main_workflows[:third]])
        last_third = statistics.mean([e.total_duration_ms for e in main_workflows[-third:]])

        if first_third > 0:
            change_pct = ((last_third - first_third) / first_third) * 100

            print(f"\n  First third avg: {format_duration(first_third)}")
            print(f"  Last third avg:  {format_duration(last_third)}")

            if change_pct > 20:
                print(f"\n  ⚠️  DEGRADATION: {change_pct:.1f}% slower over time")
                print("     Consider using --restart-between-runs to isolate cause")
            elif change_pct < -20:
                print(f"\n  📈 IMPROVEMENT: {-change_pct:.1f}% faster over time (warmup effect)")
            else:
                print(f"\n  ✓  Stable performance (±{abs(change_pct):.1f}%)")

    # =========================================================================
    # 6. OPTIMIZATION RECOMMENDATIONS
    # =========================================================================
    print("\n" + "-" * 80)
    print("6. OPTIMIZATION RECOMMENDATIONS")
    print("-" * 80)

    recommendations = []

    # Check if any phase dominates
    if total > 0:
        for name, time_ms in phases:
            if time_ms / total > 0.5:
                recommendations.append(f"• {name} takes {format_percent(time_ms, total)} of time - focus optimization here")

    # Check for degradation
    if len(main_workflows) >= 3:
        if change_pct > 20:
            recommendations.append("• Run-over-run degradation detected - investigate memory leaks or cache growth")

    # Check queue times
    if all_queue_times and statistics.mean(all_queue_times) > 1000:
        recommendations.append("• High queue times - add more Temporal workers")

    # Check if activities are missing (check all workflows including children)
    total_activities = sum(len(e.activities) for e in all_workflows_for_activities)
    if total_activities == 0:
        recommendations.append("• No activities recorded - workflows may be failing before running")
        recommendations.append("• Check Temporal UI for workflow errors")
    elif len(main_workflows) > 0 and total_activities / len(main_workflows) < 3:
        recommendations.append("• Very few activities per workflow - investigations may be short-circuiting")

    if recommendations:
        print()
        for rec in recommendations:
            print(f"  {rec}")
    else:
        print("\n  ✓  No major issues detected")

    print("\n" + "=" * 80)


def save_json(executions: list[WorkflowExecution], output_path: Path) -> None:
    """Save detailed analysis to JSON."""

    def to_dict(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return {k: to_dict(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, list):
            return [to_dict(v) for v in obj]
        elif isinstance(obj, dict):
            return {k: to_dict(v) for k, v in obj.items()}
        return obj

    data = {
        "generated_at": datetime.now().isoformat(),
        "workflow_count": len(executions),
        "executions": [to_dict(e) for e in executions],
    }

    output_path.write_text(json.dumps(data, indent=2))
    print(f"\nDetailed data saved to: {output_path}")


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze Temporal workflow performance for investigations"
    )
    parser.add_argument(
        "--temporal-host",
        default="localhost:7233",
        help="Temporal server address (default: localhost:7233)",
    )
    parser.add_argument(
        "--namespace",
        default="default",
        help="Temporal namespace (default: default)",
    )
    parser.add_argument(
        "--workflow-type",
        help="Filter by workflow type",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=50,
        help="Number of recent workflows to analyze (default: 50)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Save detailed JSON to this file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show debug output including event types",
    )

    args = parser.parse_args()

    try:
        client = await Client.connect(args.temporal_host, namespace=args.namespace)
    except Exception as e:
        print(f"Error: Could not connect to Temporal at {args.temporal_host}")
        print(f"  {e}")
        print("\nMake sure:")
        print("  1. Run benchmark with --keep-infra flag")
        print("  2. Docker containers are running: docker ps | grep temporal")
        return 1

    print(f"Connected to Temporal at {args.temporal_host}")

    executions = await fetch_all_workflows(
        client,
        limit=args.last,
        workflow_type=args.workflow_type,
        debug=args.debug,
    )

    print_analysis(executions)

    if args.output:
        save_json(executions, args.output)

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
