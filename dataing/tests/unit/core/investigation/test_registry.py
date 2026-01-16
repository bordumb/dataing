"""Tests for StepRegistry."""

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.registry import StepRegistry
from dataing.core.investigation.steps.protocol import Step, StepResult
from dataing.core.investigation.values import StepType
from maistro import Signal


class MockStep(Step[None, str]):
    """Mock step for testing."""

    step_type = StepType.GATHER_CONTEXT

    async def execute(
        self,
        context: InvestigationContext,
        input_data: None = None,
    ) -> StepResult[InvestigationContext, str]:
        """Execute mock step."""
        return StepResult(
            context=context,
            signal=Signal.CONTINUE,
            output="mock_output",
        )


class TestStepRegistry:
    """Tests for StepRegistry."""

    def test_register_step(self) -> None:
        """Can register a step."""
        registry = StepRegistry()
        step = MockStep()

        registry.register(step)

        assert registry.has(StepType.GATHER_CONTEXT)

    def test_get_registered_step(self) -> None:
        """Can get a registered step."""
        registry = StepRegistry()
        step = MockStep()
        registry.register(step)

        retrieved = registry.get(StepType.GATHER_CONTEXT)

        assert retrieved is step

    def test_get_unregistered_step_returns_none(self) -> None:
        """Getting unregistered step returns None."""
        registry = StepRegistry()

        result = registry.get(StepType.GATHER_CONTEXT)

        assert result is None

    def test_has_returns_false_for_unregistered(self) -> None:
        """has() returns False for unregistered step type."""
        registry = StepRegistry()

        assert registry.has(StepType.GATHER_CONTEXT) is False

    def test_register_multiple_steps(self) -> None:
        """Can register multiple different steps."""
        registry = StepRegistry()

        class Step1(Step[None, str]):
            """Step for gathering context."""

            step_type = StepType.GATHER_CONTEXT

            async def execute(
                self,
                context: InvestigationContext,
                input_data: None = None,
            ) -> StepResult[InvestigationContext, str]:
                """Execute step."""
                return StepResult(context=context, signal=Signal.CONTINUE)

        class Step2(Step[None, str]):
            """Step for generating hypotheses."""

            step_type = StepType.GENERATE_HYPOTHESES

            async def execute(
                self,
                context: InvestigationContext,
                input_data: None = None,
            ) -> StepResult[InvestigationContext, str]:
                """Execute step."""
                return StepResult(context=context, signal=Signal.CONTINUE)

        registry.register(Step1())
        registry.register(Step2())

        assert registry.has(StepType.GATHER_CONTEXT)
        assert registry.has(StepType.GENERATE_HYPOTHESES)

    def test_register_overwrites_existing(self) -> None:
        """Registering same step type overwrites existing."""
        registry = StepRegistry()
        step1 = MockStep()
        step2 = MockStep()

        registry.register(step1)
        registry.register(step2)

        assert registry.get(StepType.GATHER_CONTEXT) is step2

    def test_list_registered_types(self) -> None:
        """Can list all registered step types."""
        registry = StepRegistry()

        class Step1(Step[None, str]):
            """Step for gathering context."""

            step_type = StepType.GATHER_CONTEXT

            async def execute(
                self,
                context: InvestigationContext,
                input_data: None = None,
            ) -> StepResult[InvestigationContext, str]:
                """Execute step."""
                return StepResult(context=context, signal=Signal.CONTINUE)

        class Step2(Step[None, str]):
            """Step for generating hypotheses."""

            step_type = StepType.GENERATE_HYPOTHESES

            async def execute(
                self,
                context: InvestigationContext,
                input_data: None = None,
            ) -> StepResult[InvestigationContext, str]:
                """Execute step."""
                return StepResult(context=context, signal=Signal.CONTINUE)

        registry.register(Step1())
        registry.register(Step2())

        types = registry.registered_types()

        assert StepType.GATHER_CONTEXT in types
        assert StepType.GENERATE_HYPOTHESES in types
        assert len(types) == 2
