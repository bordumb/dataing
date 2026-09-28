"""Temporal workflow engine integration for durable investigation execution.

This package provides:
- InvestigationWorkflow: Main workflow for investigation orchestration
- EvaluateHypothesisWorkflow: Child workflow for parallel hypothesis evaluation
- Activities: All investigation step activities
- TemporalInvestigationClient: High-level client for workflow interaction
- Worker: Temporal worker to process workflows

Usage:
    # Start the worker
    python -m dataing.temporal.worker

    # Or import components
    from dataing.temporal.workflows import InvestigationWorkflow, EvaluateHypothesisWorkflow
    from dataing.temporal.client import TemporalInvestigationClient
    from dataing.temporal.activities import gather_context, generate_hypotheses, synthesize

    # Client usage
    client = await TemporalInvestigationClient.connect()
    handle = await client.start_investigation(...)
    await client.cancel_investigation(investigation_id)
"""
