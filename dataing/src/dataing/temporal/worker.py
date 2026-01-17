"""Temporal worker for investigation workflows.

Run this script to start a worker that processes investigation workflows.

Usage:
    python -m dataing.temporal.worker

Requires a running Temporal server:
    temporal server start-dev
"""

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from dataing.entrypoints.api.deps import settings
from dataing.temporal.activities import gather_context, generate_hypotheses, synthesize
from dataing.temporal.workflows import InvestigationWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the Temporal worker."""
    logger.info(
        f"Connecting to Temporal at {settings.TEMPORAL_HOST}, "
        f"namespace={settings.TEMPORAL_NAMESPACE}"
    )

    # Connect to Temporal server
    client = await Client.connect(
        target_host=settings.TEMPORAL_HOST,
        namespace=settings.TEMPORAL_NAMESPACE,
    )

    logger.info(f"Starting worker on task queue: {settings.TEMPORAL_TASK_QUEUE}")

    # Create and run worker
    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=[InvestigationWorkflow],
        activities=[gather_context, generate_hypotheses, synthesize],
    )

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
