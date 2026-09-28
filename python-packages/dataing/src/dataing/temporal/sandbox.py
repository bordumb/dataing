"""Workflow sandbox settings shared by the worker and the workflow tests."""

from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions


def workflow_runner() -> SandboxedWorkflowRunner:
    """Return the sandboxed runner that every worker runs workflows in.

    pydantic-ai 2 imports fastmcp, whose py-key-value-aio dependency registers
    beartype's import hooks (beartype.claw) for the whole process. The sandbox
    re-imports modules for every workflow, and re-importing beartype.claw under
    those hooks fails with a circular import, so no workflow validates. Passing
    beartype through makes the sandbox reuse the already-imported module.
    """
    return SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules("beartype")
    )
