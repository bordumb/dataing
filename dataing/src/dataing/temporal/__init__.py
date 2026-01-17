"""Temporal workflow engine integration for durable investigation execution.

This package provides:
- InvestigationWorkflow: Main workflow for investigation orchestration
- Activities: gather_context, generate_hypotheses, synthesize
- Worker: Temporal worker to process workflows

Usage:
    # Start the worker
    python -m dataing.temporal.worker

    # Or import components
    from dataing.temporal.workflows import InvestigationWorkflow
    from dataing.temporal.activities import gather_context, generate_hypotheses, synthesize
"""
