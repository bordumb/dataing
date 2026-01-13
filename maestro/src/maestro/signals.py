"""Signal enum for workflow control flow.

Signals determine what the workflow engine should do after a step executes.
"""

from __future__ import annotations

from enum import Enum


class Signal(str, Enum):
    """Control flow signals for workflow execution.

    These signals tell the workflow engine what to do next:
    - CONTINUE: Proceed to next step (explicit or implicit)
    - COMPLETE: Workflow finished successfully
    - FAIL: Workflow failed
    - BRANCH: Create child workflows for parallel execution
    - MERGE: Await convergence of child branches
    - AWAIT_USER: Pause workflow and wait for external input
    """

    CONTINUE = "continue"
    COMPLETE = "complete"
    FAIL = "fail"
    BRANCH = "branch"
    MERGE = "merge"
    AWAIT_USER = "await_user"
