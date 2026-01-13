# fn-5.8 Refactor AI-Powered Steps to BondStep

## Description
Refactor AI-powered steps to use the BondStep pattern.

## Implementation

1. Identify steps that use LLM:
   - GenerateHypothesesStep (uses AgentClient.generate_hypotheses)
   - InterpretResultsStep (uses AgentClient.interpret_results)
   - SynthesizeStep (uses AgentClient.synthesize_findings)
   - RecursiveAnalysisStep (uses AgentClient for code analysis)

2. Refactor each to extend BondStep:
   ```python
   # Example: GenerateHypothesesStep
   class GenerateHypothesesStep(BondStep[InvestigationContext, None, list[Hypothesis]]):
       name = "generate_hypotheses"

       def create_agent(self, context):
           return BondAgent(
               name="hypothesis_generator",
               instructions=HYPOTHESIS_PROMPT,
               output_type=HypothesisOutput,
           )

       def build_prompt(self, context, input_data):
           return f"Alert: {context.alert_summary}\nSchema: {context.schema_info}"

       def map_response(self, response, context):
           return StepResult(
               context=context.model_copy(update={"hypotheses": response.hypotheses}),
               signal=Signal.CONTINUE,
               output=response.hypotheses,
           )
   ```

3. Delete LLM adapter wrapper code that's no longer needed.

## Key Files
- Modify: `dataing/src/dataing/core/investigation/steps/generate_hypotheses.py`
- Modify: `dataing/src/dataing/core/investigation/steps/interpret_results.py`
- Modify: `dataing/src/dataing/core/investigation/steps/synthesize.py`
- Delete: `dataing/src/dataing/adapters/investigation/llm_adapter.py` (if now unused)
## Acceptance
- [ ] GenerateHypothesesStep extends BondStep
- [ ] InterpretResultsStep extends BondStep
- [ ] SynthesizeStep extends BondStep
- [ ] Each step implements `create_agent()`, `build_prompt()`, `map_response()`
- [ ] StreamHandlers work for token streaming
- [ ] Unit tests pass for each refactored step
- [ ] Integration test: Full flow with BondStep-based steps works
- [ ] AgentClient usage is minimal or removed
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
