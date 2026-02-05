"""Temporal workflow engine integration for durable investigation execution.

This package provides:
- InvestigationWorkflow: Main workflow for investigation orchestration
- EvaluateHypothesisWorkflow: Child workflow for parallel hypothesis evaluation
- AgentWorkflow: Generic workflow for running any registered agent
- Activities: All investigation step activities + generic agent_turn activity
- TemporalInvestigationClient: High-level client for investigation workflows
- TemporalAgentClient: High-level client for agent workflows
- Worker: Temporal worker to process workflows

Usage:
    # Start the worker
    python -m dataing.temporal.worker

    # Or import components
    from dataing.temporal.workflows import InvestigationWorkflow, AgentWorkflow
    from dataing.temporal.client import TemporalInvestigationClient, TemporalAgentClient
    from dataing.temporal.agents import AgentRegistry, TemporalAgentProtocol

    # Investigation client usage
    client = await TemporalInvestigationClient.connect()
    handle = await client.start_investigation(...)

    # Agent client usage
    agent_client = await TemporalAgentClient.connect()
    await agent_client.start_session("dataing-assistant", "sess-123", "tenant-1")
    await agent_client.send_message("sess-123", "What's wrong?")
    response = await agent_client.wait_for_response("sess-123")
"""
