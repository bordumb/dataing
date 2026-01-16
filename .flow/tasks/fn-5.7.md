# fn-5.7 Create Bond-Maistro Bridge

## Description
Create the BondStep base class for AI-powered steps.

## Implementation

1. Create `bond/src/bond/maistro/` module.

2. Define `BondStep` abstract base class:
   ```python
   # bond/src/bond/maistro/bond_step.py
   from abc import ABC, abstractmethod
   from maistro import Step, StepResult
   from bond import BondAgent, StreamHandlers

   class BondStep(ABC, Step[ContextT, InputT, OutputT]):
       """Base class for steps that use BondAgent for AI."""

       def __init__(self, handlers: StreamHandlers | None = None):
           self._handlers = handlers

       @abstractmethod
       def create_agent(self, context: ContextT) -> BondAgent:
           """Create the agent for this step."""
           ...

       @abstractmethod
       def build_prompt(self, context: ContextT, input_data: InputT) -> str:
           """Build the prompt for the agent."""
           ...

       @abstractmethod
       def map_response(self, response: Any, context: ContextT) -> StepResult:
           """Map agent response to StepResult."""
           ...

       async def execute(self, context, input_data=None):
           agent = self.create_agent(context)
           prompt = self.build_prompt(context, input_data)
           response = await agent.ask(prompt, handlers=self._handlers)
           return self.map_response(response, context)
   ```

3. Export from bond package:
   ```python
   # bond/src/bond/__init__.py
   from bond.maistro.bond_step import BondStep
   ```

## Key Files
- New: `bond/src/bond/maistro/__init__.py`
- New: `bond/src/bond/maistro/bond_step.py`
- Modify: `bond/src/bond/__init__.py`
- Reference: `bond/src/bond/agent.py:76-291`
## Acceptance
- [ ] `bond.maistro` module exists
- [ ] `BondStep` is an abstract base class
- [ ] `BondStep` satisfies `maistro.Step` protocol
- [ ] `create_agent()`, `build_prompt()`, `map_response()` are abstract
- [ ] `execute()` orchestrates agent call
- [ ] `StreamHandlers` can be passed to BondStep
- [ ] `from bond import BondStep` works
- [ ] Unit test: Mock BondStep implementation executes correctly
- [ ] No circular dependency between bond and maistro
## Done summary
- Created bond/src/bond/maistro/ module with BondStep base class
- BondStep is ABC with abstract methods: create_agent(), build_prompt(), map_response()
- execute() orchestrates agent call using template method pattern
- BondStep satisfies maistro.Step protocol via name property and execute()
- StreamHandlers can be passed to BondStep for real-time callbacks
- Exported from bond package: `from bond import BondStep`
- Added 8 unit tests verifying protocol compliance and execution

Why:
- BondStep provides clean bridge between BondAgent and maistro.Workflow
- Template method pattern separates concerns (agent creation, prompting, response mapping)
- Handles agent errors gracefully with FAIL signal

Verification:
- mypy passes on bond/src/bond/maistro --strict
- 8 unit tests pass (test_bond_step.py)
- Import test: `from bond import BondStep` works
## Evidence
- Commits:
- Tests: uv run mypy bond/src/bond/maistro --strict, uv run pytest bond/tests/unit/maistro -v (8 passed), uv run python -c 'from bond import BondStep'
- PRs:
